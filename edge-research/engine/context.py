"""Market context at a moment, from closed data only (DESIGN §4.3 context, §6.3 slices, §6.4 / §8 filter menu).

The same definitions serve the trade log (context at entry), the screen's fixed slices and the amber / random filter menu:
  session      Amsterdam hour: asia [00, 08), london [08, 14), ny [14, 22), rollover [22, 24)
  vol_pct      h4 Wilder ATR(14) of the last h4 bar closed at or before the moment, as a percentile of the previous 1,500 h4 values;
               thirds: low < 1/3 <= mid < 2/3 <= high
  trend_dir    +1 / -1: that h4 close above / below its SMA 200
  regime       'trend' if |h4 close - SMA 200| > k_symbol x h4 ATR(14), else 'range' (DESIGN A4.5: k_symbol = the symbol's median
               of |close - SMA 200| / ATR on closed h4 bars 2014-11 -> 2016-10; < 12 months there: the pooled median 3.56;
               engine/regime_k.json, part of the engine hash)
  bloc         equities (indices), usd (FX pairs with USD), metals, oil; other FX crosses: none
"""
from functools import lru_cache

import numpy as np

from engine import store
from engine.timeutil import ams_offset_ms

H4 = 4 * 3_600_000
LOOKBACK = 1500
INDICES = ("AUS200", "DE40", "F40", "HK50", "JP225", "STOXX50", "UK100", "US30", "US500", "USTEC")
METALS = ("XAUUSD", "XAGUSD")
OIL = ("XTIUSD", "XBRUSD")
SESSIONS = ((0, 8, "asia"), (8, 14, "london"), (14, 22, "ny"), (22, 24, "rollover"))
FILTERS = {"session": ("asia", "london", "ny"), "vol": ("low", "mid", "high"), "regime": ("trend", "range")}


def bloc(symbol):
    if symbol in INDICES:
        return "equities"
    if symbol in METALS:
        return "metals"
    if symbol in OIL:
        return "oil"
    if "USD" in symbol:
        return "usd"
    return "none"


def session(t_ms):
    t = np.asarray(t_ms, np.int64)
    h = ((t + ams_offset_ms(t)) // 3_600_000) % 24 if len(t) else np.zeros(0, np.int64)
    out = np.empty(len(t), dtype=object)
    for lo, hi, name in SESSIONS:
        out[(h >= lo) & (h < hi)] = name
    return out


K_JSON = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "regime_k.json")
K_WINDOW = ("2014-11", "2016-11")                     # [start, end) of the measurement window
K_POOLED = 3.56                                       # A4.5: pooled median of the 39 research symbols, measured 2026-11-12


@lru_cache(maxsize=1)
def regime_k():
    import json
    return {s: v["k"] for s, v in json.load(open(K_JSON))["symbols"].items()}


def _h4_raw(symbol):
    b = store.load_bars(symbol, "bars_h4")
    close_ms = b["open_ms"] + H4
    h, l, c = b["h"], b["l"], b["c"]
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    n = len(c)
    atr = np.full(n, np.nan)
    if n >= 14:
        atr[13] = tr[:14].mean()
        for i in range(14, n):
            atr[i] = (atr[i - 1] * 13 + tr[i]) / 14
    cs = np.cumsum(np.r_[0.0, c])
    sma = np.full(n, np.nan)
    if n >= 200:
        sma[199:] = (cs[200:] - cs[:-200]) / 200
    return close_ms, c, atr, sma


def build_regime_k(symbols):
    """A4.5: per-symbol k from closed h4 bars in the window; fewer than 12 months with bars there -> the pooled 3.56."""
    lo, hi = (int(np.datetime64(m, "M").astype("datetime64[ms]").astype(np.int64)) for m in K_WINDOW)
    out = {}
    for s in symbols:
        close_ms, c, atr, sma = _h4_raw(s)
        m = (close_ms >= lo) & (close_ms < hi) & ~np.isnan(sma) & ~np.isnan(atr) & (atr > 0)
        months = len(np.unique(close_ms[m].astype("datetime64[ms]").astype("datetime64[M]"))) if m.any() else 0
        if months >= 12:
            out[s] = {"k": round(float(np.median(np.abs(c[m] - sma[m]) / atr[m])), 3), "source": "own median", "months": months,
                      "bars": int(m.sum())}
        else:
            out[s] = {"k": K_POOLED, "source": "pooled (fewer than 12 months of h4 bars in the window)", "months": months,
                      "bars": int(m.sum())}
    return out


