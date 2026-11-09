"""Numba replica of VwapMeanReversionBot.cs in a cTrader "m1 bars from server" backtest.

The kernel replays the exact tick stream cTrader produced (FastBtExport.cs): one tick per m1 bar (its open), on which the
cBot runs, plus the m1 high/low on which cTrader's order engine also fills SL/TP. Entries fill at the tick that opens the
next chart bar. Swap, stop-out and SL/TP placement follow the rules fitted on the archives (RULES.md, section A).

Inputs are arrays: one parameter vector per pass (P_* indices, built by pass_vector from the archive's parameter values),
one symbol vector (S_* indices), the chart bars with the VWAP state of the pass's mode (vwap_segments), the ticks.
run_batch runs many passes in parallel and returns per-pass statistics (ST_* columns: everything split_plateau needs)
and, on request, the trade lists.

Supported: Session / Weekly / Intraday Dual VWAP, Fixed TP (+ break-even), R-step 1-4, VWAP band trails 5-6, Bar Close
timing, entry filters (distance, penetration, ATR percentile), hedging, Track Touches During Blocked Candles, Source Close,
FixedCashRisk sizing, news filter (calendar read from the cBot). Not (yet): day block windows, Tick timing (pass_vector
refuses them).
Checked against cTrader (REPORT.md): US30 Session Fixed TP 22,384 / 22,400 passes identical, Rstep 16,781 / 16,800.
"""
import math
import os

os.environ.setdefault("NUMBA_CACHE_DIR", os.path.expanduser("~/.cache/fastbt-numba"))
import numpy as np  # noqa: E402
from numba import njit, prange  # noqa: E402

DAY_MS = 86400000
MIN_MS = 60000
NY_TC_MS = 6 * 3600 * 1000           # trading clock = New York + 6 h
SESSION_CLOSE_MIN = 23 * 60          # 17:00 NY on the trading clock
ETH_END_MIN = 930                    # 09:30 NY cash open
RTH_MIN = SESSION_CLOSE_MIN - ETH_END_MIN
FORCE_LEAD_MIN = 10                  # ForceCloseLeadMinutes
CLOSE_LEAD_100NS = 10 * 60 * 10_000_000

EV_SL, EV_TP, EV_CLOSE = 1, 2, 3
EVENT_NAMES = {EV_SL: "Stop Loss Hit", EV_TP: "Take Profit Hit", EV_CLOSE: "Position closed"}
MODE_WEEKLY, MODE_SESSION, MODE_DUAL = 0, 1, 2

# pass parameter vector
(P_MODE, P_BAND_A, P_BAND_B, P_SRC, P_STOP, P_TP, P_MGMT, P_TRIGGER, P_CUSHION, P_BE, P_BE_R,
 P_FIRST_A, P_LAST_A, P_FIRST_B, P_LAST_B, P_CLOSE_DAY, P_CLOSE_ETH, P_CLOSE_FRI, P_HEDGE, P_TRACK,
 P_DIST_ON, P_DIST, P_PEN_ON, P_PEN, P_PEN_CLOSE, P_PCT_ON, P_PCT_MAX, P_PCT_LOOKBACK,
 P_NEWS, P_NEWS_BEFORE, P_NEWS_AFTER, P_NEWS_CLOSE, P_NEWS_TRACK) = range(33)
NP = 33

# symbol and run constants
(S_PIP, S_TICK, S_PIPDEC, S_SPREAD, S_DIGITS, S_VSTEP, S_VMIN, S_VMAX, S_ROLLMIN, S_TRIPLE, S_SWAPL, S_SWAPS,
 S_START, S_RISK, S_SAFETY, S_HLORDER, S_ATRLEN, S_PCTLEN, S_ROLLMODE, S_COMM, S_COMMMODE, S_CONVSELF) = range(22)
NS = 22

# per-pass statistics (stats-only mode). Net, wins, DD are on the TP-capped trades for Fixed TP (tools/tp_cap.py rule),
# raw net is kept as well. Years by close time (UTC), halves and news days by entry date in New York (as split_plateau).
FIRST_YEAR, NYEARS, HALF_SPLIT = 2018, 6, 2021
(ST_TRADES, ST_NET, ST_GW, ST_GL, ST_WINS, ST_DD, ST_EQDD, ST_TOP5, ST_NEWS, ST_SWAP, ST_LONG, ST_SHORT, ST_NET_RAW,
 ST_FIRST, ST_LAST, ST_OVERFLOW, ST_STOPOUT, ST_OUTSIDE) = range(18)
ST_YEAR = 18                         # NYEARS columns: net per close year
ST_YEAR_N = ST_YEAR + NYEARS         # NYEARS columns: trades per close year
ST_H1 = ST_YEAR_N + NYEARS           # n, net, gross win, gross loss, top-k sum for entries 2018-2020
ST_H2 = ST_H1 + 5                    # the same for 2021-2023
ST_COMM = ST_H2 + 5                  # commission (both sides, negative)
NST = ST_COMM + 1
STAT_NAMES = (["trades", "net", "gross_win", "gross_loss", "wins", "dd", "eq_dd", "top5", "news_net", "swap", "long_net",
               "short_net", "net_raw", "first_close_ms", "last_close_ms", "overflow", "stopped_out", "outside_years"]
              + [f"net_{FIRST_YEAR + y}" for y in range(NYEARS)] + [f"n_{FIRST_YEAR + y}" for y in range(NYEARS)]
              + [f"{h}_{c}" for h in ("h1", "h2") for c in ("n", "net", "gross_win", "gross_loss", "top")] + ["commission"])


@njit(cache=True)
def vwap_segments(tc_open, src, vol, mode):
    """VWAP state after each bar for the mode's band (UpdateVwapsForClosedBar + VwapState): vwap, deviation, valid,
    segment. Session resets at each TC date, Weekly at the TC Monday, Intraday Dual keeps two accumulators (segment 0 =
    ETH before 15:30 TC, 1 = RTH), each reset at a new TC date; a bar's values are those of its own segment."""
    n = len(src)
    vwap = np.empty(n)
    dev = np.empty(n)
    valid = np.zeros(n, dtype=np.bool_)
    seg = np.zeros(n, dtype=np.int64)
    w = np.zeros(2)
    wv = np.zeros(2)
    wv2 = np.zeros(2)
    last = np.full(2, -10**12, dtype=np.int64)
    for i in range(n):
        day = tc_open[i] // DAY_MS
        s = 0
        key = day
        if mode == MODE_WEEKLY:
            key = day - (day + 3) % 7                  # WeekStart: Monday of the TC date
        elif mode == MODE_DUAL and (tc_open[i] % DAY_MS) // MIN_MS >= ETH_END_MIN:
            s = 1
        seg[i] = s
        if key != last[s]:
            w[s] = 0.0
            wv[s] = 0.0
            wv2[s] = 0.0
            last[s] = key
        v = vol[i] if vol[i] > 0.0 else 0.0
        if v > 0.0:
            x = src[i]
            w[s] += v
            wv[s] += x * v
            wv2[s] += x * x * v
        if w[s] > 0.0:
            m = wv[s] / w[s]
            var = wv2[s] / w[s] - m * m
            if var < 0.0:
                var = 0.0
            vwap[i] = m
            dev[i] = math.sqrt(var)
            valid[i] = True
        else:
            vwap[i] = np.nan
            dev[i] = np.nan
    return vwap, dev, valid, seg


@njit(cache=True)
def round_digits(x, digits):
    """Math.Round(x, digits) of .NET (scale, round half to even, unscale)."""
    f = 10.0 ** digits
    return np.rint(x * f) / f


@njit(cache=True)
def tp_cap_gross(gross, side, entry, exit_px, sl0, target_r, tick_size):
    """Fixed TP on m1 bars: cTrader fills a take-profit at the first simulated price beyond the target, the tick fill is at the
    target. A fill beyond the target is cut back to the target = TargetR x the trade's OWN stop distance (|entry - initial SL|),
    i.e. TargetR x the trade's own risk (stop distance x USD per point x volume). Until 2026-10-29 this was TargetR x
    FixedCashRisk ($1,000), which is wrong wherever the volume cap or volume rounding makes the own risk differ from $1,000
    (JP225: volume_max binds on ~92% of the trades, median own risk $403-616; US2000 4-6%; US30 up to 5%). Fills within half a
    tick of the target (entry is the rounded fill, the TP sits around the unrounded one) are left alone."""
    mv = (exit_px - entry) * side
    d_tp = target_r * abs(entry - sl0)
    if mv > d_tp + 0.5 * tick_size and mv > 0.0:
        return round_cents(gross * d_tp / mv)
    return gross


@njit(cache=True)
def round_cents(x):
    """Money rounding of cTrader: to cents, half away from zero (archive: 5 lots x 13.937 = 69.685 -> 69.69 per night)."""
    if x >= 0.0:
        return math.floor(x * 100.0 + 0.5 + 1e-7) / 100.0
    return -math.floor(-x * 100.0 + 0.5 + 1e-7) / 100.0


