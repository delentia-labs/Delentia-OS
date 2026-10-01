"""
Data sovereignty for the Regional Adapter (Round 52).

The idea behind the Regional Adapter: whatever country runs Delentia can plug in
its own AI, and the data stays in that country. Until now the adapter only chose
a model by language and region. `TenantRegionalConfig.data_residency` was stored
and never read, every model in the routing table was a cloud model reached through
OpenRouter (so every call left the country), and `compliance_tags` was a label.

This module is the part that was missing: it decides, before a model call, whether
the data may go where the call would send it.

  HostingProfile     where a model endpoint actually processes data
                       kind    "local"        on the tenant's own machine / network
                               "in_region"    a provider hosted inside a named region
                               "cross_border" a provider whose processing region is
                                              elsewhere, or not known to be inside
                       region  an ISO 3166-1 alpha-2 code, or "GLOBAL" when it cannot
                               be pinned (OpenRouter routes to many providers)
  SovereigntyPolicy  the tenant's rule: home region, the regions a call may reach,
                     whether any cross-border call is allowed at all, and what to do
                     with personal data when one is
  PIIScanner         finds personal data in the text that would be sent (Thai national
                     ID, Japanese My Number, Chinese resident ID, Korean RRN, payment
                     cards, e-mail addresses, phone numbers) with the national
                     checksums, so a random 13-digit number is not flagged
  evaluate_call()    -> ResidencyDecision: allow, redact or block, with the reason

Fail-closed: when a policy is set, a call to a provider outside the allowed regions
is blocked unless the policy explicitly allows cross-border calls; personal data in
a permitted cross-border call is blocked or redacted according to `pii_policy`.

What this is not: legal advice, and not a guarantee about what a hosted provider does
with data once it is there. It enforces the tenant's own rule on the calls this
process makes. Laws differ: the Thai PDPA conditions cross-border transfer (adequate
protection abroad, consent or safeguards) rather than banning it, whereas some
regimes (for example China's PIPL for certain data, Vietnam's and Indonesia's rules
for certain categories) lean toward keeping data inside the country. The policy
fields below let a tenant express either; deciding which applies is for the tenant's
counsel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

LOCAL = "LOCAL"          # policy token: the tenant's own machine or network
GLOBAL = "GLOBAL"        # hosting region token: cannot be pinned to one country

KIND_LOCAL = "local"
KIND_IN_REGION = "in_region"
KIND_CROSS_BORDER = "cross_border"

PII_ALLOW = "allow"
PII_REDACT = "redact"
PII_BLOCK = "block"

_MAX_SCAN_CHARS = 200_000     # longer prompts are scanned in full by slices; this bounds one slice


# ---------------------------------------------------------------------------
# Hosting and policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HostingProfile:
    kind: str = KIND_CROSS_BORDER
    region: str = GLOBAL
    operator: str = ""
    note: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {"kind": self.kind, "region": self.region, "operator": self.operator, "note": self.note}


@dataclass
class SovereigntyPolicy:
    """One tenant's rule. `allowed_regions` defaults to the home region."""
    home_region: str
    allowed_regions: List[str] = field(default_factory=list)
    allow_cross_border: bool = False
    pii_policy: str = PII_BLOCK              # what to do with personal data in a permitted cross-border call
    legal_basis: str = ""                    # recorded with each decision, e.g. "PDPA s.28: consent + safeguards"
    tenant_id: str = "default"

    def __post_init__(self) -> None:
        self.home_region = self.home_region.upper()
        regions = [r.upper() for r in (self.allowed_regions or [self.home_region])]
        self.allowed_regions = list(dict.fromkeys(regions))
        if self.pii_policy not in (PII_ALLOW, PII_REDACT, PII_BLOCK):
            raise ValueError(f"pii_policy must be one of allow/redact/block, not {self.pii_policy!r}")

    def to_dict(self) -> Dict[str, Any]:
        return {"tenant_id": self.tenant_id, "home_region": self.home_region, "allowed_regions": self.allowed_regions,
                "allow_cross_border": self.allow_cross_border, "pii_policy": self.pii_policy, "legal_basis": self.legal_basis}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SovereigntyPolicy":
        return cls(
            home_region=str(data["home_region"]), allowed_regions=[str(r) for r in data.get("allowed_regions", [])],
            allow_cross_border=bool(data.get("allow_cross_border", False)), pii_policy=str(data.get("pii_policy", PII_BLOCK)),
            legal_basis=str(data.get("legal_basis", "")), tenant_id=str(data.get("tenant_id", "default")),
        )


def hosting_is_allowed(policy: SovereigntyPolicy, hosting: HostingProfile) -> bool:
    """Is a call to this hosting inside what the policy permits without any
    cross-border exception?"""
    if hosting.kind == KIND_LOCAL:
        return True
    if hosting.region == GLOBAL:
        return False
    return hosting.region.upper() in policy.allowed_regions


