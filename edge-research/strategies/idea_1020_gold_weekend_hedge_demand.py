"""IDEA-1020: gold weekend-hedge demand (card ideas/cards/IDEA-1020-gold-weekend-hedge-demand.md, v1).

m15 bars, XAUUSD, New York clock (DST handled by the zone), market orders at bar close:
- Friday leg: buy at the close of the bar ending F; exit at the close of the bar ending 16:30 the same Friday (exit_long flag, and
  hold_ms to 16:30 as a backstop).
- Monday leg: sell at the close of the bar ending 03:00; time exit at M the same Monday.
Stop = 2.0 * D_leg * entry, D_leg = mean |close(exit clock) / close(entry clock) - 1| over the previous 20 allowed occurrences of the
leg with both bars (earlier weeks only). No target.
Left out (trading and D_leg): Fridays that are NYSE closures or early closes (day after Thanksgiving, 24 Dec / 3 Jul) and Fridays
24 Dec - 1 Jan; Mondays that are NYSE closures, Easter Monday, and Mondays 24 Dec - 1 Jan.
params: F (720 = 12:00, minutes after midnight New York), M (420 = 07:00).
"""
from datetime import date, timedelta

import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"F": 12 * 60, "M": 7 * 60}
SYMBOLS = ("XAUUSD",)
ZONE = "America/New_York"
MIN = 60_000
DAY = 86_400_000
NWEEKS = 20
STOP = 2.0
FRI_OUT = 16 * 60 + 30
MON_IN = 3 * 60
_EPOCH = date(1970, 1, 1).toordinal()


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan), "exit_long": np.zeros(n, bool), "exit_short": np.zeros(n, bool)}


def _year_end(d):
    dt = date.fromordinal(int(d) + _EPOCH)
    return (dt.month == 12 and dt.day >= 24) or (dt.month == 1 and dt.day == 1)


def _leg(out, c, oms, first_ms, lday, lmin, weekday, t_in, t_out, side, blocked, exit_flag):
    ent = {int(lday[i]): i for i in np.nonzero(lmin == t_in)[0]}
    ext = {int(lday[i]): i for i in np.nonzero(lmin == t_out)[0]}
    past = []                                   # |leg move| of earlier allowed occurrences, in day order
    for d in sorted(ent):
        if (d + 3) % 7 != weekday or _year_end(d) or d in blocked:
            continue
        i = ent[d]
        j = ext.get(d)
        if oms[i] >= first_ms and len(past) >= NWEEKS:
            D = float(np.mean(past[-NWEEKS:]))
            if D > 0:
                out["side"][i] = side
                out["sl_dist"][i] = STOP * D * c[i]
                out["hold_ms"][i] = (t_out - t_in) * MIN
                if exit_flag and j is not None and j > i:
                    out["exit_long" if side > 0 else "exit_short"][j] = True
        if j is not None and j > i:
            past.append(abs(c[j] / c[i] - 1.0))   # joins D only from the next occurrence on


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    F, M = int(p["F"]), int(p["M"])
    if ctx["symbol"] not in SYMBOLS:
        raise ValueError(f"IDEA-1020 trades {SYMBOLS}, not {ctx['symbol']}")
    if ctx.get("timeframe") != "m15":
        raise ValueError(f"IDEA-1020 runs on m15 bars, not {ctx.get('timeframe')}")
    if not (F % 15 == 0 and 0 < F < FRI_OUT and M % 15 == 0 and MON_IN < M):
        raise ValueError("IDEA-1020: F must be a quarter-hour before 16:30, M a quarter-hour after 03:00 (New York)")
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    loc = local_ms(cms, ZONE)
    lday, lmin = loc // DAY, (loc % DAY) // MIN
    closed = _holiday_days(lday, (_us_closed,))
    early = _holiday_days(lday, (_us_early,))
    easter_mon = _holiday_days(lday, (lambda y: {_easter(y) + timedelta(days=1)},))
    _leg(out, c, oms, ctx["first_ms"], lday, lmin, 4, F, FRI_OUT, 1, closed | early, True)       # Friday long
    _leg(out, c, oms, ctx["first_ms"], lday, lmin, 0, MON_IN, M, -1, closed | easter_mon, False)  # Monday short
    return out


# ---- NYSE calendar from its published rules (no file or calendar access); dates as day numbers since 1970-01-01 ---------------
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
    """NYSE 13:00 closes: day after Thanksgiving, 24 Dec and 3 Jul on weekdays."""
    out = {_nth(y, 11, 3, 4) + timedelta(days=1)}
    for d in (date(y, 12, 24), date(y, 7, 3)):
        if d.weekday() < 5:
            out.add(d)
    return out


def _holiday_days(day, fns):
    """Day numbers of every date returned by fns over the years the bars span (one year of margin each side)."""
    if len(day) == 0:
        return set()
    y0 = date.fromordinal(int(min(day)) + _EPOCH).year - 1
    y1 = date.fromordinal(int(max(day)) + _EPOCH).year + 1
    return {_dn(d) for y in range(y0, y1 + 1) for fn in fns for d in fn(y)}
