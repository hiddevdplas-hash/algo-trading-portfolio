#!/usr/bin/env python3
"""Run a grid with the replica: per-pass statistics for every pass (stats-only), or trade lists for chosen passes.

Usage:
  ~/.venvs/fastbt/bin/python tools/fastbt/run_grid.py <export folder> <grid> <output folder> [--stats] [--passes 12,345]
    grid    a cTrader settings.optset, or a JSON grid {"fixed": {param: value}, "axes": {param: [values]}}
            (parameter names as in the cBot / archive, e.g. SessionBandMult, Timeframe, Management)
    --stats  write chunks/c*.npz + grid.json: one row of statistics per pass (engine.STAT_NAMES), no trade lists.
             Written chunk by chunk (RAM does not grow with the grid) and resumable: rerun the same command after a
             stop and it continues after the last finished chunk. grid.json is written last and marks a finished run.
             tools/fastbt/plateau.py reads it (same report as tools/split_plateau.py).
    --passes write passes.jsonl.gz in the archive format (tools/build_archive.py) for these pass ids only
    --spread PIPS / --commission USD_PER_MILLION  other costs than the export's (cost stress; recorded in grid.json)
    neither  write passes.jsonl.gz for every pass (small grids; e.g. to compare with a cTrader archive)
Pass ids follow the grid's order: the cartesian product of the axes in their order, last axis fastest, id = index + 1
(cTrader numbers the passes of a grid run differently: compare passes by their values, not by id). Always write to a new folder, never over a
cTrader archive. Fixed TP statistics are TP-capped like tools/tp_cap.py; trade lists are raw (cap them with tp_cap.py).
Swap and rollover are the export's (the broker's rate on the export day, rollover 21:00 UTC; engine.Spec).

The stats are int32 (4 bytes per number, half of float64, then compressed) and exact: every trade is in whole cents,
so money sums are stored in cents; counts as they are; close times in seconds; only eq_dd (an in-bar extreme) is rounded
to the cent. grid.json "scale" gives value = stored / scale per column; load_stats() reads them back. Runs of millions of passes belong outside iCloud (~/fastbt-runs).
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

SWITCHED = {  # tools/analyze_optimisation.py: dependants of a switched-off option are stored as "off"
    "EnableFixedTpBreakEven": ["FixedTpBreakEvenTriggerR"],
    "EnableDistanceFilter": ["MaxEntryDistanceAtr"],
    "EnablePenetrationFilter": ["MaxBandPenetrationAtr", "Penetration"],
    "EnableAtrPercentile": ["PercentileAtrLength", "PercentileLookback", "MaxAtrPercentile"],
    "WeeklyDailyWindowBlock": ["WeeklyDailyWindow"],
}
VIRTUAL_OFF = {"@News": {"NewsFilterMode": "0"}, "@ATR": {"EnableAtrPercentile": "False"},
               "@Dist": {"EnableDistanceFilter": "False"}, "@Pen": {"EnablePenetrationFilter": "False"}}
STATS_FORMAT = "int32-scaled-1"
RETRY_TRADES = 200000      # stats mode: passes that fill max_trades are rerun with this many trade slots


def fmt(x):
    if isinstance(x, str):
        return x
    return str(int(x)) if float(x).is_integer() else repr(round(float(x), 10))


def read_grid(path):
    """(fixed values, [(axis name, [values as strings])]) from an optset or a JSON grid."""
    raw = json.load(open(path, encoding="utf-8-sig"))
    if "parameters" not in raw:
        # a JSON grid (axes as a dict), or a stats run's grid.json (axes as [name, values] pairs: the grid that run used)
        items = raw["axes"].items() if isinstance(raw["axes"], dict) else raw["axes"]
        return {k: fmt(v) for k, v in raw.get("fixed", {}).items()}, [(k, [fmt(x) for x in vals]) for k, vals in items]
    fixed, axes = {}, []
    for p in raw["parameters"]:
        name = "Timeframe" if p["parameterType"] == "TimeFrame" else p["name"]
        if not p.get("optimize"):
            fixed[name] = p["value"]
            continue
        if "values" in p:
            vals = list(p["values"])
        elif p["parameterType"] == "Boolean":
            vals = ["False", "True"]
        else:
            lo, hi, step = float(p["min"]), float(p["max"]), float(p["step"])
            n = int(np.floor((hi - lo) / step + 1e-9)) + 1
            vals = [fmt(lo + k * step) for k in range(n)]
        axes.append((name, vals))
    return fixed, axes


def pass_values(fixed, axes, combo):
    v = dict(fixed)
    v.update({a[0]: c for a, c in zip(axes, combo)})
    if "BreakEven" in v:            # one axis for the break-even pair (fine grids): "off" or the trigger in R, so off is not run 3 times
        be = v.pop("BreakEven")
        v["EnableFixedTpBreakEven"] = "False" if be == "off" else "True"
        v["FixedTpBreakEvenTriggerR"] = "off" if be == "off" else be
    for k in [k for k in v if k.startswith("@")]:
        # a filter axis (filter step): "off", or "<label>:Param=value;Param=value" — one axis holds a filter's off state and
        # each of its settings, so the off pass is not repeated for every value of the filter's own parameters
        val = v.pop(k)
        v.update(VIRTUAL_OFF.get(k, {}) if val == "off" else dict(x.split("=", 1) for x in val.split(":", 1)[-1].split(";")))
    for switch, dependants in SWITCHED.items():
        if v.get(switch) == "False":
            for d in dependants:
                if d in v:
                    v[d] = "off"
    return v


def stat_scale():
    """Storage scale per stats column: the chunk files hold round(value x scale) as int32."""
    sc = np.full(engine.NST, 100.0)                                         # money: cents
    for c in (engine.ST_TRADES, engine.ST_WINS, engine.ST_OVERFLOW, engine.ST_STOPOUT, engine.ST_OUTSIDE, engine.ST_H1,
              engine.ST_H2):
        sc[c] = 1.0                                                         # counts
    sc[engine.ST_YEAR_N:engine.ST_YEAR_N + engine.NYEARS] = 1.0
    sc[[engine.ST_FIRST, engine.ST_LAST]] = 0.001                           # close times: ms -> s
    return sc


def to_store(st, scale):
    x = np.rint(st * scale)
    if x.size and np.abs(x).max() >= 2 ** 31:
        bad = engine.STAT_NAMES[int(np.argmax(np.abs(x).max(0)))]
        raise OverflowError(f"stats column {bad} beyond the int32 range (more than $21 million): needs a wider format")
    return x.astype(np.int32)


def build_chunk(fixed, axes, shape, ids):
    """Group the passes of a chunk by engine.group_key: {key: (pass indices, pass vectors)}, plus the unsupported ones."""
    groups, skipped = {}, []
    for i in ids:
        combo = [a[1][j] for a, j in zip(axes, np.unravel_index(int(i), shape))] if shape else []
        v = pass_values(fixed, axes, combo)
        try:
            vec = engine.pass_vector(v)
        except engine.Unsupported:
            skipped.append(int(i))
            continue
        groups.setdefault(engine.group_key(v), []).append((int(i), vec))
    return {k: (np.array([x[0] for x in it]), np.array([x[1] for x in it])) for k, it in groups.items()}, skipped


def override_costs(m, spec, spread=None, commission=None):
    """Run with another fixed spread (pips) and / or commission (USD per million) than the export's (cost stress, referees
    run at other costs). cTrader's ask = bid + fixed spread in floating point (RULES A3). Returns restore(), which puts the
    export's costs back."""
    saved = (m.ask, m.spread_px, m.conv_ask, spec.commission)
    if spread is not None:
        sp = spread * spec.pip_size
        m.ask = m.bid + sp
        m.spread_px = float(np.round(sp, spec.digits + 2))
        if spec.conv_self and m.conv_bid is not None:
            m.conv_ask = m.conv_bid + sp
        m._tick_key = None
    if commission is not None:
        spec.commission = commission

    def restore():
        m.ask, m.spread_px, m.conv_ask, spec.commission = saved
        m._tick_key = None
    return restore


