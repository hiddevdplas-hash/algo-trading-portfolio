"""IDEA-2014: weekend-gap fade in EURUSD and GBPUSD (card v1, ideas/cards/IDEA-2014-weekend-gap-fade-fx.md).

Rule rebuilt from the card (Caporale & Plastun, "Price gaps: Another market anomaly?", Investment Analysts Journal 2017,
"sell after positive gaps, close at the end of the day"); no code copied.
- m15 bars. Weekend reopen = the first bar after a break of >= 24 h (bar close -> next bar open). F = close of the last bar
  before the break, O = open of the first bar after it, gap g = O / F - 1.
- Monday = the Europe/Amsterdam date of the reopen bar's open if it is a Monday, else the next local day (must be a Monday).
- Entry at market at the close of the first bar (from the reopen on) whose Amsterdam close is >= Monday 00:30 and < Monday 22:30:
  sell if g >= gap_min; if both_sides = 1, buy if g <= -gap_min.
- Stop 1.0 x D, D = mean (high - low) of the last 20 complete Amsterdam weekdays (Mon-Fri) ending before the reopen. No target.
- Exit at market at the close of the first bar whose Amsterdam close is >= Monday 22:30; backstop time exit 24 h.
params (card defaults): gap_min = 0.0010, both_sides = 0.
Class A rules, entry blocks, news modes and caps are applied by the engine, not here.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

_TZ = "Europe/Amsterdam"
_HOUR = 3_600_000
_DAY = 86_400_000
_MIN = 60_000
_BREAK_MS = 24 * _HOUR
_ENTRY_MIN = 30              # Monday 00:30 local
_EXIT_MIN = 22 * 60 + 30     # Monday 22:30 local
_D_N = 20
_K_STOP = 1.0
_HOLD_MS = 24 * _HOUR


def _local_ms(ms, tzname):
    """Local wall-clock ms for UTC ms (offset looked up once per UTC hour)."""
    tz = ZoneInfo(tzname)
    hours = ms // _HOUR
    uh, inv = np.unique(hours, return_inverse=True)
    off = np.array([int(datetime.fromtimestamp(int(h) * 3600, timezone.utc).astimezone(tz).utcoffset().total_seconds() * 1000)
                    for h in uh], dtype=np.int64)
    return ms + off[inv]


def _weekday(day_num):
    """Mon = 0 ... Sun = 6 for days since 1970-01-01 (a Thursday)."""
    return (np.asarray(day_num, np.int64) + 3) % 7


def intents(bars, params, ctx):
    gap_min = float(params.get("gap_min", 0.0010))
    both_sides = int(params.get("both_sides", 0))
    n = len(bars["c"])
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "hold_ms": hold, "exit_long": exl, "exit_short": exs}
    if n < 2:
        return out
    open_ms = np.asarray(bars["open_ms"], np.int64)
    close_ms = np.asarray(bars["close_ms"], np.int64)
    o = np.asarray(bars["o"], float)
    h = np.asarray(bars["h"], float)
    lo = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    lo_open = _local_ms(open_ms, _TZ)
    lo_close = _local_ms(close_ms, _TZ)
    o_day = lo_open // _DAY

    # daily ranges per local weekday date (complete days only are used: a day counts once its last bar is before the reopen)
    days, first_idx = np.unique(o_day, return_index=True)
    last_idx = np.append(first_idx[1:] - 1, n - 1)
    d_hi = np.maximum.reduceat(h, first_idx)
    d_lo = np.minimum.reduceat(lo, first_idx)
    d_rng = d_hi - d_lo
    d_wk = _weekday(days) < 5

    reopen = np.nonzero(open_ms[1:] - close_ms[:-1] >= _BREAK_MS)[0] + 1
    for i in reopen:
        F = c[i - 1]
        if not (F > 0):
            continue
        g = o[i] / F - 1.0
        if g >= gap_min:
            sgn = -1
        elif both_sides == 1 and g <= -gap_min:
            sgn = 1
        else:
            sgn = 0
        mon = o_day[i] if _weekday(o_day[i]) == 0 else o_day[i] + 1
        if _weekday(mon) != 0:
            continue
        t_entry = mon * _DAY + _ENTRY_MIN * _MIN
        t_exit = mon * _DAY + _EXIT_MIN * _MIN
        # exit bar: first bar from the reopen on whose local close >= Monday 22:30 (flags set every week, trade or not)
        k = i + int(np.searchsorted(lo_close[i:], t_exit, side="left"))
        if k < n and lo_close[k] < t_exit + _DAY:
            exl[k] = True
            exs[k] = True
        if sgn == 0:
            continue
        j = i + int(np.searchsorted(lo_close[i:], t_entry, side="left"))
        if j >= n or lo_close[j] >= t_exit or open_ms[j] < ctx["first_ms"]:
            continue
        # D: mean range of the last 20 complete local weekdays whose last bar is before the reopen bar
        done = (last_idx < i) & d_wk & (days < o_day[i])
        idx = np.nonzero(done)[0]
        if len(idx) < _D_N:
            continue
        D = float(np.mean(d_rng[idx[-_D_N:]]))
        if not (D > 0):
            continue
        side[j] = sgn
        sl[j] = _K_STOP * D
        hold[j] = _HOLD_MS
    return out
