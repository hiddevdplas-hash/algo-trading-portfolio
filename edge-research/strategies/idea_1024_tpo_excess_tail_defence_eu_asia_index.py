"""IDEA-1024: TPO excess-tail defence, next cash session (card v1,
ideas/cards/IDEA-1024-tpo-excess-tail-defence-eu-asia-index.md).

- m30 bars (one TPO period each), local cash clock per symbol: STOXX50 09:00-17:30 Frankfurt, UK100 08:00-16:30 London,
  JP225 09:00-15:00 Tokyo. Session bars open at or after the cash open and close at or before the cash close, same local date.
  A session counts if its first bar opens at the cash open and its last bar closes at the cash close.
- R20(d) = mean range of the 20 previous counted sessions (d excluded). Profile of session d is final at the close of its last bar.
  bin = R20(d) / 40. POC and buying tail on bins anchored at the low; selling tail on bins anchored at the high (mirror).
- Buying tail = run of single-print bins from the low upward, all marked by the same bar; TT = low + run x bin. Qualifies if
  run x bin >= e x R20(d), the marking bar is neither the first nor the last session bar, and the POC price is above TT. Selling tail:
  the mirror (TT = high - run x bin, POC below TT).
- Session d + 1 (the next local date with session bars) only: buying tail dies if the first bar opens at or below TT or once the
  session's low so far <= TT; while alive, at a bar closing >= 30 min before the cash close with close > TT: buy limit at TT
  (live to the next bar's close). Selling tail mirrors. Both live on one bar: the level nearer the close (ties: neither).
- Stop |TT - tail extreme| + s x R20(d); target |POC - TT|; exit flags at the bar closing at the cash close; backstop hold to the
  cash close.
params (card defaults): e = 0.12, s = 0.10. Class A rules, news modes and caps are applied by the engine.
"""
import numpy as np

from engine.timeutil import local_ms

DEFAULTS = {"e": 0.12, "s": 0.10}
SESSIONS = {  # zone, cash open (local minutes), cash close (local minutes)
    "STOXX50": ("Europe/Berlin", 9 * 60, 17 * 60 + 30),
    "UK100": ("Europe/London", 8 * 60, 16 * 60 + 30),
    "JP225": ("Asia/Tokyo", 9 * 60, 15 * 60),
}
MIN = 60_000
DAY = 86_400_000
LOOKBACK = 20
BINS_PER_R = 40
LAST_DECISION_GAP = 30          # minutes before the cash close


def _empty(n):
    return {"side": np.zeros(n, np.int64), "otype": np.zeros(n, np.int64), "price": np.full(n, np.nan),
            "sl_dist": np.full(n, np.nan), "tp_dist": np.full(n, np.nan), "expiry_ms": np.full(n, np.nan),
            "hold_ms": np.full(n, np.nan), "exit_long": np.zeros(n, bool), "exit_short": np.zeros(n, bool)}


def _tail_run(lo_idx, hi_idx, nb):
    """Single-print run from bin 0 upward, all marked by one bar: (run length in bins, marking bar index or -1)."""
    cnt = np.zeros(nb, np.int64)
    who = np.full(nb, -1, np.int64)
    for j, (a, b) in enumerate(zip(lo_idx, hi_idx)):
        cnt[a:b + 1] += 1
        seg = who[a:b + 1]
        seg[seg == -1] = j
    if cnt[0] != 1:
        return 0, -1, cnt
    m = who[0]
    run = 0
    while run < nb and cnt[run] == 1 and who[run] == m:
        run += 1
    return run, int(m), cnt


def _profile(sh, sl, r20, e):
    """Tails and POC of one complete session -> list of (side, TT, extreme, POC)."""
    L = float(sl.min())
    H = float(sh.max())
    if not (H > L) or not (r20 > 0):
        return []
    step = r20 / BINS_PER_R
    nb = int(np.floor((H - L) / step)) + 1
    last = len(sh) - 1
    out = []
    # low-anchored bins: POC and buying tail
    a = np.clip(np.floor((sl - L) / step).astype(np.int64), 0, nb - 1)
    b = np.clip(np.floor((sh - L) / step).astype(np.int64), 0, nb - 1)
    run, m, cnt = _tail_run(a, b, nb)
    centre = L + (np.arange(nb) + 0.5) * step
    top = cnt.max()
    cand = np.flatnonzero(cnt == top)
    poc = float(centre[cand[np.argmin(np.abs(centre[cand] - 0.5 * (H + L)))]])
    if run * step >= e * r20 and 0 < m < last:
        tt = L + run * step
        if poc > tt:
            out.append((1, tt, L, poc))
    # high-anchored bins (mirror): selling tail
    a2 = np.clip(np.floor((H - sh) / step).astype(np.int64), 0, nb - 1)
    b2 = np.clip(np.floor((H - sl) / step).astype(np.int64), 0, nb - 1)
    run2, m2, _ = _tail_run(a2, b2, nb)
    if run2 * step >= e * r20 and 0 < m2 < last:
        tt = H - run2 * step
        if poc < tt:
            out.append((-1, tt, H, poc))
    return out


