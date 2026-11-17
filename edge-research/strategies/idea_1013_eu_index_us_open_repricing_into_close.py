"""IDEA-1013: European index repricing after the US cash open, into the 17:30 Xetra / Eurex close
(card ideas/cards/IDEA-1013-eu-index-us-open-repricing-into-close.md, v1).

m15 bars. Qualifying day: a weekday (New York date) with a full NYSE session (no closure, no early close) and Eurex / Xetra open,
holidays computed from the exchanges' published rules (no calendar file). M = close of the bar ending 10:00 New York - open of the
bar starting 09:30 New York (both must exist). S = mean |M| over the previous 20 qualifying days with both bars (today excluded).
If |M| >= k * S: market order at the 10:00 bar's close in the direction of M; stop s * S; no target; time exit at 17:30
Frankfurt (Europe/Amsterdam) the same day, i.e. hold = 17:30 Amsterdam - the signal bar's close.
params: k (1.0), s (1.0).
"""
from datetime import date, timedelta

import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"k": 1.0, "s": 1.0}
SYMBOLS = ("DE40", "STOXX50")
NY, EU = "America/New_York", "Europe/Amsterdam"
MIN = 60_000
DAY = 86_400_000
OPEN_NY = 9 * 60 + 30     # bar open, New York minutes
SIG_NY = 10 * 60          # bar close, New York minutes
EXIT_EU = 17 * 60 + 30    # Xetra / Eurex close, Amsterdam minutes
LOOKBACK = 20


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan)}


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    k, s = float(p["k"]), float(p["s"])
    if ctx["symbol"] not in SYMBOLS:
        raise ValueError(f"IDEA-1013 trades {SYMBOLS}, not {ctx['symbol']}")
    o = np.asarray(bars["o"], float)
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    lo = local_ms(oms, NY)
    lc = local_ms(cms, NY)
    oday, omin = lo // DAY, (lo % DAY) // MIN
    cday, cmin = lc // DAY, (lc % DAY) // MIN
    first = {int(d): i for i, d in zip(np.flatnonzero(omin == OPEN_NY), oday[omin == OPEN_NY])}
    hol = _holiday_days(cday, (_us_closed, _us_early, _eurex_closed))
    eu_off = local_ms(cms, EU) - cms          # Amsterdam UTC offset at each bar's close
    past = []                                 # |M| of past qualifying days (bars <= i only)
    for i in np.flatnonzero(cmin == SIG_NY):  # in time order; one per New York day
        d = int(cday[i])
        if (d + 3) % 7 >= 5 or d in hol:
            continue
        j = first.get(d)
        if j is None or j > i:
            continue
        M = c[i] - o[j]
        if len(past) >= LOOKBACK and oms[i] >= ctx["first_ms"]:
            S = float(np.mean(past[-LOOKBACK:]))
            # 17:30 Amsterdam on the same calendar date (the New York date and the Amsterdam date agree at 10:00 New York)
            exit_utc = d * DAY + EXIT_EU * MIN - int(eu_off[i])
            hold = exit_utc - int(cms[i])
            if S > 0 and abs(M) >= k * S and M != 0 and hold > 0:
                out["side"][i] = 1 if M > 0 else -1
                out["sl_dist"][i] = s * S
                out["hold_ms"][i] = hold
        past.append(abs(M))
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
