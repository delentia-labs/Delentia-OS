"use client";

import { useEffect, useState } from "react";

/**
 * The Delentia mark, drawn from the Architect's logo
 * (Delentia-Website/public/DelentiaIcon.png): a database symbol - three equal
 * bars - with a pair of eyes on the top layer. Geometry is measured from the
 * 500 x 500 original; colours are the logo's own.
 */
export const MARK = {
  leaf: "#80C961", // top bar and the rings around the eyes
  fern: "#519037", // middle bar
  pine: "#315721", // bottom bar
  eye: "#2C2525",
} as const;

type MarkProps = { size?: number; title?: string; className?: string };

/** Vector mark (bars + eyes, no tile), for the sidebar and small places. */
export function DelentiaMark({ size = 28, title = "Delentia", className }: MarkProps) {
  return (
    <svg viewBox="70 55 360 390" width={size} height={size} role="img" aria-label={title} className={className}>
      <title>{title}</title>
      <rect x="75" y="104" width="350" height="94" rx="14" fill={MARK.leaf} />
      <circle cx="172" cy="120.5" r="60.5" fill={MARK.leaf} />
      <circle cx="327" cy="120.5" r="60.5" fill={MARK.leaf} />
      <circle cx="172" cy="120.5" r="46" fill={MARK.eye} />
      <circle cx="327" cy="120.5" r="46" fill={MARK.eye} />
      <rect x="75" y="222" width="350" height="97" rx="14" fill={MARK.fern} />
      <rect x="75" y="343" width="350" height="97" rx="14" fill={MARK.pine} />
    </svg>
  );
}

// 26 x 28 pixel grid, symmetric by construction (column c mirrors 25 - c).
// L leaf, F fern, P pine, E eye, "." empty. Rendered two rows per text line
// with half-block characters, the way a terminal draws pixel art.
const OPEN: string[] = [
  ".....LLLLL......LLLLL.....",
  "....LLEEELL....LLEEELL....",
  "...LLEEEEELL..LLEEEEELL...",
  ".LLLEEEEEEELLLLEEEEEEELLL.",
  "LLLLEEEEEEELLLLEEEEEEELLLL",
  "LLLLEEEEEEELLLLEEEEEEELLLL",
  "LLLLLEEEEELLLLLLEEEEELLLLL",
  "LLLLLLEEELLLLLLLLEEELLLLLL",
  "LLLLLLLLLLLLLLLLLLLLLLLLLL",
  ".LLLLLLLLLLLLLLLLLLLLLLLL.",
  "..........................",
  "..........................",
  ".FFFFFFFFFFFFFFFFFFFFFFFF.",
  "FFFFFFFFFFFFFFFFFFFFFFFFFF",
  "FFFFFFFFFFFFFFFFFFFFFFFFFF",
  "FFFFFFFFFFFFFFFFFFFFFFFFFF",
  "FFFFFFFFFFFFFFFFFFFFFFFFFF",
  "FFFFFFFFFFFFFFFFFFFFFFFFFF",
  ".FFFFFFFFFFFFFFFFFFFFFFFF.",
  "..........................",
  "..........................",
  ".PPPPPPPPPPPPPPPPPPPPPPPP.",
  "PPPPPPPPPPPPPPPPPPPPPPPPPP",
  "PPPPPPPPPPPPPPPPPPPPPPPPPP",
  "PPPPPPPPPPPPPPPPPPPPPPPPPP",
  "PPPPPPPPPPPPPPPPPPPPPPPPPP",
  "PPPPPPPPPPPPPPPPPPPPPPPPPP",
  ".PPPPPPPPPPPPPPPPPPPPPPPP.",
];

// Blink: the eyes close to a single line across their middle row.
const CLOSED = OPEN.map((row, r) => (r >= 1 && r <= 7 && r !== 5 ? row.replace(/E/g, "L") : row));

const COLOR: Record<string, string | null> = { L: MARK.leaf, F: MARK.fern, P: MARK.pine, E: MARK.eye, ".": null };

function pixels(grid: string[]) {
  const out: { x: number; y: number; fill: string }[] = [];
  grid.forEach((row, y) => {
    [...row].forEach((cell, x) => {
      const fill = COLOR[cell];
      if (fill) out.push({ x, y, fill });
    });
  });
  return out;
}

const OPEN_PIXELS = pixels(OPEN);
const CLOSED_PIXELS = pixels(CLOSED);

/** Pixel-art mark for the chat banner (the spot Hermes gives its ASCII art). Blinks once after load
 *  (skipped when the user prefers reduced motion). */
export function PixelMark() {
  const [closed, setClosed] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const shut = window.setTimeout(() => setClosed(true), 900);
    const open = window.setTimeout(() => setClosed(false), 1060);
    return () => {
      window.clearTimeout(shut);
      window.clearTimeout(open);
    };
  }, []);

  const cells = closed ? CLOSED_PIXELS : OPEN_PIXELS;
  // Drawn as square pixels (crisp edges) rather than half-block characters:
  // font glyphs leave gaps between text rows at small sizes.
  return (
    <svg viewBox="0 0 26 28" width={130} height={140} role="img" aria-label="Delentia" shapeRendering="crispEdges" className="desk-pixelmark">
      {cells.map((c) => <rect key={`${c.x}-${c.y}`} x={c.x} y={c.y} width={1.02} height={1.02} fill={c.fill} />)}
    </svg>
  );
}
