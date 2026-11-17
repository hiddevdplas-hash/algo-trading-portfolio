"""Engine data loader: research store -> fill-ready ticks and bars (DESIGN §3.3). The only code that reads market data.

Quality rules applied here, not left to strategies:
  1. crossed ticks: a crossing of one point (ask = bid - 1 point, the FX 2017-2019 feed habit of -0.1 pip) is treated as
     zero spread (ask = bid); a larger crossing is dropped for fills;
  2. FX May-July 2015 is quarantined: `quarantine_mask` marks those ticks; the runner reports results with and without them;
  3. thin months come from the data check and are flagged on results that use them;
  4. h2 / h4 bars: only the exported ones (never rebuilt in Python);
  5. signals use exported bars, fills use ticks.
Venues: 'ic' = IC's ticks as they are; 'ftmo' = widened by the cost table's add-on, half on each side.
"""
import json
import os

import numpy as np

from engine import store
from engine.timeutil import ny_offset_ms

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATACHECK = os.path.join(REPO, "data-checks", "ic-tick")
QUARANTINE_FX = ("2015-05", "2015-07")


class FillTicks:
    def __init__(self, symbol, venue, t, bid, ask, mid, n_dropped, n_zeroed, close_ms, conv_bid, conv_ask, half_addon=None,
                 spread_mult=1.0):
        self.symbol, self.venue = symbol, venue
        self.t, self.bid, self.ask, self.mid = t, bid, ask, mid
        self.half_addon = np.zeros(len(t)) if half_addon is None else half_addon    # FTMO add-on / 2 per tick (price units)
        self.spread_mult = spread_mult
        self.n_dropped_crossed, self.n_zeroed_crossed = n_dropped, n_zeroed
        self.close_ms, self.conv_bid, self.conv_ask = close_ms, conv_bid, conv_ask

    def __len__(self):
        return len(self.t)


def _month(s):
    if not ("2014-11" <= s <= "2024-12"):
        raise ValueError(f"month {s} outside the research period 2014-11 .. 2024-12")
    return s


def ticks(symbol, first_month, last_month, venue="ftmo", costs=None, addon_mult=1.0, spread_mult=1.0):
    """Fill-ready ticks. venue 'ftmo' needs the cost table (engine.costs.load()). addon_mult scales the FTMO add-on only;
    spread_mult scales the whole final spread around the mid (G2 cost stress: 1.5). half_addon keeps the FTMO add-on / 2 per tick
    (after spread_mult), so the trade log can show IC's cost line."""
    meta = store.store_meta(symbol)
    tk = store.load_ticks(symbol, _month(first_month), _month(last_month))
    point = float(meta["tick_size"])
    sp = tk.ask - tk.bid
    one_pt = (sp < 0) & (sp >= -point * 1.5)
    bad = sp < -point * 1.5
    ask = np.where(one_pt, tk.bid, tk.ask)
    keep = ~bad
    t, bid, ask = tk.t[keep], tk.bid[keep], ask[keep]
    cb = None if tk.conv_bid is None else tk.conv_bid[keep]
    ca = None if tk.conv_ask is None else tk.conv_ask[keep]
    mid = (bid + ask) / 2
    half = np.zeros(len(t))
    if venue == "ftmo":
        if costs is None:
            raise ValueError("venue 'ftmo' needs the cost table")
        row = costs["symbols"][symbol]["ftmo"]
        by_h = row.get("spread_addon_bp_by_ny_hour")
        if by_h:
            h = ((t + ny_offset_ms(t)) // 3_600_000) % 24
            bp = np.asarray(by_h, dtype=float)[h]
        else:
            bp = np.full(len(t), float(row["spread_addon_bp"]))
        a = bp * addon_mult * mid / 1e4
        bid, ask = bid - a / 2, ask + a / 2
        half = a / 2
    elif venue != "ic":
        raise ValueError(venue)
    if spread_mult != 1.0:
        hs = (ask - bid) / 2 * spread_mult
        bid, ask = mid - hs, mid + hs
        half = half * spread_mult
    return FillTicks(symbol, venue, t, bid, ask, mid, int(bad.sum()), int(one_pt.sum()), tk.close_ms[keep], cb, ca, half, spread_mult)


def bars(symbol, tf, first_month=None, last_month=None, warmup=True):
    """Exported bars of timeframe tf ('m1' ... 'h4', or 'chart_m5') with their close times. With warmup=True the bars before
    first_month are kept (indicators need history); the caller decides from which bar it may decide."""
    key = tf if tf.startswith("chart_") else "bars_" + tf
    b = store.load_bars(symbol, key)
    tf_ms = store.TF_MS[key.split("_", 1)[1]]
    b["close_ms"] = b["open_ms"] + tf_ms
    if last_month is not None:
        end = int((np.datetime64(_month(last_month), "M") + 1).astype("datetime64[ms]").astype(np.int64))
        k = b["close_ms"] <= end
        b = {k2: v[k] for k2, v in b.items()}
    if first_month is not None and not warmup:
        start = int(np.datetime64(_month(first_month), "M").astype("datetime64[ms]").astype(np.int64))
        k = b["open_ms"] >= start
        b = {k2: v[k] for k2, v in b.items()}
    return b


def quarantine_mask(symbol, t):
    """True on ticks inside FX May-July 2015 (DESIGN §3.3 rule 2); always False for non-FX."""
    from engine.costs import asset_class
    if asset_class(symbol) != "fx":
        return np.zeros(len(t), dtype=bool)
    lo = int(np.datetime64(QUARANTINE_FX[0], "M").astype("datetime64[ms]").astype(np.int64))
    hi = int((np.datetime64(QUARANTINE_FX[1], "M") + 1).astype("datetime64[ms]").astype(np.int64))
    return (t >= lo) & (t < hi)


def thin_months(symbol):
    for f in os.listdir(DATACHECK):
        if f.endswith(".json") and f.split("_")[0] == symbol:
            return [m for m in json.load(open(os.path.join(DATACHECK, f))).get("thin_months", []) if "2014-11" <= m <= "2024-12"]
    return []
