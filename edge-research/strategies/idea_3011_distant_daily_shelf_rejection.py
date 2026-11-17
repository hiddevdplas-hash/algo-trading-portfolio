"""IDEA-3011: distant daily-shelf rejection (card v1, ideas/cards/IDEA-3011-distant-daily-shelf-rejection.md).

Rebuilt from the card's description of the idea source (TradingView "Impulse Move S/R Zones" by CBeamsGlitter, an indicator with no
direction or entries); no code copied.
- Trading day = NY 17:00 -> 17:00 (CFD roll). Daily bars are built from the job's bars; a day is used for levels only once complete
  (decisions on day g use days 0 .. g-1).
- ATRd(g) = simple mean of the true range of days g-14 .. g-1.
- Pivot high on day j: high(j) is the highest of days j-3 .. j+3 and above every high of days j-3 .. j-1 (pivot low: mirror).
  Reaction = (high(j) - lowest low of days j+1 .. j+10) / ATRd(j+1) (mirror for lows). A pivot becomes a level once day j+10 is
  complete, if reaction >= 1.0. Levels older than 252 days are dropped. Pivot highs and lows are both levels.
- Crossing rate of a level = number of completed days k > j whose close is on the other side of the level from day k-1's close,
  divided by the days since j. A level qualifies only with rate <= 0.10.
- Zone of a level P on day g: tol = 0.15 x ATRd(g); N = number of levels (any rate) within +-tol of P.
- Day g, resistance: the lowest qualifying level P with N >= Nmin and P - tol - open(g) >= M x ATRd(g). Armed when a bar's high
  reaches P - tol; broken when the day's high so far exceeds P + tol. Short at the close of the first bar (within 8 bars of the
  first touch, touch bar included) that closes below P - tol while not broken. Support: the mirror (long).
- Stop beyond the zone: P + tol + 0.1 ATRd (distance from the close); target T x stop; time exit 6 h. One trade a day.
- No decision before 60 completed days. Decisions only on bars with open_ms >= ctx["first_ms"].
params (card defaults): M = 0.75, Nmin = 2, T = 1.5. Class rules, news modes and caps are applied by the engine.
"""
import numpy as np

from engine.timeutil import local_ms

_TZ = "America/New_York"
_DAY = 86_400_000
_ROLL = 7 * 3_600_000          # 17:00 NY -> next trading day
_ATR_N = 14
_PIV_L = 3
_REACT_W = 10
_REACT_MIN = 1.0
_LOOKBACK = 252
_RATE_MAX = 0.10
_TOL = 0.15
_BUF = 0.10
_ARM_BARS = 8
_HOLD_MS = 6 * 3_600_000
_WARM_DAYS = 60


