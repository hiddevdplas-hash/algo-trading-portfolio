"""Simple price-only signal families used to measure how much two price feeds disagree.

Each function takes a bars DataFrame (index = bar open time in ms, columns open/high/low/close) and returns a pandas Index of
bar open times where the signal fires (decided on that bar's close). They are probes, not strategies.
"""
import numpy as np
import pandas as pd


def ema(x, n):
    return x.ewm(span=n, adjust=False).mean()


def ema_cross(b, fast=20, slow=50):
    """Bars where EMA(fast) crosses EMA(slow), either direction."""
    f, s = ema(b["close"], fast), ema(b["close"], slow)
    side = np.sign(f - s)
    return b.index[(side != side.shift(1)) & side.shift(1).notna() & (side != 0)]


def donchian_break(b, n=20):
    """Bars whose close breaks the high or low of the previous n bars."""
    hi = b["high"].rolling(n).max().shift(1)
    lo = b["low"].rolling(n).min().shift(1)
    return b.index[(b["close"] > hi) | (b["close"] < lo)]


def fractals(b, k=2):
    """Bill Williams fractal highs / lows: the high (low) of the middle bar is the strict max (min) of 2k+1 bars.
    Stamped on the bar where it becomes known (k bars after the middle one)."""
    h, l = b["high"].to_numpy(), b["low"].to_numpy()
    n = len(b)
    out = []
    for i in range(k, n - k):
        wh, wl = h[i - k:i + k + 1], l[i - k:i + k + 1]
        if (h[i] == wh.max() and (wh == h[i]).sum() == 1) or (l[i] == wl.min() and (wl == l[i]).sum() == 1):
            out.append(i + k)
    return b.index[out]


PROBES = {"EMA20/50 cross": ema_cross, "Donchian20 break": donchian_break, "Fractal(2)": fractals}


def agreement(a_idx, b_idx, bar_ms, tol_bars=1):
    """Share of signals that match: exact (same bar) and within +-tol_bars. Jaccard-style: matched / union."""
    a, b = np.asarray(a_idx, dtype=np.int64), np.asarray(b_idx, dtype=np.int64)
    if len(a) == 0 and len(b) == 0:
        return 1.0, 1.0
    sa, sb = set(a.tolist()), set(b.tolist())
    exact = len(sa & sb) / max(1, len(sa | sb))
    bs = np.sort(b)
    pos = np.searchsorted(bs, a)
    near = 0
    for p, t in zip(pos, a):
        cands = bs[max(0, p - 1):p + 1]
        if len(cands) and np.min(np.abs(cands - t)) <= tol_bars * bar_ms:
            near += 1
    near_share = near / max(1, len(sa) + len(sb) - near)
    return exact, near_share
