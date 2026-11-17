"""IDEA-1026: TPO open-in-value rotation (card v1, ideas/cards/IDEA-1026-tpo-open-in-value-rotation-gold-oil.md).

- m30 bars (one TPO period each), America/New_York clock: XAUUSD session 08:30-13:30, XTIUSD 09:00-14:30. Session bars open at or
  after the session open and close at or before the session close, same New York date. A session counts if its first bar opens at
  the session open and its last bar closes at the session close.
- R20(d) = mean range of the 20 previous counted sessions (d excluded). The profile of session d is final at the close of its last
  bar. bin = R20(d) / 40, anchored at the session low; each bar marks every bin its [low, high] touches.
  POC = bin with most TPOs (ties: centre nearest the session mid-range, then the lower). Value area: from the POC add the adjacent bin
  with more TPOs (ties: both) until >= 70% of all TPOs. VAH / VAL = outer bin edges, W = VAH - VAL. W < 0.25 x R20 -> no trade.
- Session d + 1 (the next New York date with session bars): its open = the close of the bar ending at the session open (same
  New York date; missing -> no trade that day). It trades only if that close is strictly inside (VAL, VAH). Decision bars: that
  bar and every session bar closing >= 60 min before the session close. Live until the session's high so far >= VAH or low so far
  <= VAL (session bars only, the deciding bar included). While live, at a decision bar's close: close > POC -> sell limit at VAH;
  close < POC -> buy limit at VAL (live to the next bar's close). Stop s x W beyond the edge; target t x |edge - POC|; exit flags at the session's last bar; backstop hold to the
  session close.
params (card defaults): s = 0.4, t = 1.0. Class A rules, news modes and caps are applied by the engine.
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"s": 0.4, "t": 1.0}
ZONE = "America/New_York"
SESSIONS = {  # session open, session close (New York minutes after midnight)
    "XAUUSD": (8 * 60 + 30, 13 * 60 + 30),
    "XTIUSD": (9 * 60, 14 * 60 + 30),
}
MIN = 60_000
DAY = 86_400_000
LOOKBACK = 20
BINS_PER_R = 40
VA_SHARE = 0.70
MIN_W = 0.25                    # x R20
LAST_DECISION_GAP = 60          # minutes before the session close


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan), "exit_long": np.zeros(n, bool), "exit_short": np.zeros(n, bool)}


def _value_area(sh, sl, r20):
    """(VAL, VAH, POC centre) of one complete session, or None."""
    L = float(sl.min())
    H = float(sh.max())
    if not (H > L) or not (r20 > 0):
        return None
    step = r20 / BINS_PER_R
    nb = int(np.floor((H - L) / step)) + 1
    a = np.clip(np.floor((sl - L) / step).astype(np.int64), 0, nb - 1)
    b = np.clip(np.floor((sh - L) / step).astype(np.int64), 0, nb - 1)
    cnt = np.zeros(nb, np.int64)
    for x, y in zip(a, b):
        cnt[x:y + 1] += 1
    centre = L + (np.arange(nb) + 0.5) * step
    cand = np.flatnonzero(cnt == cnt.max())
    dist = np.abs(centre[cand] - 0.5 * (H + L))
    poc = int(cand[np.flatnonzero(dist == dist.min())[0]])        # nearest the mid-range, then the lower
    total = int(cnt.sum())
    lo = hi = poc
    inside = int(cnt[poc])
    while inside < VA_SHARE * total:
        up = int(cnt[hi + 1]) if hi + 1 < nb else -1
        dn = int(cnt[lo - 1]) if lo > 0 else -1
        if up < 0 and dn < 0:
            break
        if up > dn:
            hi += 1
            inside += up
        elif dn > up:
            lo -= 1
            inside += dn
        else:                                                      # tie: add both
            hi += 1
            lo -= 1
            inside += up + dn
    return L + lo * step, L + (hi + 1) * step, float(centre[poc])


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    s, t = float(p["s"]), float(p["t"])
    sym = ctx["symbol"]
    if sym not in SESSIONS:
        raise ValueError(f"IDEA-1026 trades {tuple(SESSIONS)}, not {sym}")
    if ctx.get("timeframe", "m30") != "m30":
        raise ValueError("IDEA-1026 is defined on m30 bars")
    open_min, close_min = SESSIONS[sym]
    o = np.asarray(bars["o"], float)
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    oms = np.asarray(bars["open_ms"], np.int64)
    cms = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    out = _empty(n)
    if n == 0:
        return out
    lo_ = local_ms(oms, ZONE)
    lc = local_ms(cms, ZONE)
    off = lc - cms
    oday, omin = lo_ // DAY, (lo_ % DAY) // MIN
    cday, cmin = lc // DAY, (lc % DAY) // MIN
    in_sess = (omin >= open_min) & (cday == oday) & (cmin <= close_min)
    first_ms = ctx["first_ms"]

    ranges = []                  # ranges of counted sessions, oldest first
    cur_day = None
    cur_idx = []
    pending = None               # (VAL, VAH, POC, W) from the last finished session
    level = None                 # the same, for the current session, while live
    s_lo = s_hi = None

    def finish(idx):
        if not idx:
            return None
        if not (omin[idx[0]] == open_min and cmin[idx[-1]] == close_min):
            return None
        sh, sl_ = h[idx], l[idx]
        res = None
        if len(ranges) >= LOOKBACK:
            r20 = float(np.mean(ranges[-LOOKBACK:]))
            va = _value_area(sh, sl_, r20)
            if va is not None:
                val, vah, poc = va
                w = vah - val
                if w >= MIN_W * r20:
                    res = (val, vah, poc, w)
        ranges.append(float(sh.max() - sl_.min()))
        if len(ranges) > 4 * LOOKBACK:
            del ranges[:-LOOKBACK]
        return res

    def quote(i, d):
        val, vah, poc, w = level
        side = -1 if c[i] > poc else (1 if c[i] < poc else 0)
        if side == 0 or oms[i] < first_ms:
            return
        edge = vah if side == -1 else val
        tgt = t * abs(edge - poc)
        stop = s * w
        if stop > 0 and tgt > 0:
            out["side"][i] = side
            out["otype"][i] = 2
            out["price"][i] = edge
            out["sl_dist"][i] = stop
            out["tp_dist"][i] = tgt
            close_utc = (d * DAY + close_min * MIN) - off[i]
            out["hold_ms"][i] = float(max(close_utc - cms[i], 0))

    for i in range(n):
        if cmin[i] == open_min and cday[i] == oday[i] and not in_sess[i]:
            # the bar ending at the session open: its close is the session's open price
            d = int(cday[i])
            cur_day = d
            cur_idx = []
            level = pending
            pending = None
            s_lo = s_hi = None
            if level is not None and not (level[0] < c[i] < level[1]):
                level = None                     # not an open inside prior value
            if level is not None:
                quote(i, d)
            continue
        if not in_sess[i]:
            continue
        d = int(oday[i])
        if d != cur_day:                         # no bar ending at the session open: no trade today
            cur_day = d
            cur_idx = []
            level = None
            pending = None
        s_lo = l[i] if s_lo is None else min(s_lo, l[i])
        s_hi = h[i] if s_hi is None else max(s_hi, h[i])
        cur_idx.append(i)
        is_last = cmin[i] == close_min
        if is_last:
            out["exit_long"][i] = True
            out["exit_short"][i] = True
        if level is not None and (s_hi >= level[1] or s_lo <= level[0]):
            level = None                         # an edge was touched: no more orders today
        if level is not None and cmin[i] <= close_min - LAST_DECISION_GAP:
            quote(i, d)
        if is_last:
            pending = finish(cur_idx)
            cur_idx = []
    return out