@njit(cache=True)
def next_rollover(after_ms, roll_min):
    """First Monday-Friday rollover (roll_min UTC) strictly after after_ms."""
    d = after_ms // DAY_MS
    while True:
        r = d * DAY_MS + roll_min * MIN_MS
        if r > after_ms and (d + 3) % 7 < 5:
            return r
        d += 1


@njit(cache=True)
def global_pointer(t_ms, roll_min):
    """Rollover pointer of an account that works through one rollover per tick on every tick: its value after each tick."""
    out = np.empty(len(t_ms), dtype=np.int64)
    if len(t_ms) == 0:
        return out
    ptr = next_rollover(t_ms[0] - 1, roll_min)
    for k in range(len(t_ms)):
        if ptr <= t_ms[k]:
            ptr = next_rollover(ptr, roll_min)
        out[k] = ptr
    return out


@njit(cache=True)
def next_boundary(from_tc, close_day, close_eth, close_fri):
    """First force-close boundary strictly after from_tc (ForceCloseDue / CrossedBoundary): 22:50 TC every day (Session
    close / RTH close), 15:20 TC every day (ETH close), 22:50 TC on Fridays."""
    best = np.int64(9223372036854775807)
    d = from_tc // DAY_MS
    for dd in range(8):
        day = (d + dd) * DAY_MS
        wd = (d + dd + 3) % 7
        if close_eth:
            b = day + (ETH_END_MIN - FORCE_LEAD_MIN) * MIN_MS
            if b > from_tc and b < best:
                best = b
        if close_day or (close_fri and wd == 4):
            b = day + (SESSION_CLOSE_MIN - FORCE_LEAD_MIN) * MIN_MS
            if b > from_tc and b < best:
                best = b
    return best


@njit(cache=True)
def level_hit(pos, px, sl, tp):
    """SL/TP test of one price (bid for longs, ask for shorts)."""
    if pos > 0:
        if px <= sl:
            return EV_SL
        if px >= tp:
            return EV_TP
    else:
        if px >= sl:
            return EV_SL
        if px <= tp:
            return EV_TP
    return 0


@njit(cache=True)
def hl_exit(pos, sl, tp, o, h, l, c, spread, hl_order):
    """SL/TP on the in-bar high and low of one m1 bar (bid prices; shorts use ask = bid + spread, unrounded like cTrader).
    hl_order: 0 = bullish bar low first / bearish bar high first, 1 = high first, 2 = low first,
    3 = the one nearer the open first, 4 = the stop's side first (cTrader, RULES A17: a minute that reaches both stop and
    target fills the stop: 21 of 21 cases)."""
    high_first = True
    if hl_order == 0:
        high_first = c < o
    elif hl_order == 2:
        high_first = False
    elif hl_order == 3:
        high_first = (h - o) <= (o - l)
    elif hl_order == 4:
        high_first = pos < 0
    for step in range(2):
        p = h if (step == 0) == high_first else l
        px = p if pos > 0 else p + spread
        ev = level_hit(pos, px, sl, tp)
        if ev != 0:
            return ev, px
    return 0, 0.0


@njit(cache=True)
def commission(vol, rate, comm, mode):
    """cTrader "USD per million USD volume", both sides charged at the close: vol x (base currency -> USD) x comm / 1e6
    per side, each side rounded to the cent, the rate truncated to 2 decimals like AssetConverter (RULES A16). mode 1:
    the base is USD (rate 1); 2: the rate is the symbol's own bid (EURUSD, XAUUSD); 3: a cross, the bid of the base's own
    USD pair (EURUSD for EURGBP, from its export); 0: a cross without that export (base price x quote->USD)."""
    if comm == 0.0:
        return 0.0
    r = 1.0 if mode == 1 else math.floor(rate * 100.0 + 1e-9) / 100.0
    return -2.0 * round_cents(vol * r * comm * 1e-6)


@njit(cache=True)
def _record(o_i, o_f, ntr, t_open, t_close, side, ev, how, ek, entry, px, vol, sl0, swap, gross, com):
    o_i[ntr, 0] = t_open
    o_i[ntr, 1] = t_close
    o_i[ntr, 2] = side
    o_i[ntr, 3] = ev
    o_i[ntr, 4] = how
    o_i[ntr, 5] = ek
    o_f[ntr, 0] = entry
    o_f[ntr, 1] = px
    o_f[ntr, 2] = vol
    o_f[ntr, 3] = sl0
    o_f[ntr, 4] = swap
    o_f[ntr, 5] = gross
    o_f[ntr, 6] = com


@njit(cache=True)
def _schedule_ok(mode, minute, tc, seg, src_sel, first_a, last_a, first_b, last_b):
    """ScheduleAllows (lines 901-922, 948-955); day block windows are not supported."""
    if mode == MODE_SESSION:
        return minute >= first_a and minute < SESSION_CLOSE_MIN - last_a
    if mode == MODE_WEEKLY:
        d = tc // DAY_MS
        wk_open = (d - (d + 3) % 7) * DAY_MS
        wk_close = wk_open + 4 * DAY_MS + SESSION_CLOSE_MIN * MIN_MS
        if first_a > 0 and tc >= wk_open and tc < wk_open + first_a * MIN_MS:
            return False
        if last_a > 0 and tc >= wk_close - last_a * MIN_MS and tc < wk_close:
            return False
        return True
    if seg == 0 and src_sel == 2:
        return True                                    # RTH only: ETH candles can only re-arm
    if seg == 1 and src_sel == 1:
        return True
    if seg == 0:
        return minute >= first_a and minute < ETH_END_MIN - last_a
    within = minute - ETH_END_MIN
    return within >= first_b and within < RTH_MIN - last_b


@njit(cache=True)
def _period_end(mode, bar_tc, seg):
    """VwapPeriodEnd: end of the VWAP period (week, session, ETH/RTH segment) the signal candle belongs to."""
    d = bar_tc // DAY_MS
    if mode == MODE_WEEKLY:
        return (d - (d + 3) % 7) * DAY_MS + 4 * DAY_MS + SESSION_CLOSE_MIN * MIN_MS
    if mode == MODE_DUAL and seg == 0:
        return d * DAY_MS + ETH_END_MIN * MIN_MS
    return d * DAY_MS + SESSION_CLOSE_MIN * MIN_MS


@njit(cache=True)
def _window_active(minute, wd, close_day, close_eth, close_fri):
    """ForceCloseWindowActive: the 10-minute windows before 17:00 NY (daily or Friday) and before 09:30 NY (ETH close)."""
    if (close_day or (close_fri and wd == 4)) and minute >= SESSION_CLOSE_MIN - FORCE_LEAD_MIN and minute < SESSION_CLOSE_MIN:
        return True
    return close_eth and minute >= ETH_END_MIN - FORCE_LEAD_MIN and minute < ETH_END_MIN


