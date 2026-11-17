"""IDEA-1001: oil settlement-window price-pressure reversal (card ideas/cards/IDEA-1001-oil-settlement-window-reversal.md, v2).

m15 bars. t0 = the bar close at the settle: WTI (XTIUSD) 14:30 New York, Brent (XBRUSD) 19:30 London, each on its own clock.
r = c(t0) / c(t0 - L) - 1; D = mean |c(t0) / c(t0 - 60 min) - 1| over the previous 20 trading days. Trade if |r| >= k * D: market,
against r, Monday-Thursday only, one trade per symbol per day. Stop s * D * price, no target, time exit 2 h after t0.
"No trade on exchange holidays or early-close days" is read conservatively for both symbols: US exchange closures and early closes
(NYMEX; ICE Brent also closes early on them), plus for Brent the ICE Europe closures (Good Friday, 25 / 26 Dec, 1 Jan). Holidays are
neither trading days for D nor entry days. v2 (look-ahead review 2026-11-13): a day without the t0 - 60 min bar adds nothing to D
but can still trade if its t0 and t0 - L bars exist; a day without the t0 - L bar adds to D but does not trade.
params: L (60 min), k (1.0), s (1.5).
"""
from datetime import date, timedelta

import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"L": 60, "k": 1.0, "s": 1.5}
MIN = 60_000
DAY = 86_400_000
SPEC = {"XTIUSD": ("America/New_York", 14 * 60 + 30), "XBRUSD": ("Europe/London", 19 * 60 + 30)}
HOLD = 120
D_DAYS, D_WIN = 20, 60


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def _ice_closed(y):
    e = _easter(y)
    return {e - timedelta(days=2), date(y, 12, 25), date(y, 12, 26), date(y, 1, 1)}


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    L, k, s = int(p["L"]), float(p["k"]), float(p["s"])
    if ctx["symbol"] not in SPEC:
        raise ValueError(f"IDEA-1001 trades {tuple(SPEC)}, not {ctx['symbol']}")
    zone, t0 = SPEC[ctx["symbol"]]
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    loc = local_ms(cms, zone)
    day, mnt = loc // DAY, (loc % DAY) // MIN
    idx = {(int(d), int(m)): i for i, (d, m) in enumerate(zip(day, mnt))}
    fns = (_us_closed, _us_early) + ((_ice_closed,) if ctx["symbol"] == "XBRUSD" else ())
    hol = _holiday_days(day, fns)
    hist = []
    for d in sorted(set(day.tolist())):
        wd = (d + 3) % 7
        if wd >= 5 or d in hol:
            continue
        i0 = idx.get((d, t0))
        if i0 is None:
            continue
        i60, iL = idx.get((d, t0 - D_WIN)), idx.get((d, t0 - L))
        if wd <= 3 and len(hist) >= D_DAYS and iL is not None and oms[i0] >= ctx["first_ms"]:
            D = float(np.mean(hist[-D_DAYS:]))
            r = c[i0] / c[iL] - 1.0
            if D > 0 and abs(r) >= k * D:
                out["side"][i0] = -1 if r > 0 else 1
                out["sl_dist"][i0] = s * D * c[i0]
                out["hold_ms"][i0] = HOLD * MIN
        if i60 is not None:
            hist.append(abs(c[i0] / c[i60] - 1.0))
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
