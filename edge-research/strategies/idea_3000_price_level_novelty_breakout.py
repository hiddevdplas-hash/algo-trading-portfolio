"""IDEA-3000: price-level novelty breakout (card v1, ideas/cards/IDEA-3000-price-level-novelty-breakout.md).

Rebuilt from the card's description of the idea source (TradingView "LUBE" by Jomy); no code copied.
- O(i) = share of bars i-N .. i-1 whose [low, high] contains close(i).
- P(i) = percentile rank of O(i) among O(i-500) .. O(i-1) (ties count half), in %.
- Entry at bar i's close when P(i) <= q and P(i-1) > q: long if close(i) > mean mid-price of bars i-N .. i-1, else short.
- Stop k x Wilder ATR(14); exit flag when P >= 50; time exit 72 h. Class B rules, news modes and caps are applied by the engine.
params (card defaults): N = 480, q = 5, k = 2.0.
"""
import numpy as np

_PCT_HIST = 500
_EXIT_PCT = 50.0
_ATR_N = 14
_HOLD_MS = 72 * 3_600_000


def _wilder_atr(h, l, c, n):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        out[n - 1] = tr[:n].mean()
        for i in range(n, len(c)):
            out[i] = out[i - 1] + (tr[i] - out[i - 1]) / n
    return out


def intents(bars, params, ctx):
    N = int(params.get("N", 480))
    q = float(params.get("q", 5))
    k = float(params.get("k", 2.0))
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    om = np.asarray(bars["open_ms"], np.int64)
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "hold_ms": hold, "exit_long": exl, "exit_short": exs}
    if n <= N + _PCT_HIST + 1:
        return out

    # occupancy and mean mid-price over the previous N bars (bars i-N .. i-1 only)
    occ = np.zeros(n)
    mid = (h + l) / 2.0
    cs = np.r_[0.0, np.cumsum(mid)]
    for j in range(1, N + 1):
        occ[j:] += (l[:-j] <= c[j:]) & (c[j:] <= h[:-j])
    occ /= N
    occ[:N] = np.nan
    mmean = np.full(n, np.nan)
    idx = np.arange(N, n)
    mmean[N:] = (cs[idx] - cs[idx - N]) / N

    # percentile rank of occ(i) among the previous _PCT_HIST values
    below = np.zeros(n)
    equal = np.zeros(n)
    for j in range(1, _PCT_HIST + 1):
        below[j:] += occ[:-j] < occ[j:]
        equal[j:] += occ[:-j] == occ[j:]
    pct = 100.0 * (below + 0.5 * equal) / _PCT_HIST
    pct[: N + _PCT_HIST] = np.nan

    atr = _wilder_atr(h, l, c, _ATR_N)
    prev = np.r_[np.nan, pct[:-1]]
    trig = (pct <= q) & (prev > q) & np.isfinite(atr) & np.isfinite(mmean)
    trig &= om >= int(ctx["first_ms"])
    direction = np.where(c > mmean, 1, -1)
    side[trig] = direction[trig]
    sl[trig] = k * atr[trig]
    hold[trig] = _HOLD_MS
    back = pct >= _EXIT_PCT
    exl[back] = True
    exs[back] = True
    return out
