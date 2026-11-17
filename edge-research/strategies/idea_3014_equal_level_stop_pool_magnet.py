"""IDEA-3014: equal-level stop-pool magnet (card v1, ideas/cards/IDEA-3014-equal-level-stop-pool-magnet.md).

Rebuilt from the card's description of the idea source (TradingView "Liquidity Gravity Strategy | Weighted Swing-Pool Imbalance"
by blitz_algo); no code copied.
- h1 bars. ATR(i) = simple mean of the true range of bars i-13 .. i (ATR14).
- Swing high at bar j: h(j) > max h(j-3 .. j-1) and h(j) >= max h(j+1 .. j+3); known only at the close of bar j+3 (confirmation).
  Swing low: the mirror.
- Pools: at confirmation (bar i = j+3) a swing high joins the nearest live high pool within 0.15 x ATR(i) of h(j) (count + 1, level =
  max(level, h(j)), last swing = j), else it starts a new pool (count 1). A high pool dies at the first bar whose high > level, or when
  its last swing is more than 240 bars old. Low pools: the mirror.
- Signal at bar i's close (bars with open_ms >= first_ms): U = nearest live high pool above the close with count >= m, du = (level -
  close) / ATR; dd = distance to the nearest live low pool below the close of any count (infinite if none). Long when 0.25 <= du <= D
  and dd >= 2 x du, and U has not been traded. Short: the mirror. Both at once: no trade.
- Long: buy at the close; target = U's level + 0.1 x ATR - close; stop = s x ATR; time exit 12 h. Each pool is traded at most once.
params (card defaults): D = 1.0, s = 1.0, m = 2. Class A rules, news modes and caps are applied by the engine.
"""
import numpy as np

_ATR_N = 14
_L = 3
_TOL = 0.15
_MAX_AGE = 240
_MIN_DIST = 0.25
_PROTECT = 2.0
_THROUGH = 0.10
_HOLD_MS = 12 * 3_600_000


def _atr(h, l, c, n):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.where(np.isnan(pc), h - l, np.maximum(h, pc) - np.minimum(l, pc))
    cs = np.concatenate(([0.0], np.cumsum(tr)))
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def intents(bars, params, ctx):
    D = float(params.get("D", 1.0))
    s = float(params.get("s", 1.0))
    m = int(params.get("m", 2))
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

    atr = _atr(h, l, c, _ATR_N)
    first_ms = int(ctx["first_ms"])
    # a pool: [level, count, last_swing_bar, traded]
    highs = []
    lows = []
    for i in range(n):
        a = atr[i]
        # 1. confirm the swing at j = i - L (uses bars <= i only)
        j = i - _L
        if j - _L >= 0 and a > 0:
            if h[j] > h[j - _L:j].max() and h[j] >= h[j + 1:i + 1].max():
                best = None
                for p in highs:
                    if abs(p[0] - h[j]) <= _TOL * a and (best is None or abs(p[0] - h[j]) < abs(best[0] - h[j])):
                        best = p
                if best is None:
                    highs.append([h[j], 1, j, False])
                else:
                    best[0] = max(best[0], h[j])
                    best[1] += 1
                    best[2] = j
            if l[j] < l[j - _L:j].min() and l[j] <= l[j + 1:i + 1].min():
                best = None
                for p in lows:
                    if abs(p[0] - l[j]) <= _TOL * a and (best is None or abs(p[0] - l[j]) < abs(best[0] - l[j])):
                        best = p
                if best is None:
                    lows.append([l[j], 1, j, False])
                else:
                    best[0] = min(best[0], l[j])
                    best[1] += 1
                    best[2] = j
        # 2. pools taken out by this bar, or too old, die
        highs = [p for p in highs if not (h[i] > p[0]) and i - p[2] <= _MAX_AGE]
        lows = [p for p in lows if not (l[i] < p[0]) and i - p[2] <= _MAX_AGE]
        # 3. signal
        if not (a > 0) or om[i] < first_ms:
            continue
        up = [p for p in highs if p[0] > c[i]]
        dn = [p for p in lows if p[0] < c[i]]
        up_m = [p for p in up if p[1] >= m]
        dn_m = [p for p in dn if p[1] >= m]
        U = min(up_m, key=lambda p: p[0]) if up_m else None
        B = max(dn_m, key=lambda p: p[0]) if dn_m else None
        d_any_dn = (c[i] - max(p[0] for p in dn)) / a if dn else np.inf
        d_any_up = (min(p[0] for p in up) - c[i]) / a if up else np.inf
        go_long = False
        go_short = False
        if U is not None and not U[3]:
            du = (U[0] - c[i]) / a
            go_long = _MIN_DIST <= du <= D and d_any_dn >= _PROTECT * du
        if B is not None and not B[3]:
            dd = (c[i] - B[0]) / a
            go_short = _MIN_DIST <= dd <= D and d_any_up >= _PROTECT * dd
        if go_long and not go_short:
            side[i] = 1
            sl[i] = s * a
            tp[i] = U[0] + _THROUGH * a - c[i]
            hold[i] = _HOLD_MS
            U[3] = True
        elif go_short and not go_long:
            side[i] = -1
            sl[i] = s * a
            tp[i] = c[i] - (B[0] - _THROUGH * a)
            hold[i] = _HOLD_MS
            B[3] = True
    return out
