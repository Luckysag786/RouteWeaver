import pytest

from routeweaver.models import RuleKind
from routeweaver.rule_values import normalize_rule_value, rule_value_key


def test_normalize_edited_domain_url_and_idn():
    assert normalize_rule_value(RuleKind.DOMAIN, " HTTPS://*.例子.测试:443/path ") == "*.xn--fsqu00a.xn--0zwm56d"


def test_normalize_edited_app_and_duplicate_key():
    assert normalize_rule_value(RuleKind.APP, ' "C:\\Apps\\Browser.exe" ') == r"C:\Apps\Browser.exe"
    assert rule_value_key(RuleKind.APP, r"C:\Apps\Browser.exe") == rule_value_key(RuleKind.APP, r"c:\apps\browser.exe")


def test_reject_empty_and_non_executable_app_values():
    with pytest.raises(ValueError):
        normalize_rule_value(RuleKind.DOMAIN, "  ")
    with pytest.raises(ValueError):
        normalize_rule_value(RuleKind.APP, "Browser")
