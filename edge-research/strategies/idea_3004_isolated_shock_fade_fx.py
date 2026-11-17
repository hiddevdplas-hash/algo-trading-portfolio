"""IDEA-3004: isolated-shock fade in FX majors (card v1, ideas/cards/IDEA-3004-isolated-shock-fade-fx.md).

Rebuilt from the card's description of the idea source (TradingView "Innovation Adaptive Kalman Filter Oscillator" by jdehorty);
no code copied.
- h1 bars. Local-level filter with gain a = 2 / (L + 1): prediction p(i) = e(i-1), error v(i) = close(i) - p(i).
- z(i) = (v(i) - m(i-1)) / s(i-1); m, s^2 = exponentially weighted (gain 2 / 101) mean / variance of the centred errors to bar i-1.
- Outlier if |z| > Z: gain divided by (1 + 0.05 z^2). m and s^2 are then updated with the error clipped to m(i-1) +/- Z s(i-1).
- Trade at bar i's close when bar i is an outlier, no outlier in bars i-24 .. i-1, bar i follows bar i-1 without a time gap,
  and at least 300 bars of warm-up lie before it: sell if z > Z, buy if z < -Z. Stop = target = |v(i)| from the fill; time exit H hours.
params (card defaults): Z = 2.5, H = 6, L = 20. Class A rules, news modes and caps are applied by the engine.
"""
import numpy as np

_B = 2.0 / 101.0
_DAMP = 0.05
_ISO = 24
_WARM = 300
_HOUR = 3_600_000


def intents(bars, params, ctx):
    Z = float(params.get("Z", 2.5))
    H = float(params.get("H", 6))
    L = float(params.get("L", 20))
    c = np.asarray(bars["c"], float)
    om = np.asarray(bars["open_ms"], np.int64)
    cm = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    tp = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    out = {"side": side, "sl_dist": sl, "tp_dist": tp, "hold_ms": hold}
    if n < 2:
        return out

    a = 2.0 / (L + 1.0)
    tick = float(ctx.get("tick", 0.0) or 0.0)
    first_ms = int(ctx["first_ms"])
    e = c[0]
    m = 0.0
    s2 = max((c[1] - c[0]) ** 2, tick * tick, 1e-18)
    last_out = -10 ** 9                       # index of the latest outlier bar
    for i in range(1, n):
        p = e
        v = c[i] - p
        s = np.sqrt(s2)
        z = (v - m) / s if s > 0 else 0.0
        outlier = abs(z) > Z
        g = a / (1.0 + _DAMP * z * z) if outlier else a
        e = p + g * v
        if (outlier and i >= _WARM and i - last_out > _ISO and om[i] == cm[i - 1]
                and om[i] >= first_ms and abs(v) > 0):
            side[i] = -1 if z > 0 else 1
            sl[i] = abs(v)
            tp[i] = abs(v)
            hold[i] = H * _HOUR
        if outlier:
            last_out = i
        # error scale: clipped, centred error (uses bar i only after bar i's decision)
        vc = min(max(v, m - Z * s), m + Z * s)
        d = vc - m
        m = m + _B * d
        s2 = max((1.0 - _B) * (s2 + _B * d * d), tick * tick, 1e-18)
    return out
