"""IDEA-2012: Dash-for-cash pre-month-end reversal in indices (card v1,
ideas/cards/IDEA-2012-dash-for-cash-pre-month-end-reversal.md).

Rule rebuilt from the card (Etula, Rinne, Suominen & Vaittinen, "Dash for Cash", RFS 2020); no code copied.
- h1 bars. Daily close = last full h1 cash bar: US500 ending 16:00 New York, UK100 16:00 London, DE40 17:00 Frankfurt.
- Business days: Mon-Fri minus the exchange's fixed-rule holidays (NYSE / LSE / Xetra, computed from the date).
- T = last business day of the month; s = settlement days (US500: 3 before 2017-09-05, 2 from then, 1 from 2024-05-28;
  UK100 / DE40: 2), taken at T's date. Entry day E = T - (s + 1) business days.
- At E's daily close: R_sp = ln(close(E) / close(E - 5 business days)); sigma = SD of the last 60 daily log returns.
  Long if R_sp < thr * sigma * sqrt(5) (thr = 99: always). Stop k x ATR(20) (simple mean of daily true ranges). No target.
- Exit at the first bar whose close is at or after T-1's daily-close time; backstop time exit 7 days.
params (card defaults): thr = 99, k = 1.5.
Class C rules, entry blocks, news modes and caps are applied by the engine, not here.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

_CFG = {  # symbol: (exchange, tz, daily-close minute of day, local)
    "US500": ("NYSE", "America/New_York", 16 * 60),
    "UK100": ("LSE", "Europe/London", 16 * 60),
    "DE40": ("XETRA", "Europe/Berlin", 17 * 60),
}
_US_T2 = date(2017, 9, 5)
_US_T1 = date(2024, 5, 28)
_WIN, _SIG_N, _ATR_N = 5, 60, 20
_HOLD_MS = 7 * 86_400_000
_HOUR = 3_600_000
_DAY = 86_400_000
_EPOCH = date(1970, 1, 1)


def _local_ms(ms, tzname):
    """Local wall-clock ms for UTC ms (offset looked up once per UTC hour)."""
    tz = ZoneInfo(tzname)
    hours = ms // _HOUR
    uh, inv = np.unique(hours, return_inverse=True)
    off = np.array([int(datetime.fromtimestamp(int(h) * 3600, timezone.utc).astimezone(tz).utcoffset().total_seconds() * 1000)
                    for h in uh], dtype=np.int64)
    return ms + off[inv]


def _easter(y):
    """Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return date(y, month, day)


def _nth_weekday(y, m, wd, nth):
    """nth (1-based) weekday wd (Mon=0) of month m; nth = -1 for the last."""
    if nth > 0:
        d = date(y, m, 1)
        d += timedelta(days=(wd - d.weekday()) % 7)
        return d + timedelta(weeks=nth - 1)
    d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - wd) % 7)


def _nyse_obs(d):
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _holidays(exch, y):
    hs = set()
    e = _easter(y)
    if exch == "NYSE":
        nyd = date(y, 1, 1)
        if nyd.weekday() == 6:
            hs.add(nyd + timedelta(days=1))
        elif nyd.weekday() < 5:
            hs.add(nyd)
        hs.update({_nth_weekday(y, 1, 0, 3), _nth_weekday(y, 2, 0, 3), e - timedelta(days=2), _nth_weekday(y, 5, 0, -1),
                   _nyse_obs(date(y, 7, 4)), _nth_weekday(y, 9, 0, 1), _nth_weekday(y, 11, 3, 4), _nyse_obs(date(y, 12, 25))})
        if y >= 2022:
            hs.add(_nyse_obs(date(y, 6, 19)))
    elif exch == "LSE":
        nyd = date(y, 1, 1)
        hs.add(nyd + timedelta(days=(7 - nyd.weekday()) % 7) if nyd.weekday() >= 5 else nyd)
        hs.update({e - timedelta(days=2), e + timedelta(days=1), _nth_weekday(y, 5, 0, 1), _nth_weekday(y, 5, 0, -1),
                   _nth_weekday(y, 8, 0, -1)})
        xmas = date(y, 12, 25)
        wd = xmas.weekday()
        if wd == 5:
            hs.update({date(y, 12, 27), date(y, 12, 28)})
        elif wd == 6:
            hs.update({date(y, 12, 26), date(y, 12, 27)})
        elif wd == 4:
            hs.update({xmas, date(y, 12, 28)})
        else:
            hs.update({xmas, date(y, 12, 26)})
    else:  # XETRA
        hs.update({date(y, 1, 1), e - timedelta(days=2), e + timedelta(days=1), date(y, 5, 1),
                   date(y, 12, 24), date(y, 12, 25), date(y, 12, 26), date(y, 12, 31)})
    return hs


