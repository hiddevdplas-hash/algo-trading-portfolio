"""IDEA-1011: month-end balanced-fund rebalancing against the month's equity move
(card ideas/cards/IDEA-1011-month-end-balanced-fund-rebalance-index.md, v1).

h1 bars, New York clock. Daily close = close of the h1 bar ending 16:00 New York. T = last weekday (Mon-Fri) of the calendar month.
On the D weekdays before T, at the close of the bar ending 15:00 New York: C0 = last daily close of the previous month,
r = ln(close / C0), sigma = std of the last 60 daily log returns (today excluded), m = daily closes this month before today + 1,
z = r / (sigma * sqrt(m)). Short if z >= k, long if z <= -k. Market order; stop = 2.0 * sigma * price; no target.
Exit at the close of the bar ending 16:00 New York on T (exit flags), with a backstop time exit to that clock time.
params: k (1.0), D (3).
"""
import datetime as _dt

import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"k": 1.0, "D": 3}
SYMBOLS = ("US500", "DE40", "UK100")
MIN = 60_000
DAY = 86_400_000
ENTRY = 15 * 60          # bar close, New York minutes
CLOSE = 16 * 60          # daily close bar, New York minutes
SIG_N = 60
STOP_SIG = 2.0
EPOCH = _dt.date(1970, 1, 1)


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan), "exit_long": np.zeros(n, bool), "exit_short": np.zeros(n, bool)}


def _date(dn):
    return EPOCH + _dt.timedelta(days=int(dn))


def _last_weekday(dn):
    """Day number of the last Mon-Fri of dn's calendar month (pure calendar, no data)."""
    d = _date(dn)
    nxt = _dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    last = nxt - _dt.timedelta(days=1)
    while last.weekday() >= 5:
        last -= _dt.timedelta(days=1)
    return (last - EPOCH).days


def _weekdays_between(a, b):
    """Number of Mon-Fri days in (a, b], day numbers a < b."""
    return sum(1 for x in range(a + 1, b + 1) if ((x + 3) % 7) < 5)


def _month(dn):
    d = _date(dn)
    return d.year * 12 + d.month


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    k, D = float(p["k"]), int(p["D"])
    if ctx["symbol"] not in SYMBOLS:
        raise ValueError(f"IDEA-1011 trades {SYMBOLS}, not {ctx['symbol']}")
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    lc = local_ms(cms, "America/New_York")
    cday = lc // DAY
    cmin = (lc % DAY) // MIN
    closes_day, closes = [], []                       # daily closes seen so far (bars <= i only), oldest first
    t_cache = {}
    for i in range(n):
        d = int(cday[i])
        if cmin[i] == CLOSE:
            if d not in t_cache:
                t_cache[d] = _last_weekday(d)
            if d == t_cache[d]:
                out["exit_long"][i] = True
                out["exit_short"][i] = True
            closes_day.append(d)
            closes.append(c[i])
            continue
        if cmin[i] != ENTRY or ((d + 3) % 7) >= 5 or oms[i] < ctx["first_ms"]:
            continue
        if d not in t_cache:
            t_cache[d] = _last_weekday(d)
        T = t_cache[d]
        if d >= T or not (1 <= _weekdays_between(d, T) <= D):
            continue
        if len(closes) < SIG_N + 1:
            continue
        mon = _month(d)
        j0 = next((j for j in range(len(closes_day) - 1, -1, -1) if _month(closes_day[j]) < mon), None)
        if j0 is None:
            continue
        c0 = closes[j0]
        m = sum(1 for x in closes_day[j0 + 1:] if _month(x) == mon) + 1
        rets = np.diff(np.log(np.asarray(closes[-(SIG_N + 1):], float)))
        sig = float(np.std(rets, ddof=1))
        if not (sig > 0) or c0 <= 0:
            continue
        z = np.log(c[i] / c0) / (sig * np.sqrt(m))
        if z >= k:
            out["side"][i] = -1
        elif z <= -k:
            out["side"][i] = 1
        else:
            continue
        out["sl_dist"][i] = STOP_SIG * sig * c[i]
        out["hold_ms"][i] = (T * DAY + CLOSE * MIN) - int(lc[i])   # backstop: T 16:00 New York (local clock distance)
    return out
