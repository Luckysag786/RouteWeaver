import json

from routeweaver.platform.windows_proxy import ProxySnapshot, SystemProxyManager
from routeweaver.upstream import ProxyEndpoint


def snapshot(server, enabled=1, pac=""):
    return ProxySnapshot(values={
        "ProxyEnable": {"value": enabled, "type": 4},
        "ProxyServer": {"value": server, "type": 1},
        "ProxyOverride": None,
        "AutoConfigURL": {"value": pac, "type": 1} if pac else None,
    })


def test_detection_uses_transaction_backup_while_gateway_is_active(tmp_path, monkeypatch):
    backup = tmp_path / "proxy-backup.json"
    backup.write_text(json.dumps(snapshot("socks=127.0.0.1:1080").to_dict()), encoding="utf-8")
    manager = SystemProxyManager(backup)
    monkeypatch.setattr(manager, "is_owned", lambda: True)
    monkeypatch.setattr(manager, "snapshot", lambda: snapshot("127.0.0.1:17891"))
    monkeypatch.setattr(manager, "_winhttp_endpoint", lambda: None)
    endpoint = manager.detect_upstream(excluded=("127.0.0.1", 17891))
    assert endpoint == ProxyEndpoint("socks5", "127.0.0.1", 1080, "启用前的 Windows 系统代理")


def test_detection_never_selects_routeweaver_gateway(tmp_path, monkeypatch):
    manager = SystemProxyManager(tmp_path / "missing.json")
    monkeypatch.setattr(manager, "_discovery_snapshot", lambda: (snapshot("127.0.0.1:17891"), "Windows 系统代理"))
    monkeypatch.setattr(manager, "_winhttp_endpoint", lambda: None)
    monkeypatch.setattr("routeweaver.platform.windows_proxy.COMMON_LOCAL_PROXY_PORTS", ())
    endpoint = manager.detect_upstream(
        fallback=ProxyEndpoint("http", "127.0.0.1", 17891),
        excluded=("127.0.0.1", 17891),
    )
    assert endpoint is None


def test_static_pac_proxy_is_recognized(tmp_path):
    pac = tmp_path / "proxy.pac"
    pac.write_text(
        'function FindProxyForURL(url, host) { return "PROXY 127.0.0.1:7890; SOCKS5 127.0.0.1:1080; DIRECT"; }',
        encoding="utf-8",
    )
    endpoint = SystemProxyManager._endpoint_from_pac(pac.as_uri(), "Windows 系统代理")
    assert endpoint == ProxyEndpoint("http", "127.0.0.1", 7890, "Windows 系统代理 PAC")