def _business_days(exch, d0, d1):
    hol = set()
    for y in range(d0.year, d1.year + 1):
        hol |= _holidays(exch, y)
    out = []
    d = d0
    while d <= d1:
        if d.weekday() < 5 and d not in hol:
            out.append(d)
        d += timedelta(days=1)
    return out


def _settle(sym, t):
    if sym != "US500":
        return 2
    if t >= _US_T1:
        return 1
    if t >= _US_T2:
        return 2
    return 3


def intents(bars, params, ctx):
    thr = float(params.get("thr", 99.0))
    k = float(params.get("k", 1.5))
    n = len(bars["c"])
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "hold_ms": hold, "exit_long": exl, "exit_short": exs}
    sym = ctx["symbol"]
    if n == 0 or sym not in _CFG:
        return out
    exch, tzname, close_min = _CFG[sym]
    tz = ZoneInfo(tzname)
    close_ms = np.asarray(bars["close_ms"], np.int64)
    open_ms = np.asarray(bars["open_ms"], np.int64)
    loc = _local_ms(close_ms, tzname)
    mod = (loc // 60_000) % 1440
    dnum = loc // _DAY
    d_first = _EPOCH + timedelta(days=int(dnum[0]))
    d_last = _EPOCH + timedelta(days=int(dnum[-1]))
    # calendar runs one month past the data so that T of the data's last month is known from rules, not from future bars
    bdays = _business_days(exch, d_first - timedelta(days=10), d_last + timedelta(days=40))
    bpos = {d: i for i, d in enumerate(bdays)}
    # daily-close bars: bar ending at close_min on a business day
    cand = np.nonzero(mod == close_min)[0]
    dc_idx, dc_pos = [], []
    for i in cand:
        d = _EPOCH + timedelta(days=int(dnum[i]))
        p = bpos.get(d)
        if p is not None:
            dc_idx.append(i)
            dc_pos.append(p)
    m = len(dc_idx)
    if m < 3:
        return out
    dc = np.asarray(dc_idx, np.int64)
    dpos = np.asarray(dc_pos, np.int64)
    c = np.asarray(bars["c"], float)
    starts = np.r_[0, dc[:-1] + 1]
    C = c[dc]
    H = np.maximum.reduceat(np.asarray(bars["h"], float)[: dc[-1] + 1], starts)
    L = np.minimum.reduceat(np.asarray(bars["l"], float)[: dc[-1] + 1], starts)
    pc = np.r_[np.nan, C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    atr = np.full(m, np.nan)
    if m > _ATR_N:
        cs = np.r_[0.0, np.cumsum(np.nan_to_num(tr))]
        atr[_ATR_N:] = (cs[_ATR_N + 1:] - cs[1:m - _ATR_N + 1]) / _ATR_N
    r = np.r_[np.nan, np.log(C[1:] / C[:-1])]
    pos_to_j = {int(p): j for j, p in enumerate(dpos)}
    # months: T = last business day; entry E = T - (s + 1); exit at T - 1's daily-close time
    by_month = {}
    for i, d in enumerate(bdays):
        by_month[(d.year, d.month)] = i                    # last business day's position in each month
    for (y, mo), tpos in by_month.items():
        t_day = bdays[tpos]
        s = _settle(sym, t_day)
        epos, xpos = tpos - (s + 1), tpos - 1
        if epos - _WIN < 0:
            continue
        xd = bdays[xpos]
        x_utc = int(datetime(xd.year, xd.month, xd.day, close_min // 60, close_min % 60, tzinfo=tz).timestamp() * 1000)
        xi = int(np.searchsorted(close_ms, x_utc, side="left"))
        if xi < n:
            exl[xi] = True
        je = pos_to_j.get(epos)
        jb = pos_to_j.get(epos - _WIN)
        if je is None or jb is None or je < _SIG_N:
            continue
        i_e = dc[je]
        if open_ms[i_e] < ctx["first_ms"] or close_ms[i_e] >= x_utc:
            continue
        rr = r[je - _SIG_N + 1: je + 1]
        if not np.all(np.isfinite(rr)) or not np.isfinite(atr[je]) or atr[je] <= 0:
            continue
        sig = float(np.std(rr, ddof=1))
        r_sp = float(np.log(C[je] / C[jb]))
        if thr < 50 and not (r_sp < thr * sig * np.sqrt(_WIN)):
            continue
        side[i_e] = 1
        sl[i_e] = k * atr[je]
        hold[i_e] = _HOLD_MS
    return out
