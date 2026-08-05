from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from routeweaver.gateway import SplitProxyGateway
from routeweaver.models import AppConfig
from routeweaver.platform.windows_proxy import SystemProxyManager


def main() -> int:
    manager = SystemProxyManager()
    before = manager.current_proxy()
    config = AppConfig(listen_port=17893)
    gateway = SplitProxyGateway(config)
    gateway.start()
    during = None
    error = ""
    try:
        manager.activate(config.listen_host, config.listen_port)
        during = manager.current_proxy()
        if during != (True, "127.0.0.1:17893"):
            raise AssertionError(f"接管值不一致: {during}")
    except Exception as exc:
        error = str(exc)
    finally:
        try:
            manager.restore()
        finally:
            gateway.stop()
    after = manager.current_proxy()
    report = {
        "before": {"enabled": before[0], "server": before[1]},
        "during": {"enabled": during[0], "server": during[1]} if during else None,
        "after": {"enabled": after[0], "server": after[1]},
        "restored_exactly": before == after,
        "error": error,
        "pass": not error and before == after,
    }
    output = PROJECT / "artifacts" / "proxy-transaction-test.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
