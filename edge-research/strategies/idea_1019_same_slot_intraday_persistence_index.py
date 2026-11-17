"""IDEA-1019: same-half-hour return persistence in index CFDs
(card ideas/cards/IDEA-1019-same-slot-intraday-persistence-index.md, v1).

m30 bars, local exchange clock (DST handled by the zone). Slots: US500 the half-hours starting 10:00 ... 15:30 New York;
DE40 the half-hours starting 09:30 ... 17:00 Frankfurt. Slot j's return on a day = close(bar ending at slot end) /
close(bar ending at slot start) - 1, only when both bars exist on that local day.
On day d, slot j: take the slot's returns on the previous N allowed days that had one (earlier days only); m = mean, sd = sample SD,
z = m / (sd / sqrt(N)). If |z| >= zmin: market order at the close of the bar ending at the slot's start, side = sign(m);
stop 2 * sd * entry; time exit 30 min; no target.
Allowed days (trading and history): Monday-Friday local; US500 not on NYSE closure or early-close days (day after Thanksgiving,
24 Dec and 3 Jul on weekdays); DE40 not on Xetra closures (1 Jan, Good Friday, Easter Monday, 1 May, 24/25/26/31 Dec).
params: N (20), zmin (1.5).
"""
from datetime import date, timedelta

import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"N": 20, "zmin": 1.5}
MIN = 60_000
DAY = 86_400_000
SLOT = 30
STOP_SD = 2.0
# symbol -> (zone, entry clocks in local minutes = slot starts)
SETUP = {
    "US500": ("America/New_York", list(range(10 * 60, 15 * 60 + 31, SLOT))),
    "DE40": ("Europe/Berlin", list(range(9 * 60 + 30, 17 * 60 + 1, SLOT))),
}
_EPOCH = date(1970, 1, 1).toordinal()


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    N, zmin = int(p["N"]), float(p["zmin"])
    sym = ctx["symbol"]
    if sym not in SETUP:
        raise ValueError(f"IDEA-1019 trades {tuple(SETUP)}, not {sym}")
    if ctx.get("timeframe") != "m30":
        raise ValueError(f"IDEA-1019 runs on m30 bars, not {ctx.get('timeframe')}")
    if N < 2:
        raise ValueError("IDEA-1019: N must be at least 2")
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    zone, starts = SETUP[sym]
    loc = local_ms(cms, zone)
    lday, lmin = loc // DAY, (loc % DAY) // MIN
    idx = {(int(d), int(m)): i for i, (d, m) in enumerate(zip(lday, lmin))}
    blocked = _holiday_days(lday, (_us_closed, _us_early) if sym == "US500" else (_xetra_closed,))
    hist = {t: [] for t in starts}              # per slot: returns of earlier allowed days, in day order
    first_ms = ctx["first_ms"]
    for d in sorted(set(lday.tolist())):
        if (d + 3) % 7 >= 5 or d in blocked:
            continue
        for t in starts:
            i, j = idx.get((d, t)), idx.get((d, t + SLOT))
            if i is None:
                continue
            h = hist[t]
            if len(h) >= N and oms[i] >= first_ms:
                r = np.asarray(h[-N:])
                m, sd = float(r.mean()), float(r.std(ddof=1))
                if sd > 0 and m != 0 and abs(m) / (sd / np.sqrt(N)) >= zmin:
                    out["side"][i] = 1 if m > 0 else -1
                    out["sl_dist"][i] = STOP_SD * sd * c[i]
                    out["hold_ms"][i] = SLOT * MIN
            if j is not None and j > i:
                h.append(c[j] / c[i] - 1.0)     # today's slot return joins the history only after today's decision
    return out


# ---- exchange calendars from their published rules (no file or calendar access); dates as day numbers since 1970-01-01 -------
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
    """NYSE 13:00 closes: day after Thanksgiving, 24 Dec and 3 Jul on weekdays (a closure on the same day is left out anyway)."""
    out = {_nth(y, 11, 3, 4) + timedelta(days=1)}
    for d in (date(y, 12, 24), date(y, 7, 3)):
        if d.weekday() < 5:
            out.add(d)
    return out


def _xetra_closed(y):
    e = _easter(y)
    return {date(y, 1, 1), e - timedelta(days=2), e + timedelta(days=1), date(y, 5, 1),
            date(y, 12, 24), date(y, 12, 25), date(y, 12, 26), date(y, 12, 31)}


def _holiday_days(day, fns):
    """Day numbers of every date returned by fns over the years the bars span (one year of margin each side)."""
    if len(day) == 0:
        return set()
    y0 = date.fromordinal(int(min(day)) + _EPOCH).year - 1
    y1 = date.fromordinal(int(max(day)) + _EPOCH).year + 1
    return {_dn(d) for y in range(y0, y1 + 1) for fn in fns for d in fn(y)}
