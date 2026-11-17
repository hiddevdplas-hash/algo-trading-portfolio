"""IDEA-1008: gold session drift, long in Shanghai hours, short in New York hours
(card ideas/cards/IDEA-1008-gold-asia-long-ny-short-session-drift.md, v1).

m15 bars, XAUUSD, Monday-Friday, two legs a day, no signal filter:
- long leg:  market buy at the close of the bar ending 01:00 UTC, time exit 06:45 UTC (hold 5 h 45 min);
- short leg: market sell at the close of the bar ending 09:30 New York, time exit 15:00 New York (hold 5 h 30 min), NYSE trading days.
Stop = s * D_leg * entry, D_leg = mean |close(exit clock) / close(entry clock) - 1| over the previous 20 days on which both of that leg's
clocks had a bar (days before the entry day only, so every bar used is closed). No target.
params: s (2.0).
"""
from datetime import date, timedelta

import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"s": 2.0}
SYMBOLS = ("XAUUSD",)
MIN = 60_000
DAY = 86_400_000
NDAYS = 20
LONG_IN, LONG_OUT = 60, 6 * 60 + 45            # UTC minutes (bar close)
SHORT_IN, SHORT_OUT = 9 * 60 + 30, 15 * 60     # New York minutes (bar close)


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def _leg(out, c, oms, first_ms, lday, lmin, t_in, t_out, side, s, ok_day):
    """One leg: entry at the bar closing t_in (local minutes), time exit at t_out the same local day."""
    ent = {int(lday[i]): i for i in np.nonzero(lmin == t_in)[0]}
    ext = {int(lday[i]): i for i in np.nonzero(lmin == t_out)[0]}
    past = []                                   # |leg move| of completed earlier days, in day order
    for d in sorted(ent):
        i = ent[d]
        if ok_day(d) and oms[i] >= first_ms and len(past) >= NDAYS:
            D = float(np.mean(past[-NDAYS:]))
            if D > 0:
                out["side"][i] = side
                out["sl_dist"][i] = s * D * c[i]
                out["hold_ms"][i] = (t_out - t_in) * MIN
        j = ext.get(d)
        if j is not None and j > i and ok_day(d):
            past.append(abs(c[j] / c[i] - 1.0))   # used only from the next day on


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    s = float(p["s"])
    if ctx["symbol"] not in SYMBOLS:
        raise ValueError(f"IDEA-1008 trades {SYMBOLS}, not {ctx['symbol']}")
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    uday, umin = cms // DAY, (cms % DAY) // MIN
    loc = local_ms(cms, "America/New_York")
    nday, nmin = loc // DAY, (loc % DAY) // MIN
    closed = _holiday_days(nday, (_us_closed,))

    def weekday(d):
        return (d + 3) % 7 < 5

    _leg(out, c, oms, ctx["first_ms"], uday, umin, LONG_IN, LONG_OUT, 1, s, weekday)
    _leg(out, c, oms, ctx["first_ms"], nday, nmin, SHORT_IN, SHORT_OUT, -1, s,
         lambda d: weekday(d) and d not in closed)
    return out


# ---- NYSE holidays from their published rules (no file or calendar access); dates as day numbers since 1970-01-01 -------------
_EPOCH = date(1970, 1, 1).toordinal()


def _dn(dt):
    return dt.toordinal() - _EPOCH


def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mo = (h + l - 7 * m + 114) // 31
    return date(y, mo, (h + l - 7 * m + 114) % 31 + 1)


def _nth(y, mo, wd, nth):
    """nth weekday (0 = Monday) of a month; nth = -1 for the last."""
    if nth > 0:
        d = date(y, mo, 1)
        return d + timedelta(days=(wd - d.weekday()) % 7 + 7 * (nth - 1))
    d = date(y + (mo == 12), mo % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - wd) % 7)


def _obs(d):
    """US rule: Saturday -> Friday, Sunday -> Monday."""
    return d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1) if d.weekday() == 6 else d


def _us_closed(y):
    out = {_nth(y, 1, 0, 3), _nth(y, 2, 0, 3), _easter(y) - timedelta(days=2), _nth(y, 5, 0, -1), _obs(date(y, 7, 4)),
           _nth(y, 9, 0, 1), _nth(y, 11, 3, 4), _obs(date(y, 12, 25))}
    if date(y, 1, 1).weekday() != 5:          # NYSE does not move a Saturday New Year to Friday
        out.add(_obs(date(y, 1, 1)))
    if y >= 2022:
        out.add(_obs(date(y, 6, 19)))
    if y == 2018:
        out.add(date(2018, 12, 5))            # national day of mourning (President Bush)
    return out


def _holiday_days(day, fns):
    """Day numbers of every date returned by fns over the years the bars span (one year of margin each side)."""
    if len(day) == 0:
        return set()
    y0 = date.fromordinal(int(min(day)) + _EPOCH).year - 1
    y1 = date.fromordinal(int(max(day)) + _EPOCH).year + 1
    return {_dn(d) for y in range(y0, y1 + 1) for fn in fns for d in fn(y)}
