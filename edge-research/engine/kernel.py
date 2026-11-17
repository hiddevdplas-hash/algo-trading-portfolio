"""Engine kernel: order intents from closed bars -> trades simulated on ticks (DESIGN §4.1, the rule mechanics of §4.2 and §3.6).

Generic: no strategy code here. A strategy hands over one intent per decision bar (arrays aligned to its bars):
  side[i]       +1 buy, -1 sell, 0 nothing
  otype[i]      MARKET, STOP or LIMIT
  price[i]      entry level for STOP / LIMIT (ignored for MARKET)
  sl_dist[i]    stop distance from the actual fill price (> 0; required: an order without a stop is refused)
  tp_dist[i]    target distance from the actual fill (NaN = no target)
  expiry_ms[i]  how long a STOP / LIMIT order stays live after it goes live (NaN or <= 0 = until the next bar's close)
  hold_ms[i]    time exit: close at the first tick at or after fill time + hold_ms (NaN = none)
Per-bar position management, also from closed bars only:
  trail_long[i], trail_short[i]   candidate stop levels applied at bar i's close (tighten only, by more than min_step; NaN = none)
  exit_long[i], exit_short[i]     close at market at bar i's close
Per run (built by engine/rules.py from the card's class, the symbol's hours and the news calendar; all sorted UTC ms):
  flat_ms                 any position is closed and a pending order cancelled at the first tick at or after each
  blk_start, blk_end      entry blocks [start, end): no intent goes live inside; a pending order is cancelled when one starts
                          (22:45 -> 00:15 Amsterdam, 2 h before a close of >= 2 h, news windows)
  win_start, win_end, win_kind, win_far   news windows [start, end) for open positions:
                          kind 1 = flatten at the start, unless the stop is further from price than win_far (far-stop exemption;
                          NaN = no exemption); kind 2 = hold without target. A held or exempt position has its target removed and
                          its trail paused for the window, and exit signals / time exits wait for the window's end; after it, it is
                          closed at market if price is past the target, otherwise the target goes back.
  day_start, max_per_day  at most max_per_day entries per day (days start at day_start; 0 = no cap)
  max_orders_60s          at most this many order events (entries going live, exits) in any 60 s (0 = no cap)
  min_step                a trailed stop must improve the stop by more than this (half a tick for cTrader parity)
  pip_size                > 0: the stop and target set from the fill are entry -/+ (distance / pip_size) * pip_size in raw double
                          arithmetic, exactly as cTrader stores them (referee comparison 2026-11-12: 959 of 959 stops and targets
                          bit-identical); exact touches then fill or not as in cTrader. 0 = entry -/+ distance.
Dropped intents are counted, never silently lost.

Event order on every tick = cTrader's (VWAP tools/fastbt/RULES.md A10) with the cBot conventions of cTrader-Bots/CONVENTIONS.md:
  1. order engine: a pending order fills (STOP buy at the first tick with ask >= price, LIMIT buy with ask <= price, at that tick's
     ask, so gaps fill at the gap price; sells mirror on the bid); an open position's **stop, then target** (long: bid <= stop,
     bid >= target, at that tick's bid; shorts on the ask; exact touches fill);
  2. housekeeping (the cBot, first thing on each tick): flat time; entry block / news window start (cancel a pending order; news
     handling of a position); news window end; pending order end (expiry, or the next bar's close); time exit;
  3. bar-close events, only on the first tick at or after a bar's close and only for a position filled before that close: trailed
     stop (one already beaten by this tick's price closes at once), exit signal;
  4. a new intent: goes live on the first tick at or after its decision bar's close, if no order or position is active after
     steps 1-3 (otherwise dropped and counted). MARKET fills on that tick. A STOP / LIMIT whose level is already crossed on that
     tick is refused and counted (the cBot does not send it).
  So a pending order can still fill on the tick that ends it, an exit and a new entry can share a tick (stop-and-reverse), and
  a position never sees the bar-close events of the tick it was filled on.
  - one position per strategy per symbol; 1 R = the stop distance at the fill; results in R before costs.
Exit reasons: 1 stop, 2 target, 3 time exit, 4 exit signal, 5 flat time, 6 end of data, 7 trailed stop (hit by the order engine or
already beaten at the bar close), 8 news flatten, 9 past the target after a news window.
Per-trade news flags (bits): 1 held through a window without target, 2 far-stop exemption used, 4 closed by news (reason 8 or 9).
"""
import numpy as np
from numba import njit

