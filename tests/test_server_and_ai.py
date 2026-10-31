"""
Unit Tests for Odikyu DNS Shield Server, Block Page & AI Integration
"""

import http.client
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request

import block_page_server
import config
import dns_proxy
from threat_manager import (
    RiskAction,
    RiskAssessment,
    RiskLevel,
    ThreatDatabase,
    ThreatIntelligenceManager,
)
from website_inspector import AIInspectionResult, GemmaWebsiteInspector


class TestConfigAndEnv(unittest.TestCase):
    def test_config_loaded(self):
        self.assertTrue(bool(config.SERVER_HOSTNAME))
        self.assertEqual(config.SERVER_HOSTNAME, "dns.odikyu.tech")
        self.assertTrue(bool(config.GEMMA_API_KEY))
        self.assertIn("gemma", config.GEMMA_MODEL_NAME.lower())


class TestBlockPageServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a temporary DB for isolated testing
        cls.db_fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        os.close(cls.db_fd)
        cls.tm = ThreatIntelligenceManager(db_path=cls.db_path)

        # Seed sample threats
        cls.tm.db.upsert_threat("malicious-phish.xyz", "PhishTank", "phishing", "Confirmed banking phish")
        cls.tm.db.save_ai_inspection("ai-flagged-scam.com", AIInspectionResult(
            domain="ai-flagged-scam.com",
            is_safe=False,
            score=95,
            verdict="Block",
            risk_level="HIGH RISK",
            impersonated_brand="PayPal",
            summary="Confirmed visual credential harvesting scam",
            visual_indicators=["PayPal logo clone"],
            network_indicators=["Password post to untrusted host"],
        ))

        # Start block page server on ephemeral port
        cls.server, cls.port = block_page_server.run_block_page_server(
            host="127.0.0.1",
            port=0,
            tm=cls.tm,
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tm.close()
        if os.path.exists(cls.db_path):
            try:
                os.unlink(cls.db_path)
            except OSError:
                pass

    def test_healthz_endpoint(self):
        url = f"http://127.0.0.1:{self.port}/healthz"
        with urllib.request.urlopen(url, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("status"), "healthy")
            self.assertEqual(data.get("server"), "dns.odikyu.tech")

    def test_api_check_endpoint(self):
        url = f"http://127.0.0.1:{self.port}/api/check?domain=malicious-phish.xyz"
        with urllib.request.urlopen(url, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("domain"), "malicious-phish.xyz")
            self.assertEqual(data.get("risk_level"), "HIGH RISK")
            self.assertEqual(data.get("action"), "Block")
            self.assertEqual(data.get("score"), 100)

    def test_api_stats_endpoint(self):
        url = f"http://127.0.0.1:{self.port}/api/stats"
        with urllib.request.urlopen(url, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("total_threats", data)
            self.assertGreaterEqual(data["total_threats"], 1)

    def test_warning_page_rendering_for_blocked_domain(self):
        # Emulate browser hitting http://malicious-phish.xyz/ resolved to this server
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/", headers={"Host": "malicious-phish.xyz"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        body = resp.read().decode("utf-8")
        self.assertIn("SECURITY THREAT BLOCKED", body)
        self.assertIn("malicious-phish.xyz", body)
        self.assertIn("PhishTank", body)
        self.assertIn("Odikyu DNS Shield", body)
        conn.close()

    def test_warning_page_rendering_for_ai_flagged_domain(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/", headers={"Host": "ai-flagged-scam.com"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        body = resp.read().decode("utf-8")
        self.assertIn("ai-flagged-scam.com", body)
        self.assertIn("PayPal logo clone", body)
        self.assertIn("Gemma AI", body)
        conn.close()

    def test_dashboard_rendering(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/admin", headers={"Host": "dns.odikyu.tech"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        body = resp.read().decode("utf-8")
        self.assertIn("Odikyu DNS Shield", body)
        self.assertIn("Threat Intelligence & AI Inspection Console", body)
        conn.close()


class TestDNSProxyIntegration(unittest.TestCase):
    def test_build_blocked_response_ip(self):
        # Query for badsite.com (A record, qtype=1)
        # DNS query packet header + question
        query = (
            b"\x12\x34"  # ID
            b"\x01\x00"  # Flags: standard query, RD=1
            b"\x00\x01"  # QDCOUNT=1
            b"\x00\x00"  # ANCOUNT=0
            b"\x00\x00"  # NSCOUNT=0
            b"\x00\x00"  # ARCOUNT=0
            b"\x07badsite\x03com\x00"  # QNAME: badsite.com
            b"\x00\x01"  # QTYPE: A
            b"\x00\x01"  # QCLASS: IN
        )
        resp = dns_proxy.build_blocked_response(query, "192.0.2.1")
        self.assertIsNotNone(resp)
        self.assertGreater(len(resp), len(query))
        # The last 4 bytes of an A answer should be the IPv4 address
        self.assertEqual(resp[-4:], bytes([192, 0, 2, 1]))

    def test_ai_inspection_queue_enqueue(self):
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)
        tm = ThreatIntelligenceManager(db_path=db_path)
        queue = dns_proxy.BackgroundAIInspectionQueue(tm)

        self.assertTrue(queue.enqueue("suspicious-test-1.xyz"))
        # Duplicate enqueue should return False
        self.assertFalse(queue.enqueue("suspicious-test-1.xyz"))
        # Second domain should enqueue
        self.assertTrue(queue.enqueue("suspicious-test-2.xyz"))

        tm.close()
        if os.path.exists(db_path):
            try:
                os.unlink(db_path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
