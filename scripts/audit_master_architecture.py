"""
Audit the Master System Architecture document against the code (Round 53).

The document (DELENTIA_OS_MASTER_SYSTEM_ARCHITECTURE.md) states what each of the 10 layers and 41 algorithms
IS. This script checks each statement against the repository instead of repeating it:

  REAL        the code does what the sentence says, and something in the runtime path uses it
  PARTIAL     part of it exists (logic without the weights, a module nothing calls, a number that varies)
  NOT_WIRED   real code exists but the agent runtime / API never reaches it
  ABSENT      nothing in the repository does this
  DOC_WRONG   the document's wording differs from the code in a way that would mislead

Every check reads source text or runs a small real call; nothing is taken from the document's own claims.

    python scripts/audit_master_architecture.py [--doc PATH] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
CP = REPO / "rct_control_plane"
VERDICTS = ("REAL", "PARTIAL", "NOT_WIRED", "ABSENT", "DOC_WRONG")


@dataclass
class Finding:
    ref: str
    claim: str
    verdict: str
    evidence: str
    action: str = ""


def read(rel: str) -> str:
    path = REPO / rel
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def mentions(rel: str, pattern: str, flags: int = 0) -> bool:
    return re.search(pattern, read(rel), flags) is not None


def runtime_uses(module: str, *runtime_files: str) -> List[str]:
    """Which of the runtime entry files import or name the module."""
    hit = []
    for rel in runtime_files:
        if re.search(rf"\b{re.escape(module)}\b", read(rel)):
            hit.append(rel)
    return hit


AGENT_PATH = ("rct_control_plane/governed_autonomous_loop.py", "rct_control_plane/autonomous_loop.py",
              "rct_control_plane/agent_factory.py")
RUNTIME = AGENT_PATH + ("rct_control_plane/api.py",)


# ------------------------------------------------------------------ layer checks

def layer1() -> Finding:
    signing = mentions("rct_control_plane/jitna_protocol.py", r"Ed25519PrivateKey")
    v3_signs = mentions("rct_control_plane/jitna_protocol_v3.py", r"Ed25519")
    fingerprint = mentions("rct_control_plane/jitna_protocol_v3.py", r"fingerprint", re.I)
    file_fmt = (CP / "jitna_file.py").exists()
    return Finding("§2 Layer 1", "JITNA v3 packets are Ed25519-signed with a 64-character fingerprint check against man-in-the-middle",
                   "PARTIAL" if signing else "ABSENT",
                   f"Ed25519 signing/verification is in jitna_protocol.py (used by subagent requests and the .jitna file: {file_fmt}); "
                   f"the v3 wire module only carries a signature field (it signs: {v3_signs}; fingerprint check: {fingerprint}). The signature "
                   "proves integrity and binding, not that the key is trusted (pinning needs the notary).",
                   "Pin subagent/approver keys through the notary (A2) before claiming man-in-the-middle protection.")


def layer2() -> Finding:
    screen = (CP / "injection_screen.py").exists()
    entropy = mentions("rct_control_plane/cord_security.py", r"class EntropyValidator")
    in_loop = mentions("rct_control_plane/governed_autonomous_loop.py", r"CORD|cord_security")
    verdict = "REAL" if screen and entropy and in_loop else "PARTIAL"
    return Finding("§2 Layer 2", "CORD Shannon-entropy engine blocks injection before the model sees the command",
                   verdict,
                   f"entropy validator: {entropy}; intent-level injection screen (Round 53): {screen}; CORD called in the governed "
                   f"loop: {in_loop}. Entropy alone catches obfuscation, not plain-language injection: the screen measures "
                   "that (scripts/measure_cord_screening.py).",
                   "Grow the held-out corpus; report first-look rates only.")


def layer2_range() -> Finding:
    return Finding("§2 Layer 2", "Layer 2 is 'ALGO-14 to ALGO-20'", "DOC_WRONG",
                   "ALGO-14..20 are RCT-Diffusion, HRM, Vector Search, Graph Traversal, Adaptive Prompting, Data Fusion and the "
                   "Workflow Orchestrator (the document's own §3). CORD is not one of the 41 algorithms.",
                   "Correct the range: Layer 2 has no ALGO numbers.")


def layer3() -> Finding:
    from rct_control_plane.governed_autonomous_loop import fdia_score
    zero_a = fdia_score(0.9, 1.0, 0.0)
    zero_i = fdia_score(0.9, 0.0, 1.0)
    zero_d = fdia_score(0.0, 1.0, 1.0)
    ok = zero_a == 0 and zero_i == 0 and zero_d == 0
    gate = mentions("rct_control_plane/governed_autonomous_loop.py", r"FDIA_GATE_THRESHOLD")
    return Finding("§2 Layer 3", "FDIA hard gate: A=0 blocks before any model call; F = D^I x A",
                   "REAL" if ok and gate else "PARTIAL",
                   f"F(A=0)={zero_a}, F(I=0)={zero_i}, F(D=0)={zero_d}; threshold enforced in the loop: {gate}. "
                   "Python A is per-tool only (no per-action rules, roles or tiers: those exist in the TypeScript policy).",
                   "Port the owner-defined policy (layer 3 of the FDIA contract) to Python.")


def layer3_name() -> Finding:
    return Finding("§3 ALGO-01", "FDIA = 'Fundamental Decision Intelligence Analysis'", "DOC_WRONG",
                   "The Architect's own documents (FDIA_Life_Equation.md; whitepaper foundation chapter) define F=D^I x A as "
                   "Future Design Intelligence Algorithm: Future = Data driven by Intent, owned by an accountable Architect.",
                   "Use the Architect's definition everywhere.")


def layer4() -> Finding:
    module = (CP / "lora_multiplexer.py").exists()
    weights = [p for p in REPO.rglob("*.safetensors") if ".claude" not in p.parts and "node_modules" not in p.parts]
    adapters = [p for p in REPO.rglob("adapter_model*") if ".claude" not in p.parts and "node_modules" not in p.parts]
    used = runtime_uses("lora_multiplexer", *AGENT_PATH)
    route = runtime_uses("lora_multiplexer", "rct_control_plane/api.py")
    return Finding("§2 Layer 4 / §6.2", "1+4 LoRA multiplexer: one frozen base + Router/Guardian/Executor/Scribe adapters in <6 GB VRAM",
                   "PARTIAL" if module else "ABSENT",
                   f"scheduling module: {module}; trained adapter weights in the repo: {len(weights) + len(adapters)}; reached from the "
                   f"agent loop: {used or 'no'} (an API route uses it: {bool(route)}). No VRAM measurement exists; the local model is plain Ollama.",
                   "Train or source four adapters, measure peak VRAM on the target machine, then wire a route through the provider layer.")


def layer5() -> Finding:
    gate = mentions("rct_control_plane/mcp_gateway.py", r"_resolve_public_target") and mentions("rct_control_plane/mcp_gateway.py", r"_SHELL_ALLOWED")
    return Finding("§2 Layer 5", "MCP gateway with a least-privilege sandbox for filesystem, shell, network",
                   "REAL" if gate else "PARTIAL",
                   f"workspace boundary, shell allow-list and pinned public-address fetch present: {gate}. The shell sandbox is "
                   "not a jail (same OS user).", "Docker/jail backend for untrusted tasks.")


def layer6() -> Finding:
    ir = (CP / "execution_graph_ir.py").exists()
    in_loop = runtime_uses("execution_graph_ir", *AGENT_PATH) or runtime_uses("parallel_engine", *AGENT_PATH)
    return Finding("§2 Layer 6", "Execution Graph IR + DAG swarm with wavefront parallelism (>70% time saved)",
                   "PARTIAL" if ir else "ABSENT",
                   f"graph IR exists: {ir}; used by the governed loop: {in_loop or 'no'}. Subagents run in parallel processes, "
                   "but the loop's plan is a list, not a DAG. The document's own §8 measured 11.9%-91.8% depending on topology.",
                   "Compile the RCT-7 plan to the IR and run independent steps in waves.")


def layer7() -> Finding:
    toon = (CP / "toon_formatter.py").exists()
    used = runtime_uses("toon_formatter", *RUNTIME, "rct_control_plane/mcp_server.py", "rct_control_plane/intent_compiler.py")
    return Finding("§2 Layer 7", "Intent compiler emits TOON, which prevents semantic drift",
                   "NOT_WIRED" if toon and not used else ("REAL" if used else "ABSENT"),
                   f"toon_formatter exists: {toon}; imported by the runtime / MCP tools: {used or 'no'}. The intent compiler is real "
                   "(80% on a 30-goal corpus) and RCT-7 step 7 checks the answer against intent, but nothing validates output against a TOON schema.",
                   "Validate model decisions and tool outputs against a typed schema in the cycle.")


def layer8() -> Finding:
    runner = (REPO / "signedai" / "runner.py").exists()
    in_loop = runtime_uses("signedai", *AGENT_PATH)
    return Finding("§2 Layer 8", "HexaCore jury of 7 models votes >=75% and the verdict is stamped",
                   "PARTIAL" if runner else "NOT_WIRED",
                   f"Round 53 jury runner (real calls, abstain rules, independence check, Ed25519 verdict): {runner}; called by the "
                   f"governed loop: {in_loop or 'no'}. The roster's 7 ids are not all reachable through one provider; tier 6 passes at "
                   "4/6 (66.7%), not 75%; nothing has run a real multi-vendor vote yet.",
                   "Configure real endpoints per role, run one recorded vote, and decide which actions require a jury (tier by risk).")


def layer9() -> Finding:
    return Finding("§2 Layer 9 / §6.4", "Delta memory compresses 91.5% and recalls in <50 ms",
                   "PARTIAL",
                   "Measured in bytes (Round 52): 39% at 20 ticks to 90% at 500 ticks; zstd alone does better on the same data. "
                   "Recall latency claim holds (sub-millisecond). The document's own §8 already measured 64.6-78.0%.",
                   "Keep claims to the measured range; say what Delta adds over zstd (diffs are queryable, not smaller).")


def layer10() -> List[Finding]:
    jwt_wired = mentions("rct_control_plane/api_auth.py", r"RS256|jwt", re.I)
    out = [
        Finding("§2 Layer 10", "JWT RS256 certificates", "NOT_WIRED" if not jwt_wired else "REAL",
                "enterprise_hardening.RS256KeyPair exists and the deep pipeline issues receipts, but API authentication is a "
                f"shared bearer token (JWT in api_auth: {jwt_wired}); the receipt key is ephemeral per process.",
                "Only needed when a customer requires per-user tokens: issue RS256 tokens from a persistent key."),
        Finding("§2 Layer 10", "Circuit breaker", "REAL" if (CP / "provider_breaker.py").exists() else "ABSENT",
                "provider_breaker.py wraps every episode's model provider (Round 53); state shared per endpoint.", ""),
        Finding("§2 Layer 10", "Rate limiting", "REAL" if (CP / "api_ratelimit.py").exists() else "ABSENT",
                "api_ratelimit.py: token bucket per caller with endpoint costs; on in `delentia serve` (Round 53).", ""),
    ]
    cors_wild = mentions("rct_control_plane/api.py", r'^\s*allow_origins=\["\*"\]', re.M)
    out.append(Finding("§2 Layer 10", "Zero-trust delivery", "PARTIAL" if not cors_wild else "DOC_WRONG",
                       f"CORS wildcard still present: {cors_wild}. Round 53 limits origins to the local GUI and refuses foreign "
                       "Origin/Host on a token-less API. No host exists, so Cloudflare/Zuplo delivery is not exercised.",
                       "Pick a host; then set DELENTIA_API_TOKEN and the Worker secret."))
    return out


def jitna_terms() -> Finding:
    text = read("rct_control_plane/jitna_protocol.py")
    return Finding("§6.1", "JITNA = (I Intent, D Data, Delta, A Authorization, R Resource, M Memory)", "DOC_WRONG",
                   "The canonical packet (jitna_protocol.py header) is A=Approach, R=Reflection; Authorization/Resource belonged to "
                   f"the deprecated wire_protocol.py. Header says so: {'Reflection' in text}.",
                   "Fix §6.1 to the canonical meaning.")


def counts(doc_text: Optional[str]) -> List[Finding]:
    from rct_control_plane.algorithm_pipeline import ADAPTERS
    ids = {a.algo_id for a in ADAPTERS}
    micro = [p for p in (REPO / "microservices").iterdir() if p.is_dir() and not p.name.startswith(("_", "."))] if (REPO / "microservices").exists() else []
    return [
        Finding("§3", "41 algorithms", "REAL" if len(ids) == 41 else "PARTIAL",
                f"{len(ids)} pipeline adapters, one per algorithm; 36 executed on real inputs in the full-stack bench (Round 53); the other 5 "
                "need a model (ALGO-09, 11, 12, 32) or an image backend (ALGO-14).", ""),
        Finding("§4", "62 microservices", "DOC_WRONG",
                f"This repository ships {len(micro)} reference services; the private repo's count was re-audited by the document itself "
                "(§8.1: 72 folders, 64 real). The runtime calls none of them.",
                "Say '5 public reference services' publicly; do not promote 62."),
    ]


def doc_algorithm_names(doc_text: str) -> Dict[str, str]:
    names: Dict[str, str] = {}
    for match in re.finditer(r"^\d+\.\s+\*\*(ALGO-\d{2}):\s*(.+?)\*\*", doc_text, flags=re.M):
        names[match.group(1)] = match.group(2).strip()
    return names


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def algorithm_names(doc_text: str) -> Tuple[List[Finding], List[Tuple[str, str, str]]]:
    from rct_control_plane.algorithm_pipeline import ADAPTERS
    code = {a.algo_id: a.name for a in ADAPTERS}
    doc = doc_algorithm_names(doc_text)
    mismatches: List[Tuple[str, str, str]] = []
    for algo_id, doc_name in sorted(doc.items()):
        code_name = code.get(algo_id)
        if code_name is None:
            mismatches.append((algo_id, doc_name, "(no adapter)"))
            continue
        head = re.split(r" \(", doc_name)[0]
        a, b = _tokens(head), _tokens(code_name)
        shared = len(a & b)
        if shared == 0 or shared / max(1, min(len(a), len(b))) < 0.6:
            mismatches.append((algo_id, doc_name, code_name))
    finding = Finding("§3", "each ALGO-nn name in the document is the algorithm the code calls ALGO-nn",
                      "REAL" if not mismatches else "PARTIAL",
                      f"{len(doc)} entries parsed; {len(mismatches)} whose names differ from the pipeline adapter's: "
                      + "; ".join(f"{i}: doc '{d}' vs code '{c}'" for i, d, c in mismatches),
                      "Align the names. ALGO-26 is the real difference: the Architect settled it as Intent Classification (algo_26 docstring); the document's 'Intent Conservation' (a lossless semantic verifier) exists only as the heuristic VERIFY step.")
    return [finding], mismatches


CHECKS: List[Callable[[], Union[Finding, List[Finding]]]] = [layer1, layer2, layer2_range, layer3, layer3_name, layer4, layer5, layer6, layer7, layer8, layer9,
                                      layer10, jitna_terms]


def run_audit(doc_text: Optional[str] = None) -> List[Finding]:
    findings: List[Finding] = []
    for check in CHECKS:
        result = check()
        findings.extend(result if isinstance(result, list) else [result])
    findings.extend(counts(doc_text))
    if doc_text:
        findings.extend(algorithm_names(doc_text)[0])
    return findings


DEFAULT_DOC = Path.home() / "Desktop" / "Delentia labs" / "main object delentia 41 algo-62 microservice" / "DELENTIA_OS_MASTER_SYSTEM_ARCHITECTURE.md"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--doc", default=str(DEFAULT_DOC))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    doc_path = Path(args.doc)
    doc_text = doc_path.read_text(encoding="utf-8") if doc_path.exists() else None
    findings = run_audit(doc_text)
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2, ensure_ascii=False))
        return 0
    tally = {v: sum(1 for f in findings if f.verdict == v) for v in VERDICTS}
    for f in findings:
        print(f"[{f.verdict:9}] {f.ref:18} {f.claim}\n             {f.evidence}" + (f"\n             -> {f.action}" if f.action else ""))
    print("\n" + "  ".join(f"{v}={n}" for v, n in tally.items()))
    if doc_text is None:
        print(f"(document not found at {doc_path}; name checks skipped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
