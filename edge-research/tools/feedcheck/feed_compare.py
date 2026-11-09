"""Compare two FastBtExport folders of the same instrument from different brokers / prop firms (e.g. IC vs FTMO).

Reports, on the overlapping period:
  - server-time offset between the feeds (the shift that best aligns the bars) and bar coverage on each side
  - price differences of close / high / low (in pips or points, and as a share of the typical spread)
  - real spreads from ticks (only meaningful for a 'Tick data from server' export; m1-bar exports have a fixed spread)
  - signal agreement of simple price-only probes (EMA cross, Donchian break, fractals) per timeframe

Usage:
  feed_compare.py <folder A> <folder B> [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--tf m5,m15,h1] [--out report.md]
"""
import argparse, gzip, json, os, sys
import numpy as np
import pandas as pd
from signals import PROBES, agreement

TF_MS = {"m1": 60_000, "m5": 300_000, "m10": 600_000, "m15": 900_000, "m30": 1_800_000, "h1": 3_600_000, "h2": 7_200_000,
         "h4": 14_400_000}


def load_meta(folder):
    with open(os.path.join(folder, "meta.json")) as f:
        return json.load(f)


def load_bars(folder, tf, t0=None, t1=None):
    b = pd.read_csv(os.path.join(folder, f"bars_{tf}.csv.gz"), index_col="open_ms")
    if t0 is not None:
        b = b[(b.index >= t0) & (b.index < t1)]
    return b[["open", "high", "low", "close"]]


def load_spreads(folder, t0=None, t1=None):
    """Spread histogram over the window, read in chunks (a real tick export has 50M+ rows). Returns {spread: count}."""
    hist = {}
    for t in pd.read_csv(os.path.join(folder, "ticks.csv.gz"), usecols=["time_ms", "bid", "ask"], dtype=str, chunksize=5_000_000):
        t = t[t.time_ms != "B"].astype({"time_ms": "int64", "bid": float, "ask": float})  # "B,<ms>" rows mark bar closes
        if t0 is not None:
            t = t[(t.time_ms >= t0) & (t.time_ms < t1)]
        for s, n in (t["ask"] - t["bid"]).round(6).value_counts().items():
            hist[s] = hist.get(s, 0) + int(n)
    return hist


def hist_quantile(hist, q):
    keys = sorted(hist)
    cum, total = 0, sum(hist.values())
    for k in keys:
        cum += hist[k]
        if cum >= q * total:
            return k
    return keys[-1]


