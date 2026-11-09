"""Price-noise robustness test: how much do price-only signals change if every bar is shifted by a small, broker-like
amount? A proxy for "would this still trade the same on another firm's feed".

Noise model per bar: a common offset N(0, sigma) on open/high/low/close (one feed quotes slightly higher or lower) plus
independent jitter N(0, sigma/2) per field; high/low are then widened to stay the bar's extremes. sigma is given in multiples
of the symbol's typical spread (default 0.25, 0.5, 1.0 spread).

Usage: noise_test.py <export folder> --spread <pips> [--from YYYY-MM-DD --to YYYY-MM-DD] [--tf m5,m15,h1] [--runs 5]
Later strategies plug in here the same way: a function bars -> signal times, or bars -> trade list.
"""
import argparse
import numpy as np
import pandas as pd
from feed_compare import load_bars, load_meta, TF_MS
from signals import PROBES, agreement


def jitter(b, sigma, rng):
    n = len(b)
    common = rng.normal(0, sigma, n)
    o, h, l, c = (b[k].to_numpy() + common + rng.normal(0, sigma / 2, n) for k in ("open", "high", "low", "close"))
    h = np.maximum.reduce([h, o, c]); l = np.minimum.reduce([l, o, c])
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=b.index)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder"); ap.add_argument("--spread", type=float, required=True, help="typical spread in pips/points")
    ap.add_argument("--from", dest="t0"); ap.add_argument("--to", dest="t1")
    ap.add_argument("--tf", default="m5,m15,h1"); ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--sigmas", default="0.25,0.5,1.0")
    args = ap.parse_args()
    meta = load_meta(args.folder)
    pip = float(meta.get("pip_size") or meta.get("tick_size"))
    t0 = int(pd.Timestamp(args.t0, tz="UTC").value // 1e6) if args.t0 else None
    t1 = int(pd.Timestamp(args.t1, tz="UTC").value // 1e6) if args.t1 else None
    rng = np.random.default_rng(1)
    print(f"# Noise test: {meta['symbol']}, spread {args.spread} pips, {args.runs} runs per cell\n")
    print("| probe | tf | noise (× spread) | same bar | within ±1 bar |\n|---|---|---|---|---|")
    for tf in args.tf.split(","):
        b = load_bars(args.folder, tf, t0, t1)
        for name, fn in PROBES.items():
            base = fn(b)
            for s in map(float, args.sigmas.split(",")):
                ex, nr = zip(*(agreement(base, fn(jitter(b, s * args.spread * pip, rng)), TF_MS[tf]) for _ in range(args.runs)))
                print(f"| {name} | {tf} | {s:g} | {np.mean(ex) * 100:.1f}% | {np.mean(nr) * 100:.1f}% |")


if __name__ == "__main__":
    main()
