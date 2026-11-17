"""Grid-correlation factor (DESIGN §8 output, §7 effective count), measured on the null calibration's grids.

For every route of runs/null/state.json with a complete grid (null-grid rows), each grid point's M0 trades in the unseen years
(first walk-forward test month to the end of the period) are turned into a daily R series AT MID PRICES (r_mid: zero edge by
construction, also for the built-in-edge strategies, whose synthetic edge is added to r_gross only), on the same days as
engine.metrics.daily_sharpe (Amsterdam weekdays; a weekend exit counts on the next Monday). Two methods:
  A  correlation: the mean pairwise correlation rho of the daily series within a grid; and the participation ratio
     N^2 / sum(C_ij^2) of the correlation matrix C (an effective count of independent series).
  B  luck-bar match: with rho, simulate the best of N equicorrelated zero-edge Sharpes; the effective count k is the number of
     independent zero-edge strategies whose best has the same 95th percentile (the luck bar's own quantile):
     k = ln(0.95) / ln(Phi(q95)), q95 = 95th percentile of max of N standard normals with pairwise correlation rho.
  B' the same from the Sharpe values alone: 1 - rho_s = mean within-grid variance of the points' Sharpe / zero-edge variance
     (pooled default points of the 1,000 random strategies). Robust to a common shift of a grid (selection on the screen).
Usage: ~/.venvs/fastbt/bin/python -m tools.nullstats.grid_factor [--out data-checks/null/grid-factor.json]
"""
import argparse
import json
import os
import sys
from statistics import NormalDist

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from engine import metrics as M, pipeline as P  # noqa: E402

DAY = 86_400_000


def day_index(first_ms, end_ms):
    d0 = (first_ms + int(M.ams_offset_ms([first_ms])[0])) // DAY
    d1 = (end_ms + int(M.ams_offset_ms([end_ms])[0])) // DAY
    days = np.arange(d0, d1 + 1)
    return days[((days + 3) % 7) < 5]


def daily(r, exit_t, days):
    loc = exit_t + M.ams_offset_ms(exit_t)
    d = loc // DAY
    wd = (d + 3) % 7
    d = d + np.where(wd == 5, 2, np.where(wd == 6, 1, 0))
    s = np.zeros(len(days))
    i = np.searchsorted(days, d)
    ok = (i < len(days)) & (days[np.minimum(i, len(days) - 1)] == d)
    np.add.at(s, i[ok], r[ok])
    return s