def intents(bars, params, ctx):
    m_dist = float(params.get("M", 0.75))
    nmin = int(params.get("Nmin", 2))
    tmul = float(params.get("T", 1.5))
    o = np.asarray(bars["o"], float)
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    om = np.asarray(bars["open_ms"], np.int64)
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    tp = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    out = {"side": side, "sl_dist": sl, "tp_dist": tp, "hold_ms": hold}
    if n == 0:
        return out

    dk = (local_ms(om, _TZ) + _ROLL) // _DAY
    keys, starts = np.unique(dk, return_index=True)       # bars are in time order, so day groups are contiguous
    ends = np.r_[starts[1:], n]
    nd = keys.size
    dO = o[starts]
    dH = np.maximum.reduceat(h, starts)
    dL = np.minimum.reduceat(l, starts)
    dC = c[ends - 1]
    tr = dH - dL
    tr[1:] = np.maximum(tr[1:], np.maximum(np.abs(dH[1:] - dC[:-1]), np.abs(dL[1:] - dC[:-1])))
    # atr[g] = mean TR of days g-14 .. g-1 (known at day g's start)
    csum = np.r_[0.0, np.cumsum(tr)]
    atr = np.full(nd, np.nan)
    if nd > _ATR_N:
        g = np.arange(_ATR_N, nd)
        atr[g] = (csum[g] - csum[g - _ATR_N]) / _ATR_N

    first_ms = int(ctx["first_ms"])
    lv_p = np.empty(0)        # level prices
    lv_j = np.empty(0, np.int64)   # pivot day
    lv_x = np.empty(0)        # crossings so far
    traded_upto = -1

    for g in range(nd):
        # 1) day g-1 is now complete: update crossings with its close, then add levels confirmed by it
        k = g - 1
        if k >= 1 and lv_p.size:
            s0 = np.sign(dC[k - 1] - lv_p)
            s1 = np.sign(dC[k] - lv_p)
            lv_x = lv_x + ((s0 != s1) & (k > lv_j) & (k - 1 >= lv_j)).astype(float)
        j = k - _REACT_W                      # pivot day whose reaction window ends on day k
        if j - _PIV_L >= 0 and j + _PIV_L <= k:
            win_h = dH[j - _PIV_L: j + _PIV_L + 1]
            win_l = dL[j - _PIV_L: j + _PIV_L + 1]
            a = atr[j + 1] if j + 1 < nd else np.nan
            if np.isfinite(a) and a > 0:
                new_p = []
                if dH[j] >= win_h.max() and dH[j] > dH[j - _PIV_L: j].max():
                    if (dH[j] - dL[j + 1: k + 1].min()) / a >= _REACT_MIN:
                        new_p.append(dH[j])
                if dL[j] <= win_l.min() and dL[j] < dL[j - _PIV_L: j].min():
                    if (dH[j + 1: k + 1].max() - dL[j]) / a >= _REACT_MIN:
                        new_p.append(dL[j])
                if new_p:
                    # crossings of the new level by closes of days j+1 .. k (known now)
                    xs = []
                    for p in new_p:
                        sg = np.sign(dC[j: k + 1] - p)
                        xs.append(float(np.count_nonzero(sg[1:] != sg[:-1])))
                    lv_p = np.r_[lv_p, new_p]
                    lv_j = np.r_[lv_j, [j] * len(new_p)]
                    lv_x = np.r_[lv_x, xs]
        if lv_p.size:
            keep = (k - lv_j) <= _LOOKBACK
            lv_p, lv_j, lv_x = lv_p[keep], lv_j[keep], lv_x[keep]

        # 2) decide inside day g
        if g < _WARM_DAYS or not np.isfinite(atr[g]) or atr[g] <= 0 or lv_p.size == 0:
            continue
        a = atr[g]
        tol = _TOL * a
        age = np.maximum(k - lv_j, 1)
        rate_ok = (lv_x / age) <= _RATE_MAX
        cnt = np.abs(lv_p[:, None] - lv_p[None, :]) <= tol
        nz = cnt.sum(axis=1)
        qual = rate_ok & (nz >= nmin)
        op = dO[g]
        up = lv_p[qual & (lv_p - tol - op >= m_dist * a)]
        dn = lv_p[qual & (op - (lv_p + tol) >= m_dist * a)]
        pr = up.min() if up.size else np.nan
        ps = dn.max() if dn.size else np.nan
        if np.isnan(pr) and np.isnan(ps):
            continue

        b0, b1 = starts[g], ends[g]
        hi_so, lo_so = -np.inf, np.inf
        touch_r = touch_s = -1
        for i in range(b0, b1):
            hi_so = max(hi_so, h[i])
            lo_so = min(lo_so, l[i])
            if om[i] < first_ms or traded_upto >= g:
                if not np.isnan(pr) and touch_r < 0 and h[i] >= pr - tol:
                    touch_r = i
                if not np.isnan(ps) and touch_s < 0 and l[i] <= ps + tol:
                    touch_s = i
                continue
            if not np.isnan(pr):
                if touch_r < 0 and h[i] >= pr - tol:
                    touch_r = i
                if (touch_r >= 0 and hi_so <= pr + tol and i - touch_r < _ARM_BARS and c[i] < pr - tol):
                    d = pr + tol + _BUF * a - c[i]
                    if d > 0:
                        side[i] = -1
                        sl[i] = d
                        tp[i] = tmul * d
                        hold[i] = _HOLD_MS
                        traded_upto = g
                        continue
            if not np.isnan(ps):
                if touch_s < 0 and l[i] <= ps + tol:
                    touch_s = i
                if (touch_s >= 0 and lo_so >= ps - tol and i - touch_s < _ARM_BARS and c[i] > ps + tol):
                    d = c[i] - (ps - tol - _BUF * a)
                    if d > 0:
                        side[i] = 1
                        sl[i] = d
                        tp[i] = tmul * d
                        hold[i] = _HOLD_MS
                        traded_upto = g
    return out
