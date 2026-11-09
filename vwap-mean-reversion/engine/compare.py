#!/usr/bin/env python3
"""Replay archived cTrader passes with the fastbt replica and compare them trade for trade.

Usage:
  ~/.venvs/fastbt/bin/python tools/fastbt/compare.py <export folder> <run folder> [--sample N] [--ids 1,2,...] [--show K]
    export folder : FastBtExport output, e.g. ~/cAlgo/Exports/fastbt/US30_m5_20180101
    run folder    : optimisation/<SYM>/<Mode>/02_fullgrid_<Family> (reads its passes.jsonl.gz, raw = not TP-capped)
A trade matches when side, open time, close time and close event are equal and net P&L is within 1 cent.
"""
import argparse
import gzip
import json
import os
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data  # noqa: E402
import engine  # noqa: E402

EVENT_CODE = {"Stop Loss Hit": engine.EV_SL, "Take Profit Hit": engine.EV_TP, "Position closed": engine.EV_CLOSE}


def archive_passes(run_folder, ids=None, sample=None, seed=7):
    """Yield (pass id, values, trades). With sample: a reproducible random subset."""
    path = os.path.join(run_folder, "passes.jsonl.gz")
    want = set(ids) if ids else None
    if sample and not want:
        with gzip.open(path, "rt") as f:
            total = sum(1 for _ in f)
        rng = np.random.default_rng(seed)
        want = set(int(x) for x in rng.choice(np.arange(1, total + 1), size=min(sample, total), replace=False))
        use_line_no = True
    else:
        use_line_no = False
    with gzip.open(path, "rt") as f:
        for n, line in enumerate(f, 1):
            if want is not None:
                if use_line_no and n not in want:
                    continue
                if not use_line_no:
                    pid = int(line[8:line.index(",")])
                    if pid not in want:
                        continue
            d = json.loads(line)
            yield d["pass"], d["values"], d["trades"]


def archive_rows(trades, start=100000.0):
    rows, prev = [], start
    for t in sorted(trades, key=lambda x: (x["time"], x["open"])):
        net = round(t["balance"] - prev, 2)
        prev = t["balance"]
        rows.append({"open": t["open"], "close": t["time"], "side": 1 if t["type"] == "Buy" else -1,
                     "event": EVENT_CODE.get(t["event"], 0), "gross": t["gross"], "net": net,
                     "swap": round(net - t["gross"], 2), "risk": t.get("risk"), "notional": t.get("notional")})
    return rows