# ---------------------------------------------------------------------------
# Personal data
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PIIFinding:
    kind: str
    start: int
    end: int


def _digits(text: str) -> str:
    return "".join(c for c in text if c.isdigit())


def valid_thai_national_id(d: str) -> bool:
    if len(d) != 13 or not d.isdigit() or d[0] == "0":
        return False
    total = sum(int(d[i]) * (13 - i) for i in range(12))
    return (11 - total % 11) % 10 == int(d[12])


def valid_japan_my_number(d: str) -> bool:
    if len(d) != 12 or not d.isdigit():
        return False
    total = 0
    for n in range(1, 12):
        p = int(d[11 - n])
        q = n + 1 if n <= 6 else n - 5
        total += p * q
    remainder = total % 11
    check = 0 if remainder <= 1 else 11 - remainder
    return check == int(d[11])


def valid_china_resident_id(s: str) -> bool:
    if len(s) != 18 or not s[:17].isdigit() or not (s[17].isdigit() or s[17] in "Xx"):
        return False
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    total = sum(int(s[i]) * weights[i] for i in range(17))
    return "10X98765432"[total % 11] == s[17].upper()


def valid_korea_rrn(d: str) -> bool:
    if len(d) != 13 or not d.isdigit():
        return False
    month, day, gender = int(d[2:4]), int(d[4:6]), int(d[6])
    if not (1 <= month <= 12 and 1 <= day <= 31 and 1 <= gender <= 8):
        return False
    weights = (2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5)
    total = sum(int(d[i]) * weights[i] for i in range(12))
    return (11 - total % 11) % 10 == int(d[12])


def luhn_valid(d: str) -> bool:
    if not (13 <= len(d) <= 19) or not d.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(d)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


_EMAIL_LOCAL = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._%+-")
_EMAIL_DOMAIN = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")


class PIIScanner:
    """Linear-time scan: digit groups and e-mail addresses are found by walking the
    text once, never with a backtracking pattern."""

    def scan(self, text: str) -> List[PIIFinding]:
        findings: List[PIIFinding] = []
        for offset in range(0, len(text), _MAX_SCAN_CHARS):
            chunk = text[offset:offset + _MAX_SCAN_CHARS]
            findings += [PIIFinding(f.kind, f.start + offset, f.end + offset) for f in self._scan_chunk(chunk)]
        return findings

    def _scan_chunk(self, text: str) -> List[PIIFinding]:
        found: List[PIIFinding] = []
        n = len(text)
        i = 0
        while i < n:
            c = text[i]
            if c.isdigit() or (c == "+" and i + 1 < n and text[i + 1].isdigit()):
                j = i + 1
                # a run of digits that may be written with hyphens (inside a token) or single spaces
                while j < n and (text[j].isdigit() or (text[j] in " -" and j + 1 < n and text[j + 1].isdigit())):
                    j += 1
                found += self._scan_run(text, i, j)
                i = j
            else:
                i += 1
        found += self._emails(text)
        found.sort(key=lambda f: f.start)
        return found

    def _scan_run(self, text: str, start: int, end: int) -> List[PIIFinding]:
        """A run such as "1101702034512 4111 1111 1111 1111" may hold several numbers. Split it at
        single spaces into tokens and, from each token, try the longest combination of up to six
        consecutive tokens that is a recognised number; so two numbers written side by side are
        found separately and a card written 4-4-4-4 is found as one."""
        tokens: List[Tuple[int, int]] = []
        pos = start
        while pos < end:
            nxt = text.find(" ", pos, end)
            stop = end if nxt == -1 else nxt
            if stop > pos:
                tokens.append((pos, stop))
            pos = stop + 1
        out: List[PIIFinding] = []
        k = 0
        while k < len(tokens):
            matched = False
            for width in range(min(6, len(tokens) - k), 0, -1):       # longest first: "4111 1111 1111" alone can pass a checksum by chance
                s0, e0 = tokens[k][0], tokens[k + width - 1][1]
                group = text[s0:e0]
                kind = self._classify_group(group, text[s0:min(len(text), e0 + 1)])
                if kind:
                    out.append(PIIFinding(kind, s0, e0))
                    k += width
                    matched = True
                    break
            if not matched:
                k += 1
        return out

    @staticmethod
    def _classify_group(group: str, with_next: str) -> Optional[str]:
        d = _digits(group)
        plus = group.startswith("+")
        if len(d) == 13 and not plus:
            # "YYMMDD-GXXXXXX" with the hyphen after six digits is the Korean layout; about one
            # 13-digit number in ten also passes the Thai checksum by chance, so layout decides.
            if group[6:7] == "-" and valid_korea_rrn(d):
                return "kr_resident_registration_number"
            if valid_thai_national_id(d):
                return "th_national_id"
            if valid_korea_rrn(d):
                return "kr_resident_registration_number"
        if len(d) == 12 and not plus and valid_japan_my_number(d):
            return "jp_my_number"
        if 13 <= len(d) <= 19 and not plus and luhn_valid(d):
            return "payment_card"
        if len(d) == 18 and not plus and valid_china_resident_id(d):
            return "cn_resident_id"
        if len(d) == 17 and not plus:
            # a Chinese resident ID ends in a check character that may be X
            tail = with_next[len(group):len(group) + 1]
            if tail and (tail.isdigit() or tail in "Xx") and valid_china_resident_id(d + tail):
                return "cn_resident_id"
        if plus and 9 <= len(d) <= 15:
            return "phone_number"
        if not plus and len(d) == 10 and d[0] == "0" and d[1] in "689":
            return "th_mobile_number"
        return None

    @staticmethod
    def _emails(text: str) -> List[PIIFinding]:
        out: List[PIIFinding] = []
        n = len(text)
        pos = text.find("@")
        while pos != -1:
            s = pos
            while s > 0 and text[s - 1] in _EMAIL_LOCAL and pos - s < 64:
                s -= 1
            e = pos + 1
            while e < n and text[e] in _EMAIL_DOMAIN and e - pos < 255:
                e += 1
            domain = text[pos + 1:e].rstrip(".-")
            if s < pos and "." in domain and not domain.startswith(".") and not domain.endswith("."):
                out.append(PIIFinding("email_address", s, pos + 1 + len(domain)))
            pos = text.find("@", pos + 1)
        return out

    def redact(self, text: str) -> Tuple[str, List[PIIFinding]]:
        findings = self.scan(text)
        if not findings:
            return text, []
        pieces: List[str] = []
        last = 0
        for f in findings:
            if f.start < last:
                continue
            pieces.append(text[last:f.start])
            pieces.append(f"[REDACTED:{f.kind}]")
            last = f.end
        pieces.append(text[last:])
        return "".join(pieces), findings