@lru_cache(maxsize=64)
def _h4(symbol):
    b = store.load_bars(symbol, "bars_h4")
    close_ms = b["open_ms"] + H4
    h, l, c = b["h"], b["l"], b["c"]
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    n = len(c)
    atr = np.full(n, np.nan)
    if n >= 14:
        atr[13] = tr[:14].mean()
        for i in range(14, n):
            atr[i] = (atr[i - 1] * 13 + tr[i]) / 14
    cs = np.cumsum(np.r_[0.0, c])
    sma = np.full(n, np.nan)
    if n >= 200:
        sma[199:] = (cs[200:] - cs[:-200]) / 200
    pct = np.full(n, np.nan)
    for i in range(14 + 100, n):                      # needs at least 100 earlier values
        hist = atr[max(13, i - LOOKBACK):i]
        pct[i] = (hist <= atr[i]).mean()
    trend_dir = np.where(np.isnan(sma), 0, np.where(c > sma, 1, -1))
    k = regime_k()[symbol]                            # DESIGN A4.5: the symbol's own threshold
    regime = np.where(np.isnan(sma) | np.isnan(atr), None, np.where(np.abs(c - sma) > k * atr, "trend", "range"))
    return close_ms, pct, trend_dir, regime


def at(symbol, t_ms):
    """Context at moments t_ms (UTC ms) from the last h4 bar closed at or before each: (vol_pct, vol third, trend_dir, regime)."""
    close_ms, pct, tdir, reg = _h4(symbol)
    t = np.asarray(t_ms, np.int64)
    i = np.searchsorted(close_ms, t, side="right") - 1
    ok = i >= 0
    j = np.where(ok, i, 0)
    vp = np.where(ok, pct[j], np.nan)
    third = np.where(np.isnan(vp), None, np.where(vp < 1 / 3, "low", np.where(vp < 2 / 3, "mid", "high")))
    return vp, third, np.where(ok, tdir[j], 0), np.where(ok, reg[j], None)


def filter_mask(symbol, decision_ms, filters):
    """True where every filter of the job holds at the decision moment (the bar's close). filters: e.g.
    {"session": "london", "vol": "high", "regime": "trend"}; unknown names or values are refused."""
    m = np.ones(len(decision_ms), bool)
    if not filters:
        return m
    for k, v in filters.items():
        if k not in FILTERS or v not in FILTERS[k]:
            raise ValueError(f"filter {k}={v}: the menu is {FILTERS}")
    if "session" in filters:
        m &= session(decision_ms) == filters["session"]
    if "vol" in filters or "regime" in filters:
        _, third, _, reg = at(symbol, decision_ms)
        if "vol" in filters:
            m &= third == filters["vol"]
        if "regime" in filters:
            m &= reg == filters["regime"]
    return m


def regime_shares(symbols=None):
    """DESIGN A3.4: share of closed h4 bars in 'trend' / 'range' per symbol over 2014-11 -> 2024-12 (a data description; no results)."""
    import os
    lo = int(np.datetime64("2014-11", "M").astype("datetime64[ms]").astype(np.int64))
    hi = int(np.datetime64("2025-01", "M").astype("datetime64[ms]").astype(np.int64))
    syms = symbols or sorted(d for d in os.listdir(store.STORE_ROOT) if os.path.isfile(os.path.join(store.STORE_ROOT, d, "meta.json")))
    out = {}
    for s in syms:
        close_ms, _, _, reg = _h4(s)
        m = (close_ms >= lo) & (close_ms <= hi) & (reg != None)  # noqa: E711
        n = int(m.sum())
        out[s] = {"h4_bars": n, "trend": round(float((reg[m] == "trend").mean()), 3) if n else None,
                  "range": round(float((reg[m] == "range").mean()), 3) if n else None}
    return out


if __name__ == "__main__":
    import json
    import os
    import sys
    res = regime_shares(sys.argv[1:] or None)
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data-checks", "regime-shares.json")
    json.dump({"about": "DESIGN A3.4: share of closed h4 bars in trend (|close - SMA 200| > k_symbol x ATR 14, DESIGN A4.5, engine/regime_k.json) vs range, 2014-11 -> 2024-12, "
                        "per symbol. A data description: no strategy results.", "symbols": res}, open(path, "w"), indent=1)
    tr = [v["trend"] for v in res.values() if v["trend"] is not None]
    print(f"{len(res)} symbols; trend share min {min(tr):.2f} median {sorted(tr)[len(tr)//2]:.2f} max {max(tr):.2f}")
    for s, v in sorted(res.items(), key=lambda kv: kv[1]["trend"] or 0):
        print(s, v)
