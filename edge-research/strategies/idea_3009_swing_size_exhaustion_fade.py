"""IDEA-3009: swing-size exhaustion fade (card v1, ideas/cards/IDEA-3009-swing-size-exhaustion-fade.md).

Rebuilt from the card's description of the idea source (TradingView "Swing Exhaustion Fade | Learned Odds + Liquidity Sweeps"
by blitz_algo); no code copied.
- h1 bars. ATR(i) = simple mean of the true range of bars i-13 .. i (ATR14).
- Zigzag on highs / lows, updated at each bar's close; starts in an up swing (start = low(0), extreme = high(0)). Up swing: a higher
  high moves the extreme; if extreme - low(i) >= k x ATR(i) the up swing completes with size (extreme - start) / ATR(i) and a down
  swing starts (start = old extreme, extreme = low(i)). Down swing: the mirror.
- Reference: the last 40 completed swings of the live swing's direction (none traded before 40 exist); Q = their q-quantile.
- Live up swing: S = (extreme - start) / ATR(i) >= max(Q, 2) and (extreme - close(i)) / ATR(i) >= 0.5, once per swing -> sell at the
  close; stop 0.25 x ATR(i) beyond the extreme; target T x stop; time exit 8 h. Live down swing: the mirror (buy).
params (card defaults): k = 2.5, q = 0.8, T = 1.5. Class A rules, news modes and caps are applied by the engine.
"""
import numpy as np

_ATR_N = 14
_W = 40
_MIN_SWING = 2.0
_TURN = 0.5
_BUF = 0.25
_HOLD_MS = 8 * 3_600_000


def _atr(h, l, c, n):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.where(np.isnan(pc), h - l, np.maximum(h, pc) - np.minimum(l, pc))
    cs = np.concatenate(([0.0], np.cumsum(tr)))
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def intents(bars, params, ctx):
    k = float(params.get("k", 2.5))
    q = float(params.get("q", 0.8))
    T = float(params.get("T", 1.5))
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    om = np.asarray(bars["open_ms"], np.int64)
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    tp = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    out = {"side": side, "sl_dist": sl, "tp_dist": tp, "hold_ms": hold}
    if n == 0:
        return out

    atr = _atr(h, l, c, _ATR_N)
    first_ms = int(ctx["first_ms"])
    hist = {1: [], -1: []}          # completed swing sizes (ATR units) by direction
    d = 1
    start = l[0]
    ext = h[0]
    traded = False
    for i in range(1, n):
        a = atr[i]
        if d == 1:
            if h[i] > ext:
                ext = h[i]
            if a > 0 and ext - l[i] >= k * a:
                hist[1].append((ext - start) / a)
                d, start, ext, traded = -1, ext, l[i], False
                continue
        else:
            if l[i] < ext:
                ext = l[i]
            if a > 0 and h[i] - ext >= k * a:
                hist[-1].append((start - ext) / a)
                d, start, ext, traded = 1, ext, h[i], False
                continue
        if traded or not (a > 0) or om[i] < first_ms or len(hist[d]) < _W:
            continue
        Q = float(np.quantile(np.asarray(hist[d][-_W:]), q))
        size = d * (ext - start) / a
        turn = d * (ext - c[i]) / a
        if size >= max(Q, _MIN_SWING) and turn >= _TURN:
            stop = d * (ext + d * _BUF * a - c[i])
            if stop > 0:
                side[i] = -d
                sl[i] = stop
                tp[i] = T * stop
                hold[i] = _HOLD_MS
                traded = True
    return out
