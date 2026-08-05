from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .ip_geo import lookup_identity
from .models import AppConfig, IpIdentity, RouteDecision, Rule, RuleKind
from .policy import PolicyEngine, normalize_host


@dataclass(slots=True)
class RuleProbeResult:
    rule: Rule
    decision: RouteDecision
    identity: IpIdentity
    process_context: str
    host_context: str

    @property
    def matched(self) -> bool:
        return self.decision.matched_rule is not None

    @property
    def success(self) -> bool:
        return self.matched and not self.identity.error and bool(self.identity.ip)


def probe_host_for_rule(value: str) -> str:
    host = re.sub(r"^https?://", "", value.strip(), flags=re.IGNORECASE).split("/", 1)[0]
    if host.startswith("*."):
        host = "routeweaver-probe." + host[2:]
    else:
        host = host.replace("*", "routeweaver-probe").replace("?", "x")
    return normalize_host(host)


def probe_rule(
    config: AppConfig,
    rule: Rule,
    identity_lookup: Callable[..., IpIdentity] = lookup_identity,
) -> RuleProbeResult:
    if not rule.enabled:
        raise ValueError("停用的规则不能执行出口验证")
    if rule.kind is RuleKind.APP:
        process_context = rule.value
        host_context = "ipwho.is"
    else:
        process_context = "RouteWeaverRuleProbe.exe"
        host_context = probe_host_for_rule(rule.value)
    decision = PolicyEngine(config).decide(process_context, host_context)
    if decision.matched_rule is None:
        raise ValueError("所选规则无法匹配生成的验证上下文，请检查规则格式")
    identity = identity_lookup(
        decision.target,
        config.upstream_host,
        config.upstream_port,
        upstream_protocol=config.upstream_protocol,
    )
    return RuleProbeResult(
        rule=rule,
        decision=decision,
        identity=identity,
        process_context=process_context,
        host_context=host_context,
    )

