"""IDEA-3007: low-participation pullback in a slower trend (card v1, ideas/cards/IDEA-3007-low-participation-cci-pullback.md).

Rebuilt from the classic CCI formula and the card's description of the idea source (TradingView "RedK DualTF Volume-Accelerated CCI"
by RedKTrader); no code copied.
- h1 bars. TP = (h + l + c) / 3, w = tick volume (floored at 1). Over a window of n bars ending at i:
  mu = sum(w TP) / sum(w), D = sum(w |TP - mu|) / sum(w), CCI = (TP(i) - mu) / (0.015 D). fast: n = L; context: n = 4L.
- Long at bar i's close: fast(i-1) < -K <= fast(i), context(i) > 0, mean w of the last min(r, 10) dip bars (r = consecutive bars
  ending at i-1 with fast < -K) below the mean w of bars i-4L .. i-1, no time gap before bar i, 5L + 24 bars of warm-up. Short: mirror.
- Stop S x ATR(24) (simple mean true range of bars i-23 .. i); exit at market when fast > +K (long) / < -K (short); time exit 12 h.
params (card defaults): L = 20, K = 100, S = 1.5. Class A rules, news modes and caps are applied by the engine.
"""
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

_HOUR = 3_600_000
_HOLD_H = 12
_CTX_MULT = 4
_DIP_CAP = 10
_ATR_N = 24
_LAMBERT = 0.015


def _vw_cci(tp, w, n):
    out = np.full(len(tp), np.nan)
    if len(tp) < n:
        return out
    T = sliding_window_view(tp, n)
    W = sliding_window_view(w, n)
    sw = W.sum(axis=1)
    mu = (W * T).sum(axis=1) / sw
    D = (W * np.abs(T - mu[:, None])).sum(axis=1) / sw
    with np.errstate(divide="ignore", invalid="ignore"):
        cci = np.where(D > 0, (T[:, -1] - mu) / (_LAMBERT * D), np.nan)
    out[n - 1:] = cci
    return out


def intents(bars, params, ctx):
    L = int(params.get("L", 20))
    K = float(params.get("K", 100))
    S = float(params.get("S", 1.5))
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    w = np.maximum(np.asarray(bars["vol"], float), 1.0)
    om = np.asarray(bars["open_ms"], np.int64)
    cm = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "hold_ms": hold, "exit_long": exl, "exit_short": exs}
    if n < 2:
        return out

    tp = (h + l + c) / 3.0
    fast = _vw_cci(tp, w, L)
    ctxc = _vw_cci(tp, w, _CTX_MULT * L)

    prev_c = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h, prev_c) - np.minimum(l, prev_c)
    tr[0] = h[0] - l[0]
    ctr = np.concatenate(([0.0], np.cumsum(tr)))
    atr = np.full(n, np.nan)
    atr[_ATR_N - 1:] = (ctr[_ATR_N:] - ctr[:-_ATR_N]) / _ATR_N

    cw = np.concatenate(([0.0], np.cumsum(w)))       # cw[k] = sum of w[0 .. k-1]
    exl[:] = fast > K
    exs[:] = fast < -K

    first_ms = int(ctx["first_ms"])
    warm = 5 * L + _ATR_N
    span = _CTX_MULT * L
    run_dn = 0                                        # consecutive bars ending at i-1 with fast < -K
    run_up = 0                                        # consecutive bars ending at i-1 with fast > +K
    for i in range(1, n):
        f_prev = fast[i - 1]
        run_dn = run_dn + 1 if f_prev < -K else 0
        run_up = run_up + 1 if f_prev > K else 0
        if i < warm or om[i] < first_ms or om[i] != cm[i - 1]:
            continue
        f, cx, a = fast[i], ctxc[i], atr[i]
        if not (np.isfinite(f) and np.isfinite(cx) and np.isfinite(a) and a > 0):
            continue
        base = (cw[i] - cw[i - span]) / span          # mean w of bars i-4L .. i-1
        if run_dn >= 1 and f >= -K and cx > 0:
            m = min(run_dn, _DIP_CAP)
            if (cw[i] - cw[i - m]) / m < base:
                side[i] = 1
        elif run_up >= 1 and f <= K and cx < 0:
            m = min(run_up, _DIP_CAP)
            if (cw[i] - cw[i - m]) / m < base:
                side[i] = -1
        if side[i] != 0:
            sl[i] = S * a
            hold[i] = _HOLD_H * _HOUR
    return out
