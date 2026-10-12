"""
Round 72: a small model of the person - how they want to be answered - that is theirs to read, change and erase (Hermes: Honcho's user modeling; here without a second model and without a hidden profile).

What the person says about HOW to answer is easy to lose between conversations: "always answer in Thai", "keep it short", "use bullet points", "my time zone is Asia/Bangkok". This notices such a statement in the
person's OWN message, proposes it as a suggestion (memory_nudge.py, the same suggestion store, `/remember`, `delentia memory accept`), and once the person accepts, shows it to every episode:

    What this person asked for about how to answer (accepted by them; a style preference, never a permission):
    - Answer in Thai.
    - Keep answers short.

Rules that keep it from becoming a back door:
  * four facets only - language, answer_length, format, timezone - each with a FIXED vocabulary; a facet's sentence is built by this module from the value, so no free text from the person (let alone from a page) reaches the
    prompt through here;
  * it is read from the person's own message only: an episode that read outside text, or started from an outside payload, proposes nothing; a sentence that looks like a secret proposes nothing;
  * a standing statement needs a standing marker ("always", "from now on", "by default", "ต่อไปนี้", "เสมอ", "ทุกครั้ง", or it speaks of "your answers/replies"): "reply to the customer in English" is a task, not a preference;
  * nothing is kept until the person accepts; a facet is an ordinary memory of the person (type preference, sealed with their key, versioned in the memory log, revocable, replaceable, erased with the person) with
    context {"user_model": {"facet", "value"}}, so every control they already have over their memory is the control over their profile;
  * it can only shape the answer. The approval, policy and taint gates do not read it.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List, Optional

FACETS = ("language", "answer_length", "format", "timezone")
LANGUAGES = {"th": "Thai", "en": "English", "ja": "Japanese", "zh": "Chinese", "ko": "Korean", "fr": "French", "de": "German", "es": "Spanish"}
LENGTHS = {"short": "Keep answers short.", "detailed": "Give detailed answers."}
FORMATS = {"bullets": "Format answers as bullet points.", "table": "Use tables when comparing things."}
MAX_RENDERED_CHARS = 500
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。;])\s+|\n+")
_LANG_NAMES = {"thai": "th", "english": "en", "japanese": "ja", "chinese": "zh", "korean": "ko", "french": "fr", "german": "de", "spanish": "es",
               "ไทย": "th", "อังกฤษ": "en", "ญี่ปุ่น": "ja", "จีน": "zh", "เกาหลี": "ko", "ฝรั่งเศส": "fr", "เยอรมัน": "de", "สเปน": "es"}
_LANG_WORDS = "|".join(sorted((re.escape(k) for k in _LANG_NAMES), key=len, reverse=True))
# a statement that is about the future of the conversation, not about one task
_MARK_EN = r"(?:always|from now on|from here on|by default|going forward|every time|each time|in future|permanently|i prefer|i want your|i'd like your|i would like your|your (?:answers?|repl(?:y|ies)|responses?)|when you (?:answer|reply|respond|compare))"
_MARK_TH = r"(?:เสมอ|ทุกครั้ง|ต่อไปนี้|ตั้งแต่นี้|เป็นค่าเริ่มต้น|ทุกคำตอบ)"
_MARKED = re.compile(_MARK_EN + "|" + _MARK_TH, re.IGNORECASE)
_STAND_EN = re.compile(_MARK_EN, re.IGNORECASE)

_LANG_EN = re.compile(r"\b(?:answer|reply|respond|speak)(?:\s+to)?(?:\s+me)?(?:\s+back)?\s+in\s+(" + _LANG_WORDS + r")\b", re.IGNORECASE)
_LANG_TH = re.compile(r"ตอบ(?:กลับ)?(?:เป็น|ด้วย)?ภาษา\s*(" + _LANG_WORDS + ")")
_SHORT_EN = re.compile(r"\b(?:keep|make)\s+(?:your\s+)?(?:answers?|repl(?:y|ies)|responses?)(?:\s+to\s+be)?\s+(short|brief|concise)\b"
                       r"|\b(?:i\s+)?(?:want|prefer|like)\s+(?:your\s+)?(?:(?:answers?|repl(?:y|ies)|responses?)\s+(?:to\s+be\s+)?)?(short|brief|concise)\b(?:\s+(?:answers?|repl(?:y|ies)|responses?))?"
                       r"|\bplease\s+keep\s+(?:the\s+|your\s+)?(?:answers?|repl(?:y|ies)|responses?)\s+(short|brief|concise)\b", re.IGNORECASE)
_DETAIL_EN = re.compile(r"\b(?:always|please)\s+(?:explain|answer|reply|respond)\b[^.!?\n]{0,30}\bin\s+detail\b"
                        r"|\b(?:i\s+)?(?:want|prefer|like)\s+(?:your\s+)?(?:(?:answers?|repl(?:y|ies)|responses?)\s+(?:to\s+be\s+)?)?(?:detailed|thorough)\b"
                        r"|\b(?:always\s+)?give\s+(?:me\s+)?(?:detailed|thorough)\s+(?:answers?|explanations?|repl(?:y|ies)|responses?)\b", re.IGNORECASE)
_LEN_TH = re.compile(r"(?:ตอบ|คำตอบ|อธิบาย)[^\n.!?]{0,12}?(สั้น|กระชับ|ละเอียด)|(?:ขอ|อยากให้|ชอบ|ต้องการ)[^\n.!?]{0,6}?(?:คำตอบ|คำอธิบาย)[^\n.!?]{0,8}?(สั้น|กระชับ|ละเอียด)")
_BULLETS = re.compile(r"\bbullet(?:s|\s*points?)?\b|\bnumbered list\b", re.IGNORECASE)
_TABLE = re.compile(r"\btables?\b", re.IGNORECASE)
_NOT_TABLE = re.compile(r"\b(?:do not|don't|never|avoid|without|no)\s+(?:use\s+|using\s+|put\s+)?(?:any\s+)?tables?\b", re.IGNORECASE)
_FORMAT_TH = re.compile(r"ตอบ[^\n.!?]{0,6}?(?:เป็น)?\s*(ข้อๆ|ข้อ ๆ|ตาราง|บูลเล็ต)")
_ZONE_EN = re.compile(r"\b(?:my|our)\s+time\s?zone\s+is\s+([A-Za-z_]+/[A-Za-z_+\-0-9/]+|UTC\s?[+-]\s?\d{1,2}(?::\d{2})?|GMT\s?[+-]\s?\d{1,2}(?::\d{2})?)|\bi\s?(?:'m|am)\s+in\s+(UTC\s?[+-]\s?\d{1,2}(?::\d{2})?)", re.IGNORECASE)
_ZONE_TH = re.compile(r"เขตเวลา(?:ของ)?(?:ฉัน|ผม|หนู|เรา)?\s*(?:คือ|เป็น)?\s*([A-Za-z_]+/[A-Za-z_+\-0-9/]+|UTC\s?[+-]\s?\d{1,2}(?::\d{2})?|GMT\s?[+-]\s?\d{1,2}(?::\d{2})?)")


def _valid_zone(raw: str) -> Optional[str]:
    zone = re.sub(r"\s+", "", raw or "").replace("GMT", "UTC")
    if re.fullmatch(r"UTC[+-]\d{1,2}(?::\d{2})?", zone, re.IGNORECASE):
        hours = int(re.search(r"\d{1,2}", zone).group(0))                    # type: ignore[union-attr]
        return "UTC" + zone[3:] if hours <= 14 else None
    try:
        import zoneinfo
        return zone if zone in zoneinfo.available_timezones() else None
    except Exception:                                                        # noqa: BLE001 - no tz database on this machine: a zone cannot be checked, so none is accepted
        return None


def sentence_for(facet: str, value: str) -> str:
    """The fixed sentence that is stored and shown for a facet. Raises ValueError for a value outside the vocabulary."""
    if facet == "language" and value in LANGUAGES:
        return f"Answer in {LANGUAGES[value]}."
    if facet == "answer_length" and value in LENGTHS:
        return LENGTHS[value]
    if facet == "format" and value in FORMATS:
        return FORMATS[value]
    if facet == "timezone":
        zone = _valid_zone(value)
        if zone:
            return f"The person's time zone is {zone}."
    raise ValueError(f"not a profile value: {facet}={value!r}")


def detect(text: str) -> List[Dict[str, str]]:
    """Standing preferences about how to answer, stated in `text` (the person's own message). At most one per facet; deterministic."""
    from rct_control_plane.memory_nudge import _SECRET
    found: Dict[str, Dict[str, str]] = {}

    def add(facet: str, value: str, sentence: str) -> None:
        if facet not in found:
            found[facet] = {"facet": facet, "value": value, "evidence": sentence[:160]}

    for sentence in _SENTENCE_SPLIT.split(str(text or "")):
        sentence = " ".join(sentence.split())
        if not sentence or len(sentence) > 400 or sentence.endswith(("?", "？")) or _SECRET.search(sentence):
            continue
        marked = bool(_MARKED.search(sentence))
        # language
        match = _LANG_EN.search(sentence) or _LANG_TH.search(sentence)
        if match and marked:
            add("language", _LANG_NAMES[match.group(1).lower()], sentence)
        # length
        match = _SHORT_EN.search(sentence)
        if match and (marked or _STAND_EN.search(sentence) or re.match(r"\s{0,20}(?:please\s{1,5})?(?:keep|make)\b", sentence, re.IGNORECASE)):
            add("answer_length", "short", sentence)
        elif _DETAIL_EN.search(sentence):
            add("answer_length", "detailed", sentence)
        else:
            th = _LEN_TH.search(sentence)
            if th:
                word = next(g for g in th.groups() if g)
                add("answer_length", "detailed" if word == "ละเอียด" else "short", sentence)
        # format
        if _STAND_EN.search(sentence) or re.search(r"\b(?:always|by default)\b", sentence, re.IGNORECASE):
            wants_bullets = bool(_BULLETS.search(sentence))
            wants_table = bool(_TABLE.search(sentence)) and not _NOT_TABLE.search(sentence)
            if wants_bullets and not wants_table:
                add("format", "bullets", sentence)
            elif wants_table and not wants_bullets:
                add("format", "table", sentence)
        fmt = _FORMAT_TH.search(sentence)
        if fmt:
            add("format", "table" if fmt.group(1) == "ตาราง" else "bullets", sentence)
        # time zone
        zone = _ZONE_EN.search(sentence) or _ZONE_TH.search(sentence)
        if zone:
            value = _valid_zone(next(g for g in zone.groups() if g))
            if value:
                add("timezone", value, sentence)
    return list(found.values())


class UserModel:
    """One person's profile: facets kept as ordinary memories of theirs (see the module note)."""

    def __init__(self, persistence: Any, namespace: str) -> None:
        self._p, self.namespace = persistence, namespace

    def _rows(self) -> List[Dict[str, Any]]:
        out = []
        for m in self._p.list_memories(self.namespace):
            context = m.get("context")
            if isinstance(context, str):
                try:
                    context = json.loads(context or "{}")
                except ValueError:
                    context = {}
            facet = (context or {}).get("user_model") if isinstance(context, dict) else None
            if isinstance(facet, dict) and facet.get("facet") in FACETS:
                out.append({**m, "facet": facet["facet"], "value": facet.get("value")})
        return out

    def facets(self) -> Dict[str, Dict[str, Any]]:
        """{facet: {"value", "memory_id", "sentence"}} - the newest live memory per facet."""
        found: Dict[str, Dict[str, Any]] = {}
        for row in sorted(self._rows(), key=lambda r: str(r.get("created_at"))):
            found[row["facet"]] = {"value": row["value"], "memory_id": row["id"], "sentence": row["content"]}
        return found

    def set(self, facet: str, value: str, by: str = "") -> Dict[str, Any]:
        sentence = sentence_for(facet, value)                                # raises ValueError outside the vocabulary
        existing = self.facets().get(facet)
        if existing and existing["value"] == value:
            return {"facet": facet, "value": value, "memory_id": existing["memory_id"], "changed": False}
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        self._p.save_memory(memory_id=memory_id, namespace=self.namespace, memory_type="preference", content=sentence,
                            context={"user_model": {"facet": facet, "value": value}, "provenance": {"tainted": False, "source_tool": "", "via": "user_model"}}, importance=0.8)
        if existing:
            self._p.revoke_memory(existing["memory_id"], self.namespace, f"superseded by {memory_id}")
        try:
            self._p.append_audit(entity_type="user_model", entity_id=memory_id, action="set", actor=(by or self.namespace)[:80],
                                 changes={"namespace": self.namespace, "facet": facet, "value": value, "replaced": existing["memory_id"] if existing else None})
        except Exception:                                                    # noqa: BLE001 - the facet itself is stored
            pass
        return {"facet": facet, "value": value, "memory_id": memory_id, "changed": True}

    def unset(self, facet: str, by: str = "") -> bool:
        existing = self.facets().get(facet)
        if not existing:
            return False
        done = self._p.revoke_memory(existing["memory_id"], self.namespace, "profile entry removed by the person")
        try:
            self._p.append_audit(entity_type="user_model", entity_id=existing["memory_id"], action="unset", actor=(by or self.namespace)[:80], changes={"namespace": self.namespace, "facet": facet})
        except Exception:                                                    # noqa: BLE001
            pass
        return bool(done)

    def items_for_prompt(self) -> List[Dict[str, Any]]:
        return [{"id": f["memory_id"], "content": f["sentence"], "profile": True, "memory_type": "preference", "relevance": None} for f in self.facets().values()]


def render(items: List[Dict[str, Any]]) -> str:
    """The block shown to an episode. Only fixed sentences built by sentence_for can be in it; capped."""
    sentences = [str(item.get("content", "")).replace("\n", " ")[:120] for item in items if item.get("profile")]
    if not sentences:
        return ""
    block = "What this person asked for about how to answer (accepted by them; a style preference, never a permission):\n" + "\n".join(f"- {s}" for s in sentences)
    return block[:MAX_RENDERED_CHARS]