def compare_pass(rep, arch):
    """Match by (side, open time). Returns counts and the first differences."""
    rmap = {}
    for j in range(len(rep["open"])):
        rmap[(int(rep["side"][j]), int(rep["open"][j]))] = j
    res = Counter()
    diffs = []
    seen = set()
    for a in arch:
        key = (a["side"], a["open"])
        j = rmap.get(key)
        if j is None:
            res["missing"] += 1
            diffs.append(("missing in replica", a))
            continue
        seen.add(j)
        same_close = int(rep["close"][j]) == a["close"] and int(rep["event"][j]) == a["event"]
        dg = float(rep["gross"][j]) - a["gross"]
        dn = float(rep["net"][j]) - a["net"]
        if same_close and abs(dn) <= 0.011:
            res["exact"] += 1
        elif same_close and abs(dg) <= 0.011:
            res["swap_diff"] += 1
            diffs.append(("swap", a, j, dn))
        elif same_close:
            res["pnl_diff"] += 1
            diffs.append(("pnl", a, j, dg))
        else:
            res["exit_diff"] += 1
            diffs.append(("exit", a, j))
    res["extra"] = len(rep["open"]) - len(seen)
    return res, diffs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("run")
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--ids", default="")
    ap.add_argument("--show", type=int, default=3)
    ap.add_argument("--swap", default="export", help="'export', 'fit' (from the archive) or 'LONG,SHORT' in pips")
    ap.add_argument("--roll", type=int, default=21 * 60, help="rollover minute UTC (fullgrid.py --roll fit finds it)")
    ap.add_argument("--schedule", default="export", choices=("export", "now"),
                    help="broker trading hours: 'export' (archived runs) or 'now' (data.py, broker_hours.json)")
    args = ap.parse_args()
    m = data.load(args.export, schedule=args.schedule)
    spec = engine.Spec(m.meta)
    if args.swap == "fit":
        from fullgrid import fit_swaps
        spec.swap_long_pips, spec.swap_short_pips = fit_swaps(m, spec, args.run)
    elif args.swap != "export":
        spec.swap_long_pips, spec.swap_short_pips = (float(x) for x in args.swap.split(","))
    spec.roll_min = args.roll
    ids = [int(x) for x in args.ids.split(",") if x]
    total = Counter()
    passes_exact = 0
    npass = 0
    for pid, values, trades in archive_passes(args.run, ids=ids or None, sample=None if ids else args.sample):
        tf = values["Timeframe"]
        if tf not in m.bars:
            m.bars[tf] = data.chart_bars(m, tf)
        try:
            rep = engine.run_pass(m, spec, tf, values)
        except engine.Unsupported as e:
            print(f"pass {pid:>6}: skipped, {e}")
            continue
        arch = archive_rows(trades)
        res, diffs = compare_pass(rep, arch)
        total.update(res)
        npass += 1
        ok = res["exact"] == len(arch) and res["extra"] == 0
        passes_exact += ok
        net_a = sum(a["net"] for a in arch)
        net_r = float(rep["net"].sum())
        print(f"pass {pid:>6} {tf:>3} {short(values)} | "
              f"trades {len(arch):>4} vs {len(rep['open']):>4} exact {res['exact']:>4} | net {net_a:>10.2f} vs {net_r:>10.2f}"
              + ("  OK" if ok else ""))
        for d in diffs[:args.show]:
            print("    ", describe(d, rep))
    n = sum(total[k] for k in ("exact", "swap_diff", "pnl_diff", "exit_diff", "missing"))
    print(f"\n{npass} passes, {passes_exact} identical; archived trades {n}: " +
          ", ".join(f"{k} {total[k]} ({100.0 * total[k] / max(n, 1):.2f}%)" for k in ("exact", "swap_diff", "pnl_diff", "exit_diff", "missing"))
          + f"; extra replica trades {total['extra']}")


MODE_KEYS = {"0": ["WeeklyBandMult", "WeeklyFirstHours", "WeeklyLastHours", "WeeklyForceCloseFriday"],
             "1": ["SessionBandMult", "BlockSessionFirst", "BlockSessionLast", "SessionForceClose"],
             "2": ["IntradaySource", "EthBandMult", "RthBandMult", "BlockEthFirst", "BlockEthLast", "BlockRthFirst", "BlockRthLast",
                   "CloseAtEthEnd", "CloseAtRthEnd"]}
SHORT = {"Management": "mg", "StopAtrMult": "stop", "TargetR": "TP", "BandTrailTrigger": "trig", "VwapTrailAtrCushion": "cush"}


def short(values):
    """The parameters that matter for this pass, compactly."""
    keys = ["Management", "StopAtrMult"] + (["TargetR"] if str(values.get("Management", "0")) == "0" else []) + (
        ["BandTrailTrigger", "VwapTrailAtrCushion"] if str(values.get("Management")) in ("5", "6") else []) + MODE_KEYS.get(
        str(values.get("Mode", "1")), [])
    return " ".join(f"{SHORT.get(k, k)} {values.get(k)}" for k in keys)


def describe(d, rep):
    kind, a = d[0], d[1]
    ts = lambda ms: np.datetime64(int(ms), "ms").astype(str)[:16]
    side = "Buy" if a["side"] > 0 else "Sell"
    if kind == "missing in replica":
        return f"missing: {side} open {ts(a['open'])} close {ts(a['close'])} ev {a['event']} net {a['net']}"
    j = d[2]
    r = f"rep close {ts(rep['close'][j])} ev {rep['event'][j]} entry {rep['entry'][j]} exit {rep['exit'][j]} vol {rep['vol'][j]} gross {rep['gross'][j]} swap {rep['swap'][j]}"
    return f"{kind}: {side} open {ts(a['open'])} | arch close {ts(a['close'])} ev {a['event']} gross {a['gross']} swap {a['swap']} | {r}"


if __name__ == "__main__":
    main()
