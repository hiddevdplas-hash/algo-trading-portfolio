"""IDEA-2010: Low-volume daily reversal in the USD majors (card v1,
ideas/cards/IDEA-2010-low-volume-daily-reversal-fx.md).

Rule rebuilt from the card (Cespa, Gargano, Riddiough & Sarno, "Foreign Exchange Volume", CEPR DP16128 / RFS 2022,
time-series strategy LV RTS); no code copied.
- h1 bars, London clock. A day ends at the close of the h1 bar ending 16:00 London (Mon-Fri). r_t = log(C_t / C_{t-1})
  between consecutive decision bars; V_t = sum of tick volume of the h1 bars after the previous decision bar up to this one.
- Holidays (US federal, England-and-Wales bank holidays; fixed rules, observed dates): no entry, not in the volume baseline.
- v_t = log(V_t) - log(mean V over the previous N = 21 non-holiday days). If v_t < v_max and r_t != 0: side = -sign(r_t).
- Entry at market at the decision bar's close. Stop k x ATR(20) (simple mean of daily true ranges). No target.
- Exit at the next decision bar's close (exit flags on every decision bar); backstop time exit 4 days.
params (card defaults): v_max = 0.0, k = 1.5.
Class C rules, entry blocks, news modes and caps are applied by the engine, not here.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

_TZ = "Europe/London"
_DAY_END = 16 * 60
_N_VOL, _ATR_N = 21, 20
_HOLD_MS = 4 * 86_400_000
_HOUR = 3_600_000
_DAY = 86_400_000


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


def _us_observed(d):
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _holidays(y):
    """US federal holidays and England-and-Wales bank holidays (fixed rules) of year y, as observed."""
    hs = set()
    # US federal
    for m, dd in ((1, 1), (7, 4), (11, 11), (12, 25)):
        hs.add(_us_observed(date(y, m, dd)))
    hs.add(_us_observed(date(y + 1, 1, 1)))          # New Year on a Saturday is observed on 31 Dec
    if y >= 2021:
        hs.add(_us_observed(date(y, 6, 19)))
    hs.update({_nth_weekday(y, 1, 0, 3), _nth_weekday(y, 2, 0, 3), _nth_weekday(y, 5, 0, -1),
               _nth_weekday(y, 9, 0, 1), _nth_weekday(y, 10, 0, 2), _nth_weekday(y, 11, 3, 4)})
    # England and Wales
    nyd = date(y, 1, 1)
    hs.add(nyd + timedelta(days=(7 - nyd.weekday()) % 7) if nyd.weekday() >= 5 else nyd)
    e = _easter(y)
    hs.update({e - timedelta(days=2), e + timedelta(days=1)})
    hs.update({_nth_weekday(y, 5, 0, 1), _nth_weekday(y, 5, 0, -1), _nth_weekday(y, 8, 0, -1)})
    xmas = date(y, 12, 25)
    wd = xmas.weekday()
    if wd == 5:                                       # Sat: Christmas Mon 27, Boxing Tue 28
        hs.update({date(y, 12, 27), date(y, 12, 28)})
    elif wd == 6:                                     # Sun: Boxing Mon 26, Christmas Tue 27
        hs.update({date(y, 12, 26), date(y, 12, 27)})
    elif wd == 4:                                     # Fri: Boxing Day (Sat) moves to Mon 28
        hs.update({xmas, date(y, 12, 28)})
    else:
        hs.update({xmas, date(y, 12, 26)})
    return hs


def intents(bars, params, ctx):
    v_max = float(params.get("v_max", 0.0))
    k = float(params.get("k", 1.5))
    n = len(bars["c"])
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "hold_ms": hold, "exit_long": exl, "exit_short": exs}
    if n == 0:
        return out
    loc = _local_ms(np.asarray(bars["close_ms"], np.int64), _TZ)
    mod = (loc // 60_000) % 1440
    dnum = loc // _DAY                                   # local days since 1970-01-01 (a Thursday)
    weekday = (dnum + 3) % 7 < 5
    cc = np.nonzero(weekday & (mod == _DAY_END))[0]
    m = len(cc)
    exl[cc] = True                                       # every decision bar ends the 24 h hold
    exs[cc] = True
    if m < 3:
        return out
    c = np.asarray(bars["c"], float)
    starts = np.r_[0, cc[:-1] + 1]
    C = c[cc]
    H = np.maximum.reduceat(np.asarray(bars["h"], float)[: cc[-1] + 1], starts)
    L = np.minimum.reduceat(np.asarray(bars["l"], float)[: cc[-1] + 1], starts)
    V = np.add.reduceat(np.asarray(bars["vol"], float)[: cc[-1] + 1], starts)
    valid = np.ones(m, bool)
    valid[0] = False                                     # first day starts mid-day (before the first decision bar)
    # holidays (local London date of the decision bar)
    epoch = date(1970, 1, 1)
    days = [epoch + timedelta(days=int(x)) for x in dnum[cc]]
    hol_cache = {}
    is_hol = np.zeros(m, bool)
    for j, d in enumerate(days):
        if d.year not in hol_cache:
            hol_cache[d.year] = _holidays(d.year)
        is_hol[j] = d in hol_cache[d.year]
    base_ok = valid & ~is_hol & (V > 0)
    # abnormal volume vs the previous N baseline days (excluding today)
    vt = np.full(m, np.nan)
    nb = np.nonzero(base_ok)[0]
    if len(nb) > _N_VOL:
        cs = np.r_[0.0, np.cumsum(V[nb])]
        for p in range(_N_VOL, len(nb)):
            mean_prev = (cs[p] - cs[p - _N_VOL]) / _N_VOL
            vt[nb[p]] = np.log(V[nb[p]]) - np.log(mean_prev)
    # returns and ATR(20), simple mean of daily true ranges
    r = np.full(m, np.nan)
    r[1:] = np.log(C[1:] / C[:-1])
    pc = np.r_[np.nan, C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    tr[0] = np.nan
    atr = np.full(m, np.nan)
    if m > _ATR_N:
        cs = np.r_[0.0, np.cumsum(np.nan_to_num(tr))]
        atr[_ATR_N:] = (cs[_ATR_N + 1:] - cs[1:m - _ATR_N + 1]) / _ATR_N
    live = np.asarray(bars["open_ms"])[cc] >= ctx["first_ms"]
    with np.errstate(invalid="ignore"):
        entry = live & base_ok & np.isfinite(vt) & (vt < v_max) & np.isfinite(r) & (r != 0) & np.isfinite(atr) & (atr > 0)
    ei = cc[entry]
    side[ei] = -np.sign(r[entry]).astype(np.int64)
    sl[ei] = k * atr[entry]
    hold[ei] = _HOLD_MS
    return out
