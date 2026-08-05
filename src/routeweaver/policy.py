from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from .models import AppConfig, RouteDecision, RouteMode, RouteTarget, Rule, RuleKind


def normalize_host(host: str) -> str:
    value = host.strip().rstrip(".").lower()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    try:
        return value.encode("idna").decode("ascii")
    except UnicodeError:
        return value


def normalize_app(path: str) -> str:
    return os.path.normcase(os.path.normpath(path.strip().strip('"'))) if path else ""


def _domain_matches(pattern: str, host: str) -> bool:
    pattern = normalize_host(re.sub(r"^https?://", "", pattern).split("/", 1)[0])
    if pattern.startswith("*."):
        bare = pattern[2:]
        return host == bare or host.endswith("." + bare)
    if "*" in pattern or "?" in pattern:
        return fnmatch.fnmatch(host, pattern)
    return host == pattern or host.endswith("." + pattern)


def _app_matches(pattern: str, process_path: str) -> bool:
    pattern_n = normalize_app(pattern)
    path_n = normalize_app(process_path)
    if not path_n:
        return False
    if any(char in pattern_n for char in "*?"):
        return fnmatch.fnmatch(path_n, pattern_n) or fnmatch.fnmatch(Path(path_n).name, pattern_n)
    if "\\" not in pattern_n and "/" not in pattern_n:
        return Path(path_n).name == pattern_n
    return path_n == pattern_n


class PolicyEngine:
    def __init__(self, config: AppConfig):
        self.config = config

    def update(self, config: AppConfig) -> None:
        self.config = config

    def matching_rule(self, process_path: str, host: str) -> Rule | None:
        host_n = normalize_host(host)
        for rule in self.config.rules:
            if not rule.enabled:
                continue
            if rule.kind is RuleKind.DOMAIN and _domain_matches(rule.value, host_n):
                return rule
            if rule.kind is RuleKind.APP and _app_matches(rule.value, process_path):
                return rule
        return None

    def decide(self, process_path: str, host: str) -> RouteDecision:
        matched = self.matching_rule(process_path, host)
        if self.config.mode is RouteMode.FORWARD:
            target = RouteTarget.VPN if matched else RouteTarget.DIRECT
        else:
            target = RouteTarget.DIRECT if matched else RouteTarget.VPN
        return RouteDecision(target=target, matched_rule=matched, process_path=process_path, host=normalize_host(host))

