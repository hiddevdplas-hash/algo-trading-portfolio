"""IDEA-1004: London-open failed sweep of the Asian range (card ideas/cards/IDEA-1004-london-open-failed-sweep-asian-range.md, v2).

m15 bars, London clock, Monday-Friday. Asian range = high / low of the bars closing 00:15 -> 07:00 London. Sweep window: bars closing
07:15 -> 07:00 + T. At bar i: if the highest high since 07:00 is above the Asian high and c[i] is back inside the range -> short (mirror
for the low -> long). Both edges swept (before or on bar i) -> no trade that day. Target = swept edge -/+ f * range (no trade if the
close is already past it); stop = (extreme - entry) + b * ATR(14) (Wilder, m15); time exit 12:00 London. One trade per symbol per day.
params: T (120 min), f (0.5), b (0.5).
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"T": 120, "f": 0.5, "b": 0.5}
SYMBOLS = ("EURUSD", "GBPUSD")
MIN = 60_000
DAY = 86_400_000
ASIA_FIRST, ASIA_LAST = 15, 7 * 60   # bar close, London minutes (00:15 -> 07:00)
OPEN = 7 * 60
EXIT = 12 * 60


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
    T, f, b = int(p["T"]), float(p["f"]), float(p["b"])
    if ctx["symbol"] not in SYMBOLS:
        raise ValueError(f"IDEA-1004 trades {SYMBOLS}, not {ctx['symbol']}")
    if ctx.get("timeframe") != "m15":
        raise ValueError(f"IDEA-1004 runs on m15 bars, not {ctx.get('timeframe')}")
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
    loc = local_ms(cms, "Europe/London")
    lday = loc // DAY
    lmin = (loc % DAY) // MIN
    last = OPEN + T

    cur, ah, al, hi, lo, done = None, -np.inf, np.inf, -np.inf, np.inf, False
    for i in range(n):
        d, m = int(lday[i]), int(lmin[i])
        if d != cur:
            cur, ah, al, hi, lo, done = d, -np.inf, np.inf, -np.inf, np.inf, ((d + 3) % 7) >= 5
        if done:
            continue
        if ASIA_FIRST <= m <= ASIA_LAST:
            ah, al = max(ah, h[i]), min(al, l[i])
            continue
        if not (OPEN < m <= last) or not np.isfinite(ah):
            continue
        hi, lo = max(hi, h[i]), min(lo, l[i])
        up, dn = hi > ah, lo < al
        if up and dn:
            done = True
            continue
        if oms[i] < ctx["first_ms"] or not np.isfinite(atr[i]):
            continue
        rng = ah - al
        hold = (EXIT - m) * MIN
        if up and al < c[i] < ah:
            target = ah - f * rng
            if c[i] > target:
                out["side"][i] = -1
                out["sl_dist"][i] = (hi - c[i]) + b * atr[i]
                out["tp_dist"][i] = c[i] - target
                out["hold_ms"][i] = hold
                done = True
        elif dn and al < c[i] < ah:
            target = al + f * rng
            if c[i] < target:
                out["side"][i] = 1
                out["sl_dist"][i] = (c[i] - lo) + b * atr[i]
                out["tp_dist"][i] = target - c[i]
                out["hold_ms"][i] = hold
                done = True
    return out
