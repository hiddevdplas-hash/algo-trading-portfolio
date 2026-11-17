"""IDEA-2009: monthly time-series momentum, FX majors, gold and index CFDs (card v2,
ideas/cards/IDEA-2009-monthly-tsmom-fx-gold-indices.md).

Rule rebuilt from the card (Moskowitz-Ooi-Pedersen 2012; Hurst-Ooi-Pedersen 2017); no code copied.
- h1 bars, UTC clock. Each calendar month: decision bar = first h1 bar on a Mon-Fri UTC day whose close is at or after 11:00 UTC;
  exit flags (long and short) at its close. Entry bar = the next h1 bar, if it is in the same month.
- Signal: r = c[entry bar] / c[entry bar `lookback` months earlier] - 1; r > 0 buy, r < 0 sell, at market.
- Stop: k x sqrt(21) x sigma_daily x price; sigma_daily from an EWMA (delta = 60/61) of squared demeaned daily log returns,
  daily close = last h1 close of each UTC day, only days complete before the entry bar's UTC day.
- Backstop time exit 35 calendar days.
params (card defaults): lookback = 12 (months), k = 2.0.
Class C rules, entry blocks, news modes and caps are applied by the engine, not here.
"""
import numpy as np

_DAY = 86_400_000
_DECIDE_MS = 11 * 3_600_000
_DELTA = 60.0 / 61.0
_MIN_DAYS = 60
_HOLD_MS = 35 * _DAY


def _daily_sigma(close_ms, c):
    """Returns (day ids, sigma_daily after each day): EWMA sd of demeaned daily log returns; NaN before _MIN_DAYS returns."""
    day = (close_ms - 1) // _DAY                     # UTC day the bar ends in (a bar ending 00:00 belongs to the day before)
    last = np.nonzero(np.r_[day[1:] != day[:-1], True])[0]
    dids = day[last]
    dc = c[last]
    sig = np.full(len(dids), np.nan)
    if len(dids) < _MIN_DAYS + 2:
        return dids, sig
    r = np.diff(np.log(dc))
    mean = r[0]
    var = 0.0
    for j in range(1, len(r)):
        mean = (1 - _DELTA) * r[j] + _DELTA * mean
        var = (1 - _DELTA) * (r[j] - mean) ** 2 + _DELTA * var
        if j >= _MIN_DAYS:
            sig[j + 1] = np.sqrt(var)               # sigma known after day index j + 1 closes
    return dids, sig


def intents(bars, params, ctx):
    lookback = int(params.get("lookback", 12))
    k = float(params.get("k", 2.0))
    n = len(bars["c"])
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "hold_ms": hold, "exit_long": exl, "exit_short": exs}
    if n < 3:
        return out
    open_ms = np.asarray(bars["open_ms"], np.int64)
    close_ms = np.asarray(bars["close_ms"], np.int64)
    c = np.asarray(bars["c"], float)
    month = open_ms.astype("datetime64[ms]").astype("datetime64[M]").astype(np.int64)
    tod = close_ms % _DAY
    wkday = ((open_ms // _DAY) + 3) % 7 < 5                                   # v2: Mon-Fri UTC (1970-01-01 = Thursday)
    late = (tod >= _DECIDE_MS) & (open_ms // _DAY == (close_ms - 1) // _DAY) & wkday   # closes >= 11:00 UTC, same UTC weekday
    # first bar of each month that closes at or after 11:00 UTC
    cand = np.nonzero(late)[0]
    if len(cand) == 0:
        return out
    first = cand[np.r_[True, month[cand[1:]] != month[cand[:-1]]]]
    dec = first[first + 1 < n]
    dec = dec[month[dec + 1] == month[dec]]
    exl[first] = True
    exs[first] = True
    ent = dec + 1
    ent_month = month[ent]
    pos = {int(m): int(i) for m, i in zip(ent_month, ent)}
    dids, sig = _daily_sigma(close_ms, c)
    for e, m in zip(ent, ent_month):
        if open_ms[e] < ctx["first_ms"]:
            continue
        ref = pos.get(int(m) - lookback)
        if ref is None:
            continue
        r = c[e] / c[ref] - 1.0
        if r == 0 or not np.isfinite(r):
            continue
        dpos = np.searchsorted(dids, open_ms[e] // _DAY) - 1    # last UTC day complete before the entry bar's day
        if dpos < 0 or not np.isfinite(sig[dpos]) or sig[dpos] <= 0:
            continue
        side[e] = 1 if r > 0 else -1
        sl[e] = k * np.sqrt(21.0) * sig[dpos] * c[e]
        hold[e] = _HOLD_MS
    return out
