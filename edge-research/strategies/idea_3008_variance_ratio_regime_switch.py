"""IDEA-3008: variance-ratio regime switch (card v1, ideas/cards/IDEA-3008-variance-ratio-regime-switch.md).

Rebuilt from the textbook Lo & MacKinlay (1988) variance ratio; the idea source is the MIT-licensed package
LautaroParada/variance-test (a diagnostic, no trading rule); no code copied.
- h1 bars. r(i) = ln(c(i) / c(i-1)) when bar i follows bar i-1 without a time gap, else 0.
- Window = the last M returns (bars i-M+1 .. i), q = 4: A = sum r^2, B = sum (r(t) + .. + r(t-3))^2, VR = B / (4A),
  theta = sum_{j=1..3} (2(4-j)/4)^2 * sum r(t)^2 r(t-j)^2 / A^2, z = (VR - 1) / sqrt(theta).
- Break up at bar i: c(i) > HH(i) and c(i-1) <= HH(i-1), HH(i) = max high of bars i-N .. i-1; break down: mirror with LL.
- z > Zc: follow the break (stop 1 x ATR(24), no target). z < -Zc: fade it (stop 1 x ATR(24), target 1 x ATR(24)).
  Time exit 8 h. No time gap before bar i; M + N + 24 bars of warm-up. ATR(24) = simple mean true range of bars i-23 .. i.
params (card defaults): Zc = 1.5, M = 480, N = 24. Class A rules, news modes and caps are applied by the engine.
"""
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

_Q = 4
_ATR_N = 24
_HOUR = 3_600_000
_HOLD_H = 8


def _roll_sum(x, m):
    """sum of x over indices i-m+1 .. i (NaN before index m-1)."""
    cs = np.concatenate(([0.0], np.cumsum(x)))
    out = np.full(len(x), np.nan)
    if len(x) >= m:
        out[m - 1:] = cs[m:] - cs[:-m]
    return out


def _lag(x, j):
    y = np.zeros_like(x)
    if j < len(x):
        y[j:] = x[:-j] if j > 0 else x
    return y


def intents(bars, params, ctx):
    Zc = float(params.get("Zc", 1.5))
    M = int(params.get("M", 480))
    N = int(params.get("N", 24))
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    om = np.asarray(bars["open_ms"], np.int64)
    cm = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    tp = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    out = {"side": side, "sl_dist": sl, "tp_dist": tp, "hold_ms": hold}
    if n < max(M, N, _ATR_N) + 2:
        return out

    cont = np.zeros(n, bool)
    cont[1:] = om[1:] == cm[:-1]
    r = np.zeros(n)
    r[1:] = np.where(cont[1:], np.log(c[1:] / c[:-1]), 0.0)
    r2 = r * r
    s4 = sum(_lag(r, j) for j in range(_Q))
    A = _roll_sum(r2, M)
    B = _roll_sum(s4 * s4, M)
    th = np.zeros(n)
    for j in range(1, _Q):
        wj = (2.0 * (_Q - j) / _Q) ** 2
        th = th + wj * _roll_sum(r2 * _lag(r2, j), M)
    with np.errstate(divide="ignore", invalid="ignore"):
        vr = B / (_Q * A)
        theta = th / (A * A)
        z = np.where((A > 0) & (theta > 0), (vr - 1.0) / np.sqrt(theta), np.nan)

    HH = np.full(n, np.nan)
    LL = np.full(n, np.nan)
    HH[N:] = sliding_window_view(h, N).max(axis=1)[:n - N]     # HH[i] = max h[i-N .. i-1]
    LL[N:] = sliding_window_view(l, N).min(axis=1)[:n - N]

    prev_c = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h, prev_c) - np.minimum(l, prev_c)
    tr[0] = h[0] - l[0]
    atr = _roll_sum(tr, _ATR_N) / _ATR_N

    up = np.zeros(n, bool)
    dn = np.zeros(n, bool)
    with np.errstate(invalid="ignore"):
        up[1:] = (c[1:] > HH[1:]) & (c[:-1] <= HH[:-1])
        dn[1:] = (c[1:] < LL[1:]) & (c[:-1] >= LL[:-1])

    idx = np.arange(n)
    ok = (cont & (idx >= M + N + _ATR_N) & (om >= int(ctx["first_ms"]))
          & np.isfinite(z) & np.isfinite(atr) & (atr > 0))
    trend = ok & (z > Zc)
    fade = ok & (z < -Zc)
    side[trend & up] = 1
    side[trend & dn] = -1
    side[fade & up] = -1
    side[fade & dn] = 1
    sig = side != 0
    sl[sig] = atr[sig]
    hold[sig] = _HOLD_H * _HOUR
    tp[fade & (up | dn)] = atr[fade & (up | dn)]
    return out
