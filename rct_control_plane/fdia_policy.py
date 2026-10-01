"""
Owner-defined policy for A in F = D^I x A (Round 54).

The Architect's definition of A: the accountable human who designs, decides and signs off. A = 0 means nobody
took responsibility, so F = 0. The TypeScript engine (packages/shared/src/fdia-core.ts) lets the owner write
that responsibility down as rules: which actions are allowed, which need a human signature (and from whom), which
need two, which paths are off limits, which roles may ask. The Python runtime had only a per-tool A for the shell
and the two write tools. This module is the Python half, with the same schema and the same precedence, plus two
things the runtime can enforce that a stateless worker cannot: the signature goes through approvals.py (Ed25519, by
an approver key that has the required role, two distinct keys for dual sign-off) and a rule may require a SignedAI
jury (`jury_tier`) before the action runs.

File: DELENTIA_FDIA_POLICY or ~/.delentia/fdia_policy.json. No file = no policy = the built-in behaviour of before
(the 12 risky tools are gated, writes always need a signature). With a file, EVERY tool call is judged.

Precedence (same as TypeScript, plus one stricter rule):
  1. blocked_action_patterns             A = 0, final (TypeScript only checks these when no rules exist)
  2. rules whose intent_patterns match   the MOST restrictive wins (REQUIRE_HUMAN_SIGNATURE > CONDITIONAL > ALLOW),
                                         then the earlier rule. A rule with allowed_roles refuses other roles.
  3. require_human_dual_signoff          two signatures from distinct approver keys
  4. nothing matched                     default_fallback_A (0 = zero trust: the action is not registered, so no one
                                         can sign for it; the owner must add a rule)
The policy can only TIGHTEN the built-in floor (path safety, key-file names, the 0.5 threshold, "writes always need a
human"): the loop uses min(built-in A, policy A) and max(built-in threshold, policy threshold).

Roles are looked up from the identity the SERVER attached to the episode (the namespace: an API user, a gateway
sender), never from the request body, which the caller controls. `roles.principals` maps identity -> role.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

POLICY_ENV = "DELENTIA_FDIA_POLICY"
ACTION_TYPES = ("ALLOW", "CONDITIONAL", "REQUIRE_HUMAN_SIGNATURE")
_SEVERITY = {"ALLOW": 0, "CONDITIONAL": 1, "REQUIRE_HUMAN_SIGNATURE": 2}
RISK_LEVELS = ("LOW", "STRUCTURAL", "SYSTEMIC")      # the intent compiler's RiskProfile
JURY_TIERS = ("tier_s", "tier_4", "tier_6", "tier_7_regional", "tier_8")
MAX_RULES = 200
MAX_PATTERNS = 100
MAX_PATTERN_CHARS = 120
MAX_TEXT_CHARS = 400
_RULE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")
_ROLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\- ]{0,47}$")
_ARG_VALUE_CAP = 4000


def policy_path() -> Path:
    override = os.environ.get(POLICY_ENV)
    return Path(override) if override else Path.home() / ".delentia" / "fdia_policy.json"


@dataclass
class Rule:
    rule_id: str
    intent_patterns: List[str]
    action_type: str = "ALLOW"
    description: str = ""
    assigned_A: float = 1.0
    require_human_confirmation: bool = False
    denied_paths: List[str] = field(default_factory=list)
    allowed_roles: List[str] = field(default_factory=list)
    human_approver_role: List[str] = field(default_factory=list)
    required_signatures: int = 1
    jury_tier: str = ""


@dataclass
class Policy:
    version: str = "1.0.0"
    policy_id: str = "owner-policy"
    policy_name: str = "Owner policy"
    default_fallback_A: float = 0.0
    custom_safety_threshold: float = 0.5
    rules: List[Rule] = field(default_factory=list)
    blocked_action_patterns: List[str] = field(default_factory=list)
    require_human_dual_signoff: List[str] = field(default_factory=list)
    default_role: str = "developer"
    principals: Dict[str, str] = field(default_factory=dict)
    jury_by_risk: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["roles"] = {"default_role": data.pop("default_role"), "principals": data.pop("principals")}
        return data

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

    def role_for(self, principal: str) -> str:
        return self.principals.get(principal) or self.default_role


@dataclass
class Evaluation:
    A: float
    reason: str
    rule_id: str
    action_type: str
    needs_signature: bool = False
    required_signatures: int = 1
    approver_roles: List[str] = field(default_factory=list)
    jury_tier: str = ""
    role: str = ""
    matched_rules: List[str] = field(default_factory=list)
    policy_digest: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------ patterns

def _forms(tool_name: str) -> List[str]:
    """`delentia_write_repo_file` is matched as itself and as `write_repo_file`, so a policy written with the
    short names the TypeScript policy uses (write_*, read_*) applies here too."""
    lowered = tool_name.lower()
    short = lowered[len("delentia_"):] if lowered.startswith("delentia_") else lowered
    return [lowered, short] if short != lowered else [lowered]


def matches_tool(tool_name: str, pattern: str) -> bool:
    pat = pattern.strip().lower()
    return bool(pat) and any(fnmatch.fnmatchcase(form, pat) for form in _forms(tool_name))


def _normal(value: str) -> str:
    return value.replace("\\", "/").lower()


def _tails(path: str) -> List[str]:
    parts = [p for p in path.split("/") if p not in ("", ".")]
    return ["/".join(parts[i:]) for i in range(len(parts))] or [path]


def path_is_denied(value: str, pattern: str) -> bool:
    """A denied-path pattern against one string. `.env` denies `.env`, `app/.env` and `.env.local`'s directory
    entry only by whole segment, not `environment.py`; `.git/*` denies anything under a `.git` directory;
    `*.pem` denies any file ending in .pem; `/etc/*` denies absolute /etc paths."""
    pat = _normal(pattern.strip())
    if not pat:
        return False
    text = _normal(value)
    wild = any(c in pat for c in "*?[")
    for tail in _tails(text) + [text]:
        if wild and fnmatch.fnmatchcase(tail, pat):
            return True
        if not wild and (tail == pat or tail.startswith(pat.rstrip("/") + "/")):
            return True
    if not wild and pat.startswith(".") and "/" not in pat:
        base = text.rsplit("/", 1)[-1]
        return base == pat or base.startswith(pat + ".")                 # .env -> .env.local, .env.production
    return False


def _arg_strings(tool_args: Dict[str, Any]) -> List[str]:
    values: List[str] = []

    def walk(item: Any, depth: int = 0) -> None:
        if depth > 4:
            return
        if isinstance(item, str):
            values.append(item[:_ARG_VALUE_CAP])
        elif isinstance(item, dict):
            for v in item.values():
                walk(v, depth + 1)
        elif isinstance(item, (list, tuple)):
            for v in item[:50]:
                walk(v, depth + 1)

    walk(tool_args)
    expanded: List[str] = []
    for v in values:
        expanded.append(v)
        if " " in v or "\t" in v:                                        # a shell command: each word may be a path
            expanded.extend(t.strip("'\"") for t in re.split(r"\s+", v) if t)
    return expanded


def violates_denied_paths(tool_args: Dict[str, Any], patterns: List[str]) -> Optional[str]:
    for value in _arg_strings(tool_args):
        for pattern in patterns:
            if path_is_denied(value, pattern):
                return pattern
    return None


# ------------------------------------------------------------------ validation

def _clean_list(raw: Any, field_name: str, errors: List[str], limit: int = MAX_PATTERNS, chars: int = MAX_PATTERN_CHARS) -> List[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        errors.append(f"{field_name} must be a list of strings")
        return []
    if len(raw) > limit:
        errors.append(f"{field_name} has {len(raw)} entries (limit {limit})")
    items = [x.strip() for x in raw[:limit] if x.strip()]
    for item in items:
        if len(item) > chars:
            errors.append(f"{field_name}: entry longer than {chars} characters")
    return [x[:chars] for x in items]


def _number(raw: Any, name: str, errors: List[str], default: float, low: float = 0.0, high: float = 1.0) -> float:
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not low <= float(raw) <= high:
        errors.append(f"{name} must be a number between {low} and {high}")
        return default
    return float(raw)


def validate_policy(data: Any) -> Tuple[Optional[Policy], List[str]]:
    """(policy, []) or (None, [errors]). Unknown fields are ignored (the TypeScript schema passes them through)."""
    errors: List[str] = []
    if not isinstance(data, dict):
        return None, ["the policy must be a JSON object"]
    rules: List[Rule] = []
    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        errors.append("rules must be a list")
        raw_rules = []
    if len(raw_rules) > MAX_RULES:
        errors.append(f"too many rules ({len(raw_rules)}, limit {MAX_RULES})")
    seen: set = set()
    for index, raw in enumerate(raw_rules[:MAX_RULES]):
        label = f"rules[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{label} must be an object")
            continue
        rule_id = str(raw.get("rule_id", "")).strip()
        if not _RULE_ID.match(rule_id):
            errors.append(f"{label}.rule_id must be 1-64 letters, digits, - _ .")
        elif rule_id in seen:
            errors.append(f"{label}.rule_id {rule_id!r} is used twice")
        seen.add(rule_id)
        action = str(raw.get("action_type", "ALLOW")).strip().upper()
        if action not in ACTION_TYPES:
            errors.append(f"{label}.action_type must be one of {', '.join(ACTION_TYPES)}")
            action = "ALLOW"
        patterns = _clean_list(raw.get("intent_patterns"), f"{label}.intent_patterns", errors)
        if not patterns:
            errors.append(f"{label}.intent_patterns needs at least one pattern (e.g. read_*)")
        roles = _clean_list(raw.get("allowed_roles"), f"{label}.allowed_roles", errors, 30, 48)
        approvers = _clean_list(raw.get("human_approver_role"), f"{label}.human_approver_role", errors, 30, 48)
        for role in roles + approvers:
            if role != "*" and not _ROLE.match(role):
                errors.append(f"{label}: role {role!r} has characters that are not allowed")
        signatures = raw.get("required_signatures", 1)
        if isinstance(signatures, bool) or not isinstance(signatures, int) or not 1 <= signatures <= 3:
            errors.append(f"{label}.required_signatures must be 1, 2 or 3")
            signatures = 1
        jury = str(raw.get("jury_tier", "") or "").strip().lower()
        if jury and jury not in JURY_TIERS:
            errors.append(f"{label}.jury_tier must be one of {', '.join(JURY_TIERS)} or empty")
            jury = ""
        needs_signature = action == "REQUIRE_HUMAN_SIGNATURE" or bool(raw.get("require_human_confirmation"))
        if signatures > 1 and not needs_signature:
            errors.append(f"{label}: required_signatures above 1 only makes sense with REQUIRE_HUMAN_SIGNATURE")
        rules.append(Rule(
            rule_id=rule_id, intent_patterns=patterns, action_type=action,
            description=str(raw.get("description", ""))[:MAX_TEXT_CHARS],
            assigned_A=_number(raw.get("assigned_A"), f"{label}.assigned_A", errors, 1.0),
            require_human_confirmation=bool(raw.get("require_human_confirmation", False)),
            denied_paths=_clean_list(raw.get("denied_paths"), f"{label}.denied_paths", errors),
            allowed_roles=roles, human_approver_role=approvers, required_signatures=signatures, jury_tier=jury))
    roles_block = data.get("roles") if isinstance(data.get("roles"), dict) else {}
    principals_raw = roles_block.get("principals", {}) if isinstance(roles_block, dict) else {}
    principals: Dict[str, str] = {}
    if isinstance(principals_raw, dict):
        for who, role in list(principals_raw.items())[:500]:
            if isinstance(who, str) and isinstance(role, str) and _ROLE.match(role.strip()) and 0 < len(who) <= 128:
                principals[who] = role.strip()
            else:
                errors.append("roles.principals: each identity maps to a role name")
                break
    elif principals_raw:
        errors.append("roles.principals must be an object")
    default_role = str(roles_block.get("default_role", "developer")).strip() if isinstance(roles_block, dict) else "developer"
    if not _ROLE.match(default_role):
        errors.append("roles.default_role is not a valid role name")
        default_role = "developer"
    jury_by_risk_raw = data.get("jury_by_risk", {})
    jury_by_risk: Dict[str, str] = {}
    if isinstance(jury_by_risk_raw, dict):
        for risk, tier in jury_by_risk_raw.items():
            if str(risk).upper() in RISK_LEVELS and str(tier).lower() in JURY_TIERS:
                jury_by_risk[str(risk).upper()] = str(tier).lower()
            elif tier:
                errors.append("jury_by_risk maps LOW, STRUCTURAL or SYSTEMIC to a tier name")
                break
    elif jury_by_risk_raw:
        errors.append("jury_by_risk must be an object")
    policy = Policy(
        version=str(data.get("version", "1.0.0"))[:20], policy_id=str(data.get("policy_id", "owner-policy"))[:64],
        policy_name=str(data.get("policy_name", "Owner policy"))[:120],
        default_fallback_A=_number(data.get("default_fallback_A"), "default_fallback_A", errors, 0.0),
        custom_safety_threshold=_number(data.get("custom_safety_threshold"), "custom_safety_threshold", errors, 0.5),
        rules=rules, blocked_action_patterns=_clean_list(data.get("blocked_action_patterns"), "blocked_action_patterns", errors),
        require_human_dual_signoff=_clean_list(data.get("require_human_dual_signoff"), "require_human_dual_signoff", errors),
        default_role=default_role, principals=principals, jury_by_risk=jury_by_risk)
    return (None, errors) if errors else (policy, [])


def load_policy(path: Optional[Path] = None) -> Optional[Policy]:
    """The active policy or None when no file exists. A file that cannot be read or fails validation raises: a
    broken policy must never silently turn into no policy."""
    target = path or policy_path()
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read the FDIA policy {target}: {exc}") from exc
    policy, errors = validate_policy(data)
    if policy is None:
        raise ValueError(f"the FDIA policy {target} is invalid: " + "; ".join(errors[:5]))
    return policy


def save_policy(policy: Policy, path: Optional[Path] = None) -> Path:
    target = path or policy_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".fdia_policy.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(policy.to_dict(), handle, indent=2, ensure_ascii=False)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return target


# ------------------------------------------------------------------ evaluation

def evaluate(policy: Policy, tool_name: str, tool_args: Optional[Dict[str, Any]] = None, *, principal: str = "",
             approved: bool = False) -> Evaluation:
    """A for one tool call. `approved` means the human signatures the rule asks for are already verified (the
    resume path): the signature requirement is then satisfied, but a blocked pattern, a denied path or a refused
    role still stops the call, because a signature may not authorise what the owner forbade."""
    args = tool_args or {}
    role = policy.role_for(principal)
    digest = policy.digest()

    def verdict(A: float, reason: str, rule_id: str, action_type: str, **extra: Any) -> Evaluation:
        return Evaluation(A=A, reason=reason, rule_id=rule_id, action_type=action_type, role=role, policy_digest=digest, **extra)

    for pattern in policy.blocked_action_patterns:
        if matches_tool(tool_name, pattern):
            return verdict(0.0, f"{tool_name} matches the forbidden pattern {pattern!r}", "BLOCKED_ACTION_PATTERN", "BLOCKED")

    matched = [r for r in policy.rules if any(matches_tool(tool_name, p) for p in r.intent_patterns)]
    if matched:
        rule = max(enumerate(matched), key=lambda pair: (_SEVERITY[pair[1].action_type], -pair[0]))[1]
        names = [r.rule_id for r in matched]
        if rule.allowed_roles and role not in rule.allowed_roles and "*" not in rule.allowed_roles:
            return verdict(0.0, f"role {role!r} may not do this under rule {rule.rule_id} (allowed: {', '.join(rule.allowed_roles)})",
                           "ROLE_DENIED", rule.action_type, matched_rules=names)
        if rule.denied_paths:
            hit = violates_denied_paths(args, rule.denied_paths)
            if hit:
                return verdict(0.0, f"an argument matches the restricted path {hit!r} under rule {rule.rule_id}",
                               rule.rule_id, rule.action_type, matched_rules=names)
        dual = any(matches_tool(tool_name, p) for p in policy.require_human_dual_signoff)
        needs_signature = rule.action_type == "REQUIRE_HUMAN_SIGNATURE" or rule.require_human_confirmation or dual
        signatures = max(rule.required_signatures, 2 if dual else 1)
        if needs_signature and not approved:
            return verdict(0.0, f"{rule.rule_id}: needs {signatures} human signature(s)" + (f" from {', '.join(rule.human_approver_role)}" if rule.human_approver_role else ""),
                           rule.rule_id, rule.action_type, needs_signature=True, required_signatures=signatures,
                           approver_roles=list(rule.human_approver_role), jury_tier=rule.jury_tier, matched_rules=names)
        return verdict(rule.assigned_A if rule.action_type != "REQUIRE_HUMAN_SIGNATURE" else 1.0,
                       rule.description or f"permitted under rule {rule.rule_id}", rule.rule_id, rule.action_type,
                       required_signatures=signatures, approver_roles=list(rule.human_approver_role),
                       jury_tier=rule.jury_tier, matched_rules=names)

    dual = any(matches_tool(tool_name, p) for p in policy.require_human_dual_signoff)
    if dual:
        if not approved:
            return verdict(0.0, f"{tool_name} needs two human signatures", "DUAL_SIGNOFF", "REQUIRE_HUMAN_SIGNATURE",
                           needs_signature=True, required_signatures=2)
        return verdict(1.0, "dual sign-off satisfied", "DUAL_SIGNOFF", "REQUIRE_HUMAN_SIGNATURE", required_signatures=2)

    if policy.default_fallback_A <= 0:
        return verdict(0.0, f"{tool_name} is not registered in the owner policy (zero trust: add a rule for it)",
                       "ZERO_TRUST_FALLBACK", "BLOCKED")
    return verdict(policy.default_fallback_A, "no rule matched; the policy's fallback A applies", "FALLBACK_ALLOW", "ALLOW")


# ------------------------------------------------------------------ starting points

def template(name: str, tool_names: List[str]) -> Dict[str, Any]:
    """Starter policies. `tool_names` are the real tool names, so every tool is classified and the zero-trust
    fallback never blocks a tool the owner simply forgot."""
    readers = [t for t in tool_names if any(k in t for k in ("read", "search", "list", "recall", "query", "get_", "expand", "status", "stats", "estimate", "verify"))]
    writers = [t for t in tool_names if t not in readers]
    strict = name == "strict"
    special = {"run_sandboxed_command", "synthesize_function", "write_repo_file", "patch_repo_file", "save_exchange_file"}
    rules: List[Dict[str, Any]] = [
        {"rule_id": "R-READ", "description": "Reading and looking things up is allowed without friction.", "intent_patterns": sorted(readers) or ["read_*"], "action_type": "ALLOW", "assigned_A": 1},
        {"rule_id": "R-WRITE-FILES", "description": "Changing files needs a human signature and may never touch secrets or version control.",
         "intent_patterns": ["write_repo_file", "patch_repo_file", "save_exchange_file"], "action_type": "REQUIRE_HUMAN_SIGNATURE",
         "denied_paths": [".env", ".git/*", "*.pem", "*.key", "id_rsa*", "/etc/*", "production.config.*"], "required_signatures": 1},
        {"rule_id": "R-SHELL-AND-CODE", "description": "Running commands or generated code needs a signature, and the jury must agree first." if strict else "Running commands or generated code needs a signature.",
         "intent_patterns": ["run_sandboxed_command", "synthesize_function"], "action_type": "REQUIRE_HUMAN_SIGNATURE",
         "denied_paths": [".env", ".git/*", "*.pem", "*.key", "id_rsa*", "/etc/*"],
         "jury_tier": "tier_4" if strict else "", "required_signatures": 1},
        {"rule_id": "R-OTHER-ACTIONS", "description": "Everything else an agent can do (network, worktrees, subagents, scheduling) is allowed but audited.",
         "intent_patterns": sorted(t for t in writers if _forms(t)[-1] not in special) or ["*"],
         "action_type": "CONDITIONAL" if strict else "ALLOW", "assigned_A": 1},
    ]
    return {
        "version": "1.0.0", "policy_id": f"template-{name}", "policy_name": "Strict starter" if strict else "Balanced starter",
        "default_fallback_A": 0, "custom_safety_threshold": 0.6 if strict else 0.5, "rules": rules,
        "blocked_action_patterns": ["*drop_database*", "*export_credentials*", "*exfiltrate*"],
        "require_human_dual_signoff": ["deploy_to_production", "grant_admin_privilege"] if strict else [],
        "roles": {"default_role": "developer", "principals": {}}, "jury_by_risk": {"SYSTEMIC": "tier_4"} if strict else {},
    }
