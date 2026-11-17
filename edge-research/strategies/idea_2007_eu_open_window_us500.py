"""IDEA-2007: US500 long through the European open (card v1, ideas/cards/IDEA-2007-eu-open-window-us500.md).

Rules rebuilt from the card (Bondarenko & Muravyev 2023, Internet Appendix Tables IA.2 / IA.8); no code copied.
- m15 bars, New York clock. A session is named by the NY date D of its exit (a Mon-Fri).
- Pre-EU-open volatility of session D: sqrt(sum of squared m15 log returns) of the bars closing after 18:00 ET on the evening before D
  up to and including the bar ending 23:30 ET that evening.
- Entry: buy at the close of the bar ending 01:30 ET on D (window = second) or 23:30 ET on the evening before (window = full).
  With vol_filter on, only if that night's volatility is above the median of the previous 60 nights' values.
- Stop: k x Wilder ATR(14) of h1 bars built from the m15 bars (UTC hours fully closed at the entry bar's close).
- Exit flag at the close of the bar ending 03:30 ET on D. No target.
params (card defaults): window = "second", vol_filter = "on", k = 1.5.
Class A flat times, entry blocks, news modes and caps are applied by the engine, not here.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

_TZ = "America/New_York"
_VOL_START = 18 * 60          # bars closing after 18:00 ET ...
_VOL_END = 23 * 60 + 30       # ... up to and including the bar ending 23:30 ET (previous evening)
_ENTRY_SECOND = 1 * 60 + 30   # 01:30 ET on D
_ENTRY_FULL = 23 * 60 + 30    # 23:30 ET on D - 1
_EXIT = 3 * 60 + 30           # 03:30 ET on D
_MED_NIGHTS = 60
_ATR_N = 14
_HOUR = 3_600_000
_DAY = 86_400_000


def _flag(v):
    if isinstance(v, str):
        return v.strip().lower() in ("on", "true", "1", "yes")
    return bool(v)


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
    window = str(params.get("window", "second")).strip().lower()
    vol_filter = _flag(params.get("vol_filter", "on"))
    k = float(params.get("k", 1.5))
    c = bars["c"]
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "exit_long": exl}
    if n < 2:
        return out
    loc = _local_ms(bars["close_ms"].astype(np.int64), _TZ)
    day = loc // _DAY
    mod = (loc // 60_000) % 1440
    lr = np.r_[np.nan, np.log(c[1:] / c[:-1])]
    atr = _h1_atr_at(bars)

    # pre-EU-open volatility per evening (keyed by the session date D = evening date + 1)
    in_night = (mod > _VOL_START) & (mod <= _VOL_END) & ~np.isnan(lr)
    night_vol = {}
    for d in np.unique(day[in_night]):
        sel = in_night & (day == d)
        night_vol[int(d) + 1] = float(np.sqrt(np.sum(lr[sel] ** 2)))

    if window == "full":
        ent_idx = {int(day[i]) + 1: i for i in np.nonzero(mod == _ENTRY_FULL)[0]}
    else:
        ent_idx = {int(day[i]): i for i in np.nonzero(mod == _ENTRY_SECOND)[0]}
    ext_idx = {int(day[i]): i for i in np.nonzero(mod == _EXIT)[0]}

    past = []  # previous nights' volatility values, oldest first
    for D in sorted(set(night_vol) | set(ent_idx)):
        v = night_vol.get(D)
        i = ent_idx.get(D)
        ok_day = ((D + 3) % 7) < 5  # session date Mon-Fri (calendar only; never the future exit bar)
        if i is not None and ok_day and bars["open_ms"][i] >= ctx["first_ms"] and not np.isnan(atr[i]):
            take = True
            if vol_filter:
                take = v is not None and len(past) >= _MED_NIGHTS and v > float(np.median(past[-_MED_NIGHTS:]))
            if take:
                side[i] = 1
                sl[i] = k * atr[i]
        if v is not None:
            past.append(v)
    for D, j in ext_idx.items():
        if ((D + 3) % 7) < 5:
            exl[j] = True
    return out