def best_offset(a, b, hours=range(-4, 5)):
    """Shift (ms) to add to B's timestamps so its bars line up with A's; minimises the median |close difference|."""
    best = None
    for h in hours:
        sh = h * 3_600_000
        j = a[["close"]].join(b[["close"]].set_axis(b.index + sh), how="inner", rsuffix="_b")
        if len(j) < 100:
            continue
        m = float(np.median(np.abs(j["close"] - j["close_b"])))
        if best is None or m < best[1]:
            best = (sh, m, len(j))
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--from", dest="t0"); ap.add_argument("--to", dest="t1")
    ap.add_argument("--tf", default="m5,m15,h1"); ap.add_argument("--out")
    ap.add_argument("--b-shift-ms", type=int, default=None, help="force B's time shift instead of detecting it")
    args = ap.parse_args()
    t0 = int(pd.Timestamp(args.t0, tz="UTC").value // 1e6) if args.t0 else None
    t1 = int(pd.Timestamp(args.t1, tz="UTC").value // 1e6) if args.t1 else None
    ma, mb = load_meta(args.a), load_meta(args.b)
    pip = float(ma.get("pip_size") or ma.get("tick_size"))
    lines = [f"# Feed comparison: {ma['symbol']} (A: {os.path.basename(args.a.rstrip('/'))}) vs {mb['symbol']} "
             f"(B: {os.path.basename(args.b.rstrip('/'))})", ""]
    if ma.get("digits") != mb.get("digits"):
        lines.append(f"**Note:** digits differ (A {ma.get('digits')}, B {mb.get('digits')}); prices compared as they are.")

    a5 = load_bars(args.a, "m5", t0, t1); b5 = load_bars(args.b, "m5")
    off = (args.b_shift_ms, None, None) if args.b_shift_ms is not None else best_offset(a5, b5)
    if off is None:
        print("no overlap between the two exports"); sys.exit(1)
    shift = off[0]
    b5 = b5.set_axis(b5.index + shift)
    if t0 is not None:
        b5 = b5[(b5.index >= t0) & (b5.index < t1)]
    lo, hi = max(a5.index.min(), b5.index.min()), min(a5.index.max(), b5.index.max())
    a5o, b5o = a5[(a5.index >= lo) & (a5.index <= hi)], b5[(b5.index >= lo) & (b5.index <= hi)]
    j = a5o.join(b5o, how="inner", rsuffix="_b")
    for tag, x in (("A", a5o), ("B", b5o)):
        gaps = np.diff(x.index.to_numpy())
        for i in np.where(gaps > 7 * 86_400_000)[0]:
            lines.append(f"**WARNING: {tag} has a data gap {pd.Timestamp(x.index[i], unit='ms', tz='UTC'):%Y-%m-%d} → "
                         f"{pd.Timestamp(x.index[i + 1], unit='ms', tz='UTC'):%Y-%m-%d}; signal counts over it are not comparable. "
                         f"Rerun with --from / --to on a gap-free window.**")
    lines += [f"- overlap: {pd.Timestamp(lo, unit='ms', tz='UTC'):%Y-%m-%d} → {pd.Timestamp(hi, unit='ms', tz='UTC'):%Y-%m-%d}",
              f"- B's clock shift to match A: **{shift / 3_600_000:+.0f} h**",
              f"- m5 bars: A {len(a5o):,}, B {len(b5o):,}, both {len(j):,} "
              f"(A only {len(a5o) - len(j):,}, B only {len(b5o) - len(j):,})", ""]

    try:
        sa = load_spreads(args.a, lo, hi + 300_000); sb = load_spreads(args.b, lo - shift, hi - shift + 300_000)
        fixed_a, fixed_b = len(sa) <= 2, len(sb) <= 2
        # relative differences use a real (tick-export) spread when one side has it
        med_spread = hist_quantile(sb if fixed_a else sa, .5)
        lines += ["| spread (pips / points) | A | B |", "|---|---|---|",
                  f"| median | {hist_quantile(sa, .5) / pip:.2f}{' (fixed: m1-bar export)' if fixed_a else ''} | "
                  f"{hist_quantile(sb, .5) / pip:.2f}{' (fixed: m1-bar export)' if fixed_b else ''} |",
                  f"| 95th pct | {hist_quantile(sa, .95) / pip:.2f} | {hist_quantile(sb, .95) / pip:.2f} |", ""]
    except FileNotFoundError:
        med_spread = None

    lines += ["| m5 price difference A − B | median abs (pips) | 95th pct | max | median abs ÷ median spread |", "|---|---|---|---|---|"]
    for c in ("close", "high", "low"):
        d = np.abs(j[c] - j[c + "_b"]) / pip
        rel = f"{np.median(d) * pip / med_spread:.2f}" if med_spread else "–"
        lines.append(f"| {c} | {np.median(d):.2f} | {np.quantile(d, .95):.2f} | {d.max():.2f} | {rel} |")
    lines.append("")

    lines += ["| signal probe | tf | signals A | signals B | same bar | within ±1 bar |", "|---|---|---|---|---|---|"]
    for tf in args.tf.split(","):
        a = load_bars(args.a, tf); b = load_bars(args.b, tf)
        b = b.set_axis(b.index + shift)
        a, b = a[(a.index >= lo) & (a.index <= hi)], b[(b.index >= lo) & (b.index <= hi)]
        for name, fn in PROBES.items():
            sa_, sb_ = fn(a), fn(b)
            ex, near = agreement(sa_, sb_, TF_MS[tf])
            lines.append(f"| {name} | {tf} | {len(sa_):,} | {len(sb_):,} | {ex * 100:.1f}% | {near * 100:.1f}% |")
    text = "\n".join(lines)
    print(text)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")


if __name__ == "__main__":
    main()
