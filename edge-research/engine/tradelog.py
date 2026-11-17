"""Trade log with costs (DESIGN §4.3, §3.5): every trade's R before and after each cost, on both venues, plus market context.

The simulation runs on the FTMO venue (IC ticks widened by FTMO's add-on), so the kernel's r_gross is after FTMO's spread.
Per trade and venue (ftmo judged, ic shown; IC is approximate: the trades are FTMO's):
  r_mid          R at the mid prices of the entry and exit ticks (no spread)
  r_spread_*     spread paid: ftmo = r_gross - r_mid; ic = that plus the FTMO add-on / 2 on each side (IC's quotes)
  r_comm_*       commission (engine.costs.commission_px), converted at the entry tick
  r_swap_*       swap for every 17:00 New York rollover held (Mon-Fri; the symbol's 3-day weekday counts 3), from the policy-rate
                 model on that day (engine.costs.swap_rate_pct) x the entry mid / 365
  r_slip_*       one extra spread (that venue's, at that tick) on a market or stop fill within 2.5 min of a high-impact release
                 for the symbol (§3.5); 0 on limit fills and targets
  r_net_*        sum: ftmo = r_gross + comm + swap + slip; ic = r_mid + spread_ic + comm + swap + slip
Stress (G2): spread x 1.5 comes from the ticks (engine.data.ticks spread_mult); swap_mult and zero_positive_swap here.
Context (engine/context.py), at the decision bar's close (DESIGN A3.4; the entry time when not given): session, h4 volatility
percentile and third, trend direction, trend / range regime from the last closed h4 bar, bloc, news day
(a tier-1 event for the symbol that Amsterdam day), weekday, month.
synthetic_edge_r (calibration only, DESIGN §8 built-in-edge strategies): added to every trade's R, flagged in the ledger.
"""
from zoneinfo import ZoneInfo

import numpy as np

from engine import context as CX, costs as C, store
from engine.kernel import EXIT_NAMES, LIMIT, MARKET, STOP
from engine.rules import blocks_symbol
from engine.timeutil import ams_offset_ms, ny_offset_ms

NY = ZoneInfo("America/New_York")
DAY = 86_400_000
SLIP_HALF_WINDOW = 150_000          # 2.5 min each side of a release
WEEKDAY = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}


def quote_usd(meta, ticks, idx):
    """USD per unit of the quote currency at tick idx."""
    if meta["quote_asset"] == "USD":
        return np.ones(len(idx))
    m = (ticks.conv_bid[idx] + ticks.conv_ask[idx]) / 2
    return 1.0 / m if meta["conversion_inverted"] else m