MARKET, STOP, LIMIT = 0, 1, 2
EXIT_NAMES = {1: "stop", 2: "target", 3: "time", 4: "signal", 5: "flat", 6: "end", 7: "trail_stop", 8: "news_flat", 9: "news_target"}
TRADE_FIELDS = ("bar", "side", "otype", "live_tick", "entry_tick", "entry_t", "entry_px", "sl0", "tp", "risk",
                "exit_tick", "exit_t", "exit_px", "exit_reason", "sl_exit", "mfe_r", "mae_r", "r_gross", "news_flags")
# counters
(C_DROPPED_BUSY, C_REFUSED_NO_STOP, C_EXPIRED, C_CANCELLED_FLAT, C_NO_TICK, C_REFUSED_CROSSED, C_BLOCKED_ENTRY, C_CANCELLED_BLOCK,
 C_DAY_CAP, C_ORDER_RATE, C_NEWS_FLAT, C_FAR_STOP, C_NEWS_HELD) = range(13)
COUNTER_NAMES = ("dropped_busy", "refused_no_stop", "expired", "cancelled_flat", "no_tick_after_close", "refused_crossed",
                 "blocked_entry", "cancelled_block", "dropped_day_cap", "dropped_order_rate", "news_flattened", "far_stop_used",
                 "news_held")
RING = 16


@njit(cache=True)
def _crossed(ot, s, b, a, p):
    if ot == STOP:
        return (s > 0 and a >= p) or (s < 0 and b <= p)
    return (s > 0 and a <= p) or (s < 0 and b >= p)


@njit(cache=True)
def _inside(starts, ends, x):
    """Index of the interval [start, end) containing x, or -1 (intervals sorted and non-overlapping)."""
    w = np.searchsorted(ends, x, side="right")
    if w < starts.shape[0] and starts[w] <= x:
        return w
    return -1


