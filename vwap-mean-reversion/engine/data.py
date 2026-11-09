"""Load a FastBtExport folder into numpy arrays (cached as .npz next to the export, outside iCloud).

An export folder (written by FastBtExport.cs during one cTrader backtest) holds ticks.csv.gz, m1.csv.gz,
chart_<tf>.csv.gz, bars_<tf>.csv.gz and meta.json. `load(folder)` returns a Market with:
  ticks : t (ms UTC), bid, ask, till_close (.NET ticks, -1 closed), tc (trading-clock ms = NY + 6 h); for symbols not
          quoted in the account currency also tick_value, convert (quote -> account) and conv_bid / conv_ask (None otherwise)
  bars(tf) : open_ms, o, h, l, c, vol (+ atr for the chart timeframe), close_tick (index of the tick that closes it)
  spec  : symbol specs from meta.json
Broker hours (`load(..., schedule=)`): cTrader backtests apply the broker's *current* trading-hours table to all of history, so
the BrokerCloseSafetyNet minute depends on when cTrader runs. till_close comes from the export (the table of the export date);
schedule="now" (default, every new cTrader run) applies `broker_hours.json` on top: the closes the broker moved since the
exports. schedule="export" keeps the export's table (referee replays of cTrader runs made before those changes).
"""
import gzip
import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

NY = ZoneInfo("America/New_York")
TC_OFFSET_MS = 6 * 3600 * 1000
DAY_MS = 86400000
MIN_MS = 60000
BROKER_HOURS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "broker_hours.json")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def ny_offsets(t_ms):
    """UTC offset of New York (ms) at each UTC time, from the zoneinfo DST transitions."""
    lo = datetime.fromtimestamp(int(t_ms.min()) / 1000, timezone.utc).year - 1
    hi = datetime.fromtimestamp(int(t_ms.max()) / 1000, timezone.utc).year + 1
    edges, offs = [], []
    t = datetime(lo, 1, 1, tzinfo=timezone.utc)
    end = datetime(hi + 1, 1, 1, tzinfo=timezone.utc)
    prev = None
    while t < end:  # hourly scan is plenty: transitions are on the hour
        off = int(t.astimezone(NY).utcoffset().total_seconds() * 1000)
        if off != prev:
            edges.append(int(t.timestamp() * 1000))
            offs.append(off)
            prev = off
        t += timedelta(hours=1)
    idx = np.searchsorted(np.array(edges, dtype=np.int64), t_ms, side="right") - 1
    return np.array(offs, dtype=np.int64)[idx]


def to_tc(t_ms):
    """UTC ms -> trading-clock ms (New York local time + 6 h), the cBot's TradingClock()."""
    return t_ms + ny_offsets(t_ms) + TC_OFFSET_MS


def _read_csv(path, names=None):
    import pandas as pd
    return pd.read_csv(path, compression="gzip", engine="c", header=0, names=names)


class Bars:
    def __init__(self, open_ms, o, h, l, c, vol, atr=None):
        self.open_ms = np.ascontiguousarray(open_ms, dtype=np.int64)
        self.o, self.h, self.l, self.c = (np.ascontiguousarray(x, dtype=np.float64) for x in (o, h, l, c))
        self.vol = np.ascontiguousarray(vol, dtype=np.float64)
        self.atr = None if atr is None else np.ascontiguousarray(atr, dtype=np.float64)
        self.close_tick = None

    def __len__(self):
        return len(self.open_ms)


class Market:
    pass


def _cache_path(folder):
    return os.path.join(folder, "fastbt_cache.npz")


