"""IDEA-1005: Friday weekend de-risking in oil (card ideas/cards/IDEA-1005-friday-weekend-derisking-oil.md, v2).

m15 bars, New York clock for both symbols. Fridays only, at the bar closing at E (New York):
r_w = c(Friday E) / c(previous Friday E) - 1 (no trade if the previous Friday's E bar is missing; v2: only the missing bar decides);
D_w = mean |r_w| over the previous 26 Fridays with a valid r_w. Trade if |r_w| >= k * D_w: market, against r_w, one trade per symbol
per Friday. Stop s * D_d * price, D_d = mean |c(16:00 NY) / c(E) - 1| over the previous 20 trading days (Mon-Fri). No target; time
exit at 16:00 New York (hold = 16:00 - E). No trade on US exchange closures or early-close days, which are also left out of D_d.
params: E (660 = 11:00 NY, minutes after midnight), k (1.0), s (1.5).
"""
from datetime import date, timedelta

import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"E": 11 * 60, "k": 1.0, "s": 1.5}
SYMBOLS = ("XTIUSD", "XBRUSD")
MIN = 60_000
DAY = 86_400_000
EXIT = 16 * 60
W_FRIDAYS, D_DAYS = 26, 20


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    E, k, s = int(p["E"]), float(p["k"]), float(p["s"])
    if ctx["symbol"] not in SYMBOLS:
        raise ValueError(f"IDEA-1005 trades {SYMBOLS}, not {ctx['symbol']}")
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    loc = local_ms(cms, "America/New_York")
    day, mnt = loc // DAY, (loc % DAY) // MIN
    idx = {(int(d), int(m)): i for i, (d, m) in enumerate(zip(day, mnt))}
    hol = _holiday_days(day, (_us_closed, _us_early))
    rw_hist, dd_hist = [], []
    for d in sorted(set(day.tolist())):
        wd = (d + 3) % 7
        if wd >= 5 or d in hol:
            continue
        ie, ix = idx.get((d, E)), idx.get((d, EXIT))
        if wd == 4 and ie is not None:
            ip = idx.get((d - 7, E))
            if ip is not None:
                rw = c[ie] / c[ip] - 1.0
                # decision from past Fridays and past days only
                if len(rw_hist) >= W_FRIDAYS and len(dd_hist) >= D_DAYS and oms[ie] >= ctx["first_ms"]:
                    Dw = float(np.mean(rw_hist[-W_FRIDAYS:]))
                    Dd = float(np.mean(dd_hist[-D_DAYS:]))
                    if Dw > 0 and Dd > 0 and abs(rw) >= k * Dw:
                        out["side"][ie] = -1 if rw > 0 else 1
                        out["sl_dist"][ie] = s * Dd * c[ie]
                        out["hold_ms"][ie] = (EXIT - E) * MIN
                rw_hist.append(abs(rw))
        if ie is not None and ix is not None:
            dd_hist.append(abs(c[ix] / c[ie] - 1.0))    # today's hold-window move joins D_d only after today's decision
    return out


# ---- exchange holidays from their published rules (no file or calendar access); dates as day numbers since 1970-01-01 ----------
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
    y0 = date.fromordinal(int(min(day)) + _EPOCH).year - 1
    y1 = date.fromordinal(int(max(day)) + _EPOCH).year + 1
    return {_dn(d) for y in range(y0, y1 + 1) for fn in fns for d in fn(y)}
