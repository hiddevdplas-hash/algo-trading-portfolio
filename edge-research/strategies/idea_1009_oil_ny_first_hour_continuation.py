"""IDEA-1009: oil New York first-hour continuation (card ideas/cards/IDEA-1009-oil-ny-first-hour-continuation.md, v1).

m15 bars, New York clock, Monday-Friday. At the close of the bar ending 10:00 New York: M = that close - open of the bar starting
09:00 New York the same day (both bars must exist); S = mean |M| over the previous 20 days that had both bars (today excluded).
If |M| >= k * S: market order in the direction of M; stop = s * S; no target; time exit 4 h after entry (14:00 New York).
params: k (1.0), s (1.0).
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"k": 1.0, "s": 1.0}
SYMBOLS = ("XTIUSD", "XBRUSD")
MIN = 60_000
DAY = 86_400_000
OPEN = 9 * 60            # first-hour bar open, New York minutes
SIGNAL = 10 * 60         # signal bar close, New York minutes
HOLD = 4 * 60 * MIN
LOOKBACK = 20


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    k, s = float(p["k"]), float(p["s"])
    if ctx["symbol"] not in SYMBOLS:
        raise ValueError(f"IDEA-1009 trades {SYMBOLS}, not {ctx['symbol']}")
    o = np.asarray(bars["o"], float)
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    lo = local_ms(oms, "America/New_York")
    lc = local_ms(cms, "America/New_York")
    open_day = lo // DAY
    open_min = (lo % DAY) // MIN
    close_day = lc // DAY
    close_min = (lc % DAY) // MIN
    first_bar = {}                                    # New York day -> index of its 09:00 bar
    for j in np.nonzero(open_min == OPEN)[0]:
        first_bar.setdefault(int(open_day[j]), int(j))
    past = []                                         # |M| of earlier days, oldest first (closed bars only)
    for i in np.nonzero(close_min == SIGNAL)[0]:
        d = int(close_day[i])
        j = first_bar.get(d)
        if j is None or j > i:                        # the 09:00 bar must exist and be at or before bar i
            continue
        m = c[i] - o[j]
        if len(past) >= LOOKBACK:
            S = float(np.mean(past[-LOOKBACK:]))
            if ((d + 3) % 7) < 5 and oms[i] >= ctx["first_ms"] and S > 0 and abs(m) >= k * S and m != 0:
                out["side"][i] = 1 if m > 0 else -1
                out["sl_dist"][i] = s * S
                out["hold_ms"][i] = HOLD
        past.append(abs(m))
    return out