def load(folder, tfs=("m5", "m10"), schedule="now"):
    folder = os.path.expanduser(folder)
    meta = json.load(open(os.path.join(folder, "meta.json"), encoding="utf-8-sig"))
    cache = _cache_path(folder)
    if os.path.isfile(cache) and os.path.getmtime(cache) > os.path.getmtime(os.path.join(folder, "meta.json")):
        z = dict(np.load(cache, allow_pickle=False))
    else:
        z = {}
        import pandas as pd
        path = os.path.join(folder, "ticks.csv.gz")
        with gzip.open(path, "rt") as fh:
            header = fh.readline().strip().split(",")
        names = ["t", "bid", "ask", "ttc"] + header[4:]       # + tick_value, convert, conv_bid, conv_ask (non-USD quotes)
        raw = pd.read_csv(path, compression="gzip", header=0, names=names, dtype=str)
        mark = raw["t"].values == "B"
        # A marker line "B,<open ms>" sits where OnBarClosed fired: before the tick that follows it.
        pos = np.cumsum(~mark) - (~mark)          # number of ticks before each line
        z["marker_tick"] = pos[mark].astype(np.int64)
        z["marker_open_ms"] = raw["bid"].values[mark].astype(np.int64)
        tk = raw[~mark]
        z["t"] = tk["t"].values.astype(np.int64)
        z["bid"] = tk["bid"].values.astype(np.float64)
        z["ask"] = tk["ask"].values.astype(np.float64)
        z["ttc"] = tk["ttc"].values.astype(np.int64)
        for col in header[4:]:
            z[col] = pd.to_numeric(tk[col], errors="coerce").values.astype(np.float64)
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".csv.gz") or name == "ticks.csv.gz":
                continue
            key = name[:-7]  # m1, chart_m5, bars_m10 ...
            df = _read_csv(os.path.join(folder, name))
            z[key + "_open_ms"] = df["open_ms"].values.astype(np.int64)
            for col in ("open", "high", "low", "close", "tick_volume"):
                z[key + "_" + col] = df[col].values.astype(np.float64)
            if "atr" in df.columns:
                z[key + "_atr"] = df["atr"].values.astype(np.float64)
        np.savez(cache, **z)
    m = Market()
    m.folder = folder
    m.meta = meta
    m.spec = spec_from_meta(meta)
    m.t, m.bid, m.ask, m.ttc = z["t"], z["bid"], z["ask"], z["ttc"]
    m.tick_value, m.convert, m.conv_bid, m.conv_ask = (z.get(k) for k in ("tick_value", "convert", "conv_bid", "conv_ask"))
    m.tc = to_tc(m.t)
    m.schedule = "export"
    if schedule == "now":
        apply_broker_hours(m)
    elif schedule != "export":
        raise ValueError(f"schedule {schedule!r}: 'now' or 'export'")
    # fixed backtest spread in price units; cTrader's ask is exactly bid + this value (all US30 ticks)
    m.spread_px = float(np.round(np.median(m.ask - m.bid), int(meta["digits"]) + 2))
    if not np.array_equal(m.ask, m.bid + m.spread_px):
        print("warning: ask is not bid + fixed spread on every tick (variable spread?)")
    m.marker_tick, m.marker_open_ms = z["marker_tick"], z["marker_open_ms"]
    # cTrader's m1-bar mode: one tick per m1 bar (its open, at its open time); the bar's high/low/close only feed SL/TP.
    j = np.searchsorted(z["bars_m1_open_ms"], m.t)
    if not np.array_equal(z["bars_m1_open_ms"][j], m.t):
        raise ValueError("ticks are not one per m1 bar")
    m.tick_high, m.tick_low, m.tick_close = (np.ascontiguousarray(z["bars_m1_" + k][j]) for k in ("high", "low", "close"))
    m.raw = z
    m.bars = {}
    chart_tf = meta["chart_timeframe"]
    for tf in tfs:
        m.bars[tf] = chart_bars(m, tf)
    m.chart_tf = chart_tf
    return m


def apply_broker_hours(m):
    """The broker's current closes (broker_hours.json) over the export's till_close: on a listed UTC weekday the market closes
    at that minute — TimeTillClose counts down to it, and from it to the export's own close the market is closed (-1). An
    earlier close of the export's table (a daily break) still comes first."""
    if not os.path.isfile(BROKER_HOURS):
        return
    e = json.load(open(BROKER_HOURS, encoding="utf-8")).get(m.meta["symbol"])
    if not e:
        return
    ttc = m.ttc.copy()
    open_ = ttc >= 0
    day = m.t // DAY_MS
    wd = (day + 3) % 7                                      # 1970-01-01 was a Thursday
    for name, hm in e["close_utc"].items():
        h, mi = (int(x) for x in hm.split(":"))
        close = day * DAY_MS + (h * 60 + mi) * MIN_MS
        old_close = m.t + ttc // 10_000
        on = open_ & (wd == WEEKDAYS.index(name))
        before = on & (m.t < close)
        ttc[before] = np.minimum(ttc[before], (close[before] - m.t[before]) * 10_000)
        ttc[on & (m.t >= close) & (old_close > close)] = -1
    m.ttc = ttc
    m.schedule = "now (broker_hours.json: " + ", ".join(f"{k} close {v} UTC" for k, v in e["close_utc"].items()) + ")"


def spec_from_meta(meta):
    s = {k: meta[k] for k in ("digits", "pip_size", "tick_size", "pip_value", "tick_value", "lot_size",
                              "volume_min", "volume_max", "volume_step", "swap_long", "swap_short") if k in meta}
    props = meta.get("symbol_properties", {})
    s["swap_3days"] = props.get("Swap3DaysRollover")
    s["swap_type"] = props.get("SwapCalculationType")
    return s


def chart_bars(m, tf):
    """Bars for timeframe tf as the cBot sees them, with ATR and the tick index that closes each bar."""
    z = m.raw
    chart_key = "chart_" + tf
    key = chart_key if chart_key + "_open_ms" in z else "bars_" + tf
    if key + "_open_ms" not in z:
        raise KeyError(f"timeframe {tf} not in export")
    b = Bars(z[key + "_open_ms"], z[key + "_open"], z[key + "_high"], z[key + "_low"], z[key + "_close"],
             z[key + "_tick_volume"], z.get(key + "_atr"))
    if b.atr is None or np.isnan(b.atr).all():
        b.atr = wilder_atr(b.h, b.l, b.c, int(m.meta.get("atr_length", 14)))
    # OnBarClosed for bar i fires on the first tick of bar i+1 (the last bar never closes).
    ct = np.full(len(b), -1, dtype=np.int64)
    ct[:-1] = np.searchsorted(m.t, b.open_ms[1:], side="left")
    ct[ct >= len(m.t)] = -1
    b.close_tick = ct
    return b


def wilder_atr(h, l, c, n):
    """cTrader AverageTrueRange(WilderSmoothing): Wilder RMA of the true range, seeded with the mean of the first n.
    Reproduces every archived US30 stop distance (41,058 trades, risk = ATR x mult to the cent)."""
    tr = np.empty_like(h)
    tr[0] = h[0] - l[0]
    pc = c[:-1]
    tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - pc), np.abs(l[1:] - pc)))
    out = np.full_like(h, np.nan)
    if len(h) < n:
        return out
    out[n - 1] = tr[:n].mean()
    for i in range(n, len(h)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out
