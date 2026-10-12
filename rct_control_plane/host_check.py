"""
Round 55: is this machine ready to be the host? Answers before any host is rented.

`delentia host-check` reads the configuration the way the running server would and lists, per item, PASS / WARN / FAIL with what is wrong
and how to fix it. It changes nothing and sends nothing (an optional `--probe` makes one GET to the notary). The point is to find the
mistakes that cost the most on a public host - a shared token, an open sender list, a key sitting next to the agent, a secret pasted into
a config file - on the machine where they are free to fix.

What it cannot check, said plainly: TLS (that is the reverse proxy's job), whether the operating-system user separation for the notary
is real, and whether a remote service is trustworthy.

Apache 2.0 - Delentia Labs
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PASS, WARN, FAIL, INFO = "PASS", "WARN", "FAIL", "INFO"
MIN_TOKEN_CHARS = 24
KEY_LOOKING = re.compile(r"sk-or-[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9]{32,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[bp]-[A-Za-z0-9-]{10,}|ghp_[A-Za-z0-9]{30,}")

# channel -> (the variable that means "this channel has credentials here", allowlist variable, webhook secret variable or "")
CHANNELS = {
    "telegram": ("TELEGRAM_BOT_TOKEN", "DELENTIA_TELEGRAM_ALLOWED_SENDERS", ""),
    "discord": ("DISCORD_BOT_TOKEN", "DELENTIA_DISCORD_ALLOWED_SENDERS", ""),
    "slack": ("SLACK_BOT_TOKEN", "DELENTIA_SLACK_ALLOWED_SENDERS", ""),
    "line": ("LINE_CHANNEL_ACCESS_TOKEN", "DELENTIA_LINE_ALLOWED_SENDERS", "LINE_CHANNEL_SECRET"),
    "whatsapp": ("WHATSAPP_ACCESS_TOKEN", "DELENTIA_WHATSAPP_ALLOWED_SENDERS", "WHATSAPP_APP_SECRET"),
    "signal": ("SIGNAL_NUMBER", "DELENTIA_SIGNAL_ALLOWED_SENDERS", ""),
    "email": ("DELENTIA_EMAIL_PASSWORD", "DELENTIA_EMAIL_ALLOWED_SENDERS", ""),
}


@dataclass
class Check:
    id: str
    status: str
    title: str
    detail: str
    fix: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {"id": self.id, "status": self.status, "title": self.title, "detail": self.detail, "fix": self.fix}


def _home() -> Path:
    return Path(os.environ.get("DELENTIA_HOME") or (Path.home() / ".delentia"))


def _config_dir() -> Path:
    return Path.home() / ".delentia"


def _guard(check_id: str, title: str, fn: Callable[[], List[Check]]) -> List[Check]:
    """One broken check must not hide the others."""
    try:
        return fn()
    except Exception as exc:                                         # noqa: BLE001 - reported as a failed check
        return [Check(check_id, FAIL, title, f"the check itself failed: {type(exc).__name__}: {str(exc)[:200]}")]


# ------------------------------------------------------------------------------------------------ the checks

def check_api_auth(public: bool) -> List[Check]:
    from rct_control_plane import api_tokens
    out: List[Check] = []
    shared = os.environ.get("DELENTIA_API_TOKEN", "")
    try:
        entries = [e for e in api_tokens.load_entries() if not e.get("disabled")]
        file_error = ""
    except api_tokens.TokenFileError as exc:
        entries, file_error = [], str(exc)
    if file_error:
        out.append(Check("H01", FAIL, "API authentication", f"the per-person tokens file is unusable, so nobody can get in: {file_error}",
                         "repair or remove the file (`delentia tokens list`)"))
    elif entries or shared:
        weak = bool(shared) and len(shared) < MIN_TOKEN_CHARS and not entries
        out.append(Check("H01", FAIL if weak else PASS, "API authentication",
                         f"shared token is only {len(shared)} characters" if weak else
                         f"{len(entries)} per-person token(s)" + (" and a shared token" if shared else "") if entries else "a shared token is set",
                         f"use at least {MIN_TOKEN_CHARS} random characters" if weak else ""))
    else:
        out.append(Check("H01", FAIL if public else WARN, "API authentication",
                         "no DELENTIA_API_TOKEN and no per-person tokens: only loopback clients are accepted (fine on this machine, not on a host)",
                         "set DELENTIA_API_TOKEN and create a token per person with `delentia tokens create <name>`"))
    out.append(Check("H02", PASS if entries else WARN, "Identity per person",
                     f"{len(entries)} named token(s): namespace, memory and policy role come from the token" if entries else
                     "with one shared token every caller is the identity 'shared': a role in the policy is only a label",
                     "" if entries else "`delentia tokens create <name>` for each person"))
    return out


def check_approvers() -> List[Check]:
    from rct_control_plane import approvals
    keys = approvals.trusted_approver_keys()
    path = approvals._approvers_file()
    out: List[Check] = []
    if not keys:
        out.append(Check("H03", WARN, "Human approvers", "no approver key is trusted: nothing that needs a signature (writes, risky tools) can ever be approved",
                         "`delentia approvals keygen` on ANOTHER device, then put the public key in DELENTIA_APPROVER_PUBKEYS or approvers.json"))
    else:
        out.append(Check("H03", PASS, "Human approvers", f"{len(keys)} trusted approver key(s)"))
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "PRIVATE KEY" in text or '"private' in text.lower():
            out.append(Check("H04", FAIL, "Approver keys stay off this host", f"{path} contains private key material",
                             "keep approver private keys on the approver's own device; only public keys belong here"))
        else:
            out.append(Check("H04", PASS, "Approver keys stay off this host", "the approvers file holds public keys only"))
    return out


def check_audit_keys(probe: bool) -> List[Check]:
    from rct_control_plane import audit_chain
    out: List[Check] = []
    path = os.environ.get(audit_chain.SIGNING_KEY_ENV)
    if not path:
        out.append(Check("H05", WARN, "Audit signing key", "not set: episodes are signed with a throwaway key per process, so the audit trail cannot be re-verified later",
                         "`delentia audit-chain keygen` (outside the repository) and set DELENTIA_AUDIT_SIGNING_KEY"))
    else:
        p = Path(path).expanduser()
        repo = Path(__file__).resolve().parent.parent
        if not p.exists():
            out.append(Check("H05", FAIL, "Audit signing key", f"{p} does not exist"))
        elif repo in p.resolve().parents:
            out.append(Check("H05", FAIL, "Audit signing key", f"{p} is inside the repository the agent can read and write", "move it outside the repository"))
        else:
            try:
                audit_chain.load_signing_key()
                mode = p.stat().st_mode & 0o077 if os.name == "posix" else 0
                out.append(Check("H05", WARN if mode else PASS, "Audit signing key", "readable Ed25519 key outside the repository" + ("; group/other can read it" if mode else ""),
                                 "chmod 600" if mode else ""))
            except Exception as exc:                                  # noqa: BLE001
                out.append(Check("H05", FAIL, "Audit signing key", f"cannot load it: {exc}"))
    notary = os.environ.get("DELENTIA_NOTARY_URL")
    if notary:
        detail = f"records go to {notary}"
        status = PASS
        if probe:
            try:
                import httpx
                code = httpx.get(notary.rstrip("/") + "/health", timeout=3).status_code
                detail += f"; /health answered {code}"
                status = PASS if code == 200 else WARN
            except Exception as exc:                                  # noqa: BLE001
                detail += f"; not reachable ({type(exc).__name__}): the agent will stop (fail closed)"
                status = FAIL
        out.append(Check("H06", status, "Notary (tier A2)", detail))
    else:
        out.append(Check("H06", WARN, "Notary (tier A2)", "no notary: the audit key proves 'written by this host', not 'not written by the agent'",
                         "`delentia notary serve` as a different OS user, then DELENTIA_NOTARY_URL and DELENTIA_NOTARY_TOKEN"))
    out.append(_witness_check())
    return out


def _witness_check() -> Check:
    """H07: tier A3. One witness is one party to trust; a second, independent one means a host that is taken over must defeat both."""
    from rct_control_plane import audit_witness
    try:
        specs = audit_witness.specs_from_env()
    except (audit_witness.WitnessError, ValueError) as exc:
        return Check("H07", FAIL, "Anchoring (tier A3)", f"the witness list cannot be read ({exc}); nothing is anchored",
                     f"fix {audit_witness.WITNESSES_ENV} (a JSON list of {{type: http|git, key_id, ...}})")
    if not os.environ.get("DELENTIA_AUDIT_SIGNING_KEY"):
        return Check("H07", WARN, "Anchoring (tier A3)", "anchoring needs the audit signing key (DELENTIA_AUDIT_SIGNING_KEY) and none is set",
                     "`delentia audit-chain keygen`, then register the public key with every witness")
    kinds = {s.type for s in specs}
    if not specs:
        return Check("H07", WARN, "Anchoring (tier A3)", "not scheduled: a host that rewrites its whole log would not be noticed",
                     f"set {audit_witness.WITNESSES_ENV} (see the runbook), or DELENTIA_AUDIT_ANCHOR_URL and DELENTIA_AUDIT_ANCHOR_KEY_ID for the one HTTP witness")
    if len(specs) == 1:
        return Check("H07", WARN, "Anchoring (tier A3)", f"one witness ({specs[0].name}): its operator is one party you have to trust; a git witness on a remote this host cannot rewrite is the cheapest second one",
                     f"add a second entry to {audit_witness.WITNESSES_ENV}")
    if len(kinds) == 1:
        return Check("H07", WARN, "Anchoring (tier A3)", f"{len(specs)} witnesses but all of one kind ({next(iter(kinds))}): one failure mode can take them all",
                     "mix an http witness with a git witness")
    return Check("H07", PASS, "Anchoring (tier A3)", f"{len(specs)} independent witnesses ({', '.join(s.name for s in specs)}) receive the signed head")


def check_tenants(public: bool) -> List[Check]:
    """H22 (Round 62): who may use the Desk and the other owner-only routes when there is a token per person."""
    from rct_control_plane import api_tokens
    if not api_tokens.per_user_mode():
        return [Check("H22-tenants", INFO, "People and owners", "no per-person tokens: one shared token (or loopback) is the owner; nobody else is distinguished")]
    try:
        entries = [e for e in api_tokens.load_entries() if not e.get("disabled")]
    except api_tokens.TokenFileError as exc:
        return [Check("H22-tenants", FAIL, "People and owners", f"the tokens file cannot be used, so nobody gets in: {exc}")]
    owners = [e["name"] for e in entries if e.get("owner")]
    people = [e["name"] for e in entries if not e.get("owner")]
    if not owners and not os.environ.get("DELENTIA_API_TOKEN"):
        return [Check("H22-tenants", WARN, "People and owners", f"{len(people)} person token(s) and no owner: the Desk, the audit trail and the policy cannot be reached over the API",
                      "`delentia tokens owner <name>` for the person who runs this host")]
    return [Check("H22-tenants", PASS, "People and owners", f"{len(owners)} owner(s) ({', '.join(owners) or 'the shared token'}), {len(people)} ordinary person(s) limited to the agent, their own jobs, tasks, approvals and memory")]


def check_memory_log() -> List[Check]:
    """H23 (Round 67): is the memory history recorded, sealed per person (what makes erasure possible), and are the keys kept where the agent's file tools cannot read them?"""
    from rct_control_plane import memory_erasure, memory_eventlog
    if not memory_eventlog.enabled():
        return [Check("H23-memory-log", WARN, "Memory history", "the memory event log is off: revocation is a column, nothing can be replayed or anchored, a person's data cannot be erased",
                      "unset DELENTIA_MEMORY_EVENTLOG=off")]
    if not memory_erasure.sealing_enabled():
        return [Check("H23-memory-log", WARN, "Memory history", "the log is on but not sealed per person: its text is readable by anyone with the database, and a person cannot be erased from it",
                      "unset DELENTIA_MEMORY_SEAL=off (events written before sealing was on stay readable)")]
    keys = memory_erasure.keys_dir()
    repo = Path(__file__).resolve().parent.parent
    try:
        inside = repo in keys.resolve().parents or keys.resolve() == repo
    except OSError:
        inside = False
    if inside:
        return [Check("H23-memory-log", FAIL, "Memory history", f"the memory keys directory {keys} is inside the repository, where the agent's file tools can read it",
                      "set DELENTIA_MEMORY_KEYS_DIR to a folder outside the checkout, readable by the runtime's OS user only")]
    return [Check("H23-memory-log", PASS, "Memory history", f"the log is on and sealed per person; keys live in {keys} (a backup leaves them out unless `--include-keys`, so a restored backup cannot read the sealed history)")]


