from __future__ import annotations

from pathlib import Path

from .models import ActivityRecord, AppConfig, Rule, RuleKind
from .policy import PolicyEngine


def activity_candidate(record: ActivityRecord, kind: RuleKind) -> tuple[str, str]:
    if kind is RuleKind.DOMAIN:
        return record.host, record.host
    value = record.process_path or record.process_name
    return value, record.process_name or Path(value).stem


def matching_rule_index(config: AppConfig, record: ActivityRecord, kind: RuleKind) -> int | None:
    """Find a rule covering the selected activity, including disabled entries."""
    process = record.process_path or record.process_name
    for index, rule in enumerate(config.rules):
        if rule.kind is not kind:
            continue
        enabled_copy = Rule(rule.kind, rule.value, True, rule.label)
        probe_config = AppConfig(mode=config.mode, rules=[enabled_copy])
        if PolicyEngine(probe_config).matching_rule(process, record.host):
            return index
    return None
