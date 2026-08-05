import json

from routeweaver.config import ConfigStore
from routeweaver.models import AppConfig, RouteMode, Rule, RuleKind


def test_config_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    expected = AppConfig(mode=RouteMode.REVERSE, upstream_port=9000, rules=[Rule(RuleKind.DOMAIN, "example.com")])
    store.save(expected)
    actual = store.load()
    assert actual.mode is RouteMode.REVERSE
    assert actual.upstream_port == 9000
    assert actual.rules[0].kind is RuleKind.DOMAIN


def test_invalid_config_is_quarantined(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{broken", encoding="utf-8")
    actual = ConfigStore(path).load()
    assert actual.mode is RouteMode.FORWARD
    assert (tmp_path / "config.invalid.json").exists()


def test_new_behavior_defaults_and_legacy_tray_migration():
    fresh = AppConfig()
    assert fresh.start_with_windows is True
    assert fresh.minimize_to_tray is True

    legacy = AppConfig.from_dict({"minimize_to_tray": False})
    assert legacy.start_with_windows is True
    assert legacy.startup_configured is False
    assert legacy.minimize_to_tray is True


def test_explicit_close_behavior_is_preserved():
    configured = AppConfig.from_dict({
        "start_with_windows": False,
        "startup_configured": True,
        "minimize_to_tray": False,
    })
    assert configured.start_with_windows is False
    assert configured.startup_configured is True
    assert configured.minimize_to_tray is False
