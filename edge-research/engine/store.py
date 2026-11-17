"""Research store: IC FastBtExport folders -> compact per-symbol store for the research period only (DESIGN §3.4).

Layout, under STORE_ROOT/<SYMBOL>/:
  meta.json              symbol spec (digits, tick size, conversion pair, swap, commission, market hours) + store info
  bars_<tf>.bk, chart_m5.bk   exported bars (m1 ... h4, chart m5), same codec; chart_m5_atr.npy = cTrader's ATR
  ticks/YYYY-MM.tk       ticks of one UTC month, columns delta-coded, byte-shuffled, zstd-compressed

Tick columns (all exact, checked on every month at conversion):
  t        UTC ms                         (int64, delta-coded)
  bid      price in integer ticks          (int64, delta-coded)   bid = bid_i / 10**digits (store digits: the symbol's,
           or finer where old data needs it, e.g. XAGUSD 4 vs 3 today; meta.json 'digits' is the store's, 'symbol_digits' cTrader's)
  spread   ask - bid in integer ticks      (int32; negative = crossed tick, kept here, dropped for fills by the loader)
  close    UTC ms the market closes, from till_close_100ns (t + ttc // 10_000; -1 = market closed; sub-ms part kept)
  conv_bid, conv_ask   price of the conversion pair (non-USD quotes only), integer ticks of that pair, delta-coded
The tick_value and convert columns of the export are not stored: tick_value is recomputed from conv_* (checked).

Period: ticks 2014-11-01 -> 2024-12-31 only. Bars from the first exported bar (warm-up for indicators; no ticks, so no
trades, before 2014-11-01) to the last bar that **closes** by 2025-01-01 00:00 UTC. The export is read in time order and
reading stops at the first chunk that reaches 2025; rows from 2025 on are dropped in memory and never written.
"""
import json
import os
import struct
import time
from datetime import datetime, timezone

import numpy as np
import zstandard as zstd

STORE_ROOT = os.path.expanduser("~/Projects/Algo Trading/data/ic-research-2014-2024")
RAW_ROOT = os.path.expanduser("~/cAlgo/Exports/fastbt-ic-tick")
RESEARCH_START_MS = int(datetime(2014, 11, 1, tzinfo=timezone.utc).timestamp() * 1000)
CUTOFF_MS = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)   # first ms of the locked period
STORE_VERSION = 1
TF_MS = {"m1": 60_000, "m5": 300_000, "m10": 600_000, "m15": 900_000, "m30": 1_800_000,
         "h1": 3_600_000, "h2": 7_200_000, "h4": 14_400_000}
MAGIC = b"ERTK"
ZLEVEL = 19


# ---------------------------------------------------------------- column codec
def _shuffle(a):
    """Byte-shuffle a fixed-width integer array: all first bytes, then all second bytes ... (zstd loves the zero planes)."""
    a = np.ascontiguousarray(a)
    return a.view(np.uint8).reshape(-1, a.itemsize).T.tobytes()


def _unshuffle(b, dtype, n):
    w = np.dtype(dtype).itemsize
    return np.frombuffer(b, dtype=np.uint8).reshape(w, n).T.copy().view(dtype).reshape(n)


def _delta(x):
    d = np.empty_like(x)
    d[0] = x[0]
    d[1:] = x[1:] - x[:-1]
    return d


def _narrow(d):
    """Smallest signed dtype that holds the deltas (first element included)."""
    for dt in (np.int8, np.int16, np.int32):
        info = np.iinfo(dt)
        if d.min() >= info.min and d.max() <= info.max:
            return d.astype(dt)
    return d.astype(np.int64)


def encode_month(cols, level=ZLEVEL):
    """cols: dict name -> int64 array (same length). Returns bytes."""
    n = len(next(iter(cols.values())))
    cctx = zstd.ZstdCompressor(level=level)
    parts, header = [], {"n": int(n), "cols": []}
    for name, x in cols.items():
        x = np.asarray(x, dtype=np.int64)
        d = _narrow(_delta(x)) if n else x.astype(np.int8)
        blob = cctx.compress(_shuffle(d)) if n else b""
        header["cols"].append([name, d.dtype.str, len(blob)])
        parts.append(blob)
    h = json.dumps(header).encode()
    return MAGIC + struct.pack("<I", len(h)) + h + b"".join(parts)


def decode_month(buf):
    if buf[:4] != MAGIC:
        raise ValueError("not a store tick file")
    hl = struct.unpack("<I", buf[4:8])[0]
    header = json.loads(buf[8:8 + hl])
    n, pos, out = header["n"], 8 + hl, {}
    dctx = zstd.ZstdDecompressor()
    for name, dts, ln in header["cols"]:
        if n == 0:
            out[name] = np.zeros(0, dtype=np.int64)
            continue
        raw = dctx.decompress(buf[pos:pos + ln], max_output_size=n * np.dtype(dts).itemsize)
        pos += ln
        out[name] = np.cumsum(_unshuffle(raw, dts, n).astype(np.int64))
    return out


