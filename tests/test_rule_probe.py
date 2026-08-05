from routeweaver.models import AppConfig, IpIdentity, RouteMode, RouteTarget, Rule, RuleKind
from routeweaver.rule_probe import probe_host_for_rule, probe_rule


def identity_for(target, *_args, **_kwargs):
    return IpIdentity(
        ip="203.0.113.1" if target is RouteTarget.VPN else "198.51.100.1",
        country="Test", region="Region", city="City", isp="ISP",
        source="https://example.test/", checked_at="2026-01-01T00:00:00+00:00", route=target,
    )


def test_forward_app_rule_reports_vpn_identity():
    rule = Rule(RuleKind.APP, "browser.exe")
    result = probe_rule(AppConfig(mode=RouteMode.FORWARD, rules=[rule]), rule, identity_for)
    assert result.success
    assert result.decision.target is RouteTarget.VPN
    assert result.identity.ip == "203.0.113.1"


def test_reverse_domain_rule_reports_direct_identity():
    rule = Rule(RuleKind.DOMAIN, "*.example.com")
    result = probe_rule(AppConfig(mode=RouteMode.REVERSE, rules=[rule]), rule, identity_for)
    assert result.success
    assert result.host_context == "routeweaver-probe.example.com"
    assert result.decision.target is RouteTarget.DIRECT
    assert result.identity.ip == "198.51.100.1"


def test_probe_host_normalizes_url_and_wildcards():
    assert probe_host_for_rule("https://*.例子.测试/path") == "routeweaver-probe.xn--fsqu00a.xn--0zwm56d"

