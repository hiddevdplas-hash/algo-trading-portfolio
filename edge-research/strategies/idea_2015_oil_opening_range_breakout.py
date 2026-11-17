"""IDEA-2015: WTI opening-range breakout (card v1, ideas/cards/IDEA-2015-oil-opening-range-breakout.md).

Rule rebuilt from the card (Lundström 2017, "Day trading returns across volatility states", Eq. (4): the ORB "long strangle");
no code copied.
- m5 bars, clock America/New_York. A day trades only if it is Mon-Fri and has a bar opening at exactly 09:00 New York.
  O = that bar's open; U = O * exp(rho), L = O * exp(-rho).
- Entry at market at the close of the first bar (from the 09:00 bar on, closing <= 14:25 New York) whose high >= U (buy) or
  low <= L (sell). If that first touching bar touches both bands, no trade that day. One trade a day.
- Stop at the opposite band: long sl_dist = close - L, short sl_dist = U - close. No target.
- Exit at market at the close of the bar closing at 14:30 New York; backstop time exit 6 h.
params (card default): rho = 0.015.
Class A rules, entry blocks, news modes and caps are applied by the engine, not here.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

_TZ = "America/New_York"
_HOUR = 3_600_000
_DAY = 86_400_000
_MIN = 60_000
_OPEN_MIN = 9 * 60            # 09:00 New York
_LAST_ENTRY_MIN = 14 * 60 + 25  # entry bar must close <= 14:25
_EXIT_MIN = 14 * 60 + 30      # exit at the bar closing 14:30
_HOLD_MS = 6 * _HOUR


def _local_ms(ms, tzname):
    """Local wall-clock ms for UTC ms (offset looked up once per UTC hour)."""
    tz = ZoneInfo(tzname)
    hours = ms // _HOUR
    uh, inv = np.unique(hours, return_inverse=True)
    off = np.array([int(datetime.fromtimestamp(int(h) * 3600, timezone.utc).astimezone(tz).utcoffset().total_seconds() * 1000)
                    for h in uh], dtype=np.int64)
    return ms + off[inv]


def intents(bars, params, ctx):
    rho = float(params.get("rho", 0.015))
    n = len(bars["c"])
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "hold_ms": hold, "exit_long": exl, "exit_short": exs}
    if n == 0:
        return out
    open_ms = np.asarray(bars["open_ms"], np.int64)
    o = np.asarray(bars["o"], float)
    h = np.asarray(bars["h"], float)
    lo = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    lo_open = _local_ms(open_ms, _TZ)
    lo_close = _local_ms(np.asarray(bars["close_ms"], np.int64), _TZ)
    day = lo_open // _DAY
    tod_open = lo_open - day * _DAY
    wkday = (day + 3) % 7          # Mon = 0 (1970-01-01 was a Thursday)

    # exit flags: every weekday bar closing exactly at 14:30 New York
    cday = lo_close // _DAY
    tod_close = lo_close - cday * _DAY
    ex = (tod_close == _EXIT_MIN * _MIN) & (((cday + 3) % 7) < 5)
    exl[ex] = True
    exs[ex] = True

    starts = np.nonzero((tod_open == _OPEN_MIN * _MIN) & (wkday < 5))[0]
    first_ms = ctx["first_ms"]
    for s in starts:
        O = o[s]
        if not (O > 0):
            continue
        U = O * np.exp(rho)
        L = O * np.exp(-rho)
        d = day[s]
        last_close = d * _DAY + _LAST_ENTRY_MIN * _MIN
        j = s
        while j < n and lo_close[j] <= last_close and lo_close[j] > lo_open[s]:
            up = h[j] >= U
            dn = lo[j] <= L
            if up or dn:
                if up and dn:
                    break                       # double touch in one bar before entry: no trade today
                if open_ms[j] >= first_ms:
                    if up:
                        dist = c[j] - L
                        if dist > 0:
                            side[j] = 1
                            sl[j] = dist
                            hold[j] = _HOLD_MS
                    else:
                        dist = U - c[j]
                        if dist > 0:
                            side[j] = -1
                            sl[j] = dist
                            hold[j] = _HOLD_MS
                break                           # first touch decides the day
            j += 1
    return out
