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

RCT_EMBLEM_WIDE = "  ▗████▖     ●\n  ▐█▀▀██▖\n  ▐█ ▗▄█▌\n  ▐█▄███▌\n   ▀▀  ▀"

RCT_EMBLEM_COMPACT = " ▗██▖ ●\n ▐█▛▙\n ▐██▛"

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
#   Row 4: █ █ ╔ ▐ █ ▌ ╝ · ·   ← Junction: ╔ (col3), ▐ right-half (col4.5 start), █ full (col5), ▌ left-half (col5.5 end), ╝ (col7)
#   Row 5: █ █ ║ · · █ █ ╗ ·   ← Legs: left bar ██║ (cols 1-3), right leg ██╗ (cols 6-8)
#   Row 6: ╚ ═ ╝ · · ╚ ═ ╝ ·   ← Feet: left ╚═╝ (cols 1-3), right ╚═╝ (cols 6-8)
#
#   DIAGONAL LEG TRACE (visual edges per row):
#     Row 3: col 1-6   ← full solid bowl body
#     Row 4: col 4.5–5.5 ← ▐ (col4 right-half) + █ (col5 full) + ▌ (col6 left-half)
#                         SYMMETRIC soft edges: left edge at 4.5, right edge at 5.5
#                         = perfectly balanced, 1-col-wide leg centered at col 5 ✓
#     Row 6: col 6-8   ← foot aligns with leg above
#
#   WHY ▐+█+▌ (RIGHT HALF + FULL + LEFT HALF) in Row4:
#     The R's diagonal leg needs maximum balance and visual dimension.
#     ▐ at col4: fills RIGHT half only → left edge at "col 4.5"
#     █ at col5: fully solid → center weight
#     ▌ at col6: fills LEFT half only → right edge at "col 5.5"
#     Together: a 1-column-wide solid leg with SOFT HALF-BLOCK edges on BOTH sides,
#     centered at col5 — the most symmetric and dimensionally balanced design.
#     Row4 → Row5 diagonal: col5 center (Row4) → col6 left (Row5) = +1 col shift ✓
#
#   CONNECTION RAIL AT COL 5-6 (diagonal spine):
#     Row 3: col5=█, col6=█ (bowl solid) → Row4: col5=█, col6=▌ (taper) → Row5: col6=█ (leg) ✓

# ─────────────────────────────────────────────────────────────────────────────
# "RCT OS" — 49 cols × 6 rows
# ─────────────────────────────────────────────────────────────────────────────
RCT_WORDMARK_BLOCK = (
    " ██████╗ ███████╗██╗     ███████╗███╗   ██╗████████╗██╗ █████╗      ██████╗ ███████╗\n"
    " ██╔══██╗██╔════╝██║     ██╔════╝████╗  ██║╚══██╔══╝██║██╔══██╗    ██╔═══██╗██╔════╝\n"
    " ██║  ██║█████╗  ██║     █████╗  ██╔██╗ ██║   ██║   ██║███████║    ██║   ██║███████╗\n"
    " ██║  ██║██╔══╝  ██║     ██╔══╝  ██║ ╚████║   ██║   ██║██╔══██║    ██║   ██║╚════██║\n"
    " ██████╔╝███████╗███████╗███████╗██║  ╚███║   ██║   ██║██║  ██║    ╚██████╔╝███████║\n"
    " ╚═════╝ ╚══════╝╚══════╝╚══════╝╚═╝   ╚══╝   ╚═╝   ╚═╝╚═╝  ╚═╝     ╚═════╝ ╚══════╝"
)

# ─────────────────────────────────────────────────────────────────────────────
# "RCT" — 26 cols × 6 rows  (compact fallback, < 100 cols terminal)
# ─────────────────────────────────────────────────────────────────────────────
RCT_WORDMARK_BLOCK_COMPACT = (
    " ██████╗ ███████╗██╗     ███████╗███╗   ██╗████████╗██╗ █████╗ \n"
    " ██╔══██╗██╔════╝██║     ██╔════╝████╗  ██║╚══██╔══╝██║██╔══██╗\n"
    " ██║  ██║█████╗  ██║     █████╗  ██╔██╗ ██║   ██║   ██║███████║\n"
    " ██║  ██║██╔══╝  ██║     ██╔══╝  ██║ ╚████║   ██║   ██║██╔══██║\n"
    " ██████╔╝███████╗███████╗███████╗██║  ╚███║   ██║   ██║██║  ██║\n"
    " ╚═════╝ ╚══════╝╚══════╝╚══════╝╚═╝   ╚══╝   ╚═╝   ╚═╝╚═╝  ╚═╝"
)

# ── Plain ASCII Fallback Wordmarks ────────────────────────────────────────────
# All lines padded to equal width. Used when box-drawing chars are unavailable.

# 31 cols × 5 rows
RCT_WORDMARK = (
    "DDDD   EEEE  L     EEEE  N   N TTTTT  I   AAA      OOO   SSS \n"
    "D   D  E     L     E     NN  N   T    I  A   A    O   O S    \n"
    "D   D  EEE   L     EEE   N N N   T    I  AAAAA    O   O  SSS \n"
    "D   D  E     L     E     N  NN   T    I  A   A    O   O     S\n"
    "DDDD   EEEE  LLLLL EEEE  N   N   T    I  A   A     OOO   SSS "
)

# 55 cols × 5 rows
RCT_WORDMARK_HERO = (
    "DDDDDDD   EEEEEEEE L        EEEEEEEE N     N TTTTTTTTT I   AAAAA       OOOOOOO   SSSSSSS \n"
    "D      D  E        L        E        NN    N     TTT   I  A     A     O       O S        \n"
    "D      D  EEEEE    L        EEEEE    N N   N     TTT   I AAAAAAAA     O       O  SSSSSS  \n"
    "D      D  E        L        E        N  N  N     TTT   I A      A     O       O        S \n"
    "DDDDDDD   EEEEEEEE LLLLLLLL EEEEEEEE N   N N     TTT   I A      A      OOOOOOO   SSSSSSS "
)