# ---------------------------------------------------------------- conversion
def _ym(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m")


def _month_edges(t):
    """Indices where the UTC month changes, and the month labels."""
    days = t // 86_400_000
    dt64 = days.astype("datetime64[D]").astype("datetime64[M]")
    cut = np.flatnonzero(dt64[1:] != dt64[:-1]) + 1
    starts = np.concatenate([[0], cut])
    ends = np.concatenate([cut, [len(t)]])
    labels = [str(dt64[s]) for s in starts]
    return list(zip(labels, starts, ends))


def _price_int(px, digits):
    """Float prices -> integer ticks; exact round trip checked."""
    scale = 10 ** digits
    i = np.rint(px * scale).astype(np.int64)
    back = i / scale
    if not np.array_equal(back, px):
        bad = np.flatnonzero(back != px)[:5]
        raise ValueError(f"price not on the {digits}-digit grid: {px[bad]}")
    return i


def _conv_digits(raw_root, conv_symbol):
    if not conv_symbol:
        return None
    for d in os.listdir(raw_root):
        if d.split("_")[0] == conv_symbol:
            return int(json.load(open(os.path.join(raw_root, d, "meta.json"), encoding="utf-8-sig"))["digits"])
    return None


def _guess_digits(px):
    for d in range(0, 7):
        if np.array_equal(np.rint(px * 10 ** d) / 10 ** d, px):
            return d
    raise ValueError("cannot find a decimal grid for conversion prices")


def _price_digits(folder, digits):
    """The symbol's digits, or more if the exported m1 bars (all of history) need a finer grid."""
    import pandas as pd
    df = pd.read_csv(os.path.join(folder, "bars_m1.csv.gz"), compression="gzip", usecols=["open", "high", "low", "close"])
    px = df.values.ravel().astype(np.float64)
    for d in range(digits, digits + 3):
        if np.array_equal(np.rint(px * 10 ** d) / 10 ** d, px):
            return d
    raise ValueError(f"{folder}: prices need more than {digits + 2} decimals")


def convert_bars(folder, out_dir, digits, cutoff_ms=CUTOFF_MS, level=ZLEVEL):
    """Exported bars -> <key>.bk (open_ms, o/h/l/c in integer ticks, tick volume; same codec as ticks) and, for the chart
    timeframe, <key>_atr.npy (cTrader's own ATR values, float64)."""
    import pandas as pd
    info = {}
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".csv.gz") or name == "ticks.csv.gz":
            continue
        key = name[:-7]                                  # bars_m1, chart_m5 ...
        tf = key.split("_", 1)[1]
        df = pd.read_csv(os.path.join(folder, name), compression="gzip")
        om = df["open_ms"].values.astype(np.int64)
        keep = om + TF_MS[tf] <= cutoff_ms                # whole bar before the locked period
        cols = {"open_ms": om[keep]}
        for src in ("open", "high", "low", "close"):
            cols[src] = _price_int(df[src].values[keep].astype(np.float64), digits)
        cols["tick_volume"] = df["tick_volume"].values[keep].astype(np.int64)
        buf = encode_month(cols, level)
        back = decode_month(buf)
        if not all(np.array_equal(back[k], v) for k, v in cols.items()):
            raise ValueError(f"bar round trip failed: {key}")
        with open(os.path.join(out_dir, key + ".bk"), "wb") as fh:
            fh.write(buf)
        if "atr" in df.columns:
            np.save(os.path.join(out_dir, key + "_atr.npy"), df["atr"].values[keep].astype(np.float64))
        info[key] = {"bars": int(keep.sum()), "first": _ym(int(om[keep][0])) if keep.any() else None,
                     "last_open_utc": datetime.fromtimestamp(int(om[keep][-1]) / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")
                     if keep.any() else None, "dropped_after_cutoff": int((~keep).sum()), "bytes": len(buf)}
    return info


def convert_symbol(folder, store_root=STORE_ROOT, start_ms=RESEARCH_START_MS, cutoff_ms=CUTOFF_MS,
                   chunksize=10_000_000, level=ZLEVEL, max_months=None, log=print):
    """Convert one export folder. Returns a dict of measurements (sizes, times, counts per month)."""
    import pandas as pd
    folder = os.path.expanduser(folder)
    meta = json.load(open(os.path.join(folder, "meta.json"), encoding="utf-8-sig"))
    sym = meta["symbol"]
    digits = _price_digits(folder, int(meta["digits"]))   # finest decimal grid the data uses (XAGUSD: 4 in early years, 3 now)
    out_dir = os.path.join(store_root, sym)
    os.makedirs(os.path.join(out_dir, "ticks"), exist_ok=True)
    t0 = time.time()
    bar_info = convert_bars(folder, out_dir, digits, cutoff_ms, level)
    t_bars = time.time() - t0

    with open(os.path.join(folder, "ticks.csv.gz"), "rb") as fh:
        import gzip
        header = gzip.GzipFile(fileobj=fh).readline().decode().strip().split(",")
    has_conv = "conv_bid" in header
    conv_digits = _conv_digits(RAW_ROOT, meta.get("conversion_symbol")) if has_conv else None
    dtypes = {"time_ms": np.int64, "bid": np.float64, "ask": np.float64, "till_close_100ns": np.int64}
    usecols = ["time_ms", "bid", "ask", "till_close_100ns"] + (["tick_value", "conv_bid", "conv_ask"] if has_conv else [])

    months, pending, stats = {}, None, {"parse_s": 0.0, "encode_s": 0.0, "rows_read": 0, "rows_after_cutoff_dropped": 0,
                                         "rows_before_start": 0, "tick_value_max_rel_err": 0.0}
    tv_side = None
    reader = pd.read_csv(os.path.join(folder, "ticks.csv.gz"), compression="gzip", comment="B", usecols=usecols,
                         dtype=dtypes, chunksize=chunksize, engine="c")
    done = False
    tp = time.time()
    for chunk in reader:
        stats["parse_s"] += time.time() - tp
        stats["rows_read"] += len(chunk)
        t = chunk["time_ms"].values
        if len(t) and t[-1] >= cutoff_ms:
            done = True
        keep = (t >= start_ms) & (t < cutoff_ms)
        stats["rows_before_start"] += int((t < start_ms).sum())
        stats["rows_after_cutoff_dropped"] += int((t >= cutoff_ms).sum())
        if keep.any():
            c = chunk[keep]
            te = time.time()
            cols = {"t": c["time_ms"].values,
                    "bid": _price_int(c["bid"].values, digits)}
            cols["spread"] = _price_int(c["ask"].values, digits) - cols["bid"]
            ttc = c["till_close_100ns"].values
            close100 = np.where(ttc >= 0, cols["t"] * 10_000 + ttc, -1)
            cols["close100"] = close100
            if has_conv:
                cb, ca = c["conv_bid"].values, c["conv_ask"].values
                if conv_digits is None:
                    conv_digits = _guess_digits(np.concatenate([cb[:100000], ca[:100000]]))
                cols["conv_bid"] = _price_int(cb, conv_digits)
                cols["conv_ask"] = _price_int(ca, conv_digits)
                tv = c["tick_value"].values
                ts = float(meta["tick_size"])
                inv = bool(meta.get("conversion_inverted"))
                cands = {"bid": ts / cb if inv else ts * cb, "ask": ts / ca if inv else ts * ca}
                if tv_side is None:
                    errs = {k: float(np.nanmax(np.abs(v / tv - 1))) for k, v in cands.items()}
                    tv_side = min(errs, key=errs.get)
                stats["tick_value_max_rel_err"] = max(stats["tick_value_max_rel_err"],
                                                      float(np.nanmax(np.abs(cands[tv_side] / tv - 1))))
            if pending is not None:                       # month split across chunks: glue the tail on
                cols = {k: np.concatenate([pending[k], v]) for k, v in cols.items()}
            edges = _month_edges(cols["t"])
            last_label, ls, le = edges[-1]
            for label, s, e in edges[:-1]:
                months[label] = _write_month(out_dir, label, {k: v[s:e] for k, v in cols.items()}, level)
                log(f"{sym} {label}: {e - s:,} ticks, {months[label]['bytes'] / 1e6:.1f} MB")
                if max_months and len(months) >= max_months:
                    done = True
                    break
            pending = {k: v[ls:le] for k, v in cols.items()}
            stats["encode_s"] += time.time() - te
        if done:
            break
        tp = time.time()
    if pending is not None and not (max_months and len(months) >= max_months):
        label = _ym(int(pending["t"][0]))
        months[label] = _write_month(out_dir, label, pending, level)
        log(f"{sym} {label}: {months[label]['n']:,} ticks, {months[label]['bytes'] / 1e6:.1f} MB")
    reader.close()

    store_meta = {
        "symbol": sym, "store_version": STORE_VERSION, "source_folder": os.path.basename(folder),
        "research_start_utc": "2014-11-01", "cutoff_utc": "2025-01-01 (exclusive)",
        "digits": digits, "symbol_digits": int(meta["digits"]), "tick_size": float(meta["tick_size"]), "pip_size": float(meta["pip_size"]),
        "lot_size": float(meta["lot_size"]), "base_asset": meta.get("base_asset"), "quote_asset": meta.get("quote_asset"),
        "conversion_symbol": meta.get("conversion_symbol") or None, "conversion_inverted": bool(meta.get("conversion_inverted")),
        "conv_digits": conv_digits, "tick_value_from_conv": tv_side,
        "swap_long": meta.get("swap_long"), "swap_short": meta.get("swap_short"),
        "swap_type": meta.get("symbol_properties", {}).get("SwapCalculationType"),
        "swap_3days": meta.get("symbol_properties", {}).get("Swap3DaysRollover"),
        "commission": meta.get("symbol_properties", {}).get("Commission"),
        "commission_type": meta.get("symbol_properties", {}).get("CommissionType"),
        "market_hours": meta.get("market_hours"),
        "chart_timeframe": meta.get("chart_timeframe"), "atr_length": meta.get("atr_length"),
        "bars": bar_info, "months": {k: {"n": v["n"], "bytes": v["bytes"]} for k, v in sorted(months.items())},
        "converted_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    }
    json.dump(store_meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1)
    stats.update({"symbol": sym, "bars_s": t_bars, "total_s": time.time() - t0, "months": len(months),
                  "ticks_stored": int(sum(v["n"] for v in months.values())),
                  "tick_bytes": int(sum(v["bytes"] for v in months.values())),
                  "bar_bytes": int(sum(os.path.getsize(os.path.join(out_dir, f)) for f in os.listdir(out_dir)
                                       if f.endswith(".bk") or f.endswith(".npy")))})
    return stats


def _write_month(out_dir, label, cols, level):
    buf = encode_month(cols, level)
    back = decode_month(buf)                              # exact round trip, every month
    for k, v in cols.items():
        if not np.array_equal(back[k], np.asarray(v, dtype=np.int64)):
            raise ValueError(f"round trip failed: {label} {k}")
    path = os.path.join(out_dir, "ticks", label + ".tk")
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        fh.write(buf)
    os.replace(tmp, path)
    return {"n": int(len(cols["t"])), "bytes": len(buf)}


# ---------------------------------------------------------------- reading
class Ticks:
    """One symbol's ticks over a range of months, as numpy arrays (prices as float64, identical to the export)."""

    def __init__(self, t, bid, ask, close_ms, conv_bid=None, conv_ask=None):
        self.t, self.bid, self.ask, self.close_ms = t, bid, ask, close_ms
        self.conv_bid, self.conv_ask = conv_bid, conv_ask

    def __len__(self):
        return len(self.t)


def store_meta(symbol, store_root=STORE_ROOT):
    return json.load(open(os.path.join(store_root, symbol, "meta.json")))


def read_month_raw(symbol, label, store_root=STORE_ROOT):
    with open(os.path.join(store_root, symbol, "ticks", label + ".tk"), "rb") as fh:
        return decode_month(fh.read())


def load_ticks(symbol, first_month, last_month, store_root=STORE_ROOT):
    """Ticks from first_month to last_month inclusive ('YYYY-MM'). Never reaches past 2024-12 (the store stops there)."""
    meta = store_meta(symbol, store_root)
    labels = [m for m in sorted(meta["months"]) if first_month <= m <= last_month]
    parts = [read_month_raw(symbol, m, store_root) for m in labels]
    if not parts:
        z = np.zeros(0, dtype=np.int64)
        return Ticks(z, z.astype(float), z.astype(float), z)
    cat = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    sc = 10 ** meta["digits"]
    c100 = cat["close100"]
    close_ms = np.where(c100 >= 0, c100 // 10_000, -1)
    cb = ca = None
    if "conv_bid" in cat:
        cs = 10 ** meta["conv_digits"]
        cb, ca = cat["conv_bid"] / cs, cat["conv_ask"] / cs
    return Ticks(cat["t"], cat["bid"] / sc, (cat["bid"] + cat["spread"]) / sc, close_ms, cb, ca)


def load_bars(symbol, key, store_root=STORE_ROOT):
    """Exported bars: key = 'bars_m1' ... 'bars_h4' or 'chart_m5'. Returns open_ms (int64), o, h, l, c, vol (float64),
    and atr for the chart timeframe."""
    meta = store_meta(symbol, store_root)
    with open(os.path.join(store_root, symbol, key + ".bk"), "rb") as fh:
        z = decode_month(fh.read())
    sc = 10 ** meta["digits"]
    out = {"open_ms": z["open_ms"], "o": z["open"] / sc, "h": z["high"] / sc, "l": z["low"] / sc, "c": z["close"] / sc,
           "vol": z["tick_volume"].astype(np.float64)}
    atr = os.path.join(store_root, symbol, key + "_atr.npy")
    if os.path.isfile(atr):
        out["atr"] = np.load(atr)
    return out
