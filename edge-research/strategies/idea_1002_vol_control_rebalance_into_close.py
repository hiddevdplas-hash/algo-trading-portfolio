"""IDEA-1002: volatility-control rebalancing flow into the cash close (card ideas/cards/IDEA-1002-vol-control-rebalance-into-close.md, v1).

m15 bars. Close clock: US500 16:00 New York, STOXX50 17:30 Amsterdam. One price a day = the close of the bar ending at the close clock.
x = daily return of that price (consecutive trading days); RV5, RV20 = root mean square of the last 5 / 20 x; q = RV5 / RV20.
A day with q >= h triggers the de-lever state, q <= 1 / h the re-lever state; on day t the state is the one triggered most recently
within the previous N trading days (computed at their closes, so known before day t). Entry: market at the close of the bar ending
`lead` minutes before the close clock: short in de-lever, long in re-lever; time exit at the close clock (hold = lead). Stop
2 * D * price, D = mean |c(close) / c(close - 60 min) - 1| over the previous 20 trading days. US500 Monday-Thursday, STOXX50
Monday-Friday; no trade on exchange holidays or half days (US: NYSE closures and early closes; STOXX50: Eurex closures), which are
also left out of the daily series.
params: h (1.5), N (3), lead (60 min).
"""
from datetime import date, timedelta

import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"h": 1.5, "N": 3, "lead": 60}
MIN = 60_000
DAY = 86_400_000
# symbol: (zone, close clock, last entry weekday)
SPEC = {"US500": ("America/New_York", 16 * 60, 3), "STOXX50": ("Europe/Amsterdam", 17 * 60 + 30, 4)}
STOP_D, D_DAYS, D_WIN = 2.0, 20, 60


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    h, N, lead = float(p["h"]), int(p["N"]), int(p["lead"])
    if ctx["symbol"] not in SPEC:
        raise ValueError(f"IDEA-1002 trades {tuple(SPEC)}, not {ctx['symbol']}")
    zone, tc, last_wd = SPEC[ctx["symbol"]]
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
    fns = (_us_closed, _us_early) if ctx["symbol"] == "US500" else (_eurex_closed,)
    hol = _holiday_days(day, fns)
    prices, xs, states, dh = [], [], [], []     # per past trading day: close price, return, state trigger (+1 / -1 / 0), |last hour|
    for d in sorted(set(day.tolist())):
        wd = (d + 3) % 7
        if wd >= 5 or d in hol:
            continue
        ic, ie = idx.get((d, tc)), idx.get((d, tc - lead))
        # decision for today from past days only
        if ie is not None and wd <= last_wd and len(dh) >= D_DAYS and oms[ie] >= ctx["first_ms"]:
            side = 0
            for st in reversed(states[-N:]):
                if st != 0:
                    side = st
                    break
            D = float(np.mean(dh[-D_DAYS:]))
            if side != 0 and D > 0:
                out["side"][ie] = side
                out["sl_dist"][ie] = STOP_D * D * c[ie]
                out["hold_ms"][ie] = lead * MIN
        # today's close joins the series after the decision
        if ic is None:
            continue
        if prices:
            xs.append(c[ic] / prices[-1] - 1.0)
        prices.append(c[ic])
        st = 0
        if len(xs) >= 20:
            rv5 = np.sqrt(np.mean(np.square(xs[-5:])))
            rv20 = np.sqrt(np.mean(np.square(xs[-20:])))
            if rv20 > 0:
                q = rv5 / rv20
                st = -1 if q >= h else 1 if q <= 1.0 / h else 0
        states.append(st)
        i60 = idx.get((d, tc - D_WIN))
        if i60 is not None:
            dh.append(abs(c[ic] / c[i60] - 1.0))
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


def _eurex_closed(y):
    """Eurex / Xetra trading holidays for Euro Stoxx 50 products."""
    e = _easter(y)
    return {date(y, 1, 1), e - timedelta(days=2), e + timedelta(days=1), date(y, 5, 1), date(y, 12, 24), date(y, 12, 25),
            date(y, 12, 26), date(y, 12, 31)}


def _holiday_days(day, fns):
    """Day numbers of every date returned by fns over the years the bars span (one year of margin each side)."""
    if len(day) == 0:
        return set()
    y0 = date.fromordinal(int(min(day)) + _EPOCH).year - 1
    y1 = date.fromordinal(int(max(day)) + _EPOCH).year + 1
    return {_dn(d) for y in range(y0, y1 + 1) for fn in fns for d in fn(y)}