def engine_hash():
    """Fingerprint of the replica's code (engine.py + data.py): all chunks of a run must come from one engine, and a run made
    before an engine change is stale (its regions are re-run, not reused)."""
    h = hashlib.sha1()
    for f in ("engine.py", "data.py"):
        h.update(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), f), "rb").read())
    return h.hexdigest()[:12]


def grid_hash(fixed, axes):
    return hashlib.sha1(json.dumps([fixed, axes], sort_keys=True).encode()).hexdigest()[:16]


def run_stats(m, spec, grid_path, out, chunk=500000, max_trades=20000, log=print, progress=None):
    """Stats-only run of a whole grid into <out>, resumable. Returns grid.json's content. progress(done, total, new, dt)
    is called after every chunk (passes finished overall, total passes, passes run in this call, seconds in this call).
    <out>/chunks/c00000.npz ... hold the stats per chunk (one compressed int32 member per column: s00 ... s40, skipped);
    a chunk file appears only when its chunk is complete, so a stopped run continues after the last finished chunk."""
    fixed, axes = read_grid(grid_path)
    shape = [len(a[1]) for a in axes]
    total = int(np.prod(shape)) if shape else 1
    nchunks = (total + chunk - 1) // chunk
    cdir = os.path.join(out, "chunks")
    os.makedirs(cdir, exist_ok=True)
    info_path, prog_path = os.path.join(out, "grid.json"), os.path.join(out, "progress.json")
    if os.path.isfile(info_path):
        return json.load(open(info_path))
    state = {"grid_hash": grid_hash(fixed, axes), "engine": engine_hash(), "export": os.path.abspath(os.path.expanduser(m.folder)), "chunk": chunk,
             "max_trades": max_trades, "swap_long_pips": spec.swap_long_pips, "swap_short_pips": spec.swap_short_pips,
             "roll_min": spec.roll_min, "spread_px": m.spread_px, "commission": spec.commission,
             "passes": total, "fixed": fixed, "axes": [[a[0], a[1]] for a in axes]}
    elapsed, retried = 0.0, 0
    if os.path.isfile(prog_path):
        prev = json.load(open(prog_path))
        if {k: prev.get(k) for k in state} != state:
            what = "engine (tools/fastbt changed since)" if prev.get("engine") != state["engine"] else "grid, export or settings"
            raise SystemExit(f"{out} holds an unfinished run of a different {what}: move it away and start again")
        elapsed, retried = prev.get("elapsed_s", 0.0), prev.get("overflow_retried", 0)
    elif os.listdir(cdir):
        raise SystemExit(f"{cdir} has chunk files but no progress.json: choose a new output folder")
    have = {ci for ci in range(nchunks) if os.path.isfile(os.path.join(cdir, f"c{ci:05d}.npz"))}
    if have:
        log(f"  resuming: {len(have)} of {nchunks} chunks finished before")
    scale = stat_scale()
    t0, new = time.time(), 0
    done = sum(min(total, (c + 1) * chunk) - c * chunk for c in have)

    def save_state():
        state.update(elapsed_s=elapsed + time.time() - t0, overflow_retried=retried)
        tmp = prog_path + ".tmp"
        json.dump(state, open(tmp, "w"), indent=1)
        os.replace(tmp, prog_path)
    save_state()
    for ci in range(nchunks):
        if ci in have:
            continue
        c0, c1 = ci * chunk, min(total, (ci + 1) * chunk)
        groups, sk = build_chunk(fixed, axes, shape, range(c0, c1))
        block = np.zeros((c1 - c0, engine.NST))
        for key, (idx, P) in groups.items():
            # shuffled so each thread gets a mix of slow and fast passes (neighbouring passes cost alike): +40% speed
            perm = np.random.default_rng(ci).permutation(len(idx))
            idx, P = idx[perm], P[perm]
            st, _, _, _ = engine.run_params(m, spec, key, P, max_trades=max_trades)
            over = np.nonzero(st[:, engine.ST_OVERFLOW] > 0)[0]
            if len(over):
                st[over] = engine.run_params(m, spec, key, P[over], max_trades=RETRY_TRADES)[0]
                retried += len(over)
            block[idx - c0] = st
        skipped = np.zeros(c1 - c0, dtype=np.bool_)
        skipped[np.array(sk, dtype=np.int64) - c0] = True
        path = os.path.join(cdir, f"c{ci:05d}.npz")
        with open(path + ".tmp", "wb") as fh:
            q = to_store(block, scale)
            np.savez_compressed(fh, skipped=skipped, **{f"s{c:02d}": np.ascontiguousarray(q[:, c]) for c in range(q.shape[1])})
        os.replace(path + ".tmp", path)
        new += c1 - c0
        done += c1 - c0
        save_state()
        if progress:
            progress(done, total, new, time.time() - t0)
    over = sum(int((stat_column(out, ci, engine.ST_OVERFLOW) > 0).sum()) for ci in range(nchunks))
    nskip = sum(int(np.load(os.path.join(cdir, f"c{ci:05d}.npz"))["skipped"].sum()) for ci in range(nchunks))
    info = {"export": state["export"], "engine": state["engine"], "grid": os.path.abspath(grid_path), "fixed": fixed, "axes": state["axes"],
            "passes": total, "chunk": chunk, "stat_names": engine.STAT_NAMES, "format": STATS_FORMAT, "scale": scale.tolist(),
            "years": [engine.FIRST_YEAR, engine.FIRST_YEAR + engine.NYEARS - 1], "half_split": engine.HALF_SPLIT,
            "skipped": nskip, "swap_long_pips": spec.swap_long_pips, "swap_short_pips": spec.swap_short_pips,
            "roll_utc": f"{spec.roll_min // 60:02d}:{spec.roll_min % 60:02d}", "spread_px": m.spread_px,
            "commission": spec.commission, "max_trades": max_trades,
            "overflow_retried": retried, "overflow_left": over,
            "elapsed_s": round(state["elapsed_s"]), "written": time.strftime("%Y-%m-%d %H:%M"),
            "note": "tools/fastbt replica of cTrader's m1-bar backtest; Fixed TP stats TP-capped"}
    json.dump(info, open(info_path, "w"), indent=1)
    return info


