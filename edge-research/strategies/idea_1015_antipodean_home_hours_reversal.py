"""IDEA-1015: AUD and NZD home-hours reversal of the London-New York move (card
ideas/cards/IDEA-1015-antipodean-home-hours-reversal.md, v1).

m15 bars, London clock. On London date d (Monday-Thursday): r = c(bar ending 23:30 London) / c(bar ending 08:00 London) - 1.
D = mean |r| over the previous 20 days with an r. If |r| >= k * D: market order at the 23:30 London bar's close AGAINST r.
Stop s * D * close; no target; time exit at X London the next morning (hold = X + 24 h - 23:30). No trade on London dates
24 Dec - 1 Jan (also left out of D). A day without either bar has no r. One trade per symbol per day.
params: k (1.5), s (1.5), X (420 = 07:00 London, minutes after midnight).
"""
from datetime import date

import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"k": 1.5, "s": 1.5, "X": 7 * 60}
SYMBOLS = ("AUDUSD", "NZDUSD")
ZONE = "Europe/London"
MIN = 60_000
DAY = 86_400_000
START = 8 * 60            # bar close 08:00 London
ENTRY = 23 * 60 + 30      # bar close 23:30 London (00:30 Amsterdam)
D_DAYS = 20
_EPOCH = date(1970, 1, 1).toordinal()


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def _year_end(d):
    dt = date.fromordinal(int(d) + _EPOCH)
    return (dt.month == 12 and dt.day >= 24) or (dt.month == 1 and dt.day == 1)


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    k, s, X = float(p["k"]), float(p["s"]), int(p["X"])
    if ctx["symbol"] not in SYMBOLS:
        raise ValueError(f"IDEA-1015 trades {SYMBOLS}, not {ctx['symbol']}")
    if ctx.get("timeframe") != "m15":
        raise ValueError(f"IDEA-1015 runs on m15 bars, not {ctx.get('timeframe')}")
    if not 0 <= X < START:
        raise ValueError("IDEA-1015: the exit clock X must be before 08:00 London")
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    loc = local_ms(cms, ZONE)
    day, mnt = loc // DAY, (loc % DAY) // MIN
    idx = {(int(d), int(m)): i for i, (d, m) in enumerate(zip(day, mnt))}
    hold = (X + 24 * 60 - ENTRY) * MIN
    hist = []                                   # past |r| (earlier days only)
    for d in sorted(set(day.tolist())):
        if (d + 3) % 7 > 3 or _year_end(d):     # London Monday-Thursday only; year-end days left out entirely
            continue
        i0, ie = idx.get((d, START)), idx.get((d, ENTRY))
        if i0 is None or ie is None:
            continue
        r = c[ie] / c[i0] - 1.0
        if len(hist) >= D_DAYS and oms[ie] >= ctx["first_ms"]:
            D = float(np.mean(hist[-D_DAYS:]))
            if D > 0 and abs(r) >= k * D:
                out["side"][ie] = -1 if r > 0 else 1
                out["sl_dist"][ie] = s * D * c[ie]
                out["hold_ms"][ie] = hold
        hist.append(abs(r))                     # today's r joins D only after today's decision
    return out
