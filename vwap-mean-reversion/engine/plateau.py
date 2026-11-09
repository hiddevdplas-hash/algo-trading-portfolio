#!/usr/bin/env python3
"""tools/split_plateau.py on a stats-only grid (run_grid.py --stats): the same rules, the same report.

Reads <run>/stats.npz + grid.json and applies PROTOCOL v2's split-sample plateau check exactly as split_plateau.py does
on trade lists (thresholds, near-miss tolerance, top-3 rule per half, ±1-step box over every numeric parameter,
categoricals fixed, passes without trades left out). The neighbour search runs in numba, so millions of passes are fine.

Usage: ~/.venvs/fastbt/bin/python tools/fastbt/plateau.py <run folder> [--top 6] [--min-trades 100] [--diagnose] [--dump FILE]
       [--regions FILE] [--only KEY=VALUE ...]
--only keeps just the passes with that grid value (e.g. WeeklyForceCloseFriday=1 on a Weekly run made before Friday close was fixed).
(--half-top is fixed by the stats run: engine.py computes the top-3 sum per half.)
"""
import argparse
import json
import os
import sys
from itertools import product

import numpy as np
from numba import njit, prange

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E  # noqa: E402

START, RISK, MIN_FIT_TRADES = 100000.0, 1000.0, 150
NOT_NUMERIC = ("Management", "SessionForceClose", "WeeklyForceCloseFriday", "BandTrailTrigger", "IntradaySource")
HALVES = ("H1", "H2")


def _num_like(x):
    return x.replace(".", "", 1).replace("-", "", 1).isdigit()


def py_round(a, nd):
    """Python's round(x, nd) element-wise (correctly rounded; numpy's round can differ next to a half: those few values,
    and any that are not finite or very large, are redone with Python's round)."""
    a = np.asarray(a, dtype=np.float64)
    with np.errstate(invalid="ignore", over="ignore"):
        s = a * 10.0 ** nd
        out = np.round(a, nd)
        redo = np.nonzero(~(np.abs(s - np.floor(s) - 0.5) > 1e-6) | ~(np.abs(s) < 1e12))[0]
    for i in redo:
        out[i] = round(float(a[i]), nd)
    return out


@njit(cache=True, parallel=True)
def neighbour_stats(cand, coords, lut, strides, dims, num_dims, net, pf, fit, h1net, h1pf, h2net, h2pf):
    """For each candidate pass: number of neighbours in its ±1 box (numeric dims), share profitable and median PF in the
    full period and per half, and the plateau score (mean of max(fitness, 0))."""
    nd = len(num_dims)
    nbox = 3 ** nd
    out = np.zeros((len(cand), 8))
    for ci in prange(len(cand)):
        p = cand[ci]
        base = 0
        for dpos in range(coords.shape[1]):
            base += coords[p, dpos] * strides[dpos]
        pfs = np.empty(nbox)
        p1 = np.empty(nbox)
        p2 = np.empty(nbox)
        cnt = 0
        prof = 0.0
        prof1 = 0.0
        prof2 = 0.0
        fsum = 0.0
        for b in range(nbox):
            code = b
            flat = base
            ok = True
            for t in range(nd):
                off = code % 3 - 1
                code //= 3
                d = num_dims[t]
                c = coords[p, d] + off
                if c < 0 or c >= dims[d]:
                    ok = False
                    break
                flat += off * strides[d]
            if not ok:
                continue
            q = lut[flat]
            if q < 0:
                continue
            pfs[cnt] = pf[q]
            p1[cnt] = h1pf[q]
            p2[cnt] = h2pf[q]
            if net[q] > 0:
                prof += 1
            if h1net[q] > 0:
                prof1 += 1
            if h2net[q] > 0:
                prof2 += 1
            fsum += max(fit[q], 0.0)
            cnt += 1
        out[ci, 0] = cnt
        out[ci, 1] = prof / cnt
        out[ci, 2] = _median(pfs[:cnt])
        out[ci, 3] = prof1 / cnt
        out[ci, 4] = _median(p1[:cnt])
        out[ci, 5] = prof2 / cnt
        out[ci, 6] = _median(p2[:cnt])
        out[ci, 7] = fsum / cnt
    return out