def intents(bars, params, ctx):
    p = {**DEFAULTS, **params}
    e, s = float(p["e"]), float(p["s"])
    sym = ctx["symbol"]
    if sym not in SESSIONS:
        raise ValueError(f"IDEA-1024 trades {tuple(SESSIONS)}, not {sym}")
    if ctx.get("timeframe", "m30") != "m30":
        raise ValueError("IDEA-1024 is defined on m30 bars")
    zone, open_min, close_min = SESSIONS[sym]
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
    lo = local_ms(oms, zone)
    lc = local_ms(cms, zone)
    off = lc - cms
    oday, omin = lo // DAY, (lo % DAY) // MIN
    cday, cmin = lc // DAY, (lc % DAY) // MIN
    in_sess = (omin >= open_min) & (cday == oday) & (cmin <= close_min)
    first_ms = ctx["first_ms"]

    ranges = []                  # ranges of counted sessions, oldest first
    cur_day = None
    cur_idx = []                 # bar indices of the current session
    armed = []                   # live tails for the current session: [side, TT, extreme, POC, r20, alive]
    s_lo = s_hi = None

    def finish(idx):
        """Close a session: returns its tails (empty if not counted) and records its range."""
        if not idx:
            return []
        counted = omin[idx[0]] == open_min and cmin[idx[-1]] == close_min
        if not counted:
            return []
        sh, sl_ = h[idx], l[idx]
        tails = []
        if len(ranges) >= LOOKBACK:
            r20 = float(np.mean(ranges[-LOOKBACK:]))
            tails = [[sd, tt, ex, pc, r20, True] for (sd, tt, ex, pc) in _profile(sh, sl_, r20, e)]
        ranges.append(float(sh.max() - sl_.min()))
        if len(ranges) > 4 * LOOKBACK:
            del ranges[:-LOOKBACK]
        return tails

    pending = []                 # tails of the last finished session, for the next session
    for i in range(n):
        if not in_sess[i]:
            continue
        d = int(oday[i])
        if d != cur_day:
            armed = pending
            pending = []
            cur_day = d
            cur_idx = []
            s_lo, s_hi = l[i], h[i]
            for t in armed:      # an open through the level kills the tail
                if (t[0] == 1 and o[i] <= t[1]) or (t[0] == -1 and o[i] >= t[1]):
                    t[5] = False
        else:
            s_lo = min(s_lo, l[i])
            s_hi = max(s_hi, h[i])
        cur_idx.append(i)
        is_last = cmin[i] == close_min
        if is_last:
            out["exit_long"][i] = True
            out["exit_short"][i] = True
        # touches (this bar included) end a tail
        for t in armed:
            if t[5] and ((t[0] == 1 and s_lo <= t[1]) or (t[0] == -1 and s_hi >= t[1])):
                t[5] = False
        if cmin[i] <= close_min - LAST_DECISION_GAP and oms[i] >= first_ms:
            cands = [t for t in armed if t[5] and ((t[0] == 1 and c[i] > t[1]) or (t[0] == -1 and c[i] < t[1]))]
            if len(cands) == 2:
                d0, d1 = abs(c[i] - cands[0][1]), abs(c[i] - cands[1][1])
                cands = [] if d0 == d1 else [cands[0] if d0 < d1 else cands[1]]
            if cands:
                sd, tt, ex, pc, r20, _ = cands[0]
                stop = abs(tt - ex) + s * r20
                tgt = abs(pc - tt)
                if stop > 0 and tgt > 0:
                    out["side"][i] = sd
                    out["otype"][i] = 2
                    out["price"][i] = tt
                    out["sl_dist"][i] = stop
                    out["tp_dist"][i] = tgt
                    close_utc = (d * DAY + close_min * MIN) - off[i]
                    out["hold_ms"][i] = float(max(close_utc - cms[i], 0))
        if is_last:
            pending = finish(cur_idx)
            cur_idx = []
    return out
