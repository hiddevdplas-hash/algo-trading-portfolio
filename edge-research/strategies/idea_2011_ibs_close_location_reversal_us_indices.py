"""IDEA-2011: IBS close-location reversal in US indices (card v2,
ideas/cards/IDEA-2011-ibs-close-location-reversal-us-indices.md).

Rule rebuilt from the card (Pagonidis, "The IBS Effect: Mean Reversion in Equity ETFs", NAAIM 2013); no code copied.
- m15 bars, New York clock. Cash day = bars of one NY date with open >= 09:30 and close <= 16:00; counted only if it has the bar
  ending 16:00 and >= 20 of its 26 bars. Day high / low / close (16:00 bar) from those bars.
- IBS = (close - low) / (high - low). Long if IBS <= ibs_lo, short if IBS >= ibs_hi.
- Card v2: no volume filter (tick volume is not read; DESIGN §5 / REVIEW-FIXES 2026-11-16 hold on volume signals).
- Entry at market at the close of the 16:00 bar. Stop 2.0 x ATR(20) (simple mean of cash-day true ranges). No target.
- Exit at the close of the next counted day's 16:00 bar (exit flags on every counted 16:00 bar); backstop time exit 4 days.
params (card defaults): ibs_lo = 0.2, ibs_hi = 0.8.
Class C rules, entry blocks (incl. Friday's pre-weekend block), news modes and caps are applied by the engine, not here.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

_TZ = "America/New_York"
_OPEN, _CLOSE = 9 * 60 + 30, 16 * 60
_MIN_BARS = 20
_ATR_N = 20
_K_STOP = 2.0
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


def intents(bars, params, ctx):
    ibs_lo = float(params.get("ibs_lo", 0.2))
    ibs_hi = float(params.get("ibs_hi", 0.8))
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
    close_ms = np.asarray(bars["close_ms"], np.int64)
    lo_open = _local_ms(open_ms, _TZ)
    lo_close = _local_ms(close_ms, _TZ)
    o_mod = (lo_open // 60_000) % 1440
    c_mod = (lo_close // 60_000) % 1440
    o_day = lo_open // _DAY
    c_day = lo_close // _DAY
    in_sess = (o_day == c_day) & (o_mod >= _OPEN) & (c_mod <= _CLOSE) & (c_mod > _OPEN)
    sidx = np.nonzero(in_sess)[0]
    if len(sidx) == 0:
        return out
    h = np.asarray(bars["h"], float)
    l_ = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    # group session bars by local date (bars are time-ordered, so equal dates are contiguous)
    sd = o_day[sidx]
    starts = np.r_[0, np.nonzero(np.diff(sd))[0] + 1]
    ends = np.r_[starts[1:], len(sidx)]
    days_c, days_h, days_l, days_bar = [], [], [], []
    for s, e in zip(starts, ends):
        idx = sidx[s:e]
        last = idx[-1]
        if c_mod[last] != _CLOSE or len(idx) < _MIN_BARS:
            continue
        days_bar.append(last)
        days_c.append(c[last])
        days_h.append(h[idx].max())
        days_l.append(l_[idx].min())
    m = len(days_bar)
    if m == 0:
        return out
    db = np.asarray(days_bar, np.int64)
    C = np.asarray(days_c)
    H = np.asarray(days_h)
    L = np.asarray(days_l)
    exl[db] = True                                       # every counted 16:00 bar ends the one-session hold
    exs[db] = True
    rng = H - L
    with np.errstate(invalid="ignore", divide="ignore"):
        ibs = np.where(rng > 0, (C - L) / rng, np.nan)
    # ATR(20): simple mean of the last 20 cash-day true ranges (today included: known at today's close)
    pc = np.r_[np.nan, C[:-1]]
    tr = np.maximum(rng, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    atr = np.full(m, np.nan)
    if m > _ATR_N:
        cs = np.r_[0.0, np.cumsum(np.nan_to_num(tr))]
        atr[_ATR_N:] = (cs[_ATR_N + 1:] - cs[1:m - _ATR_N + 1]) / _ATR_N   # days 1..m-1 have a true range
    live = open_ms[db] >= ctx["first_ms"]
    ok = live & np.isfinite(ibs) & np.isfinite(atr) & (atr > 0)
    longs = ok & (ibs <= ibs_lo)
    shorts = ok & (ibs >= ibs_hi) & ~longs
    side[db[longs]] = 1
    side[db[shorts]] = -1
    ent = longs | shorts
    sl[db[ent]] = _K_STOP * atr[ent]
    hold[db[ent]] = _HOLD_MS
    return out
