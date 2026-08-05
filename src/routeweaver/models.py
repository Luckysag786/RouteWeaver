from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .upstream import normalize_upstream_protocol


class RouteMode(str, Enum):
    FORWARD = "forward"
    REVERSE = "reverse"


class RouteTarget(str, Enum):
    VPN = "vpn"
    DIRECT = "direct"


class RuleKind(str, Enum):
    APP = "app"
    DOMAIN = "domain"


@dataclass(slots=True)
class Rule:
    kind: RuleKind
    value: str
    enabled: bool = True
    label: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rule":
        return cls(
            kind=RuleKind(data["kind"]),
            value=str(data["value"]),
            enabled=bool(data.get("enabled", True)),
            label=str(data.get("label", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["kind"] = self.kind.value
        return result


@dataclass(slots=True)
class AppConfig:
    mode: RouteMode = RouteMode.FORWARD
    listen_host: str = "127.0.0.1"
    listen_port: int = 17891
    upstream_host: str = "127.0.0.1"
    upstream_port: int = 7888
    upstream_protocol: str = "http"
    rules: list[Rule] = field(default_factory=list)
    start_with_windows: bool = True
    startup_configured: bool = False
    minimize_to_tray: bool = True
    restore_on_exit: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        return cls(
            mode=RouteMode(data.get("mode", RouteMode.FORWARD.value)),
            listen_host=str(data.get("listen_host", "127.0.0.1")),
            listen_port=int(data.get("listen_port", 17891)),
            upstream_host=str(data.get("upstream_host", "127.0.0.1")),
            upstream_port=int(data.get("upstream_port", 7888)),
            upstream_protocol=normalize_upstream_protocol(str(data.get("upstream_protocol", "http"))),
            rules=[Rule.from_dict(item) for item in data.get("rules", [])],
            start_with_windows=bool(data.get("start_with_windows", True)),
            startup_configured=bool(data.get("startup_configured", False)),
            # Versions before 1.3 stored False but did not expose this setting.
            # Treat such files as unconfigured so the new documented default
            # (close to tray) is applied once during upgrade.
            minimize_to_tray=(
                bool(data.get("minimize_to_tray", True))
                if "start_with_windows" in data
                else True
            ),
            restore_on_exit=bool(data.get("restore_on_exit", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        data["rules"] = [rule.to_dict() for rule in self.rules]
        return data


@dataclass(slots=True)
class RouteDecision:
    target: RouteTarget
    matched_rule: Rule | None
    process_path: str
    host: str


@dataclass(slots=True)
class ActivityRecord:
    timestamp: str
    process_name: str
    process_path: str
    host: str
    port: int
    target: RouteTarget
    matched_rule: str = ""
    status: str = "connected"
    detail: str = ""

    @classmethod
    def now(cls, **kwargs: Any) -> "ActivityRecord":
        return cls(timestamp=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), **kwargs)


@dataclass(slots=True)
class IpIdentity:
    ip: str
    country: str
    region: str
    city: str
    isp: str
    source: str
    checked_at: str
    route: RouteTarget
    error: str = ""

    @property
    def location(self) -> str:
        return " / ".join(part for part in (self.country, self.region, self.city) if part) or "未知"


def display_process_name(path: str) -> str:
    return Path(path).name if path else "未知进程"