def stat_column(out, ci, c):
    """Column c of chunk ci as stored (int32). Each column is its own compressed member, so reading one column of a grid
    never decompresses the others (chunks written before 21 Oct 20:00 hold one "stats" block instead)."""
    z = np.load(os.path.join(out, "chunks", f"c{ci:05d}.npz"))
    return z[f"s{c:02d}"] if "stats" not in z.files else z["stats"][c]


def stat_columns(out):
    """Number of stats columns of a run (runs written before a column was added have fewer)."""
    z = np.load(os.path.join(out, "chunks", "c00000.npz"))
    return z["stats"].shape[0] if "stats" in z.files else sum(1 for f in z.files if f[0] == "s" and f[1:].isdigit())


def load_stats(out, nchunks=None):
    """(stats [passes, columns] int32 as stored, skipped [passes]) of a run_stats folder; value = stats / grid.json scale.
    The whole table in RAM: for small runs and checks (plateau.py reads column by column)."""
    cdir = os.path.join(out, "chunks")
    if nchunks is None:
        nchunks = len([f for f in os.listdir(cdir) if f.endswith(".npz")])
    skipped = np.concatenate([np.load(os.path.join(cdir, f"c{ci:05d}.npz"))["skipped"] for ci in range(nchunks)])
    ncol = stat_columns(out)
    stats = np.empty((len(skipped), ncol), dtype=np.int32)
    k = 0
    for ci in range(nchunks):
        z = np.load(os.path.join(cdir, f"c{ci:05d}.npz"))
        block = z["stats"].T if "stats" in z.files else np.stack([z[f"s{c:02d}"] for c in range(ncol)], axis=1)
        stats[k:k + len(block)] = block
        k += len(block)
    return stats, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("grid")
    ap.add_argument("out")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--passes", default="")
    ap.add_argument("--chunk", type=int, default=0, help="passes per chunk (default 500000 with --stats, else 100000)")
    ap.add_argument("--max-trades", type=int, default=0, help="trade slots per pass (default 20000 with --stats, else 6000)")
    ap.add_argument("--spread", type=float, help="fixed spread in pips instead of the export's (e.g. cost stress x 1.5)")
    ap.add_argument("--commission", type=float, help="commission in USD per million instead of the export's")
    args = ap.parse_args()
    m = data.load(args.export)
    spec = engine.Spec(m.meta)
    if args.spread is not None or args.commission is not None:
        override_costs(m, spec, args.spread, args.commission)
        print(f"costs: spread {m.spread_px / spec.pip_size:g} pips, commission {spec.commission:g} USD per million (export overridden)")
    t0 = time.time()
    if args.stats:
        def progress(done, total, new, dt):
            print(f"  {done:,} / {total:,} passes, {dt:.0f}s, ~{dt / new * (total - done):.0f}s left", flush=True)
        info = run_stats(m, spec, args.grid, args.out, chunk=args.chunk or 500000, max_trades=args.max_trades or 20000,
                         progress=progress)
        print(f"{info['passes']:,} passes in {args.out} ({time.time() - t0:.0f}s in this call)")
        return
    chunk_n, max_trades = args.chunk or 100000, args.max_trades or 6000
    fixed, axes = read_grid(args.grid)
    shape = [len(a[1]) for a in axes]
    total = int(np.prod(shape)) if shape else 1
    want = sorted({int(x) for x in args.passes.split(",") if x})
    if want and (want[0] < 1 or want[-1] > total):
        sys.exit(f"pass ids must be 1..{total}")
    os.makedirs(args.out, exist_ok=True)
    target = os.path.join(args.out, "passes.jsonl.gz")
    if os.path.exists(target):
        sys.exit(f"{target} exists: choose a new output folder")
    results = {}
    ids = (np.array(want) - 1) if want else np.arange(total)
    done = 0
    for c0 in range(0, len(ids), chunk_n):
        chunk = ids[c0:c0 + chunk_n]
        groups, sk = build_chunk(fixed, axes, shape, chunk)
        if sk:
            sys.exit(f"pass {sk[0] + 1}: settings the replica does not simulate")
        for key, (idx, P) in groups.items():
            st, counts, tr_i, tr_f = engine.run_params(m, spec, key, P, max_trades=max_trades, keep_trades=True)
            if (st[:, engine.ST_OVERFLOW] > 0).any():
                sys.exit(f"more than {max_trades} trades in a pass: raise --max-trades")
            for q, i in enumerate(idx):
                trades = []
                for j in range(int(counts[q])):
                    entry, vol, sl = tr_f[q, j, 0], tr_f[q, j, 2], tr_f[q, j, 6]
                    trades.append({"event": engine.EVENT_NAMES[int(tr_i[q, j, 3])], "time": int(tr_i[q, j, 1]),
                                   "type": "Buy" if tr_i[q, j, 2] > 0 else "Sell", "balance": round(float(tr_f[q, j, 5]), 2),
                                   "gross": round(float(tr_f[q, j, 3]), 2), "open": int(tr_i[q, j, 0]),
                                   "risk": abs(entry - sl), "notional": vol * entry})
                results[int(i)] = trades
        done += len(chunk)
        if len(ids) > chunk_n:
            el = time.time() - t0
            print(f"  {done:,} / {len(ids):,} passes, {el:.0f}s, ~{el / done * (len(ids) - done):.0f}s left", flush=True)
    with gzip.open(target, "wt", encoding="utf-8") as fh:
        for i in sorted(results):
            combo = [a[1][j] for a, j in zip(axes, np.unravel_index(i, shape))] if shape else []
            fh.write(json.dumps({"pass": i + 1, "values": pass_values(fixed, axes, combo), "trades": results[i]},
                                separators=(",", ":")) + "\n")
    with open(os.path.join(args.out, "FASTBT.txt"), "w") as fh:
        fh.write(f"Written by tools/fastbt/run_grid.py from {args.grid} on export {args.export}.\n"
                 "Replica of cTrader's m1-bar backtest (tools/fastbt/REPORT.md); raw trades (cap Fixed TP with tools/tp_cap.py).\n")
    print(f"{len(ids):,} passes written to {target} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
