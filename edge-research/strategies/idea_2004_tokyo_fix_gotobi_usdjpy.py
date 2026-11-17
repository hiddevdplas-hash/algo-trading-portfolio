"""IDEA-2004: Tokyo-fix gotobi drift on USDJPY (card, ideas/cards/IDEA-2004-tokyo-fix-gotobi-usdjpy.md).

Rules rebuilt from the card (Ito & Yamada, NBER WP 22820); no code copied.
- m5 bars, UTC clock (Japan has no DST; the fix is 09:55 JST = 00:55 UTC).
- Settlement days (UTC date = Tokyo date at 00:55 UTC): the 5th, 10th, 15th, 20th, 25th, 30th, each moved to the preceding weekday when
  it falls on a weekend; the last weekday of the month; and Fridays if fridays = on. Japanese public holidays are not known here
  (the card's stated approximation).
- Long leg: buy at the close of the m5 bar ending `lead` minutes before 00:55 UTC; exit flag at the close of the bar ending 00:55.
- Short leg (short_leg = on): sell at the close of the bar ending 00:55 (the long's exit and this entry share a tick); exit flag at the
  close of the bar ending 01:10.
- Stop on each leg: 1.0 x Wilder ATR(14) of h1 bars built from the m5 bars, using only hours fully closed at the entry bar's close.
params (card defaults): lead = 15, short_leg = off, fridays = off.
Class rules, entry blocks, news modes and caps are applied by the engine, not here.
"""
from datetime import date, timedelta

import numpy as np

_FIX_MIN = 55          # 00:55 UTC, minute of day
_SHORT_END_MIN = 70    # 01:10 UTC
_ATR_N = 14
_STOP_ATR = 1.0
_DAY = 86_400_000
_HOUR = 3_600_000


def _flag(v):
    if isinstance(v, str):
        return v.strip().lower() in ("on", "true", "1", "yes")
    return bool(v)


def _settlement_days(first, last, fridays):
    """Set of date ordinals that are settlement days between first and last (dates)."""
    out = set()
    y, mth = first.year, first.month
    while date(y, mth, 1) <= last:
        nxt = date(y + (mth == 12), mth % 12 + 1, 1)
        for dom in (5, 10, 15, 20, 25, 30):
            try:
                d = date(y, mth, dom)
            except ValueError:
                continue
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            out.add(d.toordinal())
        d = nxt - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        out.add(d.toordinal())
        y, mth = nxt.year, nxt.month
    if fridays:
        d = first
        while d <= last:
            if d.weekday() == 4:
                out.add(d.toordinal())
            d += timedelta(days=1)
    return out


def _h1_atr_at(bars):
    """For each m5 bar i: Wilder ATR(14) of the h1 bars (UTC hours) that closed at or before bar i's close."""
    om = bars["open_ms"].astype(np.int64)
    cm = bars["close_ms"].astype(np.int64)
    hr = om // _HOUR
    uh, start = np.unique(hr, return_index=True)
    end = np.r_[start[1:], len(om)]
    H = np.array([bars["h"][a:b].max() for a, b in zip(start, end)])
    L = np.array([bars["l"][a:b].min() for a, b in zip(start, end)])
    C = np.array([bars["c"][b - 1] for b in end])
    pc = np.r_[C[0], C[:-1]] if len(C) else C
    tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    atr = np.full(len(C), np.nan)
    if len(C) >= _ATR_N:
        atr[_ATR_N - 1] = tr[:_ATR_N].mean()
        for k in range(_ATR_N, len(C)):
            atr[k] = atr[k - 1] + (tr[k] - atr[k - 1]) / _ATR_N
    # index of the last hour whose end ((h + 1) * HOUR) is <= the bar's close
    k = np.searchsorted((uh + 1) * _HOUR, cm, side="right") - 1
    out = np.full(len(om), np.nan)
    ok = k >= 0
    out[ok] = atr[k[ok]]
    return out


def intents(bars, params, ctx):
    lead = int(params.get("lead", 15))
    short_leg = _flag(params.get("short_leg", "off"))
    fridays = _flag(params.get("fridays", "off"))
    n = len(bars["c"])
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "exit_long": exl, "exit_short": exs}
    if n == 0:
        return out
    cm = bars["close_ms"].astype(np.int64)
    cday = cm // _DAY
    cmin = (cm // 60_000) % 1440
    epoch = date(1970, 1, 1).toordinal()
    first = date.fromordinal(int(cday.min()) + epoch)
    last = date.fromordinal(int(cday.max()) + epoch)
    sdays = _settlement_days(first, last, fridays)
    is_sday = np.array([int(d) + epoch in sdays for d in cday], bool)
    live = bars["open_ms"] >= ctx["first_ms"]
    atr = _h1_atr_at(bars)

    entry = is_sday & live & (cmin == _FIX_MIN - lead) & ~np.isnan(atr)
    side[entry] = 1
    sl[entry] = _STOP_ATR * atr[entry]
    fix = is_sday & (cmin == _FIX_MIN)
    exl[fix] = True
    if short_leg:
        sentry = fix & live & ~np.isnan(atr)
        side[sentry] = -1
        sl[sentry] = _STOP_ATR * atr[sentry]
        exs[is_sday & (cmin == _SHORT_END_MIN)] = True
    return out