def pii_summary(findings: Iterable[PIIFinding]) -> Dict[str, int]:
    """Counts by kind. The values themselves are never kept."""
    out: Dict[str, int] = {}
    for f in findings:
        out[f.kind] = out.get(f.kind, 0) + 1
    return out


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------

@dataclass
class ResidencyDecision:
    action: str                      # "allow" | "redact" | "block"
    reason: str
    hosting: HostingProfile
    policy: SovereigntyPolicy
    pii: Dict[str, int] = field(default_factory=dict)
    cross_border: bool = False

    @property
    def allowed(self) -> bool:
        return self.action != "block"

    def to_dict(self) -> Dict[str, Any]:
        return {"action": self.action, "reason": self.reason, "hosting": self.hosting.to_dict(),
                "policy": self.policy.to_dict(), "pii": self.pii, "cross_border": self.cross_border}


_SCANNER = PIIScanner()


def evaluate_call(policy: SovereigntyPolicy, hosting: HostingProfile, text: str = "") -> ResidencyDecision:
    """May `text` be sent to an endpoint with this hosting under this policy?"""
    if hosting_is_allowed(policy, hosting):
        return ResidencyDecision("allow", "the endpoint processes data on this machine or inside an allowed region",
                                 hosting, policy, cross_border=False)
    where = "an unpinned global region" if hosting.region == GLOBAL else f"region {hosting.region}"
    if not policy.allow_cross_border:
        return ResidencyDecision(
            "block", f"{hosting.operator or 'the endpoint'} processes data in {where}, outside the allowed "
                     f"regions {policy.allowed_regions} and this policy allows no cross-border calls",
            hosting, policy, cross_border=True)
    findings = _SCANNER.scan(text) if text else []
    summary = pii_summary(findings)
    if findings and policy.pii_policy == PII_BLOCK:
        return ResidencyDecision("block", f"personal data ({', '.join(sorted(summary))}) would leave {policy.home_region} for {where}",
                                 hosting, policy, pii=summary, cross_border=True)
    if findings and policy.pii_policy == PII_REDACT:
        return ResidencyDecision("redact", f"cross-border call to {where}: personal data is replaced before sending",
                                 hosting, policy, pii=summary, cross_border=True)
    return ResidencyDecision("allow", f"cross-border call to {where} is allowed by the policy", hosting, policy,
                             pii=summary, cross_border=True)


def redact_text(text: str) -> Tuple[str, Dict[str, int]]:
    redacted, findings = _SCANNER.redact(text)
    return redacted, pii_summary(findings)


def scan_text(text: str) -> Dict[str, int]:
    return pii_summary(_SCANNER.scan(text))


KNOWN_REGIONS: FrozenSet[str] = frozenset({
    "TH", "JP", "KR", "CN", "TW", "VN", "ID", "PH", "MY", "SG", "IN", "AU", "NZ", "HK", "US", "CA", "GB", "DE", "FR", "NL", "IE", "BR",
})


def validate_region(code: str) -> str:
    c = code.strip().upper()
    if len(c) != 2 or not c.isalpha():
        raise ValueError(f"{code!r} is not an ISO 3166-1 alpha-2 region code")
    return c

