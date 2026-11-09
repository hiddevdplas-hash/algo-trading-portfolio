#!/usr/bin/env python3
"""Run a whole archived cTrader grid with the replica, compare every pass, and time it.

Usage:
  ~/.venvs/fastbt/bin/python tools/fastbt/fullgrid.py <export folder> <run folder> [--threads N] [--limit N]
Reads the run's passes.jsonl.gz once (cached in ~/.cache/fastbt), runs all passes in parallel per group (timeframe,
mode, ATR lengths) and reports how many passes have the same trade count and net profit to the cent, and the speed in
passes per hour. Passes with settings the replica does not simulate are counted and skipped.
"""
import argparse
import gzip
import hashlib
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data  # noqa: E402
import engine  # noqa: E402
import run_grid  # noqa: E402

CACHE_VERSION = "3"   # bump when pass_vector or group_key change


def load_grid(run_folder):
    """Pass id, group key, pass vector, archived trade count and net profit for every pass (cached)."""
    path = os.path.join(run_folder, "passes.jsonl.gz")
    cache_dir = os.path.expanduser("~/.cache/fastbt")
    os.makedirs(cache_dir, exist_ok=True)
    key = hashlib.sha1((os.path.abspath(run_folder) + "|" + CACHE_VERSION + "|" + str(engine.NP)).encode()).hexdigest()[:16]
    cache = os.path.join(cache_dir, key + ".npz")
    if os.path.isfile(cache) and os.path.getmtime(cache) > os.path.getmtime(path):
        z = np.load(cache, allow_pickle=False)
        g = {k: z[k] for k in z.files}
        g["key"] = [tuple(tuple(y) if isinstance(y, list) else y for y in json.loads(x)) for x in g["key"]]
        return g
    ids, keys, params, ntr, net, why = [], [], [], [], [], []
    with gzip.open(path, "rt") as fh:
        for line in fh:
            d = json.loads(line)
            v = d["values"]
            ids.append(d["pass"])
            try:
                params.append(engine.pass_vector(v))
                keys.append(engine.group_key(v))
                why.append("")
            except engine.Unsupported as e:
                params.append(np.zeros(engine.NP))
                keys.append(("", -1, 0, 0, 0.0, False, None))
                why.append(str(e).split(" (")[0])
            ntr.append(len(d["trades"]))
            last = max(d["trades"], key=lambda t: (t["time"], t["open"])) if d["trades"] else None
            net.append(last["balance"] - 100000.0 if last else 0.0)
    g = {"id": np.array(ids), "key": [json.dumps(k) for k in keys], "params": np.array(params), "trades": np.array(ntr),
         "net": np.array(net), "why": np.array(why)}
    np.savez(cache, **g)
    g["key"] = keys
    return g


def run_group(m, spec, key, params, max_trades=6000, keep_trades=False):
    return engine.run_params(m, spec, key, params, max_trades=max_trades, keep_trades=keep_trades)


