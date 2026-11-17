"""Referee comparison: cTrader's trade list (the cBot's CSV) vs the engine's (DESIGN §4.5 item 2; bar >= 99% identical).

A trade is identical when side, fill time, entry price, exit time and exit price agree (prices within a tenth of a tick) and the
exit kinds are equivalent (engine 'trail' = cTrader StopLoss after a trail, or the cBot's 'Closed:trail' when the new stop was
already beaten). Trades cut by the end of the window (engine 'end', cBot 'Closed:end' / 'Closed:?') are listed, not scored.
Identical share = identical / max(engine trades, cTrader trades), both without end-cut trades.

  ~/.venvs/fastbt/bin/python -m tests.referees.compare R1 [path to the cBot CSV]    (default ~/cAlgo/Exports/referees/<R>_<SYM>_<seed>.csv)
"""
import csv
import json
import os
import sys
from datetime import datetime, timezone

from tests.referees.referees import OUT, SPECS, Grid, day_ms

CT_ROOT = os.path.expanduser("~/cAlgo/Exports/referees")
END_KINDS = {"end", "Closed:end", "Closed:?"}


def read(path):
    rows, notes = [], []
    with open(path, newline="") as fh:
        for line in fh:
            if line.startswith("#"):
                notes.append(line.strip())
    with open(path, newline="") as fh:
        for r in csv.DictReader(l for l in fh if not l.startswith("#")):
            rows.append(r)
    return rows, notes


def f(x):
    return float(x) if x not in ("", None) else float("nan")


def kinds_match(py, ct):
    if py == ct:
        return True
    return py == "trail" and ct in ("StopLoss", "Closed:trail")


def utc(ms):
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def compare(ref, ct_path=None):
    sp = SPECS[ref]
    g = Grid(sp["symbol"])
    tol = g.tick / 10
    py_path = os.path.join(OUT, f"{ref}_{sp['symbol']}_{sp['seed']}_python.csv")
    ct_path = ct_path or os.path.join(CT_ROOT, f"{ref}_{sp['symbol']}_{sp['seed']}.csv")
    py, _ = read(py_path)
    ct, notes = read(ct_path)
    # both lists only inside the window both cover
    last_ct = max((int(r["exit_ms"]) for r in ct), default=0)
    lo, hi = day_ms(sp["trade_from"]), min(day_ms(sp["end"]), last_ct + 1)
    py = [r for r in py if lo <= int(r["fill_ms"]) < hi]
    ct = [r for r in ct if lo <= int(r["fill_ms"]) < hi]
    py_end = [r for r in py if r["exit_kind"] in END_KINDS]
    ct_end = [r for r in ct if r["exit_kind"] in END_KINDS]
    py = [r for r in py if r["exit_kind"] not in END_KINDS]
    ct = [r for r in ct if r["exit_kind"] not in END_KINDS]
    by_ct = {}
    for r in ct:
        by_ct.setdefault((int(r["side"]), int(r["fill_ms"])), []).append(r)
    identical, differ, only_py = [], [], []
    used = set()
    for r in py:
        key = (int(r["side"]), int(r["fill_ms"]))
        cands = [c for c in by_ct.get(key, []) if id(c) not in used]
        if not cands:
            only_py.append(r)
            continue
        c = cands[0]
        used.add(id(c))
        diffs = []
        if abs(f(r["entry_px"]) - f(c["entry_px"])) > tol:
            diffs.append(f"entry {r['entry_px']} vs {c['entry_px']}")
        if abs(f(r["sl0"]) - f(c["sl0"])) > tol:
            diffs.append(f"sl0 {r['sl0']} vs {c['sl0']}")
        if r["exit_ms"] != c["exit_ms"]:
            diffs.append(f"exit time {utc(r['exit_ms'])} vs {utc(c['exit_ms'])}")
        if abs(f(r["exit_px"]) - f(c["exit_px"])) > tol:
            diffs.append(f"exit {r['exit_px']} vs {c['exit_px']}")
        if not kinds_match(r["exit_kind"], c["exit_kind"]):
            diffs.append(f"kind {r['exit_kind']} vs {c['exit_kind']}")
        (differ if diffs else identical).append((r, c, diffs))
    only_ct = [c for c in ct if id(c) not in used]
    denom = max(len(py), len(ct)) or 1
    res = {"ref": ref, **sp, "ctrader_csv": ct_path, "window_utc": [utc(lo), utc(hi)],
           "engine_trades": len(py), "ctrader_trades": len(ct), "identical": len(identical),
           "identical_pct": round(100 * len(identical) / denom, 2), "pass_99": len(identical) / denom >= 0.99,
           "differ": [{"fill": utc(r["fill_ms"]), "side": r["side"], "diffs": d} for r, c, d in differ],
           "only_engine": [{"fill": utc(r["fill_ms"]), "side": r["side"], "kind": r["exit_kind"]} for r in only_py],
           "only_ctrader": [{"fill": utc(c["fill_ms"]), "side": c["side"], "kind": c["exit_kind"]} for c in only_ct],
           "end_cut": {"engine": len(py_end), "ctrader": len(ct_end)}, "ctrader_notes": notes}
    json.dump(res, open(os.path.join(OUT, f"{ref}_compare.json"), "w"), indent=1)
    return res


if __name__ == "__main__":
    r = compare(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(f"{r['ref']} {r['name']} {r['symbol']}: {r['identical']} identical of engine {r['engine_trades']} / cTrader "
          f"{r['ctrader_trades']} = {r['identical_pct']}% ({'PASS' if r['pass_99'] else 'below 99%'}); differ {len(r['differ'])}, "
          f"engine only {len(r['only_engine'])}, cTrader only {len(r['only_ctrader'])}")
    for k in ("differ", "only_engine", "only_ctrader"):
        for x in r[k][:20]:
            print(" ", k, x)
    for n in r["ctrader_notes"]:
        print(" ", n)
