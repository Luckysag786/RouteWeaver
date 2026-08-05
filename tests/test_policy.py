from routeweaver.models import AppConfig, RouteMode, RouteTarget, Rule, RuleKind
from routeweaver.policy import PolicyEngine, normalize_host


def test_forward_domain_and_default():
    config = AppConfig(mode=RouteMode.FORWARD, rules=[Rule(RuleKind.DOMAIN, "google.com")])
    engine = PolicyEngine(config)
    assert engine.decide("browser.exe", "mail.google.com").target is RouteTarget.VPN
    assert engine.decide("browser.exe", "baidu.com").target is RouteTarget.DIRECT


def test_reverse_app_and_default():
    config = AppConfig(mode=RouteMode.REVERSE, rules=[Rule(RuleKind.APP, "Weixin.exe")])
    engine = PolicyEngine(config)
    assert engine.decide(r"C:\\Apps\\Weixin.exe", "example.com").target is RouteTarget.DIRECT
    assert engine.decide(r"C:\\Apps\\chrome.exe", "example.com").target is RouteTarget.VPN


def test_disabled_rule_does_not_match():
    config = AppConfig(mode=RouteMode.FORWARD, rules=[Rule(RuleKind.DOMAIN, "example.com", enabled=False)])
    assert PolicyEngine(config).decide("x.exe", "example.com").target is RouteTarget.DIRECT


def test_idna_and_wildcard():
    config = AppConfig(rules=[Rule(RuleKind.DOMAIN, "*.xn--fsqu00a.xn--0zwm56d")])
    assert normalize_host("例子.测试") == "xn--fsqu00a.xn--0zwm56d"
    assert PolicyEngine(config).decide("x.exe", "子.例子.测试").target is RouteTarget.VPN

