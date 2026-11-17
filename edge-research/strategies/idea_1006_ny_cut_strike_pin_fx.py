"""IDEA-1006: pull toward round strikes into the 10:00 New York option cut (card ideas/cards/IDEA-1006-ny-cut-strike-pin-fx.md, v1).

m15 bars, New York clock, Monday-Friday. At the close of the bar ending 09:00 New York: L = nearest multiple of G pips to the close,
d = L - close, A = ATR(14) (Wilder, m15). If 0.5 * A <= |d| <= dmax * A: market order toward L; target = |d|; stop = s * A; time exit
75 min after entry. One trade per symbol per day.
params: G (50 pips), dmax (2.0), s (1.5).
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"G": 50, "dmax": 2.0, "s": 1.5}
PIP = {"EURUSD": 1e-4, "USDJPY": 1e-2}
MIN = 60_000
DAY = 86_400_000
ENTRY = 9 * 60          # bar close, New York minutes
HOLD = 75 * MIN
DMIN = 0.5


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def _atr(h, l, c, n=14):
    """Wilder ATR, causal: value at i uses bars <= i; NaN until n true ranges exist."""
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = h[0] - l[0]
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        out[n - 1] = tr[:n].mean()
        for i in range(n, len(c)):
            out[i] = out[i - 1] + (tr[i] - out[i - 1]) / n
    return out


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    G, dmax, s = float(p["G"]), float(p["dmax"]), float(p["s"])
    if ctx["symbol"] not in PIP:
        raise ValueError(f"IDEA-1006 trades {tuple(PIP)}, not {ctx['symbol']}")
    step = G * PIP[ctx["symbol"]]
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    atr = _atr(h, l, c)
    loc = local_ms(cms, "America/New_York")
    lday = loc // DAY
    lmin = (loc % DAY) // MIN
    for i in np.nonzero(lmin == ENTRY)[0]:
        if ((int(lday[i]) + 3) % 7) >= 5 or oms[i] < ctx["first_ms"] or not np.isfinite(atr[i]):
            continue
        a = atr[i]
        level = step * np.round(c[i] / step)
        d = level - c[i]
        if DMIN * a <= abs(d) <= dmax * a:
            out["side"][i] = 1 if d > 0 else -1
            out["sl_dist"][i] = s * a
            out["tp_dist"][i] = abs(d)
            out["hold_ms"][i] = HOLD
    return out
