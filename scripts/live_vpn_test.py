from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from routeweaver.gateway import SplitProxyGateway
from routeweaver.models import AppConfig, RouteMode, Rule, RuleKind
from routeweaver.platform.windows_proxy import SystemProxyManager


def curl_json(proxy_port: int, url: str) -> dict:
    process = subprocess.run(
        ["curl.exe", "--proxy", f"http://127.0.0.1:{proxy_port}", "--connect-timeout", "10", "--max-time", "35", "--retry", "2", "--retry-all-errors", "-sS", url],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return json.loads(process.stdout)


def python_json(proxy_port: int, url: str) -> dict:
    code = (
        "import json,urllib.request;"
        f"p='http://127.0.0.1:{proxy_port}';"
        "o=urllib.request.build_opener(urllib.request.ProxyHandler({'http':p,'https':p}));"
        f"q=urllib.request.Request({url!r},headers={{'User-Agent':'curl/8.21.0','Accept':'application/json'}});"
        "r=o.open(q,timeout=35);"
        "print(r.read().decode())"
    )
    process = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(process.stdout)


def main() -> int:
    upstream_port_text = os.environ.get("ROUTEWEAVER_UPSTREAM_PORT", "").strip()
    if not upstream_port_text:
        raise SystemExit("Set ROUTEWEAVER_UPSTREAM_PORT to the existing local proxy port before running this live test.")
    try:
        upstream_port = int(upstream_port_text)
    except ValueError as exc:
        raise SystemExit("ROUTEWEAVER_UPSTREAM_PORT must be an integer.") from exc
    upstream_host = os.environ.get("ROUTEWEAVER_UPSTREAM_HOST", "127.0.0.1").strip()
    protocols = [item.strip().lower() for item in os.environ.get("ROUTEWEAVER_TEST_PROTOCOLS", "http").split(",") if item.strip()]
    if not protocols or any(item not in ("http", "socks5") for item in protocols):
        raise SystemExit("ROUTEWEAVER_TEST_PROTOCOLS must contain http and/or socks5.")

    manager = SystemProxyManager()
    before = manager.current_proxy()
    config = AppConfig(
        mode=RouteMode.FORWARD,
        listen_port=17892,
        upstream_host=upstream_host,
        upstream_port=upstream_port,
        upstream_protocol=protocols[0],
        rules=[Rule(RuleKind.DOMAIN, "ifconfig.co")],
    )
    gateway = SplitProxyGateway(config)
    gateway.start()
    report: dict[str, object] = {
        "checked_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "upstream": {"endpoint": f"{upstream_host}:{upstream_port}", "protocols_tested": protocols},
        "system_proxy_before": {"enabled": before[0], "server": before[1]},
        "tests": [],
    }
    try:
        forward_vpn = curl_json(config.listen_port, "https://ifconfig.co/json")
        forward_direct = curl_json(config.listen_port, "https://ipwho.is/")
        report["tests"].append({
            "mode": "forward", "selected_domain": "ifconfig.co",
            "selected_result": "vpn", "selected_ip": forward_vpn.get("ip"),
            "unselected_result": "direct", "unselected_ip": forward_direct.get("ip"),
            "pass": bool(forward_vpn.get("ip") and forward_direct.get("ip") and forward_vpn.get("ip") != forward_direct.get("ip")),
        })

        config.mode = RouteMode.REVERSE
        gateway.update_config(config)
        reverse_direct = curl_json(config.listen_port, "https://ifconfig.co/json")
        reverse_vpn = curl_json(config.listen_port, "https://ipwho.is/")
        report["tests"].append({
            "mode": "reverse", "isolated_domain": "ifconfig.co",
            "selected_result": "direct", "selected_ip": reverse_direct.get("ip"),
            "unselected_result": "vpn", "unselected_ip": reverse_vpn.get("ip"),
            "pass": bool(reverse_direct.get("ip") and reverse_vpn.get("ip") and reverse_direct.get("ip") != reverse_vpn.get("ip")),
        })

        config.mode = RouteMode.FORWARD
        config.rules = [Rule(RuleKind.APP, "curl.exe")]
        gateway.update_config(config)
        app_selected_vpn = curl_json(config.listen_port, "https://ifconfig.co/json")
        app_unselected_direct = python_json(config.listen_port, "https://ifconfig.co/json")
        report["tests"].append({
            "mode": "forward", "selected_app": "curl.exe", "unselected_app": "python.exe",
            "selected_result": "vpn", "selected_ip": app_selected_vpn.get("ip"),
            "unselected_result": "direct", "unselected_ip": app_unselected_direct.get("ip"),
            "pass": bool(app_selected_vpn.get("ip") and app_unselected_direct.get("ip") and app_selected_vpn.get("ip") != app_unselected_direct.get("ip")),
        })

        config.mode = RouteMode.REVERSE
        gateway.update_config(config)
        app_selected_direct = curl_json(config.listen_port, "https://ifconfig.co/json")
        app_unselected_vpn = python_json(config.listen_port, "https://ifconfig.co/json")
        report["tests"].append({
            "mode": "reverse", "isolated_app": "curl.exe", "unselected_app": "python.exe",
            "selected_result": "direct", "selected_ip": app_selected_direct.get("ip"),
            "unselected_result": "vpn", "unselected_ip": app_unselected_vpn.get("ip"),
            "pass": bool(app_selected_direct.get("ip") and app_unselected_vpn.get("ip") and app_selected_direct.get("ip") != app_unselected_vpn.get("ip")),
        })

        for protocol in protocols[1:]:
            config.mode = RouteMode.FORWARD
            config.upstream_protocol = protocol
            config.rules = [Rule(RuleKind.DOMAIN, "ifconfig.co")]
            gateway.update_config(config)
            selected_vpn = curl_json(config.listen_port, "https://ifconfig.co/json")
            unselected_direct = curl_json(config.listen_port, "https://ipwho.is/")
            report["tests"].append({
                "mode": "forward", "upstream_protocol": protocol, "selected_domain": "ifconfig.co",
                "selected_result": "vpn", "selected_ip": selected_vpn.get("ip"),
                "unselected_result": "direct", "unselected_ip": unselected_direct.get("ip"),
                "pass": bool(selected_vpn.get("ip") and unselected_direct.get("ip") and selected_vpn.get("ip") != unselected_direct.get("ip")),
            })
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        gateway.stop()
    after = manager.current_proxy()
    report["system_proxy_after"] = {"enabled": after[0], "server": after[1]}
    report["system_proxy_unchanged"] = before == after
    report["activities"] = [
        {
            "process": record.process_name, "host": record.host, "target": record.target.value,
            "matched_rule": record.matched_rule, "status": record.status, "detail": record.detail,
        }
        for record in gateway.activities
    ]
    passed = not report.get("error") and report["system_proxy_unchanged"] and all(item["pass"] for item in report["tests"])
    report["pass"] = bool(passed)
    output = PROJECT / "artifacts" / "live-vpn-test.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
