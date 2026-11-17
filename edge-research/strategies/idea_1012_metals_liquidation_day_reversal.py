"""IDEA-1012: silver and gold forced-liquidation day reversal (card ideas/cards/IDEA-1012-metals-liquidation-day-reversal.md, v2).

h1 bars, New York clock. Daily price P = close of the h1 bar ending 15:00 New York (a day without that bar has no P).
r = P / P_prev - 1 (P_prev = the previous day with a P; no r if more than 4 calendar days apart). D = mean |r| over the previous
20 days with an r (today excluded). If |r| >= k * D: market order at that bar's close AGAINST r, Monday-Thursday only, one a day.
Stop s * D * close; no target; time exit 24 h after the fill (backstop). v2: exit_long / exit_short on every 15:00 New York bar, so
the old trade closes on the tick before a back-to-back signal enters (the engine runs bar-close exits before new intents).
params: k (1.5), s (1.5).
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"k": 1.5, "s": 1.5}
SYMBOLS = ("XAGUSD", "XAUUSD")
ZONE = "America/New_York"
MIN = 60_000
DAY = 86_400_000
CLOCK = 15 * 60          # bar close, New York minutes
LOOKBACK = 20
MAX_GAP_DAYS = 4
HOLD = 24 * 60 * MIN


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    k, s = float(p["k"]), float(p["s"])
    if ctx["symbol"] not in SYMBOLS:
        raise ValueError(f"IDEA-1012 trades {SYMBOLS}, not {ctx['symbol']}")
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    out["exit_long"], out["exit_short"] = np.zeros(n, bool), np.zeros(n, bool)
    if n == 0:
        return out
    loc = local_ms(cms, ZONE)
    day, mnt = loc // DAY, (loc % DAY) // MIN
    clock = mnt == CLOCK
    out["exit_long"][clock] = True           # v2: the day's 15:00 New York close ends yesterday's trade
    out["exit_short"][clock] = True
    rs = []                                  # past |r| values (bars <= i only)
    prev_day, prev_p = None, None
    for i in np.flatnonzero(clock):   # in time order; one such bar per New York day
        d, px = int(day[i]), c[i]
        r = None
        if prev_p is not None and d - prev_day <= MAX_GAP_DAYS:
            r = px / prev_p - 1.0
        if r is not None and len(rs) >= LOOKBACK:
            D = float(np.mean(rs[-LOOKBACK:]))
            wd = (d + 3) % 7                 # 0 = Monday
            if wd <= 3 and oms[i] >= ctx["first_ms"] and D > 0 and abs(r) >= k * D:
                out["side"][i] = -1 if r > 0 else 1
                out["sl_dist"][i] = s * D * px
                out["hold_ms"][i] = HOLD
        if r is not None:
            rs.append(abs(r))
        prev_day, prev_p = d, px
    return out