def fit_swaps(m, spec, run_folder, sample=None, seed=3):
    """Swap rates (pips, long / short) of the day the referee ran: cTrader backtests use the broker's swap of the run date,
    which changes over time. Replays a sample of passes, takes trades that match the archive except for the swap and
    hold one plain night, and picks the rate (0.001-pip steps) that reproduces most of those charges to the cent."""
    from compare import archive_passes, archive_rows
    import numpy as np
    obs = {1: [], -1: []}
    rate0 = {1: spec.swap_long_pips, -1: spec.swap_short_pips}
    _, uv = engine.tick_inputs(m, spec)
    for pid, values, trades in archive_passes(run_folder, sample=sample, seed=seed):
        try:
            rep = engine.run_pass(m, spec, values["Timeframe"], values)
        except engine.Unsupported:
            continue
        idx = {(int(rep["open"][j]), int(rep["close"][j]), int(rep["side"][j])): j for j in range(len(rep["open"]))}
        for a in archive_rows(trades):
            j = idx.get((a["open"], a["close"], a["side"]))
            if j is None or abs(float(rep["gross"][j]) - a["gross"]) > 0.011 or rep["swap"][j] == 0:
                continue
            # one plain (not triple) night, charged at the first tick of that rollover: exact cents test possible
            roll = engine.next_rollover(a["open"], spec.roll_min)
            if not (roll < a["close"] <= engine.next_rollover(roll, spec.roll_min)) or (roll // 86400000 + 3) % 7 == spec.triple_wd:
                continue
            vp = float(rep["vol"][j]) * spec.pip_size * float(uv[np.searchsorted(m.t, roll)])   # account currency per swap pip
            if abs(engine.round_cents(vp * rate0[a["side"]]) - float(rep["swap"][j])) < 0.005:
                obs[a["side"]].append((vp, a["swap"] - float(rep["commission"][j])))
    out = {}
    for sd, rows in obs.items():
        if not rows:
            out[sd] = rate0[sd]
            continue
        est = float(np.median([s / vp for vp, s in rows]))
        scored = []
        for c in sorted(set(np.round(np.arange(est - 0.3, est + 0.3, 0.001), 3)) | {round(rate0[sd], 3)}):
            n = sum(abs(engine.round_cents(vp * c) - s) < 0.005 for vp, s in rows)
            # ties: the export's own rate, then the roundest value (cTrader shows swaps with 2 decimals), then nearest
            decimals = next(d for d in range(4) if abs(round(c, d) - c) < 1e-9)
            scored.append((-n, c != round(rate0[sd], 3), decimals, abs(c - est), float(c)))
        scored.sort()
        best, best_n = scored[0][4], -scored[0][0]
        out[sd] = best
        print(f"swap {'long' if sd > 0 else 'short'}: export {rate0[sd]} pips, referee {best} pips "
              f"({best_n} of {len(rows)} one-night charges exact)")
    return out[1], out[-1]


def identical(m, spec, g, keys, karr, tol=0.011):
    """Number of passes identical to the archive (trade count, and net within tol: to the cent by default)."""
    same = 0
    for key in keys:
        sel = np.nonzero(karr == json.dumps(key))[0]
        stats, counts, _, _ = run_group(m, spec, key, g["params"][sel])
        same += int(((counts == g["trades"][sel]) & (np.abs(stats[:, engine.ST_NET_RAW] - g["net"][sel]) <= tol)).sum())
    return same


def fit_roll(m, spec, g, keys, karr, candidates=range(20 * 60, 22 * 60 + 31, 10)):
    """Rollover minute (UTC) that makes most passes match (the broker's swap time on the day the referee ran): most passes
    within $1, then most identical to the cent (FX commissions leave a few cents in many passes whatever the time)."""
    best, best_n = spec.roll_min, (-1, -1)
    for rm in candidates:
        spec.roll_min = rm
        n = (identical(m, spec, g, keys, karr, tol=1.0), identical(m, spec, g, keys, karr))
        if n > best_n:
            best, best_n = rm, n
    spec.roll_min = best
    print(f"rollover: {best // 60:02d}:{best % 60:02d} UTC fits best ({best_n[0]} passes within $1, {best_n[1]} identical)")
    return best


WIPED = -90000.0      # a pass that loses >= 90% of the 100,000 start is left out of the referee count (PROTOCOL v3)


def crashed_passes(logs):
    """Pass ids whose cTrader log (raw export folder: <pass>/log.txt) shows the cBot crashed (RULES A18)."""
    out = set()
    if logs:
        for d in os.listdir(logs):
            f = os.path.join(logs, d, "log.txt")
            if d.isdigit() and os.path.isfile(f) and "Crashed" in open(f, errors="replace").read():
                out.add(int(d))
    return out


EVENT_OF = {"Stop Loss Hit": engine.EV_SL, "Take Profit Hit": engine.EV_TP, "Position closed": engine.EV_CLOSE}


def same_trades(rep_rows, arch):
    """Same trade list: the same entries, exits (time and kind: stop, target, close), direction and volume (volume from
    the archive's notional = vol x entry)."""
    if len(rep_rows) != len(arch):
        return False
    for (o, c, sd, vol, entry, ev), a in zip(rep_rows, arch):
        if o != a["open"] or c != a["time"] or sd != (1 if a["type"] == "Buy" else -1) or ev != EVENT_OF.get(a["event"], -1):
            return False
        if a.get("notional") is not None and abs(vol * entry - a["notional"]) > 0.01 * max(1.0, entry / 100):
            return False
    return True


def rule_match(m, spec, run_folder, crashed=(), chunk=200):
    """PROTOCOL v3 referee rule per pass: (left out, same trade list, matches) where matches = same trade list and net
    within $1, left out = loses >= 90% or cTrader crashed. Returns {pass id: (left_out, same_list, match)}."""
    res = {}
    with gzip.open(os.path.join(run_folder, "passes.jsonl.gz"), "rt") as fh:
        buf = []
        for line in __import__("itertools").chain(fh, [None]):
            if line is not None:
                buf.append(json.loads(line))
            if buf and (line is None or len(buf) >= chunk):
                groups = {}
                for d in buf:
                    try:
                        groups.setdefault(engine.group_key(d["values"]), []).append((d, engine.pass_vector(d["values"])))
                    except engine.Unsupported:
                        continue
                for key, items in groups.items():
                    mt = max(len(d["trades"]) for d, _ in items) + 200
                    st, counts, tr_i, tr_f = engine.run_params(m, spec, key, np.array([v for _, v in items]), max_trades=mt,
                                                               keep_trades=True)
                    for q, (d, _) in enumerate(items):
                        arch = sorted(d["trades"], key=lambda t: (t["open"], 1 if t["type"] == "Buy" else -1, t["time"]))
                        n = int(counts[q])
                        rows = sorted((int(tr_i[q, j, 0]), int(tr_i[q, j, 1]), int(tr_i[q, j, 2]), float(tr_f[q, j, 2]),
                                       float(tr_f[q, j, 0]), int(tr_i[q, j, 3])) for j in range(n))
                        last = max(arch, key=lambda t: (t["time"], t["open"])) if arch else None
                        anet = last["balance"] - 100000.0 if last else 0.0
                        same = same_trades(rows, arch)
                        res[d["pass"]] = (anet <= WIPED or d["pass"] in crashed, same,
                                          same and abs(float(st[q, engine.ST_NET_RAW]) - anet) <= 1.0)
                buf = []
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("run")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0, help="only the first N passes per group")
    ap.add_argument("--swap", default="fit", help="'fit' (from the archive), 'export', or 'LONG,SHORT' in pips")
    ap.add_argument("--roll", default="fit", help="rollover minute UTC: 'fit' (from the archive) or e.g. 1260 (21:00)")
    ap.add_argument("--swap-sample", type=int, default=400, help="passes replayed to fit the swap rates (0 = all)")
    ap.add_argument("--logs", help="cTrader's raw export folder of this run (<pass>/log.txt): passes where cTrader crashed the "
                                   "cBot are left out of the referee count")
    ap.add_argument("--crashed", default="", help="pass ids where cTrader crashed the cBot, when the logs are gone (e.g. 2,3,4)")
    ap.add_argument("--no-rule", action="store_true", help="skip the trade-list comparison (large grids)")
    ap.add_argument("--spread", type=float, help="the referee's fixed spread in pips if it differs from the export's")
    ap.add_argument("--commission", type=float, help="the referee's commission (USD per million per side) if it differs")
    ap.add_argument("--schedule", default="export", choices=("export", "now"),
                    help="broker trading hours: 'export' (the archived runs predate broker_hours.json) or 'now' (data.py)")
    args = ap.parse_args()
    if args.threads:
        import numba
        numba.set_num_threads(args.threads)
    t0 = time.time()
    g = load_grid(args.run)
    print(f"grid: {len(g['id'])} passes read in {time.time() - t0:.0f}s")
    skipped = g["why"] != ""
    if skipped.any():
        from collections import Counter
        print(f"skipped (not simulated): {skipped.sum()} passes: {dict(Counter(g['why'][skipped]))}")
    m = data.load(args.export, schedule=args.schedule)
    spec = engine.Spec(m.meta)
    if args.spread is not None or args.commission is not None:     # cTrader's ask = bid + fixed spread (RULES A3)
        run_grid.override_costs(m, spec, args.spread, args.commission)
        print(f"costs overridden: spread {m.spread_px / spec.pip_size:g} pips, commission {spec.commission:g} USD per million")
    if args.roll != "fit":
        spec.roll_min = int(args.roll)
    if args.swap == "fit":
        spec.swap_long_pips, spec.swap_short_pips = fit_swaps(m, spec, args.run, sample=args.swap_sample or None)
    elif args.swap != "export":
        spec.swap_long_pips, spec.swap_short_pips = (float(x) for x in args.swap.split(","))
    tot_same = tot = 0
    elapsed = 0.0
    worst = []
    keys = sorted({k for k, s in zip(g["key"], skipped) if not s}, key=str)
    karr = np.array([json.dumps(k) for k in g["key"]])
    if args.roll == "fit":
        fit_roll(m, spec, g, keys, karr)
        if args.swap == "fit":                         # refit the rates at the fitted rollover time
            spec.swap_long_pips, spec.swap_short_pips = fit_swaps(m, spec, args.run, sample=args.swap_sample or None)
    dnet, nets = [], []
    for key in keys:
        sel = np.nonzero(karr == json.dumps(key))[0]
        if args.limit:
            sel = sel[:args.limit]
        run_group(m, spec, key, g["params"][sel[:2]])        # compile / warm up
        t1 = time.time()
        stats, counts, _, _ = run_group(m, spec, key, g["params"][sel])
        dt = time.time() - t1
        elapsed += dt
        same = (counts == g["trades"][sel]) & (np.abs(stats[:, engine.ST_NET_RAW] - g["net"][sel]) <= 0.011)
        tot_same += int(same.sum())
        tot += len(sel)
        dnet.append(np.abs(stats[:, engine.ST_NET_RAW] - g["net"][sel])[counts == g["trades"][sel]])
        nets.append(np.abs(g["net"][sel])[counts == g["trades"][sel]])
        print(f"{key[0]} mode {key[1]}: {len(sel)} passes in {dt:.1f}s ({len(sel) / dt * 3600:,.0f} passes/hour); "
              f"identical trade count + net to the cent: {same.sum()} ({100 * same.mean():.2f}%)")
        for i in np.nonzero(~same)[0][:10]:
            worst.append((int(g["id"][sel[i]]), key[0], int(g["trades"][sel[i]]), int(counts[i]), float(g["net"][sel[i]]),
                          float(stats[i, engine.ST_NET_RAW])))
    print(f"\nall: {tot_same} of {tot} passes identical ({100 * tot_same / tot:.2f}%); {tot / elapsed * 3600:,.0f} passes/hour "
          f"({elapsed:.0f}s for {tot} passes, numba threads {__import__('numba').get_num_threads()})")
    d = np.concatenate(dnet)
    if len(d):
        print(f"passes with the same trade count: {len(d)}; net difference median ${np.median(d):.2f}, 95% ${np.percentile(d, 95):.2f}, "
              f"99% ${np.percentile(d, 99):.2f}, max ${d.max():.2f}; within $1: {100 * np.mean(d <= 1.0):.1f}%, within $10: "
              f"{100 * np.mean(d <= 10.0):.1f}%")
    if not args.no_rule:
        crashed = crashed_passes(args.logs) | {int(x) for x in args.crashed.split(",") if x}
        r = rule_match(m, spec, args.run, crashed)
        kept = [v for v in r.values() if not v[0]]
        n_wiped = sum(1 for pid, v in r.items() if v[0])
        print(f"RULE (PROTOCOL v3): {sum(v[2] for v in kept)} of {len(kept)} passes match ({100 * sum(v[2] for v in kept) / max(len(kept), 1):.2f}%) "
              f"= same trade list and net within $1; left out {n_wiped} (lose >= 90% or cTrader crashed"
              f"{'' if (args.logs or args.crashed) else '; no logs given, crashes not checked'}); same trade list {sum(v[1] for v in r.values())} of {len(r)}")
    for w in worst[:20]:
        print("  differs: pass %d %s trades %d vs %d, net %.2f vs %.2f" % w)


if __name__ == "__main__":
    main()