def rollovers(entry_t, exit_t, triple_wd):
    """Swap nights per trade: 17:00 New York rollovers on weekdays with entry < R < exit; the 3-day weekday counts 3.
    Also returns the UTC day of each rollover for the rate lookup (as a list of arrays)."""
    nights, days = np.zeros(len(entry_t)), []
    for k, (a, b) in enumerate(zip(entry_t, exit_t)):
        d0 = (int(a) + int(ny_offset_ms([a])[0])) // DAY        # NY local day number of the entry
        d1 = (int(b) + int(ny_offset_ms([b])[0])) // DAY
        ds = []
        n = 0.0
        for d in range(d0, d1 + 1):
            wd = (d + 3) % 7                                    # 1970-01-01 was a Thursday; Monday = 0
            if wd > 4:
                continue
            local = d * DAY + 17 * 3_600_000
            r = local - int(ny_offset_ms([local])[0])            # 17:00 NY in UTC (offset at that moment; DST days are fine)
            if a < r < b:
                n += 3 if wd == triple_wd else 1
                ds.append((r // DAY, 3 if wd == triple_wd else 1))
        nights[k] = n
        days.append(ds)
    return nights, days


def build(trades, ticks, symbol, costs, events=(), swap_mult=1.0, zero_positive_swap=False, context=True, extra=None,
          synthetic_edge_r=0.0, decision_ms=None):
    """Trade log: dict of equal-length arrays (one row per trade). ticks = the FillTicks the kernel ran on (FTMO venue for
    judged runs). events: calendar events (engine.rules format) for slippage and the news-day flag. extra: constant columns
    (idea, variant, timeframe, engine hash, ...)."""
    meta = store.store_meta(symbol)
    n = len(trades["bar"])
    side = trades["side"].astype(float)
    risk = trades["risk"]
    ei, xi = trades["entry_tick"], trades["exit_tick"]
    mid_in, mid_out = (ticks.bid[ei] + ticks.ask[ei]) / 2, (ticks.bid[xi] + ticks.ask[xi]) / 2   # the FTMO widening is symmetric
    r_mid = (mid_out - mid_in) * side / risk
    log = {k: v for k, v in trades.items()}
    if synthetic_edge_r:
        log["r_gross"] = trades["r_gross"] + synthetic_edge_r
    r_gross = log["r_gross"]
    log["exit_name"] = np.array([EXIT_NAMES[int(r)] for r in trades["exit_reason"]], dtype=object)
    log["symbol"] = np.array([symbol] * n, dtype=object)
    log["venue_sim"] = np.array([ticks.venue] * n, dtype=object)
    log["r_mid"] = r_mid
    spread_ftmo = trades["r_gross"] - r_mid            # the kernel's R, without any synthetic edge
    spread_ic = spread_ftmo + (ticks.half_addon[ei] + ticks.half_addon[xi]) / risk
    # commission: per unit, converted at the entry tick
    qusd = quote_usd(meta, ticks, ei) if n else np.zeros(0)
    base_usd = mid_in * qusd
    comm = {v: -np.array([C.commission_px(costs, symbol, v, base_usd[k], qusd[k]) for k in range(n)]) / risk if n else np.zeros(0)
            for v in ("ftmo", "ic")}
    # swap
    tri = WEEKDAY[costs["symbols"][symbol].get("swap_3day", "Wednesday")]
    nights, days = rollovers(trades["entry_t"], trades["exit_t"], tri)
    swap = {}
    for v in ("ftmo", "ic"):
        out = np.zeros(n)
        for k in range(n):
            if not days[k]:
                continue
            d = np.array([np.datetime64(int(x), "D") for x, _ in days[k]])
            mult = np.array([m for _, m in days[k]], float)
            rate = C.swap_rate_pct(costs, symbol, v, "long" if side[k] > 0 else "short", d)
            if zero_positive_swap:
                rate = np.minimum(rate, 0.0)
            out[k] = float((rate * mult).sum()) / 100 * mid_in[k] / 365 * swap_mult / risk[k]
        swap[v] = out
    # slippage near high-impact releases
    rel = np.sort(np.asarray([int(e["start_ms"]) for e in events or () if e.get("kind", "release") == "release"
                              and blocks_symbol(e["ccy"], symbol)], np.int64))

    def near(tt):
        if not len(rel):
            return np.zeros(len(tt), bool)
        j = np.searchsorted(rel, tt)
        lo = np.abs(tt - rel[np.maximum(j - 1, 0)])
        hi = np.abs(rel[np.minimum(j, len(rel) - 1)] - tt)
        return np.minimum(lo, hi) <= SLIP_HALF_WINDOW

    ot = trades["otype"]
    slip_in = near(trades["entry_t"]) & ((ot == MARKET) | (ot == STOP))
    slip_out = near(trades["exit_t"]) & (trades["exit_reason"] != 2) & (trades["exit_reason"] != 6)   # all but limit targets
    sp_in_f, sp_out_f = ticks.ask[ei] - ticks.bid[ei], ticks.ask[xi] - ticks.bid[xi]
    sp_in_i, sp_out_i = sp_in_f - 2 * ticks.half_addon[ei], sp_out_f - 2 * ticks.half_addon[xi]
    slip = {"ftmo": -(slip_in * sp_in_f + slip_out * sp_out_f) / risk, "ic": -(slip_in * sp_in_i + slip_out * sp_out_i) / risk}
    log.update(r_spread_ftmo=spread_ftmo, r_spread_ic=spread_ic, r_comm_ftmo=comm["ftmo"], r_comm_ic=comm["ic"],
               r_swap_ftmo=swap["ftmo"], r_swap_ic=swap["ic"], r_slip_ftmo=slip["ftmo"], r_slip_ic=slip["ic"], swap_nights=nights,
               slip_entry=slip_in, slip_exit=slip_out)
    log["r_net_ftmo"] = r_gross + comm["ftmo"] + swap["ftmo"] + slip["ftmo"]
    log["r_net_ic"] = r_mid + synthetic_edge_r + spread_ic + comm["ic"] + swap["ic"] + slip["ic"]
    log["hold_min"] = (trades["exit_t"] - trades["entry_t"]) / 60_000
    # context (engine/context.py: the same definitions as the screen's slices and the filter menu)
    et = trades["entry_t"]
    loc = et + ams_offset_ms(et) if n else et
    log["ams_hour"] = (loc // 3_600_000) % 24 if n else np.zeros(0, np.int64)
    dt = et if decision_ms is None else np.asarray(decision_ms, np.int64)   # DESIGN A3.4: context at the decision time
    log["decision_t"] = dt
    log["session"] = CX.session(dt)
    log["weekday"] = ((loc // DAY) + 3) % 7 if n else np.zeros(0, np.int64)
    log["month"] = (np.asarray(et).astype("datetime64[ms]").astype("datetime64[M]").astype(np.int64) % 12) + 1
    log["bloc"] = np.array([CX.bloc(symbol)] * n, dtype=object)
    t1 = np.asarray([int(e["start_ms"]) for e in events or () if int(e["tier"]) == 1 and blocks_symbol(e["ccy"], symbol)], np.int64)
    if len(t1) and n:
        t1_days = set(((t1 + ams_offset_ms(t1)) // DAY).tolist())
        log["news_day"] = np.array([int(d) in t1_days for d in loc // DAY])
    else:
        log["news_day"] = np.zeros(n, bool)
    if context and n:
        vp, third, tdir, reg = CX.at(symbol, dt)
        log["vol_pct"], log["vol_third"], log["trend"], log["regime"] = vp, third.astype(object), tdir, reg.astype(object)
    for k, v in (extra or {}).items():
        log[k] = np.array([v] * n, dtype=object)
    return log


def summary(log, venue="ftmo"):
    """Headline numbers of a trade log (R per trade before / after costs, cost shares)."""
    n = len(log["bar"])
    if not n:
        return {"trades": 0}
    net = log[f"r_net_{venue}"]
    out = {"trades": n, "r_gross_mean": round(float(log["r_gross"].mean()), 4), "r_net_mean": round(float(net.mean()), 4),
           "r_net_sum": round(float(net.sum()), 3)}
    for c in ("spread", "comm", "swap", "slip"):
        out[f"{c}_mean"] = round(float(log[f"r_{c}_{venue}"].mean()), 4)
    pos, neg = net[net > 0].sum(), -net[net < 0].sum()
    out["profit_factor"] = round(float(pos / neg), 3) if neg > 0 else None
    return out
