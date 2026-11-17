"""IDEA-1016: US closing-auction pressure faded after the cash close (card ideas/cards/IDEA-1016-us-close-auction-pressure-reversal.md,
v1).

m15 bars, New York clock. T = the bar ending 16:00 New York. r = c(T) / c(T - L) - 1; D = mean |r| (same L) over the previous 20
valid days. If |r| >= k * D: market order at T's close AGAINST r, Monday-Thursday only, one a day. Stop 2.0 * D * close; no target;
time exit H minutes after the fill. Valid days: Monday-Friday that are neither US exchange closures nor early closes (no 16:00 auction);
those neither trade nor count in D. A day without the T or T - L bar has no r.
params: L (30 min), k (1.5), H (30 min).
"""
from datetime import date, timedelta

import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"L": 30, "k": 1.5, "H": 30}
SYMBOLS = ("US500", "USTEC")
ZONE = "America/New_York"
MIN = 60_000
DAY = 86_400_000
T = 16 * 60                # bar close 16:00 New York
STOP_D = 2.0
D_DAYS = 20


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    L, k, H = int(p["L"]), float(p["k"]), int(p["H"])
    if ctx["symbol"] not in SYMBOLS:
        raise ValueError(f"IDEA-1016 trades {SYMBOLS}, not {ctx['symbol']}")
    if ctx.get("timeframe") != "m15":
        raise ValueError(f"IDEA-1016 runs on m15 bars, not {ctx.get('timeframe')}")
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
    hol = _holiday_days(day, (_us_closed, _us_early))
    hist = []                                   # past |r| (earlier valid days only)
    for d in sorted(set(day.tolist())):
        wd = (d + 3) % 7                        # 0 = Monday
        if wd >= 5 or d in hol:
            continue
        i0, iL = idx.get((d, T)), idx.get((d, T - L))
        if i0 is None or iL is None:
            continue
        r = c[i0] / c[iL] - 1.0
        if wd <= 3 and len(hist) >= D_DAYS and oms[i0] >= ctx["first_ms"]:
            D = float(np.mean(hist[-D_DAYS:]))
            if D > 0 and abs(r) >= k * D:
                out["side"][i0] = -1 if r > 0 else 1
                out["sl_dist"][i0] = STOP_D * D * c[i0]
                out["hold_ms"][i0] = H * MIN
        hist.append(abs(r))                     # today's r joins D only after today's decision
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
