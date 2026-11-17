"""IDEA-1007: monthly option-expiry week long, the week after short (card ideas/cards/IDEA-1007-monthly-opex-dealer-hedge-flow.md, v1).

m15 bars, New York clock. F = third Friday of the month (no trades for that month if F is a NYSE holiday). Long leg: the week
(Mon-Fri) containing F; short leg: the week after. Entry: market order at the close of the bar ending 10:30 New York on the week's first
NYSE trading day. Exit: 15:45 New York on weekday X of the same week (2 Wed, 3 Thu, 4 Fri), stepped back over NYSE holidays, 12:45 on an
early-close day; no trade if the exit day is not after the entry day. Stop = s * D * entry, D = mean |daily return| over the previous 20
NYSE trading days (daily price = close of the bar ending 16:00 New York, closed bars before the entry bar only). No target.
params: X (3), s (3).
"""
from datetime import date, timedelta

import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"X": 3, "s": 3.0}
SYMBOLS = ("US500", "USTEC")
MIN = 60_000
DAY = 86_400_000
ENTRY = 10 * 60 + 30     # bar close, New York minutes
DAILY = 16 * 60
EXIT_FULL = 15 * 60 + 45
EXIT_EARLY = 12 * 60 + 45
NDAYS = 20


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def _wd(d):
    """Weekday of a day number since 1970-01-01 (0 = Monday)."""
    return (int(d) + 3) % 7


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    X, s = int(p["X"]), float(p["s"])
    if ctx["symbol"] not in SYMBOLS:
        raise ValueError(f"IDEA-1007 trades {SYMBOLS}, not {ctx['symbol']}")
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    loc = local_ms(cms, "America/New_York")
    lday = loc // DAY
    lmin = (loc % DAY) // MIN
    closed = _holiday_days(lday, (_us_closed,))
    early = _holiday_days(lday, (_us_early,))

    def trading(d):
        return _wd(d) < 5 and d not in closed

    # daily close-clock prices on NYSE trading days, in bar order (each a closed bar)
    di = [i for i in np.nonzero(lmin == DAILY)[0] if trading(int(lday[i]))]
    dpos = np.array(di, np.int64)
    dret = np.full(len(di), np.nan)
    for k in range(1, len(di)):
        dret[k] = abs(c[di[k]] / c[di[k - 1]] - 1.0)

    for i in np.nonzero(lmin == ENTRY)[0]:
        d = int(lday[i])
        if not trading(d) or oms[i] < ctx["first_ms"]:
            continue
        mon = d - _wd(d)
        if any(trading(x) for x in range(mon, d)):
            continue                                   # not the week's first trading day
        fri = mon + 4
        if 15 <= _date(fri).day <= 21:
            side, F = 1, fri
        elif 15 <= _date(fri - 7).day <= 21:
            side, F = -1, fri - 7
        else:
            continue
        if F in closed:
            continue
        ex = mon + X
        while ex > d and not trading(ex):
            ex -= 1
        if ex <= d:
            continue
        k = int(np.searchsorted(dpos, i))              # daily prices strictly before bar i
        r = dret[max(1, k - NDAYS):k]
        if len(r) < NDAYS or not np.all(np.isfinite(r)):
            continue
        D = float(r.mean())
        if not D > 0:
            continue
        xmin = EXIT_EARLY if ex in early else EXIT_FULL
        out["side"][i] = side
        out["sl_dist"][i] = s * D * c[i]
        out["hold_ms"][i] = (ex - d) * DAY + (xmin - ENTRY) * MIN
    return out


# ---- NYSE holidays from their published rules (no file or calendar access); dates as day numbers since 1970-01-01 -------------
_EPOCH = date(1970, 1, 1).toordinal()


def _date(d):
    return date.fromordinal(int(d) + _EPOCH)


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


def _us_early(y):
    closed = _us_closed(y)
    out = {_nth(y, 11, 3, 4) + timedelta(days=1)}
    for d in (date(y, 7, 3), date(y, 12, 24)):
        if d.weekday() < 5 and d not in closed:
            out.add(d)
    return out


def _holiday_days(day, fns):
    """Day numbers of every date returned by fns over the years the bars span (one year of margin each side)."""
    if len(day) == 0:
        return set()
    y0 = _date(int(min(day))).year - 1
    y1 = _date(int(max(day))).year + 1
    return {_dn(d) for y in range(y0, y1 + 1) for fn in fns for d in fn(y)}