def check_envelope(public: bool) -> List[Check]:
    """H21 (Round 60): what stops the agent when nobody is watching, and who is told when it needs a person."""
    from rct_control_plane import envelope, owner_notify
    out: List[Check] = []
    state = envelope.paused()
    if state is not None:
        out.append(Check("H21-paused", WARN, "Pause switch", f"the agent is PAUSED ({state['by']}: {state['reason'] or 'no reason given'}): nothing will run until `delentia resume`",
                         "`delentia resume` (needs a signature when an approver key exists)"))
    lim = envelope.limits()
    if any(lim[k] for k in ("daily_usd", "daily_tokens", "user_daily_usd", "user_daily_tokens")):
        out.append(Check("H21-limits", PASS, "Spending limits", "a daily limit is set (envelope.py)"))
    else:
        out.append(Check("H21-limits", WARN if public else INFO, "Spending limits", "no daily money or token limit: only the per-episode cap bounds what a flood of requests can cost",
                         "set DELENTIA_DAILY_BUDGET_USD (or DELENTIA_DAILY_MAX_TOKENS) and DELENTIA_USER_DAILY_BUDGET_USD"))
    notify = owner_notify.status()
    if notify["targets"]:
        out.append(Check("H21-owner-alerts", PASS, "Owner alerts", f"{len(notify['targets'])} target(s) will be told when a signature is needed or something fails"))
    elif notify["configured"]:
        out.append(Check("H21-owner-alerts", FAIL if public else WARN, "Owner alerts", "DELENTIA_OWNER_NOTIFY names targets but none passes the allowlist rule: "
                         + "; ".join(f"{d['channel']}:{d['to']} ({d['why']})" for d in notify["dropped"]), "list the same person in that channel's DELENTIA_<CHANNEL>_ALLOWED_SENDERS by name"))
    else:
        out.append(Check("H21-owner-alerts", WARN if public else INFO, "Owner alerts", "nobody is told when the agent needs a signature: approvals wait silently until someone opens the Desk",
                         "set DELENTIA_OWNER_NOTIFY=telegram:<your id> (and list that id in DELENTIA_TELEGRAM_ALLOWED_SENDERS)"))
    return out


