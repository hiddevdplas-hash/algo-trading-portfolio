"""IDEA-2006: USD into the ECB fix, out after the London fix (card v1, ideas/cards/IDEA-2006-europe-fix-usd-reversal.md).

Rules rebuilt from the card (Krohn, Mueller, Whelan, BoC SWP 2021-48, Table IX windows; Breedon & Ranaldo 2011); no code copied.
Symbols are XXXUSD pairs (EURUSD, GBPUSD): long USD = sell the pair.
- m15 bars, New York clock.
- Pre leg (legs = pre or both): sell at the close of the bar ending 02:00 ET; exit flag (short) at the close of the bar ending 08:15 ET.
- Post leg (legs = post or both): buy at the close of the bar ending 11:00 ET; exit flag (long) at the close of the bar ending 16:30 ET.
- Weekdays only (Mon-Fri, New York date). Stop: k x Wilder ATR(14) of h1 bars built from the m15 bars (UTC hours fully closed at the
  entry bar's close). No target.
params (card defaults): legs = "both", k = 3.0.
Class A flat times, entry blocks, news modes and caps are applied by the engine, not here.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

_TZ = "America/New_York"
_PRE_IN, _PRE_OUT = 2 * 60, 8 * 60 + 15
_POST_IN, _POST_OUT = 11 * 60, 16 * 60 + 30
_ATR_N = 14
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


def _h1_atr_at(bars):
    """For each bar i: Wilder ATR(14) of the h1 bars (UTC hours) that closed at or before bar i's close."""
    om = bars["open_ms"].astype(np.int64)
    cm = bars["close_ms"].astype(np.int64)
    uh, start = np.unique(om // _HOUR, return_index=True)
    end = np.r_[start[1:], len(om)]
    H = np.array([bars["h"][a:b].max() for a, b in zip(start, end)])
    L = np.array([bars["l"][a:b].min() for a, b in zip(start, end)])
    C = np.array([bars["c"][b - 1] for b in end])
    pc = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    atr = np.full(len(C), np.nan)
    if len(C) >= _ATR_N:
        atr[_ATR_N - 1] = tr[:_ATR_N].mean()
        for k in range(_ATR_N, len(C)):
            atr[k] = atr[k - 1] + (tr[k] - atr[k - 1]) / _ATR_N
    k = np.searchsorted((uh + 1) * _HOUR, cm, side="right") - 1
    out = np.full(len(om), np.nan)
    ok = k >= 0
    out[ok] = atr[k[ok]]
    return out


def intents(bars, params, ctx):
    legs = str(params.get("legs", "both")).strip().lower()
    k = float(params.get("k", 3.0))
    n = len(bars["c"])
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "exit_long": exl, "exit_short": exs}
    if n == 0:
        return out
    loc = _local_ms(bars["close_ms"].astype(np.int64), _TZ)
    mod = (loc // 60_000) % 1440
    weekday = ((loc // _DAY) + 3) % 7 < 5
    live = (bars["open_ms"] >= ctx["first_ms"]) & weekday
    atr = _h1_atr_at(bars)
    ok = live & ~np.isnan(atr)
    if legs in ("pre", "both"):
        e = ok & (mod == _PRE_IN)
        side[e] = -1
        sl[e] = k * atr[e]
        exs[weekday & (mod == _PRE_OUT)] = True
    if legs in ("post", "both"):
        e = ok & (mod == _POST_IN)
        side[e] = 1
        sl[e] = k * atr[e]
        exl[weekday & (mod == _POST_OUT)] = True
    return out
