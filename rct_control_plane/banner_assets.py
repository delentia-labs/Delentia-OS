"""Static brand assets for the Rich-powered RCT launch header.

Block Unicode Design Specification
===================================
All wordmarks use Unicode box-drawing characters (═ ║ ╗ ╔ ╝ ╚) and FULL BLOCK (█).

Design rules:
  1. ALL lines within a constant are padded to EXACTLY EQUAL WIDTH
     → Rich's Align.center() treats the block as a single locked unit (no per-line jitter)
  2. Inter-letter gap  : built into letter trailing/leading spaces
  3. Word gap (RCT↔OS) : 5 explicit separator spaces → 6+ visible space between words
                         Word-gap (6) >> inter-letter gap (1-3) → clear "RCT OS" reading
  4. R design uses distinct rows 3-6 so it cannot be confused with letter A:
       - Row 3 is a SOLID FILL (bowl closes) — A has a hollow crossbar here
       - Row 4 is DIFFERENT from Row 2 (bowl-bottom hook) — A has identical legs here
       - Rows 5-6 show the leg shifted clearly to the RIGHT

Terminal compatibility:
  - VS Code integrated terminal (xterm.js)
  - Windows Terminal (Cascadia Code / JetBrains Mono / Fira Code)
  - Any modern terminal with complete Unicode monospace font support
"""

from __future__ import annotations

# ── Emblem Glyphs ─────────────────────────────────────────────────────────────

RCT_EMBLEM_WIDE = (
    "  ▗████▖     ●\n"
    "  ▐█▀▀██▖\n"
    "  ▐█ ▗▄█▌\n"
    "  ▐█▄███▌\n"
    "   ▀▀  ▀"
)

RCT_EMBLEM_COMPACT = (
    " ▗██▖ ●\n"
    " ▐█▛▙\n"
    " ▐██▛"
)

# ── Block Unicode Wordmarks ────────────────────────────────────────────────────
#
# LETTER SLOT WIDTHS:
#   R = 9  ·  C = 8  ·  T = 9  ·  word_gap = 5  ·  O = 9  ·  S = 9
#   Total "RCT OS" = 9+8+9+5+9+9 = 49 cols × 6 rows
#   Total "RCT"    = 9+8+9        = 26 cols × 6 rows
#
# R LETTER ANATOMY — Full redesign from scratch (6 rows × 9 cols):
#
#   Col:   1 2 3 4 5 6 7 8 9
#   Row 1: █ █ █ █ █ █ ╗ · ·   ← Top bar: solid cols 1-6, ╗ corner at col 7
#   Row 2: █ █ ╔ ═ ═ █ █ ╗ ·   ← Bowl frame: wall ██, inner ╔══, right ██╗
#   Row 3: █ █ █ █ █ █ ╔ ╝ ·   ← Bowl body: SOLID cols 1-6, closing compound ╔╝
#   Row 4: █ █ ╔ ═ █ █ ╝ · ·   ← Junction: inner floor ╔═ (cols 3-4), leg ██ (cols 5-6), ╝ (col 7)
#   Row 5: █ █ ║ · · █ █ ╗ ·   ← Legs: left bar ██║ (cols 1-3), right leg ██╗ (cols 6-8)
#   Row 6: ╚ ═ ╝ · · ╚ ═ ╝ ·   ← Feet: left ╚═╝ (cols 1-3), right ╚═╝ (cols 6-8)
#
#   DIAGONAL LEG TRACE (left-edge column per row):
#     Row 3: col 1-6 (full solid bowl body)
#     Row 4: col 5-6 ← leg emerges from solid bowl at col 5
#     Row 5: col 6-8 ← leg shifts +1 RIGHT (col 5→col 6) = diagonal going DOWN-RIGHT ✓
#     Row 6: col 6-8 ← foot aligns with leg above
#
#   CONNECTION RAIL AT COL 6 (spine of diagonal):
#     Row 3: █ (bowl solid) → Row 4: █ (leg top) → Row 5: █ (leg body) → Row 6: ╚ (foot) ✓

# ─────────────────────────────────────────────────────────────────────────────
# "RCT OS" — 49 cols × 6 rows
# ─────────────────────────────────────────────────────────────────────────────
RCT_WORDMARK_BLOCK = (
    "██████╗   ██████╗████████╗      ██████╗  ███████╗\n"
    "██╔══██╗ ██╔════╝╚══██╔══╝     ██╔═══██╗ ██╔════╝\n"
    "██████╔╝ ██║        ██║        ██║   ██║ ███████╗\n"
    "██╔═██╝  ██║        ██║        ██║   ██║ ╚════██║\n"
    "██║  ██╗ ╚██████╗   ██║        ╚██████╔╝ ███████║\n"
    "╚═╝  ╚═╝  ╚═════╝   ╚═╝         ╚═════╝  ╚══════╝"
)

# ─────────────────────────────────────────────────────────────────────────────
# "RCT" — 26 cols × 6 rows  (compact fallback, < 100 cols terminal)
# ─────────────────────────────────────────────────────────────────────────────
RCT_WORDMARK_BLOCK_COMPACT = (
    "██████╗   ██████╗████████╗\n"
    "██╔══██╗ ██╔════╝╚══██╔══╝\n"
    "██████╔╝ ██║        ██║   \n"
    "██╔═██╝  ██║        ██║   \n"
    "██║  ██╗ ╚██████╗   ██║   \n"
    "╚═╝  ╚═╝  ╚═════╝   ╚═╝   "
)

# ── Plain ASCII Fallback Wordmarks ────────────────────────────────────────────
# All lines padded to equal width. Used when box-drawing chars are unavailable.

# 31 cols × 5 rows
RCT_WORDMARK = (
    "RRR    CCC  TTTTT    OOO    SSS\n"
    "R  R  C       T     O   O  S   \n"
    "RRR   C       T     O   O   SS \n"
    "R  R  C       T     O   O     S\n"
    "R   R  CCC    T      OOO   SSS "
)

# 55 cols × 5 rows
RCT_WORDMARK_HERO = (
    "RRRRR      CCCCCC   TTTTTTTTT      OOOOOOO      SSSSSSS\n"
    "RR   RR   CC           TTT        OOO   OOO   SSS      \n"
    "RRRRR    CC            TTT        OO     OO     SSSS   \n"
    "RR  RR   CC            TTT        OOO   OOO        SSS \n"
    "RR   RR   CCCCCC       TTT         OOOOOOO    SSSSSSS  "
)