def check_channels(public: bool) -> List[Check]:
    out: List[Check] = []
    present = 0
    for name, (credential, allow_var, secret_var) in CHANNELS.items():
        if not os.environ.get(credential):
            continue
        present += 1
        allow = (os.environ.get(allow_var) or "").strip()
        if allow == "*":
            out.append(Check(f"H08-{name}", FAIL, f"Channel {name}", f"{allow_var}=* lets anyone who can reach the bot give the agent work",
                             "list the exact sender ids"))
        elif not allow:
            out.append(Check(f"H08-{name}", WARN, f"Channel {name}", f"credentials are set but {allow_var} is empty: nobody can send work (safe, but useless)",
                             f"set {allow_var} to the sender ids that may"))
        elif secret_var and not os.environ.get(secret_var):
            out.append(Check(f"H08-{name}", FAIL, f"Channel {name}", f"{secret_var} is missing, so the webhook signature cannot be verified", f"set {secret_var}"))
        else:
            out.append(Check(f"H08-{name}", PASS, f"Channel {name}", f"{len([p for p in allow.split(',') if p.strip()])} sender(s) allowed"))
    if os.environ.get("DELENTIA_EMAIL_TRUST_UNVERIFIED") == "1":
        out.append(Check("H08-email-auth", FAIL if public else WARN, "Email sender verification",
                         "DELENTIA_EMAIL_TRUST_UNVERIFIED=1 trusts the From header, which anyone can forge", "unset it unless only you can deliver to this mailbox"))
    if not present:
        out.append(Check("H08", INFO, "Chat channels", "no channel has credentials in this environment"))
    return out


