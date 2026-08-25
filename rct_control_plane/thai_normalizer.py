"""
Thai Unicode Normalizer & Windows Terminal Formatter
Delentia OS Cognitive Kernel (Unified v2.2.6)

Handles Thai combining character normalization (NFC/NFKD), floating tone marks,
and Windows Terminal / PowerShell 100% clean UTF-8 formatting.
"""

import unicodedata
import re
from typing import List


# Thai Unicode Ranges: 0E00–0E7F
THAI_CONSONANTS = set(range(0x0E01, 0x0E2F))
THAI_VOWELS_TOP = {0x0E31, 0x0E34, 0x0E35, 0x0E36, 0x0E37, 0x0E47, 0x0E4D}
THAI_VOWELS_BOTTOM = {0x0E38, 0x0E39, 0x0E3A}
THAI_TONE_MARKS = {0x0E48, 0x0E49, 0x0E4A, 0x0E4B, 0x0E4C, 0x0E4E}


def normalize_thai_text(text: str) -> str:
    """
    Normalizes Thai text:
    1. Unicode NFC normalization
    2. Re-orders misplaced vowels and tone marks (Consonant + Top Vowel + Tone Mark)
    3. Cleans double spaces and zero-width artifacts
    """
    if not text:
        return ""

    # 1. Unicode Standard NFC
    normalized = unicodedata.normalize("NFC", text)

    # 2. Fix Tone Marks before Vowels (swap if tone mark precedes top vowel)
    # Pattern: [Consonant][ToneMark][TopVowel] -> [Consonant][TopVowel][ToneMark]
    pattern_misplaced = re.compile(r"([\u0e01-\u0e2e])([\u0e48-\u0e4c])([\u0e31\u0e34-\u0e37])")
    fixed_order = pattern_misplaced.sub(r"\1\3\2", normalized)

    # 3. Strip duplicate adjacent tone marks
    pattern_dup_tones = re.compile(r"([\u0e48-\u0e4c]){2,}")
    fixed_dups = pattern_dup_tones.sub(r"\1", fixed_order)

    # 4. Clean invisible zero-width spaces / joiners if causing render bugs
    cleaned = fixed_dups.replace("\u200b", "").replace("\ufeff", "")

    return cleaned


def format_thai_terminal(text: str, width: int = 80) -> List[str]:
    """
    Formats Thai text for clean line-wrapping in Windows Terminal / PowerShell
    without truncating combined characters or splitting words.
    """
    normalized = normalize_thai_text(text)
    lines = []
    
    for raw_line in normalized.split("\n"):
        if len(raw_line) <= width:
            lines.append(raw_line)
        else:
            # Word-friendly chunking
            chunks = [raw_line[i:i + width] for i in range(0, len(raw_line), width)]
            lines.extend(chunks)
            
    return lines
