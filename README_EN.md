# RouteWeaver

> Select which proxy-aware Windows apps and websites use your existing local VPN/proxy, while the rest keep the direct connection.

[中文说明](README.md) · [Architecture](docs/ARCHITECTURE.md) · [Platform limits](docs/PLATFORM_LIMITS.md) · [Release story](docs/blog/routeweaver-launch.md)

RouteWeaver is an auditable split-routing gateway placed in front of an existing local HTTP or SOCKS5 proxy. It supports two policies:

- **Forward mapping:** only matched apps or domains use the VPN/proxy; everything else connects directly.
- **Reverse isolation:** traffic uses the VPN/proxy by default; matched apps or domains connect directly.

The Windows app includes process/application discovery, editable rules, connection activity, real exit-IP checks, transactional system-proxy takeover, startup settings and tray operation.

## Quick start

Download the Windows installer from [GitHub Releases](https://github.com/Luckysag786/RouteWeaver/releases), keep your existing VPN/proxy connected, launch RouteWeaver, confirm the detected upstream endpoint, add rules, then select **Enable split routing**.

For development:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m routeweaver
```

## Honest platform limits

The stable Windows backend covers applications that honor the Windows system proxy and HTTP(S) browser traffic. UDP, QUIC, games and applications that bypass the system proxy require a signed WFP driver or per-app proxy configuration.

Android allows one active `VpnService` per user profile. The companion APK therefore manages rules, verifies exits and hands rules to compatible VPN providers; it does not claim to transparently split another provider's tunnel.

## License

[MIT](LICENSE). Use the software in compliance with the laws, network policies and service terms applicable to you.