def check_exposure() -> List[Check]:
    out: List[Check] = []
    origins = os.environ.get("DELENTIA_CORS_ORIGINS", "")
    if "*" in origins:
        out.append(Check("H09", FAIL, "CORS", "DELENTIA_CORS_ORIGINS contains '*': any web page could drive the API from a visitor's browser", "list the exact origins"))
    else:
        out.append(Check("H09", PASS, "CORS", "only loopback/Tauri origins" + (f" plus {origins}" if origins else "")))
    limit = os.environ.get("DELENTIA_RATE_LIMIT", "")
    out.append(Check("H10", WARN if limit.strip().lower() in ("0", "off", "false") else PASS, "Rate limit",
                     "disabled" if limit.strip().lower() in ("0", "off", "false") else "on (`delentia serve` turns it on)"))
    if os.environ.get("DELENTIA_CRAWL_ALLOW_PRIVATE") == "1":
        out.append(Check("H11", WARN, "Agent web fetch", "DELENTIA_CRAWL_ALLOW_PRIVATE=1: the agent may fetch internal addresses (cloud metadata, this machine's own API)",
                         "unset it unless you crawl internal documentation on purpose"))
    out.append(Check("H12", INFO, "TLS", "not checkable here: terminate TLS in a reverse proxy; LINE and WhatsApp webhooks need public HTTPS"))
    return out


