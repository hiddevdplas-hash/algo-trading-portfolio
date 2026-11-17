"""IDEA-3010: US morning volume-pace continuation (card v1, ideas/cards/IDEA-3010-us-morning-volume-pace-continuation.md).

Rebuilt from the card's description of the idea source (TradingView "Session Volume Pace Curve [Pineify]" by Pineify, an indicator
with no direction); no code copied.
- m15 bars, NY clock. Cash bars open 09:30 ... 15:45; a complete session has all 26, contiguous (09:30 open -> 16:00 close).
- Reference per day: the 20 most recent complete sessions before it (no trade until 20 exist). CVref(j) = median cumulative tick
  volume from the 09:30 bar to cash slot j; Rref = median cash range (high - low).
- Today: the 09:30 bar and every cash bar up to the decision bar (the bar ending at E, NY) present and contiguous.
  P = today's cumulative tick volume to that bar / CVref(j*); m = (close of that bar - open of the 09:30 bar) / Rref.
- P >= Pmin and |m| >= Mmin -> market in the sign of m at the decision bar's close; stop 0.5 x Rref; no target;
  exit flag at the close of the cash bar ending 16:00 NY. One trade a day.
params (card defaults): E = "12:00", Pmin = 1.3, Mmin = 0.35. Class A rules, news modes and caps are applied by the engine.
"""
from collections import deque

import numpy as np

from engine.timeutil import local_ms

_TZ = "America/New_York"
_OPEN_MIN = 9 * 60 + 30
_CLOSE_MIN = 16 * 60
_STEP = 15
_SLOTS = (_CLOSE_MIN - _OPEN_MIN) // _STEP   # 26
_NREF = 20
_STOP_R = 0.5
_DAY = 86_400_000
_MIN = 60_000


def _minutes(e):
    if isinstance(e, str):
        hh, mm = e.split(":")
        return int(hh) * 60 + int(mm)
    return int(e)


def intents(bars, params, ctx):
    e_min = _minutes(params.get("E", "12:00"))
    pmin = float(params.get("Pmin", 1.3))
    mmin = float(params.get("Mmin", 0.35))
    o = np.asarray(bars["o"], float)
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    v = np.asarray(bars["vol"], float)
    om = np.asarray(bars["open_ms"], np.int64)
    cm = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    exl = np.zeros(n, bool)
    exs = np.zeros(n, bool)
    out = {"side": side, "sl_dist": sl, "exit_long": exl, "exit_short": exs}
    if n == 0:
        return out

    jstar = (e_min - _OPEN_MIN) // _STEP - 1          # slot of the bar ending at E
    if not (0 <= jstar < _SLOTS) or (e_min - _OPEN_MIN) % _STEP:
        raise ValueError(f"E={params.get('E')} is not an m15 cash bar end")

    lo = local_ms(om, _TZ)
    lday = lo // _DAY
    lmin = (lo % _DAY) // _MIN
    lcmin = (local_ms(cm, _TZ) % _DAY) // _MIN
    in_cash = (lmin >= _OPEN_MIN) & (lmin < _CLOSE_MIN)
    at_close = in_cash & (lcmin == _CLOSE_MIN)
    exl[at_close] = True
    exs[at_close] = True

    cash_idx = np.flatnonzero(in_cash)
    if cash_idx.size == 0:
        return out
    days, starts = np.unique(lday[cash_idx], return_index=True)
    ends = np.r_[starts[1:], cash_idx.size]
    first_ms = int(ctx["first_ms"])
    ref_cv = deque(maxlen=_NREF)    # cumulative-volume curves (26,) of complete sessions
    ref_rng = deque(maxlen=_NREF)

    for a, b in zip(starts, ends):
        ii = cash_idx[a:b]
        # leading run of on-time, contiguous slots from 09:30
        good = 0
        for j, i in enumerate(ii):
            if lmin[i] != _OPEN_MIN + j * _STEP:
                break
            if j > 0 and om[i] != cm[ii[j - 1]]:
                break
            good = j + 1
        if good > jstar and len(ref_cv) == _NREF:
            i = ii[jstar]
            cvref = float(np.median([cv[jstar] for cv in ref_cv]))
            rref = float(np.median(ref_rng))
            if cvref > 0 and rref > 0 and om[i] >= first_ms:
                pace = float(v[ii[:jstar + 1]].sum()) / cvref
                m = (c[i] - o[ii[0]]) / rref
                if pace >= pmin and abs(m) >= mmin:
                    side[i] = 1 if m > 0 else -1
                    sl[i] = _STOP_R * rref
        if good == _SLOTS and len(ii) == _SLOTS and lcmin[ii[-1]] == _CLOSE_MIN:
            seg = ii
            ref_cv.append(np.cumsum(v[seg]))
            ref_rng.append(float(h[seg].max() - l[seg].min()))
    return out