@njit(cache=True)
def _median(a):
    """statistics.median: middle value, or the mean of the two middle values (inf-safe as in Python)."""
    n = len(a)
    s = np.sort(a)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def load(run):
    """grid.json, a column reader (chunk files of run_grid.run_stats, or the older stats.npy / float64 stats.npz) and the
    skipped flags."""
    info = json.load(open(os.path.join(run, "grid.json")))
    if os.path.isdir(os.path.join(run, "chunks")):
        import run_grid
        nchunks = -(-info["passes"] // info["chunk"])
        scale = np.array(info["scale"], dtype=np.float64)
        skipped = np.concatenate([np.load(os.path.join(run, "chunks", f"c{ci:05d}.npz"))["skipped"] for ci in range(nchunks)])
        if "stats" in np.load(os.path.join(run, "chunks", "c00000.npz")).files:      # chunks of the first format
            return info, Columns(run_grid.load_stats(run, nchunks)[0], scale), skipped
        return info, ChunkColumns(run, nchunks, len(skipped), scale), skipped
    if os.path.isfile(os.path.join(run, "stats.npy")):
        raw = np.load(os.path.join(run, "stats.npy"), mmap_mode="r")
        return info, Columns(raw, np.array(info["scale"], dtype=np.float64)), np.load(os.path.join(run, "skipped.npy"))
    z = np.load(os.path.join(run, "stats.npz"))
    return info, Columns(z["stats"], np.ones(z["stats"].shape[1])), z["skipped"]


class Columns:
    """Stats columns as float64 values, read one at a time (a whole grid's stats never sit in RAM as float64)."""

    def __init__(self, raw, scale):
        self.raw, self.scale = raw, scale

    def __len__(self):
        return self.raw.shape[0]

    def __call__(self, c):
        x = np.asarray(self.raw[:, c], dtype=np.float64)
        return x if self.scale[c] == 1.0 else x / self.scale[c]


class ChunkColumns(Columns):
    """The same from run_stats chunk files, one column at a time (the stats table is never in RAM as a whole)."""

    def __init__(self, run, nchunks, total, scale):
        self.run, self.nchunks, self.total, self.scale = run, nchunks, total, scale

    def __len__(self):
        return self.total

    def __call__(self, c):
        import run_grid
        x = np.concatenate([run_grid.stat_column(self.run, ci, c) for ci in range(self.nchunks)]).astype(np.float64)
        return x if self.scale[c] == 1.0 else x / self.scale[c]


def pass_table(info, S, skipped):
    """split_plateau's per-pass numbers that the neighbour search needs, for every pass (pass_stats + half_stats)."""
    n = S(E.ST_TRADES)
    have = (n > 0) & ~skipped
    first, last = S(E.ST_FIRST), S(E.ST_LAST)
    months = (last[have].max() - first[have].min()) / 1000 / 86400 / 30.44
    del first, last
    net = S(E.ST_NET)
    with np.errstate(divide="ignore", invalid="ignore"):
        gw, gl = S(E.ST_GW), S(E.ST_GL)
        pf = np.where(gl > 0, py_round(gw / np.where(gl > 0, gl, 1), 3), np.inf)
        del gw, gl
        # fitness (analyze_optimisation.metrics, cBot GetFitness v2 on the closed-balance DD)
        w = np.minimum(1.0, n / MIN_FIT_TRADES)
        fit = np.where(n == 0, -1e9, np.where(net <= 0, net, net / np.maximum(S(E.ST_DD), 0.01 * np.abs(START + net)) * w * w))
        del w
        T = {"have": have, "trades": n, "net": net, "pf": pf, "fitness": py_round(fit, 3), "months": months}
        del fit
        for h, c in zip(HALVES, (E.ST_H1, E.ST_H2)):
            T[h + "_net"] = S(c + 1)
            hgw, hgl = S(c + 2), S(c + 3)
            T[h + "_pf"] = np.where(hgl > 0, hgw / np.where(hgl > 0, hgl, 1), np.where(hgw > 0, 99.0, 0.0))
    return T


def cand_table(S, T, cand):
    """The rest of split_plateau's numbers, for the candidate passes only (arrays indexed like cand)."""
    C = {k: T[k][cand] for k in ("trades", "net", "pf", "H1_net", "H1_pf", "H2_net", "H2_pf")}
    n, net, months = C["trades"], C["net"], T["months"]
    with np.errstate(divide="ignore", invalid="ignore"):
        C["dd"] = py_round(100.0 * S(E.ST_DD)[cand] / START, 2)
        C["eq_dd"] = 100.0 * S(E.ST_EQDD)[cand] / START
        C["tpm"], C["Rpm"] = n / months, net / RISK / months
        C["net_wo_top5"] = net - S(E.ST_TOP5)[cand]
        C["news_share"] = np.where(net > 0, S(E.ST_NEWS)[cand] / net, np.nan)
        C["years"] = (S(E.ST_OUTSIDE)[cand] > 0).astype(np.int64)
        C["pos_years"] = np.zeros(len(cand), dtype=np.int64)
        for y in range(E.NYEARS):
            C["years"] += S(E.ST_YEAR_N + y)[cand] > 0
            C["pos_years"] += np.rint(S(E.ST_YEAR + y)[cand]) > 0           # round(v) > 0 (half to even)
        for h, c in zip(HALVES, (E.ST_H1, E.ST_H2)):
            hnet = C[h + "_net"]
            C[h + "_wo5"] = np.where(hnet > 0, (hnet - S(c + 4)[cand]) / hnet, -1.0)
    return C


GRADE = ("no", "near", "ok")


def grade(vals, strict, near):
    """split_plateau's grade for arrays of candidates: 2 ok (all strict), 1 near (all within the tolerance), 0 no."""
    ok = np.logical_and.reduce([x >= s for x, s in zip(vals, strict)])
    nr = np.logical_and.reduce([x >= nn for x, nn in zip(vals, near)])
    return np.where(ok, 2, np.where(nr, 1, 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--min-trades", type=int, default=100)
    ap.add_argument("--diagnose", action="store_true")
    ap.add_argument("--dump", help="every qualifying set as JSON lines (split_plateau --dump)")
    ap.add_argument("--regions", help="the distinct regions the report lists (per group, best first) as JSON lines")
    ap.add_argument("--label", help="name printed in the first line (default: the run folder)")
    ap.add_argument("--only", nargs="+", default=[], metavar="KEY=VALUE", help="keep only the passes with these axis values")
    a = ap.parse_args()
    info, S, skipped = load(a.run)
    T = pass_table(info, S, skipped)
    have = T["have"]
    axes = info["axes"]
    shape = [len(v) for _, v in axes]
    total = len(S)
    pidx = np.arange(total, dtype=np.int64)
    ax_stride = [int(np.prod(shape[d + 1:])) for d in range(len(shape))]

    def coord(d):
        return (pidx // ax_stride[d]) % shape[d]
    for kv in a.only:                                    # in place: T["have"] is the same array
        k, v = kv.split("=", 1)
        d = [n for n, _ in axes].index(k)
        have &= coord(d) == [str(x) for x in axes[d][1]].index(v)
    fixed = info["fixed"]

    # split_plateau: keys sorted by name; a key varies when passes with trades have more than one value; its values are
    # those that occur among passes with trades, sorted numerically where they look numeric
    keys = sorted(set(fixed) | {name for name, _ in axes})
    axis_of = {name: d for d, (name, _) in enumerate(axes)}
    varying = {}
    for k in keys:
        if k not in axis_of:
            continue
        d = axis_of[k]
        present = np.nonzero(np.bincount(coord(d)[have], minlength=shape[d]))[0]
        vals = [axes[d][1][j] for j in present]
        if len(set(vals)) > 1:
            varying[k] = sorted(set(vals), key=lambda x: (float(x) if _num_like(x) else 0, x))

    def isnum(k):
        return all(_num_like(v) for v in varying[k]) and k not in NOT_NUMERIC
    numeric = [k for k in varying if isnum(k)]
    cats = [k for k in varying if k not in numeric]
    names = list(varying)
    # compressed coordinates over the varying keys (split_plateau's value order), lookup table pass -> index
    dims = [len(varying[k]) for k in names]
    cc = np.zeros((total, len(names)), dtype=np.int16)          # value index per varying key (< 32,768 values)
    for t, k in enumerate(names):
        d = axis_of[k]
        pos = {x: i for i, x in enumerate(varying[k])}
        m = np.array([pos.get(x, -1) for x in axes[d][1]])
        cc[:, t] = m[coord(d)]
    del pidx
    strides = np.array([int(np.prod(dims[t + 1:])) for t in range(len(dims))], dtype=np.int64)
    lut = np.full(int(np.prod(dims)), -1, dtype=np.int64)
    flat = np.zeros(total, dtype=np.int64)
    for t in range(len(names)):
        flat += cc[:, t].astype(np.int64) * strides[t]
    ok = have & (cc >= 0).all(1)
    lut[flat[ok]] = np.nonzero(ok)[0]                  # a later pass with the same key wins, as split_plateau's dict
    del flat, ok
    num_dims = np.array([names.index(k) for k in numeric], dtype=np.int64)

    def value_of(p, k):
        return varying[k][cc[p, names.index(k)]] if k in varying else fixed.get(k)

    cand = np.nonzero(have & (T["trades"] >= a.min_trades) & (T["net"] > 0))[0]
    NB = neighbour_stats(cand, cc, lut, strides, np.array(dims, dtype=np.int64), num_dims, T["net"], T["pf"], T["fitness"],
                         T["H1_net"], T["H1_pf"], T["H2_net"], T["H2_pf"])
    _, fprof, fpf, h1prof, h1pf, h2prof, h2pf, plat = NB.T
    n_have = int(have.sum())
    C = cand_table(S, T, cand)
    del T, have

    def box(p):
        out = []
        for delta in product(*[(-1, 0, 1) if k in numeric else (0,) for k in names]):
            c = cc[p].astype(np.int64) + np.array(delta, dtype=np.int64)
            if (c < 0).any() or (c >= np.array(dims)).any():
                continue
            q = lut[int((c * strides).sum())]
            if q >= 0:
                out.append(int(q))
        return out

    # grades per candidate (positions in cand): full period, each half, verdict = the worst of the three
    yrs_ok = (C["pos_years"] >= C["years"] - 1).astype(np.float64)
    full = grade([fprof, fpf, C["pf"], C["net_wo_top5"] / C["net"], yrs_ok],
                 [0.80, 1.2, 1.2, 0.40, 1], [0.75, 1.15, 1.15, 0.35, 1])
    hg = {}
    for h, prof, mpf in (("H1", h1prof, h1pf), ("H2", h2prof, h2pf)):
        hw = np.where(C[h + "_net"] > 0, C[h + "_wo5"], -1.0)
        hg[h] = grade([prof, mpf, C[h + "_pf"], hw], [0.80, 1.2, 1.2, 0.40], [0.75, 1.15, 1.15, 0.35])
    hprof = {"H1": h1prof, "H2": h2prof}
    hmpf = {"H1": h1pf, "H2": h2pf}
    verdict = np.minimum(full, np.minimum(hg["H1"], hg["H2"]))
    qpos = np.nonzero(verdict > 0)[0]
    pid = lambda p: p + 1  # noqa: E731
    vals = lambda p: {k: value_of(p, k) for k in names}  # noqa: E731

    def record(i):
        p = int(cand[i])
        return {"pass": pid(p), "values": vals(p), "verdict": GRADE[verdict[i]], "plateau": round(float(plat[i]), 3),
                "pf": round(float(C["pf"][i]), 3), "dd": round(float(C["dd"][i]), 2), "Rpm": round(float(C["Rpm"][i]), 3),
                "trades": int(C["trades"][i]), "tpm": round(float(C["tpm"][i]), 2), "net": round(float(C["net"][i])),
                "wo5": round(float(C["net_wo_top5"][i] / C["net"][i]), 3), "pos_years": int(C["pos_years"][i]),
                "years": int(C["years"][i]), "news": round(float(C["news_share"][i]), 3),
                "nb": {"full": [round(float(fprof[i]), 3), round(float(fpf[i]), 3)],
                       "H1": [round(float(h1prof[i]), 3), round(float(h1pf[i]), 3)],
                       "H2": [round(float(h2prof[i]), 3), round(float(h2pf[i]), 3)]},
                "half_net": {h: round(float(C[h + "_net"][i])) for h in HALVES}}
    if a.dump:
        with open(a.dump, "w") as f:
            for i in qpos:
                f.write(json.dumps(record(i)) + "\n")
    nf = full > 0
    print(f"{a.label or a.run}: {n_have} passes; numeric {numeric}; groups {cats}")
    print(f"sets with >= {a.min_trades} trades and net > 0: {len(cand)} | qualify full period: {int(nf.sum())} | "
          f"+ H1 2018–20: {int((nf & (hg['H1'] > 0)).sum())} | + H2 2021–23 (= qualify v2): {len(qpos)}")
    print(f"full-period plateaus that fail a half: only H1 {int((nf & (hg['H1'] == 0) & (hg['H2'] > 0)).sum())} · "
          f"only H2 {int((nf & (hg['H2'] == 0) & (hg['H1'] > 0)).sum())} · both {int((nf & (hg['H1'] == 0) & (hg['H2'] == 0)).sum())}")
    fmtnum = lambda p, k: value_of(p, k)  # noqa: E731

    def distinct(order, limit):
        """Walk candidates best first; keep one per ±1 box (a set inside the box of a listed one is skipped)."""
        listed, inbox = [], set()
        for i in order:
            p = int(cand[i])
            if p in inbox:
                continue
            listed.append(i)
            inbox.update(box(p))
            if len(listed) >= limit:
                break
        return listed
    if a.diagnose:
        by_plat = np.argsort(-plat, kind="stable")
        print("\n-- best full-period regions that fail a half (half: grade, nb%prof/medPF, set PF, net, w/o5):")
        for i in distinct(by_plat[nf[by_plat] & (verdict[by_plat] == 0)], 10):
            p = int(cand[i])
            print(f"{pid(p):6} {dict((k, fmtnum(p, k)) for k in cats)} " + " ".join(f"{k[:6]}={fmtnum(p, k)}" for k in numeric)
                  + f" | plateau {plat[i]:.2f} PF {C['pf'][i]:.2f}"
                  + "".join(f" | {h}: {GRADE[hg[h][i]]} {hprof[h][i]:.0%}/{hmpf[h][i]:.2f} PF {C[h + '_pf'][i]:.2f} "
                            f"${C[h + '_net'][i] / 1e3:.1f}k w/o5 {C[h + '_wo5'][i]:.0%}" for h in HALVES))
    # qualifying sets best first, grouped by the categorical values (groups in the order of their best set)
    qs = qpos[np.argsort(-plat[qpos], kind="stable")]
    cat_cols = [names.index(k) for k in cats]
    gcode = np.zeros(len(qs), dtype=np.int64)
    for t in cat_cols:
        gcode = gcode * dims[t] + cc[cand[qs], t]
    uniq, first = np.unique(gcode, return_index=True)
    regions = []
    for g in uniq[np.argsort(first)]:
        rs = qs[gcode == g]
        p0 = int(cand[rs[0]])
        gv = tuple(str(fmtnum(p0, k)) for k in cats)
        listed = distinct(rs, a.top)
        print(f"\n== {dict(zip(cats, gv))}: {len(rs)} qualifying sets, {len(listed)} distinct regions shown")
        print("pass | " + " ".join(k[:10] for k in numeric) + " | v2 | plateau | tr/mo PF DD% R/mo | nb%prof/medPF full · H1 · H2 | net H1/H2 | +yrs w/o5 news")
        for rank, i in enumerate(listed, 1):
            p = int(cand[i])
            print(f"{pid(p):6} | " + " ".join(f"{str(fmtnum(p, k)):>10}" for k in numeric) + f" | {GRADE[verdict[i]]:4} | {plat[i]:5.2f} | "
                  f"{C['tpm'][i]:4.1f} {C['pf'][i]:.2f} {C['dd'][i]:4.1f} {C['Rpm'][i]:.2f}"
                  f" | {fprof[i]:.0%}/{fpf[i]:.2f} · {h1prof[i]:.0%}/{h1pf[i]:.2f} · {h2prof[i]:.0%}/{h2pf[i]:.2f}"
                  f" | ${C['H1_net'][i] / 1e3:.1f}k/${C['H2_net'][i] / 1e3:.1f}k | {int(C['pos_years'][i])}/{int(C['years'][i])} "
                  f"{C['net_wo_top5'][i] / C['net'][i]:.0%} {C['news_share'][i]:.0%}")
            regions.append({"group": dict(zip(cats, gv)), "rank": rank, "group_sets": int(len(rs)), **record(i),
                            "eq_dd": round(float(C["eq_dd"][i]), 2)})
    if a.regions:
        with open(a.regions, "w") as f:
            for r in regions:
                f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