def check_model_and_data() -> List[Check]:
    from rct_control_plane import fdia_policy, model_config, residency
    out: List[Check] = []
    selection = model_config.resolve_model_selection()
    provider = selection.provider
    paid = provider in ("openrouter", "openai-compat")
    has_cap = bool(os.environ.get("DELENTIA_EPISODE_BUDGET_USD") or os.environ.get("DELENTIA_EPISODE_MAX_TOKENS"))
    if paid and not has_cap:
        out.append(Check("H13", WARN, "Model spend", f"{provider}/{selection.model} is a remote model and no per-episode cap is set: one runaway episode spends without limit",
                         "set DELENTIA_EPISODE_BUDGET_USD and DELENTIA_EPISODE_MAX_TOKENS (and a credit limit at the provider)"))
    else:
        out.append(Check("H13", PASS, "Model spend", f"{provider}/{selection.model}" + (" (local, free)" if provider == "ollama" else " with a per-episode cap")))
    sovereignty = residency.load_policy()
    if sovereignty is None and paid:
        out.append(Check("H14", WARN, "Data location policy", "no sovereignty policy: prompts, search queries and remote-MCP arguments may go to any country",
                         "`delentia sovereignty set ...` if data location matters (it is a control, not a compliance claim)"))
    else:
        out.append(Check("H14", PASS if sovereignty else INFO, "Data location policy", "a policy is set" if sovereignty else "no policy, and the model is local"))
    try:
        policy = fdia_policy.load_policy()
        out.append(Check("H15", PASS if policy else WARN, "Owner policy for A (FDIA)",
                         "policy loaded; a broken file would fail closed" if policy else "no policy file: only the built-in floor judges tool calls",
                         "" if policy else "write one in the Desk page /fdia or `delentia fdia ...`"))
    except ValueError as exc:
        out.append(Check("H15", FAIL, "Owner policy for A (FDIA)", f"the policy file is invalid, so every tool call is refused (fail closed): {exc}"))
    return out


