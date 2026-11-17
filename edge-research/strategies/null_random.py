"""Random-entry strategy for the null calibration (DESIGN §8). Lane 'null'. No edge by construction: entry bars and directions are
drawn from a seeded generator that depends only on (seed, symbol), so every grid point and filter variation trades the same random
entry moments and only the exits differ.

params:
  seed        int; the draw for each symbol uses (seed, crc32(symbol))
  freq        expected entries per year per symbol (before the engine's rules and the one-position limit)
  stop_atr    stop distance in Wilder ATR(14) of the decision bar's timeframe
  target_r    target in R (0 = none)
  hold_h      time exit in hours (0 = none)
  stop_mult, exit_mult   grid multipliers on stop_atr and on target_r (or hold_h when there is no target)
  entry_variant          grid axis that changes the entry draw (real grids often tune entry parameters); 0 = the base draw
"""
import zlib

import numpy as np


def _atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        out[n - 1] = tr[:n].mean()
        a = 1.0 / n
        for i in range(n, len(c)):
            out[i] = out[i - 1] + a * (tr[i] - out[i - 1])
    return out


def intents(bars, params, ctx):
    o = bars["open_ms"]
    n = len(o)
    rng = np.random.default_rng([int(params["seed"]), zlib.crc32(ctx["symbol"].encode()), int(params.get("entry_variant", 0))])
    u = rng.random(n)
    d = rng.choice(np.array([-1, 1]), n)
    live = (o >= ctx["first_ms"]) & (o < ctx["end_ms"])
    years = max((ctx["end_ms"] - ctx["first_ms"]) / (365.25 * 86_400_000), 1e-9)
    per_year = max(live.sum() / years, 1.0)
    p = min(float(params["freq"]) / per_year, 1.0)
    atr = _atr(bars["h"], bars["l"], bars["c"])
    side = np.where(live & (u < p) & ~np.isnan(atr), d, 0).astype(np.int64)
    sl = float(params["stop_atr"]) * float(params.get("stop_mult", 1.0)) * atr
    em = float(params.get("exit_mult", 1.0))
    tr = float(params.get("target_r", 0) or 0)
    hh = float(params.get("hold_h", 0) or 0)
    tp = sl * tr * em if tr > 0 else np.full(n, np.nan)
    hold = np.full(n, hh * em * 3_600_000 if hh > 0 and tr <= 0 else (hh * 3_600_000 if hh > 0 else np.nan))
    return {"side": side, "sl_dist": sl, "tp_dist": tp, "hold_ms": hold}
