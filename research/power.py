"""
Power by simulation that keeps the clustering (protocol section 17: "calculate final power with a simulation that keeps the real clustering").

The rough formula n = (1.96 + 0.84)^2 * q / delta^2 treats every pair as independent and needs q, the share of pairs that disagree, which nobody knows before a pilot.
This simulates what the study will actually do: units (tasks or trajectories) differ in how easy they are; each unit is run under two arms for k episodes and its success
rate is averaged; the paired differences are bootstrapped over units; the study "wins" when the lower end of the 95% interval is above zero. Power = the share of simulated
studies that win.

    python research/power.py                       # the table the Round 64 report quotes
    python research/power.py --effect 0.10 --base 0.55 --concentration 4 --episodes 2.5

Assumptions to replace with pilot numbers: the baseline success rate (--base), how different units are (--concentration: small = very different, large = alike), and how many episodes
make up a unit (--episodes). Outcomes inside a unit are Bernoulli draws of the unit's own success rate under each arm; the two arms see the same unit (paired).
"""
from __future__ import annotations

import argparse
from typing import List, Sequence

import numpy as np


def simulate_power(n_units: int, effect: float, base: float, concentration: float, episodes: int, *, sims: int = 400, boot: int = 400, seed: int = 20261009) -> float:
    rng = np.random.default_rng(seed + n_units)
    a, b = base * concentration, (1.0 - base) * concentration
    wins = 0
    for _ in range(sims):
        p_control = rng.beta(a, b, size=n_units)
        p_treat = np.clip(p_control + effect, 0.0, 1.0)
        y_control = rng.binomial(episodes, p_control) / episodes
        y_treat = rng.binomial(episodes, p_treat) / episodes
        diff = y_treat - y_control
        idx = rng.integers(0, n_units, size=(boot, n_units))
        lower = np.percentile(diff[idx].mean(axis=1), 2.5)
        wins += int(lower > 0)
    return wins / sims


def smallest_n(effect: float, base: float, concentration: float, episodes: int, target: float = 0.8, grid: Sequence[int] = (20, 40, 60, 80, 120, 160, 240, 320, 480, 640, 960)) -> int | None:
    for n in grid:
        if simulate_power(n, effect, base, concentration, episodes) >= target:
            return n
    return None


def table(base: float, concentration: float, episodes: int, effects: Sequence[float] = (0.05, 0.10, 0.20), sizes: Sequence[int] = (40, 80, 160, 236, 320, 480)) -> str:
    lines: List[str] = [f"baseline success {base:.0%}, units differ with concentration {concentration}, {episodes} episode(s) per unit and arm; power = share of 400 simulated studies whose 95% interval lies above zero", "",
                        "| units | " + " | ".join(f"effect +{e * 100:.0f} pp" for e in effects) + " |", "|---|" + "---|" * len(effects)]
    for n in sizes:
        lines.append(f"| {n} | " + " | ".join(f"{simulate_power(n, e, base, concentration, episodes):.0%}" for e in effects) + " |")
    need = ", ".join(f"+{e * 100:.0f} pp: {smallest_n(e, base, concentration, episodes) or '> 960'} units" for e in effects)
    lines += ["", f"units needed for 80% power on the grid {{20..960}}: {need}"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", type=float, default=0.55)
    parser.add_argument("--concentration", type=float, default=4.0)
    parser.add_argument("--episodes", type=float, default=2.5)
    parser.add_argument("--effect", type=float, default=None)
    args = parser.parse_args()
    episodes = max(1, round(args.episodes))
    if args.effect is not None:
        print(table(args.base, args.concentration, episodes, effects=(args.effect,)))
    else:
        print(table(args.base, args.concentration, episodes))
        print()
        print(table(args.base, 12.0, episodes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
