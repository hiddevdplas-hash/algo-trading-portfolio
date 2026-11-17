"""IDEA-2005: turn-of-the-month long on US500 and DE40 CFDs (card v2, ideas/cards/IDEA-2005-turn-of-month-index.md).

Rules rebuilt from the card (Xu & McConnell 2008; Carchano & Tornero; Dzhabarov & Ziemba); no code copied.
- h1 bars, each index on its own exchange clock: US500 New York (cash 09:30-16:00), DE40 Frankfurt (Xetra 09:00-17:30).
- Trading days = weekdays that are not exchange holidays. The holidays are computed from the exchanges' fixed rules (below), not read
  from data or from future bars, so day -1 / day +n are known in advance (no look-ahead from a missing bar).
  NYSE: New Year (Sun -> Mon), MLK, Presidents, Good Friday, Memorial, Juneteenth (from 2022, Sat -> Fri, Sun -> Mon), Independence
  Day (Sat -> Fri, Sun -> Mon), Labor, Thanksgiving, Christmas (Sat -> Fri, Sun -> Mon). One-off closures (e.g. 2018-12-05) are not known.
  Xetra: 1 Jan, Good Friday, Easter Monday, 1 May, 24, 25, 26 and 31 Dec.
- Day -1 = last trading day of the month, day +1 = first trading day of the next month; there is no day 0.
- Entry: market buy at the close of the last h1 bar of the cash session (the h1 bar that closes at or before the cash close:
  US500 the bar ending 16:00 NY; DE40 the bar ending 17:00 Frankfurt, since h1 bars end on the full hour) on trading day start - 1.
  NYSE early closes (v2): 13:00 NY on the day after Thanksgiving, and on 3 July and 24 December when they are weekdays and not
  holidays; on those days the last cash-session bar is the one ending 13:00 NY.
- v2: no US500 entry on a day followed by a market closure (a Friday, or a day whose next weekday is an NYSE holiday): the 16:00 NY
  entry would sit inside the engine's 2-h pre-close block. DE40 (17:00 Frankfurt, about 5 h before its close) is not affected.
- Exit (v2): exit flag on the first bar of trading day `end` whose close is at or after that day's session close (the bar ending
  16:00 NY / 13:00 NY on early closes / 17:00 Frankfurt), or, if that day has no such bar (an unscheduled closure), on the first bar
  of a later local date. Long only. No target.
- Stop: k x ATR(20) of daily bars: local calendar dates of the CFD h1 bars (overnight hours and Sunday-evening stub days kept),
  true range against the previous such day's close, simple mean of the 20 days fully before the entry day.
params (card defaults): start = -1, end = 3, k = 2.5.
Class rules, entry blocks, news modes and caps are applied by the engine, not here.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

_SESSIONS = {  # symbol -> (time zone, minute of day at which the last h1 cash-session bar closes, holiday set)
    "US500": ("America/New_York", 16 * 60, "nyse"),
    "DE40": ("Europe/Berlin", 17 * 60, "xetra"),
}
_ATR_N = 20
_DAY = 86_400_000


def _local_ms(ms, tzname):
    """Local wall-clock ms for UTC ms (offset looked up once per UTC hour)."""
    tz = ZoneInfo(tzname)
    hours = ms // 3_600_000
    uh, inv = np.unique(hours, return_inverse=True)
    off = np.array([int(datetime.fromtimestamp(int(h) * 3600, timezone.utc).astimezone(tz).utcoffset().total_seconds() * 1000)
                    for h in uh], dtype=np.int64)
    return ms + off[inv]


def _easter(y):
    """Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a = y % 19
    b, c = divmod(y, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(y, month, day)


def _nth_weekday(y, m, wd, n):
    d = date(y, m, 1)
    d += timedelta(days=(wd - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(y, m, wd):
    d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - wd) % 7)


def _observed(d, sat_to_fri=True):
    if d.weekday() == 5:
        return d - timedelta(days=1) if sat_to_fri else None
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _holidays(y, cal):
    if cal == "xetra":
        ea = _easter(y)
        return {date(y, 1, 1), ea - timedelta(days=2), ea + timedelta(days=1), date(y, 5, 1),
                date(y, 12, 24), date(y, 12, 25), date(y, 12, 26), date(y, 12, 31)}
    ea = _easter(y)
    out = {
        _nth_weekday(y, 1, 0, 3),               # Martin Luther King Jr. Day
        _nth_weekday(y, 2, 0, 3),               # Presidents' Day
        ea - timedelta(days=2),                 # Good Friday
        _last_weekday(y, 5, 0),                 # Memorial Day
        _nth_weekday(y, 9, 0, 1),               # Labor Day
        _nth_weekday(y, 11, 3, 4),              # Thanksgiving
        _observed(date(y, 7, 4)),
        _observed(date(y, 12, 25)),
    }
    ny = _observed(date(y, 1, 1), sat_to_fri=False)   # NYSE does not close the Friday before a Saturday New Year
    if ny is not None:
        out.add(ny)
    if y >= 2022:
        out.add(_observed(date(y, 6, 19)))
    return out


def _early_closes(y):
    """NYSE scheduled 13:00 closes: day after Thanksgiving; 3 Jul and 24 Dec when weekdays and not holidays."""
    hol = _holidays(y, "nyse")
    out = {_nth_weekday(y, 11, 3, 4) + timedelta(days=1)}
    for d in (date(y, 7, 3), date(y, 12, 24)):
        if d.weekday() < 5 and d not in hol:
            out.add(d)
    return out


def _trading_days(first, last, cal):
    """Sorted list of trading-day ordinals from first to last (dates), from the rules only."""
    hol = set()
    for y in range(first.year - 1, last.year + 2):
        hol |= _holidays(y, cal)
    out = []
    d = first
    while d <= last:
        if d.weekday() < 5 and d not in hol:
            out.append(d.toordinal())
        d += timedelta(days=1)
    return out


def intents(bars, params, ctx):
    start = int(params.get("start", -1))
    end = int(params.get("end", 3))
    k = float(params.get("k", 2.5))
    n = len(bars["c"])
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "exit_long": exl, "exit_short": np.zeros(n, bool)}
    if ctx["symbol"] not in _SESSIONS or n == 0:
        return out
    tzname, close_min, cal = _SESSIONS[ctx["symbol"]]
    cm = bars["close_ms"].astype(np.int64)
    loc = _local_ms(cm, tzname)
    # the local trading date of a bar is the date of its open (a bar closing at 00:00 belongs to the day before)
    lday = (_local_ms(bars["open_ms"].astype(np.int64), tzname)) // _DAY
    mod = (loc // 60_000) % 1440
    epoch = date(1970, 1, 1).toordinal()

    # daily bars on the local calendar date, ATR(20) (simple mean of true range) over completed days before each day
    ud, idx0 = np.unique(lday, return_index=True)
    idx1 = np.r_[idx0[1:], n]
    H = np.array([bars["h"][a:b].max() for a, b in zip(idx0, idx1)])
    L = np.array([bars["l"][a:b].min() for a, b in zip(idx0, idx1)])
    C = np.array([bars["c"][b - 1] for b in idx1])
    pc = np.r_[np.nan, C[:-1]]
    tr = np.where(np.isnan(pc), H - L, np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc))))
    atr_before = np.full(len(ud), np.nan)       # ATR of the 20 days strictly before day j
    cs = np.r_[0.0, np.cumsum(tr)]
    for j in range(_ATR_N, len(ud)):
        atr_before[j] = (cs[j] - cs[j - _ATR_N]) / _ATR_N
    atr_of_day = dict(zip(ud.tolist(), atr_before.tolist()))

    first = date.fromordinal(int(lday.min()) + epoch)
    last = date.fromordinal(int(lday.max()) + epoch)
    tdays = _trading_days(first - timedelta(days=10), last + timedelta(days=40), cal)
    month = [(date.fromordinal(t).year, date.fromordinal(t).month) for t in tdays]

    entry_days, exit_days = set(), set()
    for p in range(len(tdays) - 1):
        if month[p + 1] != month[p]:            # tdays[p] is day -1, tdays[p + 1] is day +1
            # trading day t -> list position: day -m at p - (m - 1), day +m at p + m
            def pos(t):
                return p + t if t > 0 else p + t + 1
            e_pos = pos(start) - 1              # entry on the trading day before `start`
            x_pos = pos(end)
            if 0 <= e_pos and x_pos < len(tdays):
                entry_days.add(tdays[e_pos] - epoch)
                exit_days.add(tdays[x_pos] - epoch)

    # session close (minute of day) per local date: 13:00 NY on scheduled NYSE early closes (v2)
    early = set()
    if cal == "nyse":
        for y in range(first.year - 1, last.year + 2):
            early |= {e.toordinal() - epoch for e in _early_closes(y)}
    tset = set(t - epoch for t in tdays)

    def sclose(d):
        return 13 * 60 if d in early else close_min

    def pre_closure(d):                          # next calendar day is not a trading day (weekend or holiday)
        return (d + 1) not in tset

    live = bars["open_ms"] >= ctx["first_ms"]
    for d in sorted(entry_days):
        if ctx["symbol"] == "US500" and pre_closure(d):
            continue                             # v2: entry would fall in the engine's pre-close block
        hit = np.nonzero((lday == d) & (mod == sclose(d)))[0]
        if len(hit) == 0:
            continue
        i = int(hit[0])
        if not live[i]:
            continue
        a = atr_of_day.get(d, np.nan)
        if not np.isnan(a) and a > 0:
            side[i] = 1
            sl[i] = k * a
    for x in sorted(exit_days):
        hit = np.nonzero(((lday == x) & (mod >= sclose(x))) | (lday > x))[0]
        if len(hit):
            exl[int(hit[0])] = True
    return out
