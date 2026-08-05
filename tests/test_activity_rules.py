from routeweaver.activity_rules import activity_candidate, matching_rule_index
from routeweaver.models import ActivityRecord, AppConfig, RouteTarget, Rule, RuleKind


def sample_activity() -> ActivityRecord:
    return ActivityRecord.now(
        process_name="browser.exe",
        process_path=r"C:\Apps\Browser\browser.exe",
        host="news.example.com",
        port=443,
        target=RouteTarget.DIRECT,
    )


def test_activity_candidate_supports_app_and_domain():
    record = sample_activity()
    assert activity_candidate(record, RuleKind.APP) == (r"C:\Apps\Browser\browser.exe", "browser.exe")
    assert activity_candidate(record, RuleKind.DOMAIN) == ("news.example.com", "news.example.com")


def test_activity_detects_existing_disabled_app_rule():
    record = sample_activity()
    config = AppConfig(rules=[Rule(RuleKind.APP, "browser.exe", enabled=False)])
    assert matching_rule_index(config, record, RuleKind.APP) == 0


def test_activity_detects_parent_domain_rule():
    record = sample_activity()
    config = AppConfig(rules=[Rule(RuleKind.DOMAIN, "example.com")])
    assert matching_rule_index(config, record, RuleKind.DOMAIN) == 0
