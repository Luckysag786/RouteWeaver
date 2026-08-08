from routeweaver import ip_geo
from routeweaver.app import _split_proxy
from routeweaver.models import RouteTarget
from routeweaver.upstream import normalize_upstream_protocol, parse_proxy_setting


def test_proxy_setting_parser_supports_socks_and_prefers_http():
    assert _split_proxy("socks=127.0.0.1:1080") == ("socks5", "127.0.0.1", 1080)
    assert _split_proxy("socks5://localhost:1080") == ("socks5", "localhost", 1080)
    assert _split_proxy("SOCKS5://[::1]:1080") == ("socks5", "::1", 1080)
    assert _split_proxy("socks=127.0.0.1:1080;http=127.0.0.1:7890") == ("http", "127.0.0.1", 7890)
    assert _split_proxy("https=proxy.local:8080") == ("http", "proxy.local", 8080)
    assert _split_proxy("http://[::1]:7890") == ("http", "::1", 7890)
    assert parse_proxy_setting("DIRECT") is None


def test_protocol_normalization():
    assert normalize_upstream_protocol("SOCKS") == "socks5"
    assert normalize_upstream_protocol("https") == "http"


def test_ip_identity_uses_socks_fetcher(monkeypatch):
    calls = []

    def fake(url, host, port, timeout, accept):
        calls.append((url, host, port, timeout, accept))
        return b'{"ip":"8.8.4.4","country_name":"Testland","region":"Region","city":"City","org":"Test ISP"}'

    monkeypatch.setattr(ip_geo, "_fetch_bytes_socks", fake)
    monkeypatch.setattr(ip_geo, "PROVIDERS", (("test", "https://example.test/", "application/json", ip_geo._parse_ipapi),))
    result = ip_geo.lookup_identity(
        RouteTarget.VPN, "127.0.0.1", 1080, upstream_protocol="socks5",
    )
    assert result.ip == "8.8.4.4"
    assert result.isp == "Test ISP"
    assert calls and calls[0][1:3] == ("127.0.0.1", 1080)


def test_ip_identity_falls_back_and_keeps_ip_without_geo(monkeypatch):
    calls = []

    def fake(url, proxy_url, timeout, accept):
        calls.append(url)
        if len(calls) == 1:
            raise OSError("temporary TLS EOF")
        return b"1.1.1.1\n"

    monkeypatch.setattr(ip_geo, "_fetch_bytes", fake)
    monkeypatch.setattr(ip_geo, "PROVIDERS", (
        ("broken", "https://broken.test/", "application/json", ip_geo._parse_json_ip),
        ("text", "https://working.test/", "text/plain", ip_geo._parse_text_ip),
    ))
    result = ip_geo.lookup_identity(RouteTarget.VPN, "::1", 7890, upstream_protocol="http")
    assert result.ip == "1.1.1.1"
    assert result.location == "未知"
    assert result.source == "https://working.test/"
    assert set(calls) == {"https://broken.test/", "https://working.test/"}
