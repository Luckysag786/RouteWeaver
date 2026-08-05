from routeweaver import ip_geo
from routeweaver.app import _split_proxy
from routeweaver.models import RouteTarget
from routeweaver.upstream import normalize_upstream_protocol


def test_proxy_setting_parser_supports_socks_and_prefers_http():
    assert _split_proxy("socks=127.0.0.1:1080") == ("socks5", "127.0.0.1", 1080)
    assert _split_proxy("socks5://localhost:1080") == ("socks5", "localhost", 1080)
    assert _split_proxy("SOCKS5://[::1]:1080") == ("socks5", "::1", 1080)
    assert _split_proxy("socks=127.0.0.1:1080;http=127.0.0.1:7890") == ("http", "127.0.0.1", 7890)


def test_protocol_normalization():
    assert normalize_upstream_protocol("SOCKS") == "socks5"
    assert normalize_upstream_protocol("https") == "http"


def test_ip_identity_uses_socks_fetcher(monkeypatch):
    calls = []

    def fake(url, host, port, timeout):
        calls.append((url, host, port, timeout))
        return {
            "success": True,
            "ip": "203.0.113.10",
            "country": "Testland",
            "region": "Region",
            "city": "City",
            "connection": {"isp": "Test ISP"},
        }

    monkeypatch.setattr(ip_geo, "_fetch_json_socks", fake)
    result = ip_geo.lookup_identity(
        RouteTarget.VPN, "127.0.0.1", 1080, upstream_protocol="socks5",
    )
    assert result.ip == "203.0.113.10"
    assert result.isp == "Test ISP"
    assert calls and calls[0][1:3] == ("127.0.0.1", 1080)
