"""IDEA-1018: home-hours currency weakness (card ideas/cards/IDEA-1018-home-hours-currency-weakness.md, v1).

m15 bars, market orders at bar close, local clocks (DST handled by the zone), Monday-Friday by each leg's own clock:
- EURUSD home leg: sell at the close of the bar ending 08:00 Europe/Berlin;
- USDJPY home leg: buy at the close of the bar ending 09:00 Asia/Tokyo;
- USD leg: at the close of the bar ending 12:30 America/New_York, EURUSD buy, USDJPY sell (not on NYSE closure days).
Time exit H hours after the fill; no target. Stop = s * D_leg * entry, D_leg = mean |close(entry clock + H) / close(entry clock) - 1|
over the previous 20 allowed days on which the leg had both bars (days before the entry day only).
Days 24 Dec - 1 Jan (by the leg's local date) are left out of trading and of D_leg. Japanese / euro-area holidays are not filtered.
params: H (3, hours), s (2.0).
"""
from datetime import date, timedelta

import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"H": 3, "s": 2.0}
SYMBOLS = ("EURUSD", "USDJPY")
MIN = 60_000
DAY = 86_400_000
NDAYS = 20
# symbol -> list of (zone, entry clock in local minutes (bar close), side, use NYSE closures)
LEGS = {
    "EURUSD": [("Europe/Berlin", 8 * 60, -1, False), ("America/New_York", 12 * 60 + 30, 1, True)],
    "USDJPY": [("Asia/Tokyo", 9 * 60, 1, False), ("America/New_York", 12 * 60 + 30, -1, True)],
}
_EPOCH = date(1970, 1, 1).toordinal()


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def _year_end(d):
    dt = date.fromordinal(int(d) + _EPOCH)
    return (dt.month == 12 and dt.day >= 24) or (dt.month == 1 and dt.day == 1)


def _leg(out, c, oms, cms, first_ms, zone, t_in, side, use_nyse, H, s):
    loc = local_ms(cms, zone)
    lday, lmin = loc // DAY, (loc % DAY) // MIN
    t_out = t_in + H * 60
    ent = {int(lday[i]): i for i in np.nonzero(lmin == t_in)[0]}
    ext = {int(lday[i]): i for i in np.nonzero(lmin == t_out)[0]}
    closed = _holiday_days(lday, (_us_closed,)) if use_nyse else set()
    past = []                                   # |leg move| of completed earlier days, in day order
    for d in sorted(ent):
        if (d + 3) % 7 >= 5 or _year_end(d) or d in closed:
            continue
        i = ent[d]
        if oms[i] >= first_ms and len(past) >= NDAYS:
            D = float(np.mean(past[-NDAYS:]))
            if D > 0:
                out["side"][i] = side
                out["sl_dist"][i] = s * D * c[i]
                out["hold_ms"][i] = H * 60 * MIN
        j = ext.get(d)
        if j is not None and j > i:
            past.append(abs(c[j] / c[i] - 1.0))   # joins D only from the next day on


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    H, s = int(p["H"]), float(p["s"])
    sym = ctx["symbol"]
    if sym not in SYMBOLS:
        raise ValueError(f"IDEA-1018 trades {SYMBOLS}, not {sym}")
    if ctx.get("timeframe") != "m15":
        raise ValueError(f"IDEA-1018 runs on m15 bars, not {ctx.get('timeframe')}")
    if H not in (2, 3, 4):
        raise ValueError("IDEA-1018: H must be 2, 3 or 4 hours")
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    for zone, t_in, side, use_nyse in LEGS[sym]:
        _leg(out, c, oms, cms, ctx["first_ms"], zone, t_in, side, use_nyse, H, s)
    return out


# ---- NYSE closures from their published rules (no file or calendar access); dates as day numbers since 1970-01-01 -------------
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
