"""Power of the PL1 U1 rule (research/LAUNCH_PL1_CRITERIA_R116.md): TC-003 tier V has 7 fixed tasks, r repeats per task per arm, stratified interval.
Run: python research/pl1/power_u1_r116.py  (seeded, about 10 s; prints the table quoted in the criteria)."""
import random, math
def sim(r, td, margin, mean_p=0.64, spread=0.2, n=3000, tasks=7, seed=2):
    rng = random.Random(seed); ok = 0
    for _ in range(n):
        ps = [min(0.98, max(0.02, rng.gauss(mean_p, spread))) for _ in range(tasks)]
        dsum = 0.0; var = 0.0
        for p in ps:
            q = min(0.99, max(0.0, p + td))
            b = sum(rng.random() < p for _ in range(r)) / r
            d = sum(rng.random() < q for _ in range(r)) / r
            dsum += d - b
            # stratified variance (tasks fixed), with a floor so 0/r and r/r do not give 0
            bb = min(max(b, 0.5/r), 1-0.5/r); dd = min(max(d, 0.5/r), 1-0.5/r)
            var += bb*(1-bb)/r + dd*(1-dd)/r
        est = dsum / tasks; se = math.sqrt(var) / tasks
        if est - 1.96*se > -margin: ok += 1
    return ok / n
for margin in (0.10, 0.15, 0.20):
    for r in (6, 12, 24, 36):
        print(f"margin {margin:.2f} r {r:2d} n/arm {7*r:3d}: power(diff 0) {sim(r,0.0,margin):.2f}  false pass(diff -margin) {sim(r,-margin,margin):.3f}")
