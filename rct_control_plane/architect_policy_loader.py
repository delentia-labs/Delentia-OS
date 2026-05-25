"""
Architect Policy Loader — YAML → PolicyRule Objects

Loads architect-level policy definitions from YAML files and converts
them into PolicyRule objects that the PolicyEvaluator can consume.

YAML schema (architect_policy.yaml):
    policies:
      - name: "block-systemic-risk"
        description: "Block SYSTEMIC risk intents without approval"
        scope: "intent"
        priority: "critical"
        conditions:
          - field: "risk_level"
            operator: "=="
            value: "SYSTEMIC"
            description: "Systemic risk requires approval"
        action: "require_approval"
        approver_roles:
          - "senior-engineer"
          - "security-team"
        timeout_seconds: 3600
        channel: "slack"
        enabled: true

Usage:
    loader = ArchitectPolicyLoader()
    rules = loader.load("config/architect_policy.yaml")
    evaluator.add_rules(rules)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

from rct_control_plane.policy_language import (
    ConditionOperator,
    PolicyAction,
    PolicyCondition,
    PolicyPriority,
    PolicyRule,
    PolicyScope,
)


# ---------------------------------------------------------------------------
# Schema validation helpers
# ---------------------------------------------------------------------------

_VALID_SCOPES = {s.value for s in PolicyScope}
_VALID_PRIORITIES = {p.value for p in PolicyPriority}
_VALID_ACTIONS = {a.value for a in PolicyAction}
_VALID_OPERATORS = {o.value for o in ConditionOperator}


class PolicyLoadError(Exception):
    """Raised when architect policy YAML is invalid or unreadable."""


# ---------------------------------------------------------------------------
# ArchitectPolicyLoader
# ---------------------------------------------------------------------------

class ArchitectPolicyLoader:
    """
    Load and validate architect policy definitions from YAML files.

    Converts YAML policy definitions into PolicyRule objects compatible
    with the existing PolicyEvaluator.
    """

    def load(self, path: str | Path) -> List[PolicyRule]:
        """
        Load all policy rules from a YAML file.

        Args:
            path: Path to architect_policy.yaml

        Returns:
            List of PolicyRule objects ready for PolicyEvaluator

        Raises:
            PolicyLoadError: If file is invalid or cannot be parsed
        """
        path = Path(path)
        if not path.exists():
            raise PolicyLoadError(f"Policy file not found: {path}")

        raw = self._read_file(path)
        return self._parse(raw, source=str(path))

    def load_from_string(self, yaml_text: str, source: str = "<string>") -> List[PolicyRule]:
        """
        Load policy rules from a YAML string.

        Args:
            yaml_text: YAML content as string
            source: Source label for error messages

        Returns:
            List of PolicyRule objects
        """
        raw = self._parse_yaml(yaml_text, source)
        return self._parse(raw, source=source)

    def load_from_dict(self, data: Dict[str, Any]) -> List[PolicyRule]:
        """Load policy rules from an already-parsed dict."""
        return self._parse(data, source="<dict>")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_file(self, path: Path) -> Dict[str, Any]:
        """Read and parse YAML file."""
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PolicyLoadError(f"Cannot read policy file {path}: {exc}") from exc
        return self._parse_yaml(content, source=str(path))

    def _parse_yaml(self, content: str, source: str) -> Dict[str, Any]:
        """Parse YAML string into dict, with JSON fallback."""
        if _HAS_YAML:
            try:
                data = _yaml.safe_load(content)
            except _yaml.YAMLError as exc:
                raise PolicyLoadError(
                    f"YAML parse error in {source}: {exc}"
                ) from exc
        else:
            # Fallback: try JSON (useful if PyYAML not installed)
            try:
                data = json.loads(content)
            except json.JSONDecodeError as exc:
                raise PolicyLoadError(
                    f"Cannot parse {source}: PyYAML not installed and JSON parse failed: {exc}"
                ) from exc

        if not isinstance(data, dict):
            raise PolicyLoadError(
                f"Expected top-level mapping in {source}, got {type(data).__name__}"
            )
        return data

    def _parse(self, data: Dict[str, Any], source: str) -> List[PolicyRule]:
        """Convert raw dict into a list of PolicyRule objects."""
        policies_raw = data.get("policies", [])
        if not isinstance(policies_raw, list):
            raise PolicyLoadError(
                f"'policies' must be a list in {source}"
            )

        rules: List[PolicyRule] = []
        for idx, entry in enumerate(policies_raw):
            label = f"{source}[{idx}]"
            rules.append(self._build_rule(entry, label))

        return rules

    def _build_rule(self, entry: Dict[str, Any], label: str) -> PolicyRule:
        """Convert a single policy dict entry into a PolicyRule."""
        if not isinstance(entry, dict):
            raise PolicyLoadError(
                f"Policy entry {label} must be a mapping, got {type(entry).__name__}"
            )

        # Required: name
        name = str(entry.get("name", "")).strip()
        if not name:
            raise PolicyLoadError(f"Policy {label} is missing required field 'name'")

        # scope
        scope_raw = str(entry.get("scope", PolicyScope.INTENT.value)).lower()
        if scope_raw not in _VALID_SCOPES:
            raise PolicyLoadError(
                f"Policy '{name}' has invalid scope '{scope_raw}'. "
                f"Valid: {sorted(_VALID_SCOPES)}"
            )
        scope = PolicyScope(scope_raw)

        # priority
        priority_raw = str(entry.get("priority", PolicyPriority.MEDIUM.value)).lower()
        if priority_raw not in _VALID_PRIORITIES:
            raise PolicyLoadError(
                f"Policy '{name}' has invalid priority '{priority_raw}'. "
                f"Valid: {sorted(_VALID_PRIORITIES)}"
            )
        priority = PolicyPriority(priority_raw)

        # action
        action_raw = str(entry.get("action", PolicyAction.LOG.value)).lower()
        if action_raw not in _VALID_ACTIONS:
            raise PolicyLoadError(
                f"Policy '{name}' has invalid action '{action_raw}'. "
                f"Valid: {sorted(_VALID_ACTIONS)}"
            )
        action = PolicyAction(action_raw)

        # conditions
        conditions = self._build_conditions(
            entry.get("conditions", []), policy_name=name
        )

        # action_metadata (approver_roles, timeout_seconds, channel, etc.)
        action_metadata: Dict[str, Any] = {}
        if "approver_roles" in entry:
            action_metadata["approver_roles"] = list(entry["approver_roles"])
        if "timeout_seconds" in entry:
            action_metadata["timeout_seconds"] = int(entry["timeout_seconds"])
        if "channel" in entry:
            action_metadata["channel"] = str(entry["channel"])
        if "notification_message" in entry:
            action_metadata["notification_message"] = str(entry["notification_message"])

        return PolicyRule(
            rule_id=str(entry.get("id", uuid4())),
            name=name,
            description=str(entry.get("description", "")),
            scope=scope,
            priority=priority,
            conditions=conditions,
            action=action,
            action_metadata=action_metadata,
            enabled=bool(entry.get("enabled", True)),
            created_by=str(entry.get("created_by", "architect_policy_loader")),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    def _build_conditions(
        self, raw_conditions: List[Any], policy_name: str
    ) -> List[PolicyCondition]:
        """Convert raw condition dicts into PolicyCondition objects."""
        if not isinstance(raw_conditions, list):
            raise PolicyLoadError(
                f"Policy '{policy_name}' conditions must be a list"
            )

        conditions: List[PolicyCondition] = []
        for idx, cond_raw in enumerate(raw_conditions):
            if not isinstance(cond_raw, dict):
                raise PolicyLoadError(
                    f"Policy '{policy_name}' condition[{idx}] must be a mapping"
                )

            field_name = str(cond_raw.get("field", "")).strip()
            if not field_name:
                raise PolicyLoadError(
                    f"Policy '{policy_name}' condition[{idx}] missing 'field'"
                )

            operator_raw = str(cond_raw.get("operator", "=="))
            if operator_raw not in _VALID_OPERATORS:
                raise PolicyLoadError(
                    f"Policy '{policy_name}' condition[{idx}] has invalid operator "
                    f"'{operator_raw}'. Valid: {sorted(_VALID_OPERATORS)}"
                )
            operator = ConditionOperator(operator_raw)

            value = cond_raw.get("value")
            description = cond_raw.get("description")

            conditions.append(
                PolicyCondition(
                    field=field_name,
                    operator=operator,
                    value=value,
                    description=description,
                )
            )

        return conditions
