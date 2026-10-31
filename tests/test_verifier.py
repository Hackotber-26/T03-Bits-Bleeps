import gzip
import os
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

import dns_proxy
from threat_manager import (
    CheckResult,
    LocalListFeed,
    OpenPhishFeed,
    PhishTankFeed,
    RiskAction,
    RiskAssessment,
    RiskLevel,
    ThreatDatabase,
    ThreatIntelligenceManager,
    extract_domain_from_url,
    get_candidate_domains,
)


class TestThreatManagerAndRiskScoring(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_threats.db")
        self.manager = ThreatIntelligenceManager(db_path=self.db_path)

    def tearDown(self):
        self.manager.close()
        self.tmp_dir.cleanup()

    def test_extract_domain_from_url(self):
        self.assertEqual(extract_domain_from_url("http://example.com/path"), "example.com")
        self.assertEqual(extract_domain_from_url("https://sub.evil.com:8443/login?q=1"), "sub.evil.com")
        self.assertEqual(extract_domain_from_url("http://user:pass@phish.net/x"), "phish.net")
        self.assertEqual(extract_domain_from_url("simple-domain.org"), "simple-domain.org")
        self.assertIsNone(extract_domain_from_url(""))

    def test_get_candidate_domains(self):
        cands = get_candidate_domains("a.b.c.malicious.com")
        self.assertEqual(cands, ["a.b.c.malicious.com", "b.c.malicious.com", "c.malicious.com", "malicious.com"])

        cands_two = get_candidate_domains("malicious.com")
        self.assertEqual(cands_two, ["malicious.com"])

    def test_high_risk_tier_confirmed_feed_match(self):
        """Confirmed threat-feed match must be HIGH RISK and Block with score 100."""
        db = self.manager.db
        db.upsert_threat("confirmed-phish.com", "PhishTank", "phishing", "Target: PayPal, ID: 12345")

        # 1. Exact match
        res = self.manager.check_domain("confirmed-phish.com")
        self.assertEqual(res.risk_level, RiskLevel.HIGH)
        self.assertEqual(res.action, RiskAction.BLOCK)
        self.assertEqual(res.score, 100)
        self.assertTrue(res.is_blocked)
        self.assertIn("Confirmed malicious domain from a trusted feed", res.summary)
        self.assertTrue(any(r.rule_id == "CONFIRMED_FEED_MATCH" for r in res.triggered_rules))

        # 2. Subdomain match
        res_sub = self.manager.check_domain("login.secure.confirmed-phish.com")
        self.assertEqual(res_sub.risk_level, RiskLevel.HIGH)
        self.assertEqual(res_sub.action, RiskAction.BLOCK)
        self.assertEqual(res_sub.score, 100)
        self.assertTrue(res_sub.is_blocked)

    def test_suspicious_tier_heuristic_evidence(self):
        """Suspicious characteristics without confirmed evidence must be SUSPICIOUS / Caution."""
        # Domain with brand impersonation, suspicious TLD, and security keywords
        domain = "paypal-security-verification.xyz"
        res = self.manager.check_domain(domain)

        self.assertEqual(res.risk_level, RiskLevel.SUSPICIOUS)
        self.assertEqual(res.action, RiskAction.CAUTION)
        self.assertFalse(res.is_blocked)  # Caution allows/forwards by default with alert
        self.assertGreaterEqual(res.score, 35)
        self.assertLessEqual(res.score, 75)  # Heuristics capped at 75
        self.assertIn("Suspicious characteristics without confirmed malicious evidence", res.summary)

        rule_ids = [r.rule_id for r in res.triggered_rules]
        self.assertIn("SUSPICIOUS_TLD", rule_ids)
        self.assertIn("BRAND_IMPERSONATION", rule_ids)
        self.assertIn("SECURITY_KEYWORDS", rule_ids)

    def test_suspicious_tier_punycode_homograph(self):
        """Punycode homograph attacks should be flagged as SUSPICIOUS."""
        domain = "xn--apple-security-9za.com"
        res = self.manager.check_domain(domain)

        self.assertEqual(res.risk_level, RiskLevel.SUSPICIOUS)
        self.assertEqual(res.action, RiskAction.CAUTION)
        self.assertTrue(any(r.rule_id == "PUNYCODE_HOMOGRAPH" for r in res.triggered_rules))

    def test_low_risk_tier_clean_domain(self):
        """Clean domains must be LOW RISK and Allow, with non-guarantee disclaimer."""
        domain = "python.org"
        res = self.manager.check_domain(domain)

        self.assertEqual(res.risk_level, RiskLevel.LOW)
        self.assertEqual(res.action, RiskAction.ALLOW)
        self.assertFalse(res.is_blocked)
        self.assertLess(res.score, 35)
        self.assertIn("No known threat detected. This does not guarantee that the domain is safe.", res.summary)

    def test_whitelist_exemption_overrides_heuristics(self):
        """Whitelisted domains must evaluate to LOW RISK and Allow with score 0."""
        # google.com contains keyword 'google', but is whitelisted
        res = self.manager.check_domain("google.com")
        self.assertEqual(res.risk_level, RiskLevel.LOW)
        self.assertEqual(res.action, RiskAction.ALLOW)
        self.assertEqual(res.score, 0)
        self.assertTrue(any(r.rule_id == "WHITELIST_EXEMPTION" for r in res.triggered_rules))

    def test_bulk_upsert_performance(self):
        db = self.manager.db
        records = [
            (f"domain{i}.bad.org", "PhishTank", "phishing", f"ID: {i}")
            for i in range(5000)
        ]
        t0 = time.time()
        count = db.bulk_upsert_threats(records)
        elapsed = time.time() - t0
        self.assertEqual(count, 5000)
        self.assertLess(elapsed, 1.0)

        # Microsecond lookup test
        t0 = time.time()
        res = self.manager.check_domain("domain4999.bad.org")
        lookup_ms = (time.time() - t0) * 1000
        self.assertEqual(res.risk_level, RiskLevel.HIGH)
        self.assertLess(lookup_ms, 10.0)

    def test_audit_logging_with_risk_scores(self):
        self.manager.db.upsert_threat("audit-target.com", "OpenPhish", "phishing", "Test Phish")
        res = self.manager.check_domain("audit-target.com")
        self.manager.log_security_event("192.168.1.55", "audit-target.com", "A", res)

        stats = self.manager.db.get_stats()
        self.assertEqual(stats["total_threats"], 1)
        self.assertEqual(stats["total_blocked_queries"], 1)

        logs = self.manager.db.get_recent_audit_logs(limit=5)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["client_ip"], "192.168.1.55")
        self.assertEqual(logs[0]["domain"], "audit-target.com")
        self.assertEqual(logs[0]["score"], 100)
        self.assertEqual(logs[0]["risk_level"], "HIGH RISK")
        self.assertEqual(logs[0]["action"], "Block")
        self.assertIn("CONFIRMED_FEED_MATCH", logs[0]["rules"])

    @patch("urllib.request.urlopen")
    def test_phishtank_feed_fetch(self, mock_urlopen):
        csv_data = (
            "phish_id,url,phish_detail_url,submission_time,verified,verification_time,online,target\n"
            "111,https://evil1.com/login,http://...,2026-10-31,yes,2026-10-31,yes,PayPal\n"
            "222,http://evil2.org/auth,http://...,2026-10-31,yes,2026-10-31,yes,Google\n"
        ).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = csv_data
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        feed = PhishTankFeed()
        results = list(feed.fetch_records())
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0], "evil1.com")
        self.assertIn("PayPal", results[0][1])
        self.assertEqual(results[1][0], "evil2.org")

    @patch("urllib.request.urlopen")
    def test_phishtank_descriptive_user_agent_and_gzip(self, mock_urlopen):
        """Compressed feed + descriptive UA on every request (PhishTank dev requirement)."""
        csv_data = (
            "phish_id,url,phish_detail_url,submission_time,verified,verification_time,online,target\n"
            "333,https://gzip-phish.com/pay,http://...,2026-10-31,yes,2026-10-31,yes,Netflix\n"
        ).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = gzip.compress(csv_data)
        mock_resp.headers = {"ETag": '"rev-1"'}
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        feed = PhishTankFeed()
        results = list(feed.fetch_records())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "gzip-phish.com")
        self.assertIn("Netflix", results[0][1])

        request = mock_urlopen.call_args[0][0]
        self.assertIn("odikyu-dns-shield", request.get_header("User-agent"))
        self.assertTrue(feed.primary_url.startswith("https://"))
        self.assertTrue(feed.primary_url.endswith("online-valid.csv.gz"))

    @patch("urllib.request.urlopen")
    def test_phishtank_app_key_url_and_etag_skip(self, mock_urlopen):
        """Keyed URL format + unlimited HEAD/ETag checks skip unchanged downloads."""
        csv_data = (
            "phish_id,url,phish_detail_url,submission_time,verified,verification_time,online,target\n"
            "444,https://keyed-phish.com/x,http://...,2026-10-31,yes,2026-10-31,yes,Bank\n"
        ).encode("utf-8")

        head_resp = MagicMock()
        head_resp.headers = {"ETag": '"hour-1"'}
        head_resp.__enter__.return_value = head_resp

        get_resp = MagicMock()
        get_resp.read.return_value = csv_data
        get_resp.headers = {"ETag": '"hour-1"'}
        get_resp.__enter__.return_value = get_resp

        mock_urlopen.side_effect = lambda request, *a, **kw: (
            head_resp if request.get_method() == "HEAD" else get_resp
        )

        feed = PhishTankFeed(api_key="APPKEY123")
        # Keyed URL per https://data.phishtank.com/data/<your app key>/...
        self.assertEqual(
            feed.primary_url,
            "https://data.phishtank.com/data/APPKEY123/online-valid.csv.gz",
        )

        first = list(feed.fetch_records())
        self.assertEqual(len(first), 1)
        second = list(feed.fetch_records())
        self.assertEqual(second, [])  # ETag unchanged -> no second download

        methods = [call[0][0].get_method() for call in mock_urlopen.call_args_list]
        self.assertEqual(methods, ["HEAD", "GET", "HEAD"])
        # HEAD carried the descriptive UA too.
        for call in mock_urlopen.call_args_list:
            self.assertIn("odikyu-dns-shield", call[0][0].get_header("User-agent"))

    @patch("urllib.request.urlopen")
    def test_phishtank_falls_back_to_plain_csv(self, mock_urlopen):
        """If the compressed asset 404s, retry the documented plain-CSV URL."""
        csv_data = (
            "phish_id,url,phish_detail_url,submission_time,verified,verification_time,online,target\n"
            "555,https://plain-fallback.com/a,http://...,2026-10-31,yes,2026-10-31,yes,Apple\n"
        ).encode("utf-8")

        not_found = urllib.error.HTTPError(
            "https://data.phishtank.com/data/online-valid.csv.gz",
            404, "Not Found", {}, None,
        )
        mock_resp = MagicMock()
        mock_resp.read.return_value = csv_data
        mock_resp.headers = {}
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.side_effect = [not_found, mock_resp]

        feed = PhishTankFeed()
        results = list(feed.fetch_records())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "plain-fallback.com")
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("urllib.request.urlopen")
    def test_openphish_feed_fetch(self, mock_urlopen):
        txt_data = (
            "http://phish1.com/update\n"
            "https://phish2.net/account\n"
        ).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = txt_data
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        feed = OpenPhishFeed()
        results = list(feed.fetch_records())
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0], "phish1.com")
        self.assertEqual(results[1][0], "phish2.net")

    def test_locallist_feed(self):
        feed = LocalListFeed(domains=["custom1.org", "custom2.net"])
        records = list(feed.fetch_records())
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][0], "custom1.org")

    def test_ai_inspection_caching_and_automatic_blocking(self):
        """Test AI inspection caching and automatic threat table block registration."""
        from website_inspector import AIInspectionResult

        db = self.manager.db
        ai_res = AIInspectionResult(
            domain="malicious-ai-test.com",
            is_safe=False,
            score=90,
            verdict="Block",
            risk_level="HIGH RISK",
            impersonated_brand="Apple",
            summary="Apple ID phishing landing page.",
            visual_indicators=["Apple logo detected on unauthorized domain"],
            network_indicators=["Password form submits to remote server"],
            screenshot_path="screenshots/test.png",
            model_name="gemma-4-31b-it",
        )

        db.save_ai_inspection("malicious-ai-test.com", ai_res)

        # 1. Verify saved in cache database
        cached = db.get_cached_ai_inspection("malicious-ai-test.com")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.score, 90)
        self.assertEqual(cached.verdict, "Block")
        self.assertEqual(cached.impersonated_brand, "Apple")

        # 2. Verify automatically registered in threats table so DNS blocks it
        risk = self.manager.check_domain("malicious-ai-test.com")
        self.assertEqual(risk.risk_level, RiskLevel.HIGH)
        self.assertEqual(risk.action, RiskAction.BLOCK)
        self.assertTrue(risk.is_blocked)

    def test_ai_inspection_allow_cached_verdict(self):
        """Test cached Allow verdict integrates into check_domain."""
        from website_inspector import AIInspectionResult

        db = self.manager.db
        ai_res = AIInspectionResult(
            domain="safe-portfolio.io",
            is_safe=True,
            score=15,
            verdict="Allow",
            risk_level="LOW RISK",
            summary="Personal developer portfolio.",
            visual_indicators=["No brand logos"],
            network_indicators=["Standard HTTPS"],
            model_name="gemma-4-31b-it",
        )
        db.save_ai_inspection("safe-portfolio.io", ai_res)

        risk = self.manager.check_domain("safe-portfolio.io")
        self.assertEqual(risk.risk_level, RiskLevel.LOW)
        self.assertEqual(risk.action, RiskAction.ALLOW)
        self.assertEqual(risk.score, 15)
        self.assertTrue(any(r.rule_id == "GEMMA_AI_VERDICT" for r in risk.triggered_rules))


if __name__ == "__main__":
    unittest.main()
