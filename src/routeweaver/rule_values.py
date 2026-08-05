from __future__ import annotations

import re

from .models import RuleKind
from .policy import normalize_app, normalize_host


def normalize_rule_value(kind: RuleKind, raw_value: str) -> str:
    value = str(raw_value).strip().strip('"')
    if not value:
        raise ValueError("匹配值不能为空")
    if kind is RuleKind.APP:
        if not value.casefold().endswith(".exe") and not any(char in value for char in "*?"):
            raise ValueError("应用规则应填写 EXE 路径、EXE 名称或带通配符的程序匹配值")
        return value

    value = re.sub(r"^https?://", "", value, flags=re.IGNORECASE).split("/", 1)[0]
    if value.count(":") == 1:
        host, port = value.rsplit(":", 1)
        if port.isdigit():
            value = host
    wildcard = value.startswith("*.")
    host = normalize_host(value[2:] if wildcard else value)
    if not host or " " in host:
        raise ValueError("网站规则应填写有效域名，例如 example.com 或 *.example.com")
    return "*." + host if wildcard else host


def rule_value_key(kind: RuleKind, value: str) -> str:
    if kind is RuleKind.APP:
        return normalize_app(value)
    return normalize_rule_value(kind, value).casefold()