@njit(cache=True)
def _run(t, bid, ask, bar_close_ms, side, otype, price, sl_dist, tp_dist, expiry_ms, hold_ms,
         trail_long, trail_short, exit_long, exit_short, flat_ms, blk_start, blk_end, win_start, win_end, win_kind, win_far,
         day_start, max_per_day, max_orders_60s, min_step, pip_size, out_i, out_f, counters):
    """Tick loop. out_i[k] = bar, side, otype, live_tick, entry_tick, entry_t, exit_tick, exit_t, exit_reason, news_flags;
    out_f[k] = entry_px, sl0, tp, risk, exit_px, sl_exit, mfe_r, mae_r, r_gross. Returns the number of trades."""
    n_t = t.shape[0]
    n_b = bar_close_ms.shape[0]
    nf = flat_ms.shape[0]
    nb = blk_start.shape[0]
    nw = win_start.shape[0]
    nd = day_start.shape[0]
    k = 0
    free_from = 0            # first tick on which a new intent may go live (the tick an order / position ended on counts)
    ring = np.full(RING, np.int64(-(2 ** 62)))      # times of the last order events (entries going live, exits)
    rpos = 0
    cap_day = -1
    cap_count = 0
    for i in range(n_b):
        s = side[i]
        if s == 0:
            continue
        j = np.searchsorted(t, bar_close_ms[i])       # first tick at or after the decision bar's close
        if j >= n_t:
            counters[C_NO_TICK] += 1
            continue
        if j < free_from:
            counters[C_DROPPED_BUSY] += 1
            continue
        if not (sl_dist[i] > 0.0):
            counters[C_REFUSED_NO_STOP] += 1
            continue
        tl = t[j]
        if _inside(blk_start, blk_end, tl) >= 0 or _inside(win_start, win_end, tl) >= 0:
            counters[C_BLOCKED_ENTRY] += 1
            continue
        if max_per_day > 0 and nd > 0:
            d = np.searchsorted(day_start, tl, side="right") - 1
            if d == cap_day and cap_count >= max_per_day:
                counters[C_DAY_CAP] += 1
                continue
        if max_orders_60s > 0:
            recent = 0
            for q in range(RING):
                if ring[q] > tl - 60_000:
                    recent += 1
            if recent >= max_orders_60s:
                counters[C_ORDER_RATE] += 1
                continue
        live_tick = j
        ot = otype[i]
        if ot != MARKET and _crossed(ot, s, bid[j], ask[j], price[i]):
            counters[C_REFUSED_CROSSED] += 1
            continue
        ring[rpos % RING] = tl
        rpos += 1
        # pending order end: expiry, or the next decision bar's close
        if ot == MARKET:
            end_ms = tl
        elif expiry_ms[i] > 0.0:
            end_ms = tl + np.int64(expiry_ms[i])
        else:
            end_ms = bar_close_ms[i + 1] if i + 1 < n_b else t[n_t - 1] + 1
        f = np.searchsorted(flat_ms, tl)                      # first flat time at or after going live
        bs = np.searchsorted(blk_start, tl, side="right")     # next entry block starting after going live
        ws = np.searchsorted(win_start, tl, side="right")     # next news window starting after going live
        # ---- wait for the fill (the live tick itself cannot fill a pending order: the level is not crossed there)
        filled = -1
        if ot == MARKET:
            filled = j
        else:
            j += 1
            while j < n_t:
                tj = t[j]
                if _crossed(ot, s, bid[j], ask[j], price[i]):
                    filled = j
                    break
                if f < nf and tj >= flat_ms[f]:
                    counters[C_CANCELLED_FLAT] += 1
                    break
                if (bs < nb and tj >= blk_start[bs]) or (ws < nw and tj >= win_start[ws]):
                    counters[C_CANCELLED_BLOCK] += 1
                    break
                if tj >= end_ms:
                    counters[C_EXPIRED] += 1
                    break
                j += 1
            if filled < 0:
                free_from = j if j < n_t else n_t      # a new intent may go live on the tick that ended this order
                continue
        j = filled
        if max_per_day > 0 and nd > 0:
            d = np.searchsorted(day_start, t[j], side="right") - 1
            if d != cap_day:
                cap_day = d
                cap_count = 0
            cap_count += 1
        entry = ask[j] if s > 0 else bid[j]
        risk = sl_dist[i]
        d_sl = risk
        d_tp = tp_dist[i]
        if pip_size > 0.0:                    # cTrader stores entry +- (distance / PipSize) * PipSize in raw doubles (referees 2026-11-12)
            d_sl = (risk / pip_size) * pip_size
            d_tp = (d_tp / pip_size) * pip_size
        sl = entry - d_sl if s > 0 else entry + d_sl
        tp = np.nan
        if tp_dist[i] > 0.0:
            tp = entry + d_tp if s > 0 else entry - d_tp
        sl_first = sl
        t_exit_time = np.int64(-1)
        if hold_ms[i] > 0.0:
            t_exit_time = t[j] + np.int64(hold_ms[i])
        b = np.searchsorted(bar_close_ms, t[j], side="right")    # bar-close events: first bar whose close is after the fill
        w = np.searchsorted(win_end, t[j], side="right")         # first news window not over at the fill
        in_win = False
        tp_saved = np.nan
        deferred = 0
        flags = 0
        trailed = False
        best = 0.0
        worst = 0.0
        reason = 6
        exit_px = bid[n_t - 1] if s > 0 else ask[n_t - 1]
        ex = n_t - 1
        while j < n_t:
            tj = t[j]
            px = bid[j] if s > 0 else ask[j]
            mv = (px - entry) * s / risk
            if mv > best:
                best = mv
            if mv < worst:
                worst = mv
            # 1. order engine: stop, then target
            if (s > 0 and px <= sl) or (s < 0 and px >= sl):
                reason = 7 if trailed else 1
                exit_px, ex = px, j
                break
            if tp == tp and ((s > 0 and px >= tp) or (s < 0 and px <= tp)):
                reason, exit_px, ex = 2, px, j
                break
            # 2. housekeeping: flat time, news window end / start, time exit
            if f < nf and tj >= flat_ms[f]:
                reason, exit_px, ex = 5, px, j
                break
            if in_win and tj >= win_end[w]:
                in_win = False
                w += 1
                if tp_saved == tp_saved:
                    if (s > 0 and px >= tp_saved) or (s < 0 and px <= tp_saved):
                        reason, exit_px, ex = 9, px, j
                        flags |= 4
                        break
                    tp = tp_saved
                    tp_saved = np.nan
                if deferred > 0:
                    reason, exit_px, ex = deferred, px, j
                    break
            if not in_win:
                while w < nw and win_end[w] <= tj:          # windows with no tick inside: nothing to do
                    w += 1
                if w < nw and tj >= win_start[w]:
                    exempt = win_kind[w] == 2
                    if win_kind[w] == 1:
                        far = win_far[w]
                        if far == far and ((s > 0 and px - sl > far) or (s < 0 and sl - px > far)):
                            exempt = True
                            flags |= 2
                            counters[C_FAR_STOP] += 1
                    if not exempt:
                        counters[C_NEWS_FLAT] += 1
                        flags |= 4
                        reason, exit_px, ex = 8, px, j
                        break
                    if win_kind[w] == 2:
                        flags |= 1
                        counters[C_NEWS_HELD] += 1
                    in_win = True
                    tp_saved = tp
                    tp = np.nan
            if t_exit_time >= 0 and tj >= t_exit_time:
                if in_win:
                    if deferred == 0:
                        deferred = 3
                else:
                    reason, exit_px, ex = 3, px, j
                    break
            # 3. bar closes passed by this tick (oldest first): trail (paused in a news window), then exit signal
            done = False
            while b < n_b and bar_close_ms[b] <= tj:
                if s > 0:
                    if not in_win and trail_long[b] == trail_long[b] and trail_long[b] > sl + min_step:
                        sl = trail_long[b]
                        trailed = True
                        if px <= sl:
                            reason, exit_px, ex, done = 7, px, j, True
                    if not done and exit_long[b]:
                        if in_win:
                            if deferred == 0:
                                deferred = 4
                        else:
                            reason, exit_px, ex, done = 4, px, j, True
                else:
                    if not in_win and trail_short[b] == trail_short[b] and trail_short[b] < sl - min_step:
                        sl = trail_short[b]
                        trailed = True
                        if px >= sl:
                            reason, exit_px, ex, done = 7, px, j, True
                    if not done and exit_short[b]:
                        if in_win:
                            if deferred == 0:
                                deferred = 4
                        else:
                            reason, exit_px, ex, done = 4, px, j, True
                b += 1
                if done:
                    break
            if done:
                break
            j += 1
        out_i[k, 0] = i
        out_i[k, 1] = s
        out_i[k, 2] = ot
        out_i[k, 3] = live_tick
        out_i[k, 4] = filled
        out_i[k, 5] = t[filled]
        out_i[k, 6] = ex
        out_i[k, 7] = t[ex]
        out_i[k, 8] = reason
        out_i[k, 9] = flags
        out_f[k, 0] = entry
        out_f[k, 1] = sl_first
        out_f[k, 2] = tp if tp == tp else tp_saved
        out_f[k, 3] = risk
        out_f[k, 4] = exit_px
        out_f[k, 5] = sl
        out_f[k, 6] = best
        out_f[k, 7] = worst
        out_f[k, 8] = (exit_px - entry) * s / risk
        k += 1
        if reason != 6:
            ring[rpos % RING] = t[ex]
            rpos += 1
        free_from = ex if reason != 6 else n_t
    return k