def k_match(rho, n, sims=200_000, seed=1):
    """Effective independent count whose best-of-k 95th percentile equals that of n points with pairwise correlation rho."""
    if n <= 1:
        return 1.0
    rho = min(max(rho, 0.0), 0.999)
    rng = np.random.default_rng(seed)
    z = np.sqrt(rho) * rng.standard_normal((sims, 1)) + np.sqrt(1 - rho) * rng.standard_normal((sims, n))
    q = float(np.percentile(z.max(axis=1), 95))
    return float(np.log(0.95) / np.log(NormalDist().cdf(q)))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REPO, "data-checks", "null", "grid-factor.json"))
    a = ap.parse_args(argv)
    plan = {s["id"]: s for s in json.load(open(os.path.join(REPO, "null", "PLAN.json")))["strategies"]}
    S = json.load(open(os.path.join(REPO, "runs", "null", "state.json")))
    rows = {}
    for f in sorted(os.listdir(os.path.join(REPO, "ledger"))):
        if f.endswith(".jsonl"):
            for line in open(os.path.join(REPO, "ledger", f)):
                if line.strip():
                    r = json.loads(line)
                    rows[r["test_id"]] = r
    first, end = P.month_ms(P.TH["walk_forward"]["first_test"]), P.month_ms("2024-12", 1)
    days = day_index(first, end)
    zero = np.array([S[i]["screen"]["sharpe_unseen_mid"] for i in S if plan[i]["kind"] == "random"
                     and S[i]["screen"].get("sharpe_unseen_mid") is not None], float)
    var0 = float(zero.var(ddof=1))
    grids = []
    for sid, st in S.items():
        s = plan[sid]
        for rr in st.get("routes", []):
            g = rr.get("grid")
            if not g or None in g:
                continue
            ser, sh = [], []
            for t in g:
                row = rows[t]
                lg = P.load_logs(os.path.join(REPO, row["run_path"]), row["symbols"], ["M0"])["M0"]
                k = lg["entry_t"] >= first
                x = daily(lg["r_mid"][k].astype(float), lg["exit_t"][k], days)
                ser.append(x)
                sh.append(x.mean() / x.std(ddof=1) * np.sqrt(252) if x.std() > 0 else np.nan)
            X = np.array(ser)
            keep = X.std(axis=1) > 0
            X, sh = X[keep], np.array(sh)[keep]
            n = len(X)
            if n < 2:
                continue
            C = np.corrcoef(X)
            off = C[~np.eye(n, dtype=bool)]
            grids.append({"id": sid, "route": rr["route"], "kind": s["kind"], "class": s["class"], "n": n,
                          "shape": s["grid_shape"], "rho": float(off.mean()), "rho_min": float(off.min()),
                          "participation": float(n * n / (C ** 2).sum()), "sharpe_var_within": float(np.var(sh, ddof=1))})
    out = {"about": __doc__.split("\n")[0], "method": "see module docstring", "zero_edge_sharpe_var": round(var0, 5),
           "grids": len(grids), "by": {}}

    def summ(gs):
        n = int(np.median([g["n"] for g in gs]))
        rho = float(np.mean([g["rho"] for g in gs]))
        rho_s = 1 - float(np.mean([g["sharpe_var_within"] for g in gs])) / var0
        return {"grids": len(gs), "points_median": n, "rho_mean": round(rho, 3),
                "rho_p10_p90": [round(float(np.percentile([g["rho"] for g in gs], q)), 3) for q in (10, 90)],
                "participation_mean": round(float(np.mean([g["participation"] for g in gs])), 2),
                "k_eff_from_rho": round(k_match(rho, n), 2), "rho_from_sharpe_dispersion": round(rho_s, 3),
                "k_eff_from_sharpe_dispersion": round(k_match(rho_s, n), 2)}
    out["by"]["all"] = summ(grids)
    for c in "ABC":
        gs = [g for g in grids if g["class"] == c]
        if gs:
            out["by"][f"class {c}"] = summ(gs)
    for n in sorted({g["n"] for g in grids}):
        out["by"][f"{n} points"] = summ([g for g in grids if g["n"] == n])
    # the null's third axis (entry_variant) draws new random entries, so points along it are near-independent by construction;
    # only the stop / exit axes behave like a real parameter grid
    ent = lambda g: len(g["shape"]) == 3 and g["shape"][2] > 1
    for name, sel in (("stop / exit axes only", lambda g: not ent(g)), ("with the entry-variant axis", ent)):
        gs = [g for g in grids if sel(g)]
        if gs:
            out["by"][name] = summ(gs)
            for c in "ABC":
                gc = [g for g in gs if g["class"] == c]
                if gc:
                    out["by"][f"{name}, class {c}"] = summ(gc)
    exit_only = [g for g in grids if not ent(g)]
    rho_x = float(np.mean([g["rho"] for g in exit_only])) if exit_only else None
    rho_all = out["by"]["all"]["rho_mean"]
    out["k_eff_for_grid_size_at_rho_all"] = {str(n): round(k_match(rho_all, n), 2) for n in (3, 9, 12, 27)}
    if rho_x is not None:
        out["k_eff_for_grid_size_at_rho_stop_exit"] = {"rho": round(rho_x, 3),
                                                       **{str(n): round(k_match(rho_x, n), 2) for n in (3, 9, 12, 27)}}
    out["grids_detail"] = grids
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "grids_detail"}, indent=1))


if __name__ == "__main__":
    main()