def check_config_files() -> List[Check]:
    out: List[Check] = []
    leaks: List[str] = []
    for path in (list(_config_dir().glob("*.json")) if _config_dir().exists() else []) + [Path(p) for p in (os.environ.get("DELENTIA_MCP_SERVERS"), os.environ.get("DELENTIA_SEARCH_CONFIG"), os.environ.get("DELENTIA_MODEL_CONFIG")) if p]:
        try:
            if path.exists() and KEY_LOOKING.search(path.read_text(encoding="utf-8", errors="replace")):
                leaks.append(str(path))
        except OSError:
            continue
    out.append(Check("H16", FAIL if leaks else PASS, "Secrets in configuration files",
                     f"credential-looking text in: {', '.join(sorted(set(leaks)))}" if leaks else "no credential-looking text in the configuration files",
                     "keep only the NAME of an environment variable in a config file; rotate anything that was written" if leaks else ""))
    from rct_control_plane import external_mcp, web_search
    try:
        servers = external_mcp.load_servers()
        unpinned = [n for n, s in servers.items() if s.enabled and not s.tools_sha256]
        remote_unknown = [n for n, s in servers.items() if s.enabled and s.url and not s.region]
        status = WARN if unpinned or remote_unknown else (PASS if servers else INFO)
        bits = [f"{len(servers)} server(s)"] if servers else ["no external MCP servers"]
        if unpinned:
            bits.append(f"not pinned: {', '.join(unpinned)}")
        if remote_unknown:
            bits.append(f"remote with no declared region: {', '.join(remote_unknown)}")
        out.append(Check("H17", status, "External MCP servers", "; ".join(bits), "`delentia mcp inspect <name>` then set tools_sha256" if unpinned else ""))
    except external_mcp.ExternalMCPError as exc:
        out.append(Check("H17", FAIL, "External MCP servers", f"the configuration is invalid, so none is exposed: {exc}"))
    try:
        search = web_search.load_config()
        out.append(Check("H18", PASS if search else INFO, "Web search", f"{search['provider']} at {search['base_url']}" if search else "not configured (the tool says so)"))
    except web_search.SearchConfigError as exc:
        out.append(Check("H18", FAIL, "Web search", f"misconfigured: {exc}"))
    return out


def check_storage() -> List[Check]:
    home = _home()
    try:
        home.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=home, delete=True):
            pass
        free_gb = shutil.disk_usage(home).free / 1e9
        return [Check("H19", WARN if free_gb < 2 else PASS, "Data directory", f"{home} is writable, {free_gb:.1f} GB free" + ("; the audit trail and memory grow" if free_gb < 2 else ""),
                      "free some space" if free_gb < 2 else ""),
                Check("H20", INFO, "Backups", "the audit trail, memory and approvals live in SQLite under the data directory: back it up (and never delete it: Zero-Delete)")]
    except OSError as exc:
        return [Check("H19", FAIL, "Data directory", f"{home} is not writable: {exc}")]


def run_checks(*, public: bool = True, probe: bool = False) -> List[Check]:
    checks: List[Check] = []
    for check_id, title, fn in (
        ("H01", "API authentication", lambda: check_api_auth(public)),
        ("H03", "Human approvers", check_approvers),
        ("H05", "Audit and notary", lambda: check_audit_keys(probe)),
        ("H08", "Channels", lambda: check_channels(public)),
        ("H09", "Exposure", check_exposure),
        ("H13", "Model and data", check_model_and_data),
        ("H16", "Configuration", check_config_files),
        ("H19", "Storage", check_storage),
        ("H21", "Safety envelope and owner alerts", lambda: check_envelope(public)),
        ("H22", "People and owners", lambda: check_tenants(public)),
        ("H23", "Memory history", check_memory_log),
    ):
        checks.extend(_guard(check_id, title, fn))
    return checks


def summarise(checks: List[Check]) -> Dict[str, Any]:
    counts = {s: sum(1 for c in checks if c.status == s) for s in (PASS, WARN, FAIL, INFO)}
    return {"counts": counts, "ready_for_a_public_host": counts[FAIL] == 0,
            "ready_without_warnings": counts[FAIL] == 0 and counts[WARN] == 0}


def render(checks: List[Check]) -> str:
    lines = []
    for c in checks:
        lines.append(f"[{c.status:4}] {c.id:<14} {c.title}: {c.detail}")
        if c.fix and c.status in (WARN, FAIL):
            lines.append(f"       -> {c.fix}")
    summary = summarise(checks)
    lines.append("")
    lines.append(f"{summary['counts'][PASS]} pass, {summary['counts'][WARN]} warn, {summary['counts'][FAIL]} fail, {summary['counts'][INFO]} info")
    return "\n".join(lines)


def as_json(checks: List[Check]) -> str:
    return json.dumps({**summarise(checks), "checks": [c.to_dict() for c in checks]}, indent=2, ensure_ascii=False)


def run(public: bool = True, probe: bool = False) -> Optional[int]:
    """Exit code for the CLI: 1 when anything FAILS."""
    return 1 if summarise(run_checks(public=public, probe=probe))["counts"][FAIL] else 0