def _arr(x, n, dtype, fill):
    if x is None:
        return np.full(n, fill, dtype=dtype)
    a = np.ascontiguousarray(x, dtype=dtype)
    if a.shape != (n,):
        raise ValueError(f"intent array has shape {a.shape}, expected ({n},)")
    return a


def _intervals(starts, ends, name):
    s = np.ascontiguousarray(np.asarray([] if starts is None else starts, dtype=np.int64))
    e = np.ascontiguousarray(np.asarray([] if ends is None else ends, dtype=np.int64))
    if s.shape != e.shape:
        raise ValueError(f"{name}: starts and ends differ in length")
    if len(s) and (np.any(e <= s) or np.any(s[1:] < e[:-1])):
        raise ValueError(f"{name}: intervals must be non-empty, sorted and non-overlapping (merge them in the rules layer)")
    return s, e


def run(t, bid, ask, bar_close_ms, side, otype=None, price=None, sl_dist=None, tp_dist=None, expiry_ms=None,
        hold_ms=None, trail_long=None, trail_short=None, exit_long=None, exit_short=None, flat_ms=None, min_step=0.0, pip_size=0.0,
        blk_start=None, blk_end=None, win_start=None, win_end=None, win_kind=None, win_far=None, day_start=None, max_per_day=0,
        max_orders_60s=0):
    """Simulate one strategy on one symbol. Ticks must be fill-ready (crossed ticks handled by the loader).
    Returns (trades: dict of arrays, counters: dict)."""
    t = np.ascontiguousarray(t, dtype=np.int64)
    bid = np.ascontiguousarray(bid, dtype=np.float64)
    ask = np.ascontiguousarray(ask, dtype=np.float64)
    bar_close_ms = np.ascontiguousarray(bar_close_ms, dtype=np.int64)
    n = len(bar_close_ms)
    if len(t) and np.any(np.diff(t) < 0):
        raise ValueError("tick times run backwards")
    if n and np.any(np.diff(bar_close_ms) <= 0):
        raise ValueError("bar closes must increase")
    side = _arr(side, n, np.int64, 0)
    args = (side, _arr(otype, n, np.int64, MARKET), _arr(price, n, np.float64, np.nan),
            _arr(sl_dist, n, np.float64, np.nan), _arr(tp_dist, n, np.float64, np.nan),
            _arr(expiry_ms, n, np.float64, np.nan), _arr(hold_ms, n, np.float64, np.nan),
            _arr(trail_long, n, np.float64, np.nan), _arr(trail_short, n, np.float64, np.nan),
            _arr(exit_long, n, np.bool_, False), _arr(exit_short, n, np.bool_, False))
    flat = np.ascontiguousarray(np.sort(np.asarray([] if flat_ms is None else flat_ms, dtype=np.int64)))
    bs, be = _intervals(blk_start, blk_end, "entry blocks")
    ws, we = _intervals(win_start, win_end, "news windows")
    nw = len(ws)
    wk = _arr(win_kind, nw, np.int64, 1)
    wf = _arr(win_far, nw, np.float64, np.nan)
    if nw and not np.all((wk == 1) | (wk == 2)):
        raise ValueError("win_kind must be 1 (flatten) or 2 (hold without target)")
    ds = np.ascontiguousarray(np.asarray([] if day_start is None else day_start, dtype=np.int64))
    if int(max_orders_60s) > RING:
        raise ValueError(f"max_orders_60s above {RING}")
    m = int((side != 0).sum())
    out_i = np.zeros((max(m, 1), 10), dtype=np.int64)
    out_f = np.zeros((max(m, 1), 9), dtype=np.float64)
    counters = np.zeros(len(COUNTER_NAMES), dtype=np.int64)
    k = _run(t, bid, ask, bar_close_ms, *args, flat, bs, be, ws, we, wk, wf, ds, int(max_per_day), int(max_orders_60s),
             float(min_step), float(pip_size), out_i, out_f, counters)
    oi, of = out_i[:k], out_f[:k]
    trades = {"bar": oi[:, 0], "side": oi[:, 1], "otype": oi[:, 2], "live_tick": oi[:, 3], "entry_tick": oi[:, 4],
              "entry_t": oi[:, 5], "exit_tick": oi[:, 6], "exit_t": oi[:, 7], "exit_reason": oi[:, 8], "news_flags": oi[:, 9],
              "entry_px": of[:, 0], "sl0": of[:, 1], "tp": of[:, 2], "risk": of[:, 3], "exit_px": of[:, 4],
              "sl_exit": of[:, 5], "mfe_r": of[:, 6], "mae_r": of[:, 7], "r_gross": of[:, 8]}
    return trades, dict(zip(COUNTER_NAMES, (int(c) for c in counters)))


def bar_closes(open_ms, tf_ms):
    """Close time of each bar = open + timeframe (the decision moment)."""
    return np.asarray(open_ms, dtype=np.int64) + np.int64(tf_ms)
