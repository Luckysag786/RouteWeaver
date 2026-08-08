from __future__ import annotations

import argparse
import json
import signal
import time
from dataclasses import asdict

from .app import run_app
from .config import ConfigStore
from .diagnostics import run_diagnostics
from .gateway import SplitProxyGateway
from .platform.windows_proxy import SystemProxyManager
from .platform.windows_single_instance import ensure_single_instance, release_single_instance, show_duplicate_notice


def main() -> None:
    parser = argparse.ArgumentParser(description="路由织网：在现有本地 VPN 代理前按应用/域名分流")
    parser.add_argument("--diagnose", action="store_true", help="运行命令行诊断后退出")
    parser.add_argument("--gateway-only", action="store_true", help="只启动本地网关，不接管系统代理")
    parser.add_argument("--minimized", action="store_true", help="启动后隐藏到系统托盘")
    args = parser.parse_args()
    if not args.diagnose and not ensure_single_instance():
        show_duplicate_notice()
        return
    try:
        _run(args)
    finally:
        if not args.diagnose:
            release_single_instance()


def _run(args: argparse.Namespace) -> None:
    config = ConfigStore().load()
    if args.diagnose:
        results = run_diagnostics(config, SystemProxyManager())
        print(json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2))
        return
    if args.gateway_only:
        gateway = SplitProxyGateway(config)
        gateway.start()
        stop = False

        def request_stop(*_: object) -> None:
            nonlocal stop
            stop = True

        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)
        print(f"RouteWeaver gateway listening on {config.listen_host}:{config.listen_port}")
        try:
            while not stop:
                time.sleep(0.25)
        finally:
            gateway.stop()
        return
    run_app(start_minimized=args.minimized)


if __name__ == "__main__":
    main()
