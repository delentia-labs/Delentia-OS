"use client";

import { useEffect, useState } from "react";
import type { Mood } from "@/lib/run-state";

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

const COLOR: Record<string, string | null> = { L: MARK.leaf, F: MARK.fern, P: MARK.pine, E: MARK.eye, ".": null };

type Pixel = { x: number; y: number; fill: string };

function pixels(grid: string[], keep: (cell: string, row: number) => string | null): Pixel[] {
  const out: Pixel[] = [];
  grid.forEach((row, y) => {
    [...row].forEach((cell, x) => {
      const mapped = keep(cell, y);
      const fill = mapped ? COLOR[mapped] : null;
      if (fill) out.push({ x, y, fill });
    });
  });
  return out;
}

// The face is drawn in two layers so the eyes can move: the body with the eyes painted over in the
// ring colour, and the eyes on top. Moving or closing the eyes only changes the top layer. Every
// eye pixel can slide one pixel sideways and still lie inside its ring (rows 1-7 of the grid).
const BODY_PIXELS = pixels(OPEN, (cell) => (cell === "E" ? "L" : cell));
const EYES_OPEN = pixels(OPEN, (cell) => (cell === "E" ? "E" : null));
const EYES_CLOSED = pixels(OPEN, (cell, row) => (cell === "E" && row === 5 ? "E" : null)); // one line across the middle

type Look = -1 | 0 | 1;

/** A plan for the idle loop: what to do, and how long to wait before the next thing. Pure, so it can
 *  be tested; both rolls are numbers in [0, 1) and are independent (what it does must not decide how
 *  long it waits, or the rarer actions would also be the slower ones). */
export function nextIdleStep(roll: number, look: Look, waitRoll: number): { action: "blink" | "double_blink" | "look"; look: Look; waitMs: number } {
  const waitMs = 1200 + Math.floor(waitRoll * 2200);   // 1.2 to 3.4 seconds between things
  if (roll < 0.4) return { action: "blink", look, waitMs };
  if (roll < 0.5) return { action: "double_blink", look, waitMs };
  const options: Look[] = look === 0 ? [-1, 1] : [0, look === -1 ? 1 : -1];   // from the middle go left or right; from a side go back or across
  return { action: "look", look: options[Math.floor(roll * 1000) % options.length], waitMs };
}

const BLINK_MS = 140;

// Eyes for the states the runtime reports. Each is a small pixel pattern drawn over the same body, so the mark is
// always recognisably the Delentia mark; only the eyes say what the agent is doing.
const EYE_ROWS = (from: number) => pixels(OPEN, (cell, row) => (cell === "E" && row >= from ? "E" : null));
const EYES_HAPPY: Pixel[] = [                       // two arcs, ^ ^ : the work is done
  [7, 3], [6, 4], [8, 4], [5, 5], [9, 5], [18, 3], [17, 4], [19, 4], [16, 5], [20, 5],
].map(([x, y]) => ({ x, y, fill: MARK.eye }));
const RUST = "#E2694C";
const EYES_FROWN: Pixel[] = EYE_ROWS(4).map((p) => ({ ...p, fill: RUST }));       // the top of each eye is cut off: something was stopped
const EYES_LOOK_UP = EYES_OPEN;                     // moved up one pixel with a transform

const REDUCED = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Pixel-art mark. With no `mood` it idles (blinks, glances, bobs). With a mood it shows what the agent is really doing, and the
 *  mood comes from the runtime's own events (see lib/run-state.ts), never from the interface guessing:
 *  thinking = eyes scan slowly, acting = scan fast and bob fast, waiting = looking up for a human, blocked = a rust frown, done = ^ ^.
 *  Nothing moves under prefers-reduced-motion (the mood is still shown by the eyes), and the loops pause while the tab is hidden. */
export function PixelMark({ mood = "idle", size = 130 }: { mood?: Mood; size?: number }) {
  // The animation state remembers which mood it belongs to, so a mood change starts from a neutral face without setting state inside the effect.
  const [anim, setAnim] = useState<{ mood: Mood; closed: boolean; look: Look }>({ mood, closed: false, look: 0 });
  const closed = anim.mood === mood && anim.closed;
  const look: Look = anim.mood === mood ? anim.look : 0;

  useEffect(() => {
    if (REDUCED()) return;
    const setClosed = (value: boolean) => setAnim((a) => ({ mood, closed: value, look: a.mood === mood ? a.look : 0 }));
    const setLook = (value: Look) => setAnim((a) => ({ mood, closed: a.mood === mood ? a.closed : false, look: value }));
    let alive = true;
    let timer: number | undefined;
    let current: Look = 0;
    const later = (fn: () => void, ms: number) => {
      timer = window.setTimeout(() => { if (alive) fn(); }, ms);
    };
    const blink = (then: () => void) => {
      setClosed(true);
      later(() => { setClosed(false); then(); }, BLINK_MS);
    };

    if (mood === "idle") {
      const step = () => {
        if (document.hidden) { later(step, 1000); return; }
        const plan = nextIdleStep(Math.random(), current, Math.random());
        const done = () => later(step, plan.waitMs);
        if (plan.action === "blink") blink(done);
        else if (plan.action === "double_blink") blink(() => later(() => blink(done), BLINK_MS));
        else { current = plan.look; setLook(plan.look); done(); }
      };
      later(step, 900);                              // the first blink comes soon after the page opens
    } else if (mood === "thinking" || mood === "acting") {
      const every = mood === "acting" ? 260 : 650;   // scanning left and right: faster while a tool is running
      const step = () => {
        if (!document.hidden) { current = current === -1 ? 1 : -1; setLook(current); }
        later(step, every);
      };
      later(step, every);
    } else if (mood === "waiting") {
      const step = () => {
        if (document.hidden) { later(step, 1000); return; }
        blink(() => later(step, 3200));              // a slow blink while it waits for a person
      };
      later(step, 2200);
    }
    return () => { alive = false; window.clearTimeout(timer); };
  }, [mood]);

  const eyes = mood === "done" ? EYES_HAPPY : mood === "blocked" ? EYES_FROWN : closed ? EYES_CLOSED : mood === "waiting" ? EYES_LOOK_UP : EYES_OPEN;
  const up = mood === "waiting" && !closed ? -1 : 0;
  const fast = mood === "acting" ? " desk-pixelmark-fast" : "";
  // Drawn as square pixels (crisp edges) rather than half-block characters:
  // font glyphs leave gaps between text rows at small sizes.
  return (
    <svg viewBox="0 0 26 28" width={size} height={Math.round(size * 28 / 26)} role="img" aria-label={`Delentia, ${mood}`} data-mood={mood}
      shapeRendering="crispEdges" className={`desk-pixelmark${fast}`}>
      <g>
        {BODY_PIXELS.map((c) => <rect key={`b${c.x}-${c.y}`} x={c.x} y={c.y} width={1.02} height={1.02} fill={c.fill} />)}
        <g style={{ transform: `translate(${look}px, ${up}px)`, transition: "transform 120ms steps(2, end)" }}>
          {eyes.map((c) => <rect key={`e${c.x}-${c.y}`} x={c.x} y={c.y} width={1.02} height={1.02} fill={c.fill} />)}
        </g>
      </g>
    </svg>
  );
}