@njit(cache=True)
def run_kernel(p, s, b_tc_open, b_high, b_low, b_close, b_atr, b_patr, b_vwap, b_dev, b_valid, b_seg, b_close_tick,
               first_bar, b_span, t_ms, t_tc, bid, ask, ttc, m1_high, m1_low, m1_close, pv, uv, br, gptr, ev_t, ev_d, o_i, o_f,
               o_eq):
    """One pass. p: pass vector (P_*), s: symbol vector (S_*). pv / uv: pip value and value of a 1.0 price move per unit
    of volume in account currency at each tick. Writes the trades to o_i (open ms, close ms, side, event, how, entry tick)
    and o_f (entry, exit, volume, initial SL, swap, gross, commission) and returns their number; o_eq = [max equity drawdown,
    trade buffer full, stopped out]."""
    mode = int(p[P_MODE])
    band_a = p[P_BAND_A]
    band_b = p[P_BAND_B]
    src_sel = int(p[P_SRC])
    stop_mult = p[P_STOP]
    target_r = p[P_TP]
    mgmt = int(p[P_MGMT])
    trigger_close = p[P_TRIGGER] > 0.5
    cushion_mult = p[P_CUSHION]
    be_on = p[P_BE] > 0.5 and mgmt == 0
    be_r = p[P_BE_R]
    first_a = int(p[P_FIRST_A])
    last_a = int(p[P_LAST_A])
    first_b = int(p[P_FIRST_B])
    last_b = int(p[P_LAST_B])
    close_day = p[P_CLOSE_DAY] > 0.5
    close_eth = p[P_CLOSE_ETH] > 0.5
    close_fri = p[P_CLOSE_FRI] > 0.5
    hedge = p[P_HEDGE] > 0.5
    track = p[P_TRACK] > 0.5
    dist_on = p[P_DIST_ON] > 0.5
    dist_max = p[P_DIST]
    pen_on = p[P_PEN_ON] > 0.5
    pen_max = p[P_PEN]
    pen_close = p[P_PEN_CLOSE] > 0.5
    pct_on = p[P_PCT_ON] > 0.5
    pct_max = p[P_PCT_MAX]
    lookback = int(p[P_PCT_LOOKBACK])
    news = int(p[P_NEWS])                    # 0 off, 1 block entries, 2 block entries + close trades
    news_before = int(p[P_NEWS_BEFORE]) * MIN_MS
    news_after = int(p[P_NEWS_AFTER]) * MIN_MS
    news_close_before = int(p[P_NEWS_CLOSE]) * MIN_MS
    news_track = p[P_NEWS_TRACK] > 0.5
    ev_maxd = 0
    for z in range(len(ev_d)):
        if ev_d[z] > ev_maxd:
            ev_maxd = ev_d[z]

    pip_size = s[S_PIP]
    tick_size = s[S_TICK]
    pip_dec = int(s[S_PIPDEC])
    spread_px = s[S_SPREAD]
    digits = int(s[S_DIGITS])
    p10 = 10.0 ** digits
    vol_step = s[S_VSTEP]
    vol_min = s[S_VMIN]
    vol_max = s[S_VMAX]
    roll_min = int(s[S_ROLLMIN])
    roll_global = s[S_ROLLMODE] > 0.5
    comm = s[S_COMM]
    comm_mode = int(s[S_COMMMODE])
    conv_self = s[S_CONVSELF] > 0.5
    triple_wd = int(s[S_TRIPLE])
    swap_long = s[S_SWAPL]
    swap_short = s[S_SWAPS]
    risk_cash = s[S_RISK]
    safety_net = s[S_SAFETY] > 0.5
    hl_order = int(s[S_HLORDER])
    atr_len = int(s[S_ATRLEN])
    pct_len = int(s[S_PCTLEN])
    req_idx = max(atr_len, lookback + pct_len) if pct_on else atr_len

    # trade management (cBot lines 447-451): R-step step / gap / activation in R
    trailing = mgmt >= 1
    trail_step = 1.0 if mgmt == 3 else 0.5
    trail_gap = 0.5 if mgmt == 2 else 1.0
    trail_act = 1.0 if mgmt == 4 else trail_step

    # position slots: 0 = long, 1 = short (without hedging only one is open at a time)
    act = np.zeros(2, dtype=np.bool_)
    side = np.zeros(2, dtype=np.int64)
    entry = np.zeros(2)
    sl = np.zeros(2)
    tp = np.zeros(2)
    vol = np.zeros(2)
    risk_d = np.zeros(2)
    sl0 = np.zeros(2)
    ostop = np.zeros(2)
    swp = np.zeros(2)
    cme = np.zeros(2)                        # commission of the open position as estimated at entry (equity only)
    ek = np.zeros(2, dtype=np.int64)
    fcb = np.zeros(2, dtype=np.int64)
    ncb = np.zeros(2, dtype=np.int64)
    stage = np.zeros(2, dtype=np.int64)
    be_done = np.zeros(2, dtype=np.bool_)
    tseg = np.zeros(2, dtype=np.int64)
    evs = np.zeros(2, dtype=np.int64)
    pxs = np.zeros(2)
    hows = np.zeros(2, dtype=np.int64)

    n = len(b_low)
    max_tr = o_i.shape[0]
    lower_armed = True
    upper_armed = True
    last_exit = np.int64(-10**15)
    k_done = -1
    ntr = 0
    bal = s[S_START]
    eq_peak = bal
    eq_dd = 0.0
    o_eq[0] = 0.0
    o_eq[1] = 0.0
    o_eq[2] = 0.0
    next_roll = np.int64(-1)                 # rollover pointer: starts at the pass's first entry (see the tick loop)
    nt = len(t_ms)
    for i in range(first_bar, n + 1):
        if i < n:
            kc = b_close_tick[i]
            if kc < 0:
                continue
        else:
            kc = nt - 1                                # after the last bar close: open positions run to the last tick
        # --- open positions, up to and including the bar-closing tick. cTrader's m1-bar mode calls the cBot only on each
        # m1 open (one tick per m1 bar), but its order engine also checks that bar's high and low for SL/TP and fills at
        # that price, stamped at the next tick (archive: SL at 17:30 = high of the 17:29 bar).
        # Order of events when tick k arrives (fitted on the archive, RULES.md A10/A8):
        #   1. SL/TP on the in-bar high/low of m1 bar k-1, stamped at tick k
        #   2. SL/TP on tick k's price
        #   3. swap: at most ONE rollover (21:00 UTC, Mon-Fri, triple day) is processed per tick
        #   4. the cBot (OnBarClosed, OnTick): force closes, then bar-close management and entries
        if act[0] or act[1]:
            k = k_done + 1
            while k <= kc:
                j = k - 1
                # equity at the in-bar adverse extreme (max equity drawdown statistic)
                eq = bal
                for q in range(2):
                    if act[q]:
                        adv = m1_low[j] if side[q] > 0 else m1_high[j] + spread_px
                        eq += (adv - entry[q]) * side[q] * vol[q] * uv[k] + swp[q] + cme[q]
                if eq_peak - eq > eq_dd:
                    eq_dd = eq_peak - eq
                open_eq = 0.0
                for q in range(2):
                    evs[q] = 0
                    if not act[q]:
                        continue
                    ev, px = hl_exit(side[q], sl[q], tp[q], bid[j], m1_high[j], m1_low[j], m1_close[j], spread_px, hl_order)
                    how = 1
                    if ev == 0:
                        how = 0
                        px = bid[k] if side[q] > 0 else ask[k]
                        ev = level_hit(side[q], px, sl[q], tp[q])
                        if ev == 0:
                            open_eq += (px - entry[q]) * side[q] * vol[q] * uv[k] + swp[q] + cme[q]
                    evs[q] = ev
                    pxs[q] = px
                    hows[q] = how
                # stop-out: cTrader ends the backtest once equity at a tick price reaches zero (the in-bar high/low does
                # not count); that last position is closed by a "Stop Out" event, which the archive does not keep
                if (evs[0] == 0 and act[0]) or (evs[1] == 0 and act[1]):
                    if bal + open_eq <= 0.0:
                        o_eq[0] = eq_dd
                        o_eq[2] = 1.0
                        return ntr
                # one rollover per tick from a pointer that starts at the first rollover after the pass's first entry and
                # moves only on ticks that began with a position open (also when SL/TP closes it on this tick, then without
                # a charge). A pass that was flat for long therefore works through old rollovers first and can miss a fresh
                # one (fitted on 2.94 M rollover-spanning trades of the US30 Session Fixed TP + Rstep grids: e.g. passes
                # 11136 vs 11159 on 3 Jul 2020)
                if next_roll <= t_ms[k]:
                    for q in range(2):
                        if act[q] and evs[q] == 0 and t_ms[ek[q]] < next_roll:
                            wdr = (next_roll // DAY_MS + 3) % 7
                            # converted like the P&L (EURGBP maps: GBPUSD bid at the rollover tick, 99.8% exact)
                            rate = (swap_long if side[q] > 0 else swap_short) * pip_size * uv[k]
                            swp[q] += round_cents(vol[q] * rate * (3.0 if wdr == triple_wd else 1.0))
                    next_roll = next_rollover(next_roll, roll_min)
                tc = t_tc[k]
                wd = (tc // DAY_MS + 3) % 7
                minute = (tc % DAY_MS) // MIN_MS
                for q in range(2):
                    if not act[q]:
                        continue
                    if evs[q] == 0:
                        if tc >= fcb[q] or tc >= ncb[q] or _window_active(minute, wd, close_day, close_eth, close_fri):
                            evs[q] = EV_CLOSE
                        elif (safety_net and (close_day or (close_fri and wd == 4)) and ttc[k] >= 0
                              and ttc[k] <= CLOSE_LEAD_100NS):
                            evs[q] = EV_CLOSE
                    if evs[q] != 0:
                        if ntr >= max_tr:
                            o_eq[0] = eq_dd
                            o_eq[1] = 1.0
                            return ntr
                        px = pxs[q]
                        # converted at this tick; a stop/target fill of a symbol that is its own conversion pair converts
                        # at the previous tick (the order engine fills before the tick updates the symbol, RULES A15)
                        kv = j if (conv_self and evs[q] != EV_CLOSE) else k
                        gross = round_cents((px - entry[q]) * side[q] * vol[q] * uv[kv])
                        # base -> USD: the symbol's own bid at the previous tick for a stop/target fill (the order engine
                        # fills before the tick updates the symbol), at this tick for a close by the cBot
                        kb = j if evs[q] != EV_CLOSE else k
                        com = commission(vol[q], bid[kb] if comm_mode == 2 else (br[k] if comm_mode == 3 else
                                                                                  0.5 * (bid[k] + ask[k]) * uv[k]), comm, comm_mode)
                        _record(o_i, o_f, ntr, t_ms[ek[q]], t_ms[k], side[q], evs[q], hows[q], ek[q], entry[q], px,
                                vol[q], sl0[q], swp[q], gross, com)
                        ntr += 1
                        act[q] = False
                        last_exit = t_ms[k]
                        bal += gross + swp[q] + com
                        if bal <= 0.0:
                            o_eq[0] = eq_dd
                            o_eq[2] = 1.0
                            return ntr                 # account at zero: cTrader stops the backtest
                eq = bal                               # equity at this tick's price after the closes
                for q in range(2):
                    if act[q]:
                        eq += (pxs[q] - entry[q]) * side[q] * vol[q] * uv[k] + swp[q] + cme[q]
                if eq > eq_peak:
                    eq_peak = eq
                if not (act[0] or act[1]):
                    break
                k += 1
        k_done = kc
        if i == n:
            break
        # --- ProcessClosedBar for bar i at tick kc: ManageVwapBandTrails, then ManageBarCloseProtection (cBot 558-700)
        for q in range(2):
            if not act[q]:
                continue
            isb = side[q] > 0
            new_sl = np.nan
            close_now = False
            if mgmt >= 5:
                # VWAP band trail on the trade's own VWAP (Intraday Dual: only while the bar is in that segment)
                if b_seg[i] != tseg[q] or not b_valid[i]:
                    continue
                atr_i = b_atr[i]
                if mgmt == 6 and not (atr_i > 0.0):
                    continue
                vw = b_vwap[i]
                dv = b_dev[i]
                tprice = b_close[i] if trigger_close else (b_high[i] if isb else b_low[i])
                st = stage[q]
                if isb:
                    if tprice >= vw - dv * 2.0:
                        st = max(st, 1)
                    if tprice >= vw - dv * 1.0:
                        st = max(st, 2)
                    if tprice >= vw:
                        st = max(st, 3)
                    if tprice >= vw + dv * 1.0:
                        st = max(st, 4)
                    if tprice >= vw + dv * 2.0:
                        st = max(st, 5)
                    if tprice >= vw + dv * 3.0:
                        st = max(st, 6)
                else:
                    if tprice <= vw + dv * 2.0:
                        st = max(st, 1)
                    if tprice <= vw + dv * 1.0:
                        st = max(st, 2)
                    if tprice <= vw:
                        st = max(st, 3)
                    if tprice <= vw - dv * 1.0:
                        st = max(st, 4)
                    if tprice <= vw - dv * 2.0:
                        st = max(st, 5)
                    if tprice <= vw - dv * 3.0:
                        st = max(st, 6)
                stage[q] = st
                if st == 0:
                    continue
                sgn = 1.0 if isb else -1.0
                if mgmt == 5:
                    # static ladder: entry, then the 2/1-band, VWAP, ... behind the price; only tightens
                    cush = atr_i * cushion_mult if cushion_mult > 0 else 0.0
                    if st == 1:
                        cand = entry[q]
                    elif st == 2:
                        cand = vw - sgn * dv * 2.0 - sgn * cush
                    elif st == 3:
                        cand = vw - sgn * dv * 1.0 - sgn * cush
                    elif st == 4:
                        cand = vw - sgn * cush
                    elif st == 5:
                        cand = vw + sgn * dv * 1.0 - sgn * cush
                    else:
                        cand = vw + sgn * dv * 2.0 - sgn * cush
                    tighten_only = True
                else:
                    # dynamic: follows the current band (may loosen), never beyond the original stop
                    if st == 1:
                        lvl = vw - sgn * dv * 3.0
                    elif st == 2:
                        lvl = vw - sgn * dv * 2.0
                    elif st == 3:
                        lvl = vw - sgn * dv * 1.0
                    elif st == 4:
                        lvl = vw
                    elif st == 5:
                        lvl = vw + sgn * dv * 1.0
                    else:
                        lvl = vw + sgn * dv * 2.0
                    cand = max(ostop[q], lvl - atr_i * cushion_mult) if isb else min(ostop[q], lvl + atr_i * cushion_mult)
                    tighten_only = False
                # ApplyVwapTrailStop with the bar's close as reference (Bar Close timing)
                cand = round_digits(np.rint(cand / tick_size) * tick_size, digits)
                improves = (cand > sl[q] + tick_size / 2) if isb else (cand < sl[q] - tick_size / 2)
                if tighten_only and not improves:
                    continue
                execut = (cand < bid[kc] - tick_size) if isb else (cand > ask[kc] + tick_size)
                valid_close = (cand < b_close[i] - tick_size) if isb else (cand > b_close[i] + tick_size)
                if not valid_close:
                    continue
                if not execut:
                    if not improves:
                        continue
                    close_now = True
                elif abs(cand - sl[q]) >= tick_size / 2:
                    new_sl = cand
            elif mgmt >= 1:
                # R-step (cBot 558-604): from the closed bar's high/low the stop moves to entry + (milestone - gap) R
                reached = ((b_high[i] - entry[q]) if isb else (entry[q] - b_low[i])) / risk_d[q]
                if reached < trail_act:
                    continue
                milestone = math.floor(reached / trail_step) * trail_step
                prop = entry[q] + (milestone - trail_gap) * risk_d[q] if isb else entry[q] - (milestone - trail_gap) * risk_d[q]
                cand = round_digits(np.rint(prop / tick_size) * tick_size, digits)
                if not ((cand > sl[q] + tick_size / 2) if isb else (cand < sl[q] - tick_size / 2)):
                    continue
                if (cand < bid[kc] - tick_size) if isb else (cand > ask[kc] + tick_size):
                    new_sl = cand
                else:
                    close_now = True
            elif be_on and not be_done[q]:
                # Fixed TP break-even: once the bar reached the trigger and closed beyond entry, stop to entry (TP kept)
                reached = ((b_high[i] - entry[q]) if isb else (entry[q] - b_low[i])) / risk_d[q]
                if reached < be_r:
                    continue
                if not ((entry[q] < b_close[i] - tick_size) if isb else (entry[q] > b_close[i] + tick_size)):
                    continue
                cand = round_digits(np.rint(entry[q] / tick_size) * tick_size, digits)
                if not ((cand > sl[q] + tick_size / 2) if isb else (cand < sl[q] - tick_size / 2)):
                    continue
                if (cand < bid[kc] - tick_size) if isb else (cand > ask[kc] + tick_size):
                    new_sl = cand
                    be_done[q] = True
                    # RULES A20: the target re-sent with the stop (position.TakeProfit, reported at the symbol's digits)
                    # is stored truncated too (EURUSD 10 Sep 2020: sent as 1.18942, stored 1.18941, filled at an m1 high
                    # of exactly 1.18941)
                    tp[q] = math.floor(round_digits(tp[q], digits) * p10) / p10
                else:
                    close_now = True
            if close_now:
                # the new stop is already beaten at this candle's open: closed at market on this tick
                if ntr >= max_tr:
                    o_eq[0] = eq_dd
                    o_eq[1] = 1.0
                    return ntr
                px = bid[kc] if isb else ask[kc]
                gross = round_cents((px - entry[q]) * side[q] * vol[q] * uv[kc])
                com = commission(vol[q], bid[kc] if comm_mode == 2 else (br[kc] if comm_mode == 3 else
                                                                         0.5 * (bid[kc] + ask[kc]) * uv[kc]), comm, comm_mode)
                _record(o_i, o_f, ntr, t_ms[ek[q]], t_ms[kc], side[q], EV_CLOSE, 2, ek[q], entry[q], px, vol[q], sl0[q],
                        swp[q], gross, com)
                ntr += 1
                act[q] = False
                bal += gross + swp[q] + com
                last_exit = t_ms[kc]
                if bal > eq_peak:
                    eq_peak = bal
                if bal <= 0.0:
                    o_eq[0] = eq_dd
                    o_eq[2] = 1.0
                    return ntr
            elif not math.isnan(new_sl):
                # RULES A20: cTrader stores a modified stop truncated to the symbol's digits, floor(price x 10^digits):
                # a stop whose double sits just below its decimal (33725.7 x 100 = 3372569.9999999995) ends a tick lower
                sl[q] = math.floor(new_sl * p10) / p10
        # --- signal on bar i
        bar_tc = b_tc_open[i]
        minute = (bar_tc % DAY_MS) // MIN_MS
        seg = b_seg[i]
        sched = _schedule_ok(mode, minute, bar_tc, seg, src_sel, first_a, last_a, first_b, last_b)
        news_blocked = False
        if news > 0:
            # NewsBlocksCandle: the candle [open, open + span] overlaps [release - before, release + duration + after)
            bar_end = bar_tc + b_span[i]
            z = np.searchsorted(ev_t, bar_tc - ev_maxd - news_after)
            while z < len(ev_t) and ev_t[z] <= bar_end + news_before:
                if bar_end >= ev_t[z] - news_before and bar_tc < ev_t[z] + ev_d[z] + news_after:
                    news_blocked = True
                    break
                z += 1
        if not ((sched or track) and (not news_blocked or news_track)):
            continue                                   # blocked candle, Track Touches = No: arm state untouched
        valid = b_valid[i]
        if mode == MODE_DUAL and ((seg == 0 and src_sel == 2) or (seg == 1 and src_sel == 1)):
            valid = False                              # the segment not selected has no band (re-arms only)
        mult = band_a if seg == 0 else band_b
        lower = b_vwap[i] - b_dev[i] * mult
        upper = b_vwap[i] + b_dev[i] * mult
        long_touch = valid and b_low[i] <= lower
        short_touch = valid and b_high[i] >= upper
        long_sig = long_touch and lower_armed
        short_sig = short_touch and upper_armed
        lower_armed = not long_touch
        upper_armed = not short_touch
        if not sched or news_blocked or not valid:
            continue
        if long_sig and short_sig:
            continue                                   # SkipBoth
        if not (long_sig or short_sig):
            continue
        now_tc = t_tc[kc]
        wd = (now_tc // DAY_MS + 3) % 7
        now_min = (now_tc % DAY_MS) // MIN_MS
        if _window_active(now_min, wd, close_day, close_eth, close_fri):
            continue                                   # ForceCloseWindowActive
        if now_tc >= _period_end(mode, bar_tc, seg):
            continue                                   # signal's VWAP period has ended
        if safety_net and (close_day or (close_fri and wd == 4)) and ttc[kc] >= 0 and ttc[kc] <= CLOSE_LEAD_100NS:
            continue                                   # BrokerCloseImminent
        if next_boundary(bar_tc, close_day, close_eth, close_fri) <= now_tc:
            continue                                   # ForceCloseDue(signal bar open, now)
        if t_ms[kc] <= last_exit + 1000:
            continue
        atr = b_atr[i]
        if not (i >= req_idx and atr > 0.0):
            continue                                   # AtrReadyForSignal
        q = 0 if long_sig else 1
        if act[q] or (act[1 - q] and not hedge):
            continue                                   # CanEnter
        band = lower if long_sig else upper
        # Qualifies: PassesFilters (distance, penetration) + ATR percentile
        if math.isnan(band):
            continue
        if dist_on:
            dist = max(b_close[i] - band, 0.0) if long_sig else max(band - b_close[i], 0.0)
            if dist > atr * dist_max:
                continue
        if pen_on:
            ppx = b_close[i] if pen_close else (b_low[i] if long_sig else b_high[i])
            pen = max(band - ppx, 0.0) if long_sig else max(ppx - band, 0.0)
            if pen > atr * pen_max:
                continue
        if pct_on:
            start = i - lookback
            if start < pct_len:
                continue
            val = b_patr[i]
            below = 0
            for z in range(start, i):
                if b_patr[z] <= val:
                    below += 1
            if not (100.0 * below / lookback <= pct_max):
                continue
        risk = atr * stop_mult
        if risk <= 0.0:
            continue
        sl_pips = risk / pip_size
        v = math.floor(risk_cash / (sl_pips * pv[kc]) / vol_step + 1e-9) * vol_step
        if v > vol_max:
            v = vol_max                                # export probe: 1000 $ at 23 pips -> 250 (VolumeInUnitsMax)
        if v < vol_min - 1e-12:
            continue                                   # below broker minimum: signal skipped
        # cTrader rounds the requested SL/TP distances to 0.1 pip (= tick size) and places them around the UNROUNDED fill
        # (ask = bid + spread); only the reported entry price is rounded. Archive: |entry - SL| equal to the bit on all
        # 16,346 trades checked.
        d_sl = round_digits(sl_pips, pip_dec) * pip_size
        d_tp = round_digits(sl_pips * target_r, pip_dec) * pip_size
        if long_sig:
            side[q] = 1
            raw = ask[kc]
            sl[q] = raw - d_sl
            tp[q] = raw + d_tp if not trailing else np.inf
        else:
            side[q] = -1
            raw = bid[kc]
            sl[q] = raw + d_sl
            tp[q] = raw - d_tp if not trailing else -np.inf
        if roll_global:
            next_roll = gptr[kc]                       # the account-wide pointer after this tick's rollover step
        elif next_roll < 0:
            next_roll = next_rollover(t_ms[kc], roll_min)
        # RULES A19: a stop inside the spread (beyond the opposite price) is refused, so the trade opens without one and the
        # cBot closes it at once at market; a stop exactly at the opposite price is set and fills on the entry tick
        opp = bid[kc] if long_sig else ask[kc]
        room = (opp - sl[q]) if long_sig else (sl[q] - opp)
        if room <= 0.5 * tick_size:
            if ntr >= max_tr:
                o_eq[0] = eq_dd
                o_eq[1] = 1.0
                return ntr
            ev_now = EV_SL if room >= -0.5 * tick_size else EV_CLOSE
            px = sl[q] if ev_now == EV_SL else opp
            e0 = round_digits(raw, digits)
            v0 = round_digits(v, 8)
            gross = round_cents((px - e0) * side[q] * v0 * uv[kc])
            com = commission(v0, bid[kc] if comm_mode == 2 else (br[kc] if comm_mode == 3 else
                                                              0.5 * (bid[kc] + ask[kc]) * uv[kc]), comm, comm_mode)
            _record(o_i, o_f, ntr, t_ms[kc], t_ms[kc], side[q], ev_now, 0, kc, e0, px, v0, sl[q], 0.0, gross, com)
            ntr += 1
            bal += gross + com
            last_exit = t_ms[kc]
            if bal > eq_peak:
                eq_peak = bal
            if bal <= 0.0:
                o_eq[0] = eq_dd
                o_eq[2] = 1.0
                return ntr
            continue
        act[q] = True
        sl0[q] = sl[q]
        risk_d[q] = risk
        entry[q] = round_digits(raw, digits)
        ostop[q] = entry[q] - risk if long_sig else entry[q] + risk
        vol[q] = round_digits(v, 8)
        ek[q] = kc
        swp[q] = 0.0
        cme[q] = commission(vol[q], bid[kc] if comm_mode == 2 else (br[kc] if comm_mode == 3 else
                                                                 0.5 * (bid[kc] + ask[kc]) * uv[kc]), comm, comm_mode)
        stage[q] = 0
        be_done[q] = False
        tseg[q] = seg
        fcb[q] = next_boundary(t_tc[kc], close_day, close_eth, close_fri)
        ncb[q] = np.int64(9223372036854775807)
        if news == 2:
            # NewsCloseDue: the first "release - Close Trades Minutes Before News" after the entry
            z = np.searchsorted(ev_t, t_tc[kc] + news_close_before, side="right")
            if z < len(ev_t):
                ncb[q] = ev_t[z] - news_close_before
    o_eq[0] = eq_dd
    return ntr


@njit(cache=True)
def _top_insert(top, x):
    """Keep the largest values in top (descending, -inf = empty)."""
    for a in range(len(top)):
        if x > top[a]:
            for b in range(len(top) - 1, a, -1):
                top[b] = top[b - 1]
            top[a] = x
            return


@njit(cache=True)
def _top_sum(top):
    t = 0.0
    for a in range(len(top)):
        if top[a] > -np.inf:
            t += top[a]
    return t


@njit(cache=True, parallel=True)
def run_batch(P, S, b_tc_open, b_high, b_low, b_close, b_atr, b_patr, b_vwap, b_dev, b_valid, b_seg, b_close_tick,
              first_bar, b_span, t_ms, t_tc, bid, ask, ttc, m1_high, m1_low, m1_close, pv, uv, br, gptr, ev_t, ev_d, year_ms,
              news_days, half_top, max_trades, keep_trades):
    """Many passes (rows of P) of one timeframe and mode in parallel. Returns stats (npass x NST, ST_* columns), the
    trade counts and, with keep_trades, the trade lists: tr_i = open, close, side, event, how; tr_f = entry, exit,
    volume, gross, swap, balance, initial SL (raw, not TP-capped), commission."""
    npass = P.shape[0]
    stats = np.zeros((npass, NST))
    keep = max_trades if keep_trades else 1
    tr_i = np.zeros((npass, keep, 5), dtype=np.int64)
    tr_f = np.zeros((npass, keep, 8))
    counts = np.zeros(npass, dtype=np.int64)
    start_bal = S[S_START]
    risk_cash = S[S_RISK]
    for pi in prange(npass):
        o_i = np.empty((max_trades, 6), dtype=np.int64)
        o_f = np.empty((max_trades, 7))
        o_eq = np.zeros(3)
        p = P[pi]
        n = run_kernel(p, S, b_tc_open, b_high, b_low, b_close, b_atr, b_patr, b_vwap, b_dev, b_valid, b_seg, b_close_tick,
                       first_bar, b_span, t_ms, t_tc, bid, ask, ttc, m1_high, m1_low, m1_close, pv, uv, br, gptr, ev_t, ev_d,
                       o_i, o_f, o_eq)
        counts[pi] = n
        st = stats[pi]
        cap = int(p[P_MGMT]) == 0
        top5 = np.full(5, -np.inf)
        top_h = np.full((2, max(half_top, 1)), -np.inf)
        bal = start_bal
        bal_raw = start_bal
        peak = start_bal
        mdd = 0.0
        for j in range(n):
            gross = o_f[j, 5]
            swap = o_f[j, 4]
            com = o_f[j, 6]
            net_raw = gross + swap + com
            bal_raw += net_raw
            if keep_trades:
                tr_i[pi, j, 0] = o_i[j, 0]
                tr_i[pi, j, 1] = o_i[j, 1]
                tr_i[pi, j, 2] = o_i[j, 2]
                tr_i[pi, j, 3] = o_i[j, 3]
                tr_i[pi, j, 4] = o_i[j, 4]
                tr_f[pi, j, 0] = o_f[j, 0]
                tr_f[pi, j, 1] = o_f[j, 1]
                tr_f[pi, j, 2] = o_f[j, 2]
                tr_f[pi, j, 3] = gross
                tr_f[pi, j, 4] = swap
                tr_f[pi, j, 5] = bal_raw
                tr_f[pi, j, 6] = o_f[j, 3]
                tr_f[pi, j, 7] = com
            # tools/tp_cap.py: a Fixed TP fill beyond the target is cut back to TargetR x the trade's own risk (tp_cap_gross)
            net = net_raw
            if cap and o_i[j, 3] == EV_TP:
                net = net_raw - (gross - tp_cap_gross(gross, o_i[j, 2], o_f[j, 0], o_f[j, 1], o_f[j, 3], p[P_TP], S[S_TICK]))
            bal += net
            st[ST_TRADES] += 1
            st[ST_NET_RAW] += net_raw
            st[ST_SWAP] += swap
            st[ST_COMM] += com
            if net > 0:
                st[ST_GW] += net
                st[ST_WINS] += 1
            else:
                st[ST_GL] -= net
            if bal > peak:
                peak = bal
            if peak - bal > mdd:
                mdd = peak - bal
            if o_i[j, 2] > 0:
                st[ST_LONG] += net
            else:
                st[ST_SHORT] += net
            _top_insert(top5, net)
            close_ms = o_i[j, 1]
            if j == 0:
                st[ST_FIRST] = close_ms
            st[ST_LAST] = close_ms
            yc = np.searchsorted(year_ms, close_ms, side="right") - 1
            if yc >= 0 and yc < NYEARS:
                st[ST_YEAR + yc] += net
                st[ST_YEAR_N + yc] += 1
            else:
                st[ST_OUTSIDE] += 1
            ny_open = t_tc[o_i[j, 5]] - NY_TC_MS
            yo = np.searchsorted(year_ms, ny_open, side="right") - 1
            h = -1
            if yo >= 0 and yo < NYEARS:
                h = 0 if FIRST_YEAR + yo < HALF_SPLIT else 1
            if h >= 0:
                c = ST_H1 if h == 0 else ST_H2
                st[c] += 1
                st[c + 1] += net
                if net > 0:
                    st[c + 2] += net
                elif net < 0:
                    st[c + 3] -= net
                if half_top > 0:
                    _top_insert(top_h[h], net)
            day = ny_open // DAY_MS
            dpos = np.searchsorted(news_days, day)
            if dpos < len(news_days) and news_days[dpos] == day:
                st[ST_NEWS] += net
        st[ST_NET] = bal - start_bal
        st[ST_DD] = mdd
        st[ST_EQDD] = o_eq[0]
        st[ST_TOP5] = _top_sum(top5)
        st[ST_OVERFLOW] = o_eq[1]
        st[ST_STOPOUT] = o_eq[2]
        if half_top > 0:
            st[ST_H1 + 4] = _top_sum(top_h[0])
            st[ST_H2 + 4] = _top_sum(top_h[1])
    return stats, counts, tr_i, tr_f


# ----------------------------------------------------------------------------------------------------------------------
# Python side: parameter vectors, symbol vector, cached inputs

WEEKDAY = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}


class Unsupported(ValueError):
    pass


class Spec:
    """Symbol figures the kernel needs (from the export's meta.json)."""

    def __init__(self, meta):
        self.pip_size = float(meta["pip_size"])
        self.tick_size = float(meta["tick_size"])
        self.digits = int(meta["digits"])
        self.pip_value = float(meta["pip_value"])       # account currency per pip per unit of volume
        self.vol_step = float(meta["volume_step"])
        self.vol_min = float(meta["volume_min"])
        self.vol_max = float(meta["volume_max"])
        self.pip_dec = int(round(math.log10(self.pip_size / self.tick_size)))   # SL/TP pips are rounded to this many decimals
        # account currency per 1.0 price move per unit (USD-quoted symbols on a USD account)
        self.unit_value = self.pip_value / self.pip_size
        props = meta.get("symbol_properties", {})
        if props.get("SwapCalculationType", "Pips") != "Pips":
            raise NotImplementedError("percentage swaps: not needed for US30, add when a symbol uses them")
        # cTrader "Pips" swaps, charged as swap pips x pip value per unit of volume per night
        self.swap_long_pips = float(meta.get("swap_long", 0.0))
        self.swap_short_pips = float(meta.get("swap_short", 0.0))
        self.triple_wd = WEEKDAY.get(props.get("Swap3DaysRollover", "Friday"), 4)
        # rollover minute (UTC): the broker's swap time, not in the Automate API, and it changes like the swap rates
        # (US30: 21:00 in the grids of 19-20 Oct 2026 and the export of 20 Oct, 21:30 in the maps of 16-18 Oct); referee
        # comparisons fit it from the archive (fullgrid.fit_roll)
        self.roll_min = 21 * 60
        self.roll_mode = 0               # 0 = rollover pointer from the pass's first entry (RULES A8), 1 = account-wide
        # quote currency -> account currency: the conversion pair's price at each tick (export columns conv_bid/conv_ask)
        self.quote = meta.get("quote_asset", "USD")
        self.account = meta.get("account_asset", "USD")
        self.conv_inverted = bool(meta.get("conversion_inverted", False))
        # which conversion rate (RULES A15): the volume is sized at the higher of the bid/ask rates, the P&L and swap are
        # converted at the lower one (EURGBP maps, GBPUSD: ask / bid; USDJPY maps, JPY->USD = 1/USDJPY: 1/bid / 1/ask)
        self.conv_size = "high"
        self.conv_pnl = "low"
        # the conversion pair is the symbol itself (USDJPY, USDCAD, USDCHF): stop/target fills convert at the symbol's
        # previous tick (USDJPY maps 100%), closes by the cBot at the tick; another pair (GBPUSD for EURGBP) always at the tick
        self.conv_self = meta.get("conversion_symbol") == meta.get("symbol")
        # commission: USD per million USD of volume per side (the symbol's broker setting; backtests must use the same)
        self.base = meta.get("base_asset", "")
        # cross commission (RULES A16): the base currency's own USD pair, read from its export next to this one
        self.base_pair = self.base + self.account if self.base and self.base != self.account and self.quote != self.account else None
        self.base_pair_ok = False
        self.commission = float(props.get("Commission", 0) or 0)
        if self.commission and props.get("CommissionType") != "UsdPerMillionUsdVolume":
            raise NotImplementedError(f"commission type {props.get('CommissionType')}: not simulated")


def symbol_vector(spec, m, risk_cash=1000.0, safety_net=True, hl_order=4, atr_len=14, pct_len=14, start_balance=100000.0):
    s = np.zeros(NS)
    s[S_PIP], s[S_TICK], s[S_PIPDEC], s[S_SPREAD] = spec.pip_size, spec.tick_size, spec.pip_dec, m.spread_px
    s[S_DIGITS], s[S_VSTEP], s[S_VMIN], s[S_VMAX] = spec.digits, spec.vol_step, spec.vol_min, spec.vol_max
    s[S_ROLLMIN], s[S_TRIPLE], s[S_SWAPL], s[S_SWAPS] = spec.roll_min, spec.triple_wd, spec.swap_long_pips, spec.swap_short_pips
    s[S_START], s[S_RISK], s[S_SAFETY], s[S_HLORDER] = start_balance, risk_cash, 1.0 if safety_net else 0.0, hl_order
    s[S_ATRLEN], s[S_PCTLEN] = atr_len, pct_len
    s[S_ROLLMODE] = spec.roll_mode
    s[S_COMM] = spec.commission
    s[S_COMMMODE] = 1 if spec.base == spec.account else (2 if spec.quote == spec.account else (3 if spec.base_pair_ok else 0))
    s[S_CONVSELF] = 1.0 if spec.conv_self and spec.quote != spec.account else 0.0
    return s


def _b(v):
    return str(v) in ("True", "1", "Yes")


# Settings the replica does not simulate: value it must have (as the archive stores it)
REQUIRED = {"Source": "3", "Timing": "0", "TradeDirection": "2", "BothAction": "0", "EnableMaxEntrySpreadFilter": "False",
            "SelectedRiskModel": "2", "MaxCashRiskCap": "0",
            "SessionDailyWindowBlock": "False", "WeeklyDailyWindowBlock": "False", "IntradayDailyWindowBlock": "False"}
DAY_BLOCKS = [f"{sec}{d}Block" for sec in ("Session", "Weekly", "Intraday")
              for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")]


def check_supported(v):
    for k, want in REQUIRED.items():
        if k in v and str(v[k]) != want:
            raise Unsupported(f"{k} = {v[k]} (replica supports {want} only)")
    for k in DAY_BLOCKS:
        if k in v and _b(v[k]):
            raise Unsupported(f"{k} = {v[k]} (day block windows not simulated)")


def pass_vector(v):
    """Kernel parameter vector from a pass's parameter values (archive strings or numbers)."""
    check_supported(v)
    g = lambda k, d=0.0: float(v[k]) if k in v and str(v[k]) not in ("off", "") else d  # noqa: E731
    p = np.zeros(NP)
    mode = int(g("Mode", 1))
    p[P_MODE] = mode
    src = int(g("IntradaySource", 0))
    p[P_SRC] = src
    if mode == MODE_SESSION:
        p[P_BAND_A] = g("SessionBandMult")
        p[P_FIRST_A], p[P_LAST_A] = g("BlockSessionFirst"), g("BlockSessionLast")
        p[P_CLOSE_DAY] = 1.0 if g("SessionForceClose") > 0.5 else 0.0
        p[P_CLOSE_FRI] = 1.0 if g("SessionForceCloseFriday") > 0.5 else 0.0
    elif mode == MODE_WEEKLY:
        p[P_BAND_A] = g("WeeklyBandMult")
        p[P_FIRST_A], p[P_LAST_A] = g("WeeklyFirstHours") * 60, g("WeeklyLastHours") * 60
        p[P_CLOSE_FRI] = 1.0 if g("WeeklyForceCloseFriday") > 0.5 else 0.0
    else:
        p[P_BAND_A], p[P_BAND_B] = g("EthBandMult"), g("RthBandMult")
        p[P_FIRST_A], p[P_LAST_A] = g("BlockEthFirst"), g("BlockEthLast")
        p[P_FIRST_B], p[P_LAST_B] = g("BlockRthFirst"), g("BlockRthLast")
        p[P_CLOSE_DAY] = 1.0 if _b(v.get("CloseAtRthEnd", "False")) and src != 1 else 0.0
        p[P_CLOSE_ETH] = 1.0 if _b(v.get("CloseAtEthEnd", "False")) and src != 2 else 0.0
        p[P_CLOSE_FRI] = 1.0 if _b(v.get("IntradayForceCloseFriday", "False")) else 0.0
    p[P_STOP], p[P_TP], p[P_MGMT] = g("StopAtrMult"), g("TargetR", 1.0), g("Management")
    p[P_TRIGGER], p[P_CUSHION] = g("BandTrailTrigger"), g("VwapTrailAtrCushion")
    p[P_BE], p[P_BE_R] = (1.0 if _b(v.get("EnableFixedTpBreakEven", "False")) else 0.0), g("FixedTpBreakEvenTriggerR", 0.5)
    p[P_HEDGE] = 1.0 if _b(v.get("AllowHedgeTrades", "False")) else 0.0
    p[P_TRACK] = 1.0 if _b(v.get("TrackTouchesWhileBlocked", "False")) else 0.0
    p[P_DIST_ON], p[P_DIST] = (1.0 if _b(v.get("EnableDistanceFilter", "False")) else 0.0), g("MaxEntryDistanceAtr", 1.0)
    p[P_PEN_ON], p[P_PEN] = (1.0 if _b(v.get("EnablePenetrationFilter", "False")) else 0.0), g("MaxBandPenetrationAtr", 0.5)
    p[P_PEN_CLOSE] = g("Penetration", 0.0)
    p[P_PCT_ON], p[P_PCT_MAX] = (1.0 if _b(v.get("EnableAtrPercentile", "False")) else 0.0), g("MaxAtrPercentile", 90.0)
    p[P_PCT_LOOKBACK] = g("PercentileLookback", 100.0)
    news = int(g("NewsFilterMode", 0))
    p[P_NEWS] = news
    before, close_before = g("NewsMinutesBefore", 5), g("NewsCloseMinutesBefore", 5)
    p[P_NEWS_BEFORE] = max(before, close_before) if news == 2 else before    # NewsEntryMinutesBefore
    p[P_NEWS_AFTER], p[P_NEWS_CLOSE] = g("NewsMinutesAfter", 10), close_before
    p[P_NEWS_TRACK] = 1.0 if _b(v.get("NewsTrackTouches", "True")) else 0.0
    return p


def news_key(v):
    """The news events a pass filters (None when the filter is off): part of the group key."""
    if int(float(v.get("NewsFilterMode", 0))) == 0:
        return None
    return tuple(_b(v.get(k, "True")) for k in ("NewsCpi", "NewsNfp", "NewsFomc", "NewsUsdMore", "NewsOtherCurrencies")) + (
        str(v.get("NewsCurrencies", "Auto")), _b(v.get("NewsUsdEverywhere", "False")))


_CALENDAR = {}


def news_calendar():
    """The cBot's NewsCalendar (release times in New York time, yyyyMMddHHmm), read from VwapMeanReversionBot.cs."""
    if not _CALENDAR:
        import re
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                "cTrader-Bots", "VwapMeanReversionBot.cs"), encoding="utf-8-sig").read()
        block = src[src.index("NEWS-CALENDAR-BEGIN"):src.index("NEWS-CALENDAR-END")]
        for name, body in re.findall(r"long\[\] (\w+) =\s*\{([^}]*)\}", block):
            _CALENDAR[name] = [int(x) for x in re.findall(r"\d{12}", body)]
    return _CALENDAR


NEWS_CODES = ("USD", "EUR", "GBP", "JPY", "CAD", "AUD", "NZD", "CHF")


def news_currencies(symbol, setting="Auto"):
    """NewsFilter.Currencies: the currencies whose news moves this symbol."""
    if setting and setting.strip().lower() != "auto":
        out = []
        for part in setting.replace(";", ",").replace(" ", ",").replace("+", ",").split(","):
            c = part.strip().upper()
            if c and c not in out:
                out.append(c)
        return out
    s = (symbol or "").upper()
    if any(x in s for x in ("XTI", "XBR", "OIL", "WTI", "BRENT")):
        return ["OIL", "USD"]
    if (s.startswith("US") and not s.startswith("USD")) or s.startswith(("NAS", "SPX", "DJ", "WS30")):
        return ["USD"]
    if s.startswith(("DE", "GER")) or "DAX" in s or (s.startswith("EU") and not s.startswith("EUR")) or s.startswith(("FRA", "F40")):
        return ["EUR"]
    if s.startswith("UK") or "FTSE" in s:
        return ["GBP"]
    if s.startswith("JP") or "NIK" in s:
        return ["JPY"]
    if s.startswith(("AUS", "AU200")):
        return ["AUD"]
    out = ["USD"] if s.startswith(("XAU", "XAG", "XPT", "XPD")) else []
    for i in range(0, len(s) - 2, 3):
        c = s[i:i + 3]
        if c in NEWS_CODES and c not in out:
            out.append(c)
    return out


def news_events(symbol, key):
    """Sorted release times (trading clock ms) and window durations (ms) of the events a pass filters (NewsFilter.Build)."""
    from datetime import datetime, timezone
    if key is None:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
    cpi, nfp, fomc, usd_more, other, setting, usd_everywhere = key
    cal = news_calendar()
    ccys = news_currencies(symbol, setting)
    items = []
    if usd_everywhere or "USD" in ccys:
        for flag, name in ((cpi, "Cpi"), (nfp, "Nfp"), (fomc, "Fomc"), (usd_more, "UsdMore")):
            if flag:
                items += [(t, 0) for t in cal[name]]
    if other:
        names = {"EUR": "Eur", "GBP": "Gbp", "JPY": "Jpy", "CAD": "Cad", "AUD": "Aud", "NZD": "Nzd", "CHF": "Chf", "OIL": "Oil"}
        for c in ccys:
            if c != "USD" and c in names:
                items += [(t, 180 if c == "JPY" else 0) for t in cal[names[c]]]
    tc = [int(datetime.strptime(str(t), "%Y%m%d%H%M").replace(tzinfo=timezone.utc).timestamp() * 1000) + NY_TC_MS for t, _ in items]
    order = np.argsort(tc, kind="stable")
    return (np.array(tc, dtype=np.int64)[order] if items else np.zeros(0, dtype=np.int64),
            np.array([d * MIN_MS for _, d in items], dtype=np.int64)[order] if items else np.zeros(0, dtype=np.int64))


def group_key(v):
    """Passes that can share one run_batch call: timeframe, mode, ATR lengths, risk, safety net."""
    g = lambda k, d: str(v.get(k, d)) if str(v.get(k, d)) != "off" else str(d)  # noqa: E731
    return (str(v["Timeframe"]), int(float(g("Mode", 1))), int(float(g("AtrLength", 14))),
            int(float(g("PercentileAtrLength", 14))), float(g("FixedCashRisk", 1000)), g("BrokerCloseSafetyNet", "True") == "True",
            news_key(v))


def bar_inputs(m, tf, mode, atr_len=14, pct_len=14):
    """Chart bars of tf with the VWAP state of mode and the ATR series (cached on m)."""
    import data
    key = (tf, mode, atr_len, pct_len)
    cache = m.__dict__.setdefault("_bar_inputs", {})
    if key in cache:
        return cache[key]
    if tf not in m.bars:
        m.bars[tf] = data.chart_bars(m, tf)
    b = m.bars[tf]
    if not hasattr(b, "tc_open"):
        b.tc_open = data.to_tc(b.open_ms)
        b.first_bar = first_closing_bar(m, b)
    out = type("BarInputs", (), {})()
    out.tc_open, out.h, out.l, out.c = b.tc_open, b.h, b.l, b.c
    out.atr = b.atr if atr_len == int(m.meta.get("atr_length", 14)) else data.wilder_atr(b.h, b.l, b.c, atr_len)
    out.patr = data.wilder_atr(b.h, b.l, b.c, pct_len) if pct_len != atr_len else out.atr
    out.vwap, out.dev, out.valid, out.seg = vwap_segments(b.tc_open, b.c, b.vol, mode)
    out.close_tick, out.first_bar = b.close_tick, b.first_bar
    out.span = candle_span(b.open_ms, b.first_bar)
    cache[key] = out
    return out


def tick_inputs(m, spec):
    """Pip value (sizing) and value of a 1.0 price move per unit (P&L, swap, equity) in account currency at every tick:
    constant for USD quotes, otherwise the quote currency converted at the conversion pair's price of that tick."""
    key = (spec.quote, spec.account, spec.conv_inverted, spec.conv_size, spec.conv_pnl, spec.conv_self)
    if getattr(m, "_tick_key", None) != key:
        if spec.quote == spec.account:
            m.uv_tick = np.full(len(m.t), spec.unit_value)
            m.pv_tick = np.full(len(m.t), spec.pip_value)
        else:
            if m.conv_bid is None:
                raise Unsupported(f"export without conversion prices for {spec.quote}->{spec.account}: rerun FastBtExport")

            def rate(which):
                rb, ra = (1.0 / m.conv_bid, 1.0 / m.conv_ask) if spec.conv_inverted else (m.conv_bid, m.conv_ask)
                r = {"bid": rb, "ask": ra, "mid": 0.5 * (rb + ra), "high": np.maximum(rb, ra), "low": np.minimum(rb, ra)}[which]
                return np.ascontiguousarray(r, dtype=np.float64)
            m.uv_tick = rate(spec.conv_pnl)
            m.pv_tick = rate(spec.conv_size) * spec.pip_size
        m._tick_key = key
    return m.pv_tick, m.uv_tick


def base_pair_folder(m, spec):
    """Export folder of the base currency's USD pair (EURUSD for EURGBP), or None."""
    if not spec.base_pair or not getattr(m, "folder", None):
        return None
    parent = os.path.dirname(os.path.abspath(m.folder))
    for name in sorted(os.listdir(parent)):
        if name.startswith(spec.base_pair + "_m") and os.path.isfile(os.path.join(parent, name, "meta.json")):
            return os.path.join(parent, name)
    return None


def base_rate(m, spec):
    """Per tick: the bid of the base currency's USD pair at its last tick at or before that time (cross commission,
    RULES A16), or zeros when not needed or not available (then spec.base_pair_ok stays False: estimate from the cross)."""
    if getattr(m, "_base_rate_key", "unset") != spec.base_pair:
        folder = base_pair_folder(m, spec)
        if folder is None:
            m._base_rate = np.zeros(len(m.t))
        else:
            import data as _data
            b = _data.load(folder)
            k = np.searchsorted(b.t, m.t, side="right") - 1
            m._base_rate = np.ascontiguousarray(np.where(k >= 0, b.bid[np.maximum(k, 0)], b.bid[0]), dtype=np.float64)
        m._base_rate_key = spec.base_pair
    spec.base_pair_ok = bool(m._base_rate.any())
    return m._base_rate


def stat_inputs():
    """Year boundaries (naive ms, used for UTC close and New York entry dates) and CPI/NFP days (New York, day numbers)."""
    import csv
    from datetime import datetime, timezone
    year_ms = np.array([int(datetime(FIRST_YEAR + y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000) for y in range(NYEARS + 1)],
                       dtype=np.int64)
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "us_news_dates.csv")
    days = []
    with open(path) as f:
        for r in csv.DictReader(line for line in f if not line.startswith("#")):
            if r["event"] in ("CPI", "NFP"):
                days.append(int(datetime.strptime(r["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000) // DAY_MS)
    return year_ms, np.array(sorted(set(days)), dtype=np.int64)


@njit(cache=True)
def candle_span(open_ms, first_bar):
    """CandleSpan of the news filter: the smallest gap between consecutive bar opens seen so far (looking back 20 bars from
    each closed bar, from the first bar that closes during the backtest)."""
    n = len(open_ms)
    out = np.zeros(n, dtype=np.int64)
    cur = np.int64(9223372036854775807)
    for i in range(first_bar, n):
        for k in range(max(1, i - 20), i + 1):
            gap = open_ms[k] - open_ms[k - 1]
            if gap > 0 and gap < cur:
                cur = gap
        out[i] = cur if cur < 9223372036854775807 else 0
    return out


def run_params(m, spec, key, P, max_trades=6000, keep_trades=False, half_top=3, hl_order=4):
    """run_batch for one group_key and a matrix of pass vectors."""
    tf, mode, atr_len, pct_len, risk_cash, safety, nkey = key
    b = bar_inputs(m, tf, mode, atr_len, pct_len)
    pv, uv = tick_inputs(m, spec)
    gkey = "_gptr_%d" % spec.roll_min
    if gkey not in m.__dict__:
        m.__dict__[gkey] = global_pointer(m.t, spec.roll_min)
    base_rate(m, spec)
    s = symbol_vector(spec, m, risk_cash, safety, hl_order, atr_len, pct_len)
    year_ms, news_days = m.__dict__.get("_stat_inputs") or m.__dict__.setdefault("_stat_inputs", stat_inputs())
    ev_t, ev_d = news_events(m.meta.get("symbol", ""), tuple(nkey) if nkey is not None else None)
    return run_batch(np.ascontiguousarray(P), s, b.tc_open, b.h, b.l, b.c, b.atr, b.patr, b.vwap, b.dev, b.valid, b.seg,
                     b.close_tick, b.first_bar, b.span, m.t, m.tc, m.bid, m.ask, m.ttc, m.tick_high, m.tick_low, m.tick_close,
                     pv, uv, base_rate(m, spec), m.__dict__[gkey], ev_t, ev_d, year_ms, news_days, half_top, max_trades, keep_trades)


def run_pass(m, spec, tf, v, max_trades=20000, hl_order=4):
    """One pass from its parameter values (dict, archive strings ok). Returns a trades dict."""
    v = dict(v, Timeframe=tf)
    _, counts, tr_i, tr_f = run_params(m, spec, group_key(v), pass_vector(v)[None, :], max_trades, True, hl_order=hl_order)
    n = int(counts[0])
    ti, tf_ = tr_i[0, :n], tr_f[0, :n]
    return {"open": ti[:, 0], "close": ti[:, 1], "side": ti[:, 2], "event": ti[:, 3], "how": ti[:, 4],
            "entry": tf_[:, 0], "exit": tf_[:, 1], "vol": tf_[:, 2], "gross": tf_[:, 3], "swap": tf_[:, 4],
            "sl": tf_[:, 6], "commission": tf_[:, 7], "net": np.round(tf_[:, 3] + tf_[:, 4] + tf_[:, 7], 2)}


def first_closing_bar(m, b):
    """Bars whose OnBarClosed fires during the backtest: bar i+1 opens after the backtest start (a bar that already
    existed at OnStart is history: its predecessor never fires) and its first tick lies inside bar i+1."""
    ct = b.close_tick
    n = len(b)
    start = int(m.meta.get("start_server_time_ms", m.t[0]))
    ok = ct >= 0
    nxt = np.append(b.open_ms[1:], np.iinfo(np.int64).max)
    nxt2 = np.append(b.open_ms[2:], [np.iinfo(np.int64).max] * 2)[:n]
    t_at = np.where(ok, m.t[np.clip(ct, 0, len(m.t) - 1)], 0)
    ok &= (t_at < nxt2) & (nxt > start)
    b.close_tick = np.where(ok, ct, -1)
    idx = np.nonzero(ok)[0]
    return int(idx[0]) if len(idx) else n
