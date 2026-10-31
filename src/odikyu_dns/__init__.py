"""
Odikyu DNS: DNS Proxy with local threat database, rule-based risk scoring, and Gemma AI website inspector.
"""

from dns_proxy import (
    THREAT_MANAGER,
    check_domain,
    is_blocked,
    main,
    show_security_alert,
    show_warning,
)
from threat_manager import (
    CheckResult,
    LocalListFeed,
    OpenPhishFeed,
    PhishTankFeed,
    PhishTankLookupFeed,
    RiskAction,
    RiskAssessment,
    RiskLevel,
    ScoredRule,
    ThreatDatabase,
    ThreatFeed,
    ThreatIntelligenceManager,
    ThreatRecord,
    create_default_manager,
    evaluate_domain_risk,
)
from website_inspector import (
    AIInspectionResult,
    GemmaWebsiteInspector,
    NetworkTelemetry,
    capture_site_screenshot,
    collect_network_telemetry,
)

__all__ = [
    "ThreatDatabase",
    "ThreatRecord",
    "CheckResult",
    "RiskLevel",
    "RiskAction",
    "RiskAssessment",
    "ScoredRule",
    "evaluate_domain_risk",
    "ThreatFeed",
    "PhishTankFeed",
    "PhishTankLookupFeed",
    "OpenPhishFeed",
    "LocalListFeed",
    "ThreatIntelligenceManager",
    "create_default_manager",
    "THREAT_MANAGER",
    "check_domain",
    "is_blocked",
    "show_security_alert",
    "show_warning",
    "main",
    "NetworkTelemetry",
    "AIInspectionResult",
    "GemmaWebsiteInspector",
    "collect_network_telemetry",
    "capture_site_screenshot",
]
