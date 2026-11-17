"""Build / check the research store (DESIGN §3.4).

  python -m engine.build_store convert EURUSD XAUUSD [--workers 2]   convert those symbols (raw export -> store)
  python -m engine.build_store convert --all [--workers 8]           every symbol in the raw exports
  python -m engine.build_store check EURUSD XAUUSD                   counts vs data-checks/ic-tick/*.json, sizes, read speed

Results are appended to data-checks/research-store.json (one entry per symbol per action).
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from engine import store

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATACHECK = os.path.join(REPO, "data-checks", "ic-tick")
RESULTS = os.path.join(REPO, "data-checks", "research-store.json")


def raw_folder(symbol):
    for d in sorted(os.listdir(store.RAW_ROOT)):
        if d.split("_")[0] == symbol and os.path.isfile(os.path.join(store.RAW_ROOT, d, "meta.json")):
            return os.path.join(store.RAW_ROOT, d)
    raise FileNotFoundError(symbol)


def all_symbols():
    return sorted(d.split("_")[0] for d in os.listdir(store.RAW_ROOT)
                  if os.path.isfile(os.path.join(store.RAW_ROOT, d, "meta.json")))


def _convert(symbol):
    lines = []
    st = store.convert_symbol(raw_folder(symbol), log=lines.append)
    return st


def check(symbol):
    """Month tick counts vs the data check; sizes; time to read each month (decode + float conversion)."""
    folder = os.path.basename(raw_folder(symbol))
    dc = json.load(open(os.path.join(DATACHECK, folder + ".json")))
    want = {m["ym"]: m["ticks"] for m in dc["months"] if "2014-11" <= m["ym"] <= "2024-12"}
    meta = store.store_meta(symbol)
    have = {k: v["n"] for k, v in meta["months"].items()}
    mismatches = {m: [want.get(m), have.get(m)] for m in sorted(set(want) | set(have)) if want.get(m) != have.get(m)}
    times = []
    for m in sorted(have):
        t0 = time.perf_counter()
        tk = store.load_ticks(symbol, m, m)
        times.append(time.perf_counter() - t0)
        assert len(tk) == have[m]
        assert tk.t.max() < store.CUTOFF_MS and tk.t.min() >= store.RESEARCH_START_MS
    sdir = os.path.join(store.STORE_ROOT, symbol)
    tick_bytes = sum(os.path.getsize(os.path.join(sdir, "ticks", f)) for f in os.listdir(os.path.join(sdir, "ticks")))
    bar_bytes = sum(os.path.getsize(os.path.join(sdir, f)) for f in os.listdir(sdir) if f.endswith((".bk", ".npy")))
    t0 = time.perf_counter()
    b = store.load_bars(symbol, "bars_m1")
    t_m1 = time.perf_counter() - t0
    assert b["open_ms"].max() + 60_000 <= store.CUTOFF_MS
    big = max(have, key=have.get)
    return {
        "symbol": symbol, "action": "check", "months": len(have), "ticks": int(sum(have.values())),
        "count_mismatches": mismatches, "tick_gb": round(tick_bytes / 1e9, 3), "bar_gb": round(bar_bytes / 1e9, 3),
        "bytes_per_tick": round(tick_bytes / max(1, sum(have.values())), 3),
        "read_month_s_median": round(float(np.median(times)), 3), "read_month_s_max": round(float(np.max(times)), 3),
        "largest_month": [big, have[big]], "read_m1_bars_s": round(t_m1, 3), "m1_bars": int(len(b["open_ms"])),
        "checked_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime()),
    }


def _append(entry):
    data = json.load(open(RESULTS)) if os.path.isfile(RESULTS) else []
    data.append(entry)
    json.dump(data, open(RESULTS, "w"), indent=1)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["convert", "check"])
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args(argv)
    syms = all_symbols() if a.all else a.symbols
    if a.action == "convert":
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            for sym, st in zip(syms, ex.map(_convert, syms)):
                st["action"] = "convert"
                _append(st)
                print(json.dumps(st), flush=True)
    for sym in syms:
        r = check(sym)
        _append(r)
        print(json.dumps(r), flush=True)


if __name__ == "__main__":
    sys.exit(main())
