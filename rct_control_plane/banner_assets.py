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
#   Row 4: █ █ ╔ ═ █ ▌ ╝ · ·   ← Junction: ╔═ (cols3-4), leg █ (col5 full), ▌ half-taper (col6=right edge at 5.5), ╝ (col7)
#   Row 5: █ █ ║ · · █ █ ╗ ·   ← Legs: left bar ██║ (cols 1-3), right leg ██╗ (cols 6-8)
#   Row 6: ╚ ═ ╝ · · ╚ ═ ╝ ·   ← Feet: left ╚═╝ (cols 1-3), right ╚═╝ (cols 6-8)
#
#   DIAGONAL LEG TRACE (visual edges per row):
#     Row 3: col 1-6   ← full solid bowl body
#     Row 4: col 5–5.5 ← █ at col5 (full) + ▌ at col6 (LEFT HALF = right edge at 5.5)
#                         RIGHT EDGE TAPERS at 5.5 = leg “pointingtoward” col6 below
#     Row 5: col 6-8   ← leg expands full-width at col6 = natural rightward continuation
#     Row 6: col 6-8   ← foot aligns with leg above
#
#   WHY ▌ (U+258C LEFT HALF BLOCK) at col6 in Row4:
#     The R's diagonal leg slants LEFT→RIGHT (upper-left to lower-right).
#     Using ▌ at col6 fills only the LEFT half, placing the right edge at "col 5.5".
#     In Row5, col6 becomes fully solid █ — the transition:
#       Row4 col6: ▌ (left half only) → Row5 col6: █ (fully solid)
#     Creates sub-column taper: the leg NARROWS on the right as it descends,
#     then EXPANDS in Row5, producing a natural diagonal dimension ✓
#
#   CONNECTION RAIL AT COL 5-6 (diagonal spine):
#     Row 3: col5=█, col6=█ (bowl solid) → Row4: col5=█, col6=▌ (taper) → Row5: col6=█ (leg) ✓

# ─────────────────────────────────────────────────────────────────────────────
# "RCT OS" — 49 cols × 6 rows
# ─────────────────────────────────────────────────────────────────────────────
RCT_WORDMARK_BLOCK = (
    "██████╗   ██████╗████████╗      ██████╗  ███████╗\n"
    "██╔══██╗ ██╔════╝╚══██╔══╝     ██╔═══██╗ ██╔════╝\n"
    "██████╔╝ ██║        ██║        ██║   ██║ ███████╗\n"
    "██╔═█▌╝  ██║        ██║        ██║   ██║ ╚════██║\n"
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
    "██╔═█▌╝  ██║        ██║   \n"
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