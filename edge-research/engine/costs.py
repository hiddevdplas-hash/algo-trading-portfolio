"""Cost table (DESIGN §3.5, addendum A2): build engine/costs.json, and the functions the engine uses to charge costs.

  python -m engine.costs build        writes engine/costs.json (+ data-checks/cost-table.md, the readable report)

Judged on FTMO, IC shown. All costs end up in **price units of the symbol per unit of volume**, so a trade's cost in R is
cost / risk (its stop distance), with no account currency involved:
  - spread: the fill prices themselves. IC = IC's ticks. FTMO = IC's ticks widened by the add-on, half on each side
    (bid - a/2, ask + a/2), add-on = FTMO median spread - IC median spread, in basis points of mid (prices of gold and the
    indices moved 3-4x since 2014; a fixed price add-on would overcharge the early years), by New York hour where FTMO shows
    a pattern (FX, 2020-04 -> 2021-06), flat otherwise (feed reports, 2025-07 -> 2026-10). Never below 0.
  - commission, round trip: IC $3 per side per USD 100k of notional (FX, metals; 0 indices and oil). FTMO $5.00 per lot (100k)
    FX; metals 0.0027% of notional; 0 indices and oil.
  - swap per night, each side: P_t * (carry_t - markup) / 365, carry = r_base - r_quote for FX (long; the short is the opposite),
    r_base = 0 for gold, silver and indices. markup per symbol, venue and side, fitted on today's swaps and today's policy rates.
    Oil: today's swap as a share of price (it follows the futures curve, not rates), flagged. Triple night: the symbol's
    3-day weekday. Rollover at 17:00 New York.
  - slippage: 0 on limit orders; stop and market orders one extra spread inside +-2.5 min of a high-impact release (news calendar).
"""
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COSTS_JSON = os.path.join(REPO, "engine", "costs.json")
RATES_JSON = os.path.join(REPO, "engine", "policy_rates.json")
IC_RAW = os.path.expanduser("~/cAlgo/Exports/fastbt-ic-tick")
FTMO_RAW = [os.path.expanduser("~/cAlgo/Exports/fastbt-ftmo-tick"), os.path.expanduser("~/cAlgo/Exports/fastbt")]

# research symbols (IC names) -> FTMO names
FTMO_NAME = {"US500": "US500.cash", "USTEC": "US100.cash", "US30": "US30.cash", "DE40": "GER40.cash", "UK100": "UK100.cash",
             "JP225": "JP225.cash", "STOXX50": "EU50.cash", "XTIUSD": "USOIL.cash", "XBRUSD": "UKOIL.cash"}
INDEX_CCY = {"US500": "USD", "USTEC": "USD", "US30": "USD", "DE40": "EUR", "STOXX50": "EUR", "F40": "EUR", "UK100": "GBP",
             "JP225": "JPY", "AUS200": "AUD", "HK50": "HKD"}
OIL = ("XTIUSD", "XBRUSD")
METALS = ("XAUUSD", "XAGUSD")

# FTMO - IC median spread from the feed reports (tools/feedcheck/reports, 2025-07 -> 2026-10, UK100 from 2025-09), in the
# reports' pips (IC pip: FX 0.0001 / JPY 0.01, gold and oil 0.01, indices 0.1)
REPORT_SPREADS = {  # symbol: (IC median, FTMO median, pip)
    "XAUUSD": (8.0, 43.0, 0.01), "XTIUSD": (2.0, 8.2, 0.01), "US30": (12.0, 21.0, 0.1), "USTEC": (10.0, 15.0, 0.1),
    "US500": (5.0, 5.6, 0.1), "DE40": (5.0, 13.9, 0.1), "UK100": (9.0, 8.5, 0.1),
    # FX pairs that also have the 2025-26 window (compared with 2020-21 below; the larger is used)
    "EURUSD": (0.0, 0.1, 0.0001), "GBPUSD": (0.2, 0.5, 0.0001), "AUDUSD": (0.1, 0.4, 0.0001), "USDJPY": (0.1, 0.5, 0.01),
    "EURJPY": (0.5, 1.4, 0.01)}

FTMO_FX_COMMISSION_PER_LOT_RT = 5.00        # USD, confirmed by test trade 2026-11-10
FTMO_METAL_COMMISSION_PCT_RT = 0.0027       # % of notional: published $11.08 (gold) / $7.11 (silver) per lot at the 2 Nov prices
IC_COMMISSION_PER_MILLION_SIDE = 30.0       # USD per USD 1M notional per side (FX, metals)


# ------------------------------------------------------------------ helpers
def _meta(folder):
    return json.load(open(os.path.join(folder, "meta.json"), encoding="utf-8-sig"))


def _folders(roots):
    """symbol -> export folder; with several folders for one symbol the one with the most ticks; '_broken' folders skipped."""
    out, n = {}, {}
    for root in roots:
        if not os.path.isdir(root):
            continue
        for d in sorted(os.listdir(root)):
            p = os.path.join(root, d)
            if d.endswith("_broken") or not os.path.isfile(os.path.join(p, "meta.json")):
                continue
            m = _meta(p)
            if m["symbol"] not in out or int(m["tick_count"]) > n[m["symbol"]]:
                out[m["symbol"]], n[m["symbol"]] = p, int(m["tick_count"])
    return out


def asset_class(sym):
    if sym in METALS:
        return "metal"
    if sym in OIL:
        return "oil"
    if sym in INDEX_CCY:
        return "index"
    return "fx"


def carry_ccys(sym, base, quote):
    """(base currency or None, quote currency) for the carry formula."""
    if asset_class(sym) == "fx":
        return base, quote
    if asset_class(sym) == "index":
        return None, INDEX_CCY[sym]
    return None, "USD"                               # metals, oil


def rate_series(rates, ccy):
    s = rates[ccy]
    days = np.array([np.datetime64(d, "D") for d, _ in s])
    vals = np.array([v for _, v in s], dtype=float)
    return days, vals


def rate_at(rates, ccy, day):
    """Policy rate (%) in force on a UTC day (numpy datetime64[D] array or scalar)."""
    if ccy is None:
        return np.zeros(np.shape(day))
    days, vals = rate_series(rates, ccy)
    i = np.searchsorted(days, day, side="right") - 1
    if np.any(i < 0):
        raise ValueError(f"no {ccy} rate before {np.min(day)}")
    return vals[i]


# ------------------------------------------------------------------ swap fit
def swap_now(meta, price):
    """Today's swap per side as % of price per year (meta swaps are pips per unit per night, 'Pips' type)."""
    pip = float(meta["pip_size"])
    if meta.get("symbol_properties", {}).get("SwapCalculationType") not in ("Pips", None):
        raise ValueError(f"{meta['symbol']}: swap type {meta['symbol_properties'].get('SwapCalculationType')}")
    return {"long": meta["swap_long"] * pip * 365 / price * 100, "short": meta["swap_short"] * pip * 365 / price * 100}


def implied_rates_now(ic_metas, prices, known):
    """Fill currencies whose current policy rate wasn't read (NZD, JPY, HKD) from IC's swaps: rate gap = (long - short) / 2,
    median over the pairs that combine the currency with one whose rate is known."""
    out = dict(known)
    for ccy in [c for c, v in known.items() if v is None]:
        est = []
        for sym, m in ic_metas.items():
            b, q = carry_ccys(sym, m.get("base_asset"), m.get("quote_asset"))
            if ccy not in (b, q):
                continue
            other = q if b == ccy else b
            if other is not None and known.get(other) is None:
                continue
            sw = swap_now(m, prices[sym])
            gap = (sw["long"] - sw["short"]) / 2                  # = r_base - r_quote
            r_other = 0.0 if other is None else known[other]
            est.append(r_other + gap if b == ccy else r_other - gap)
        out[ccy] = round(float(np.median(est)), 2) if est else None
        out["_implied_" + ccy] = {"n_pairs": len(est), "values": [round(x, 2) for x in est]}
    return out


def fit_markups(metas, prices, now_rates):
    """markup (%/yr) per symbol and side = carry now - swap now. Oil: no markup, today's swap kept as a share of price."""
    out = {}
    for sym, m in metas.items():
        sw = swap_now(m, prices[sym])
        if asset_class(sym) == "oil":
            out[sym] = {"model": "fixed_pct", "long_pct": round(sw["long"], 4), "short_pct": round(sw["short"], 4)}
            continue
        b, q = carry_ccys(sym, m.get("base_asset"), m.get("quote_asset"))
        rb = 0.0 if b is None else now_rates[b]
        rq = now_rates[q]
        if rb is None or rq is None:
            out[sym] = {"model": "missing_rate"}
            continue
        carry = rb - rq
        out[sym] = {"model": "rate_gap", "base": b, "quote": q,
                    "markup_long": round(carry - sw["long"], 4), "markup_short": round(-carry - sw["short"], 4),
                    "swap_now_long_pct": round(sw["long"], 4), "swap_now_short_pct": round(sw["short"], 4)}
    return out


def fit_quality(fits):
    rep = {}
    for cls in ("fx", "index", "metal"):
        ml = [v["markup_long"] for s, v in fits.items() if v.get("model") == "rate_gap" and asset_class(s) == cls]
        ms = [v["markup_short"] for s, v in fits.items() if v.get("model") == "rate_gap" and asset_class(s) == cls]
        if ml:
            rep[cls] = {"n": len(ml), "long_median": round(float(np.median(ml)), 2),
                        "long_range": [round(min(ml), 2), round(max(ml), 2)],
                        "short_median": round(float(np.median(ms)), 2), "short_range": [round(min(ms), 2), round(max(ms), 2)]}
    return rep


# ------------------------------------------------------------------ spread add-ons
def ny_hour(t_ms):
    from engine.timeutil import ny_offset_ms
    return ((t_ms + ny_offset_ms(t_ms)) // 3_600_000) % 24


def read_ftmo_ticks(folder, first_ms, end_ms, chunksize=10_000_000):
    """FTMO export ticks in [first_ms, end_ms): stops reading at the first chunk past end_ms (never past 2024)."""
    import pandas as pd
    from engine.store import CUTOFF_MS
    end_ms = min(end_ms, CUTOFF_MS)
    parts = []
    for c in pd.read_csv(os.path.join(folder, "ticks.csv.gz"), compression="gzip", comment="B",
                         usecols=["time_ms", "bid", "ask"], dtype={"time_ms": np.int64, "bid": float, "ask": float},
                         chunksize=chunksize):
        t = c["time_ms"].values
        k = (t >= first_ms) & (t < end_ms)
        if k.any():
            parts.append((t[k], c["bid"].values[k], c["ask"].values[k]))
        if len(t) and t[-1] >= end_ms:
            break
    if not parts:
        return None
    return tuple(np.concatenate([p[i] for p in parts]) for i in range(3))


def hourly_spread_bp(t, bid, ask):
    """Median spread in bp of mid, overall and per New York hour; crossed ticks left out."""
    ok = ask >= bid
    t, bid, ask = t[ok], bid[ok], ask[ok]
    sp = (ask - bid) / ((ask + bid) / 2) * 1e4
    h = ny_hour(t)
    per = [float(np.median(sp[h == x])) if np.any(h == x) else float("nan") for x in range(24)]
    cnt = [int(np.sum(h == x)) for x in range(24)]
    return float(np.median(sp)), per, cnt


def fx_addon(sym, ftmo_folder, first="2020-04", last="2021-06"):
    """FTMO - IC spread (bp) for an FX pair, 2020-04 -> 2021-06, overall and by New York hour."""
    from engine import store
    f0 = int(np.datetime64(first + "-01", "ms").astype(np.int64))
    f1 = int((np.datetime64(last, "M") + 1).astype("datetime64[ms]").astype(np.int64))
    ft = read_ftmo_ticks(ftmo_folder, f0, f1)
    if ft is None or len(ft[0]) < 1_000_000:
        return {"status": "ftmo_too_short", "ftmo_ticks": 0 if ft is None else int(len(ft[0]))}
    ic = store.load_ticks(sym, first, last)
    # common span only
    lo, hi = max(ft[0][0], ic.t[0]), min(ft[0][-1], ic.t[-1])
    kf = (ft[0] >= lo) & (ft[0] <= hi)
    ki = (ic.t >= lo) & (ic.t <= hi)
    fo, fh, fc = hourly_spread_bp(ft[0][kf], ft[1][kf], ft[2][kf])
    io, ih, icn = hourly_spread_bp(ic.t[ki], ic.bid[ki], ic.ask[ki])
    add_h = [max(0.0, a - b) for a, b in zip(fh, ih)]
    add = max(0.0, fo - io)
    pattern = (max(add_h) - min(add_h)) > add
    mid = float(np.median((ic.bid[ki] + ic.ask[ki]) / 2))
    return {"status": "measured", "window": [datetime.fromtimestamp(lo / 1000, timezone.utc).strftime("%Y-%m-%d"),
                                             datetime.fromtimestamp(hi / 1000, timezone.utc).strftime("%Y-%m-%d")],
            "ftmo_ticks": int(kf.sum()), "ic_ticks": int(ki.sum()),
            "ic_median_bp": round(io, 4), "ftmo_median_bp": round(fo, 4), "addon_bp": round(add, 4),
            "hourly": pattern, "addon_bp_by_ny_hour": [round(x, 4) for x in add_h] if pattern else None,
            "mid": mid}


# ------------------------------------------------------------------ build
def build(log=print):
    from engine import store
    rates = json.load(open(RATES_JSON))
    ic_f = _folders([IC_RAW])
    ft_f = _folders(FTMO_RAW)
    ic_m = {s: _meta(p) for s, p in ic_f.items()}
    ft_m = {s: _meta(p) for s, p in ft_f.items()}
    # today's prices: IC's last price in each export (2026-11-04/05)
    prices = {s: (float(m["symbol_properties"]["Bid"]) + float(m["symbol_properties"]["Ask"])) / 2 for s, m in ic_m.items()}
    ic_name = {v: k for k, v in FTMO_NAME.items()}
    ft_prices = {s: prices[ic_name.get(s, s)] for s in ft_m if ic_name.get(s, s) in prices}

    now = {k: v for k, v in rates["verified"]["now_2026-11"].items() if not k.startswith("_")}
    now.setdefault("HKD", None)
    now = implied_rates_now(ic_m, prices, now)
    now_clean = {k: v for k, v in now.items() if not k.startswith("_")}
    ic_fit = fit_markups(ic_m, prices, now_clean)
    ft_fit_raw = fit_markups({ic_name.get(s, s): m for s, m in ft_m.items()}, {ic_name.get(s, s): p for s, p in ft_prices.items()},
                             now_clean)
    # FTMO exports that are broken for prices are fine for swaps (symbol settings are today's); NZDJPY's prices are 2020's,
    # so the IC price is used (done above via ft_prices).
    flags = []
    # FTMO UK100: positive long swap today (dividend adjustment or a setting error): not credible as a rate model
    if "UK100" in ft_fit_raw and ft_fit_raw["UK100"].get("swap_now_long_pct", 0) > 0:
        flags.append("FTMO UK100 long swap is positive today (%.1f%%/yr): treated as not credible; the median FTMO index markup is used."
                     % ft_fit_raw["UK100"]["swap_now_long_pct"])
        ft_fit_raw["UK100"]["excluded"] = True
    ftq = fit_quality({k: v for k, v in ft_fit_raw.items() if not v.get("excluded")})
    icq = fit_quality(ic_fit)

    symbols = sorted(ic_m)
    table = {}
    for sym in symbols:
        m = ic_m[sym]
        cls = asset_class(sym)
        b, q = carry_ccys(sym, m.get("base_asset"), m.get("quote_asset"))
        row = {"class": cls, "digits": int(m["digits"]), "lot_size": float(m["lot_size"]), "base": m.get("base_asset"),
               "quote": m.get("quote_asset"), "carry_base": b, "carry_quote": q,
               "swap_3day": m["symbol_properties"].get("Swap3DaysRollover"), "flags": []}
        # ---- commission
        ic_comm = IC_COMMISSION_PER_MILLION_SIDE if float(m["symbol_properties"].get("Commission", 0)) > 0 else 0.0
        row["ic"] = {"commission": {"type": "usd_per_million_notional_side", "value": ic_comm}}
        if cls == "fx":
            fcomm = {"type": "usd_per_lot_round_trip", "value": FTMO_FX_COMMISSION_PER_LOT_RT, "lot": 100_000}
        elif cls == "metal":
            fcomm = {"type": "pct_notional_round_trip", "value": FTMO_METAL_COMMISSION_PCT_RT}
            row["flags"].append("FTMO metal commission: published $ per lot as % of notional at the 2 Nov price; meta shows half")
        else:
            fcomm = {"type": "none", "value": 0.0}
        row["ftmo"] = {"commission": fcomm}
        # ---- swap
        row["ic"]["swap"] = ic_fit[sym]
        fsym = sym
        if sym in ft_fit_raw and not ft_fit_raw[sym].get("excluded") and ft_fit_raw[sym].get("model") != "missing_rate":
            row["ftmo"]["swap"] = dict(ft_fit_raw[sym], source="FTMO platform today")
        else:
            # no FTMO swap (not exported, or excluded): IC's markup + the median FTMO - IC markup gap of the class
            src = "IC markup + median FTMO-IC gap of the class"
            if cls == "oil":
                fo = ft_fit_raw.get("XTIUSD")
                row["ftmo"]["swap"] = dict(fo, source="FTMO USOIL as a share of price (Brent not exported)") if fo else ic_fit[sym]
            else:
                gaps_l = [ft_fit_raw[s]["markup_long"] - ic_fit[s]["markup_long"] for s in ft_fit_raw
                          if asset_class(s) == cls and ft_fit_raw[s].get("model") == "rate_gap" and not ft_fit_raw[s].get("excluded")
                          and ic_fit.get(s, {}).get("model") == "rate_gap"]
                gaps_s = [ft_fit_raw[s]["markup_short"] - ic_fit[s]["markup_short"] for s in ft_fit_raw
                          if asset_class(s) == cls and ft_fit_raw[s].get("model") == "rate_gap" and not ft_fit_raw[s].get("excluded")
                          and ic_fit.get(s, {}).get("model") == "rate_gap"]
                base = ic_fit[sym]
                if base.get("model") == "rate_gap" and gaps_l:
                    row["ftmo"]["swap"] = {"model": "rate_gap", "base": base["base"], "quote": base["quote"],
                                           "markup_long": round(base["markup_long"] + float(np.median(gaps_l)), 4),
                                           "markup_short": round(base["markup_short"] + float(np.median(gaps_s)), 4),
                                           "source": src}
                else:
                    row["ftmo"]["swap"] = dict(base, source="IC (no FTMO data, no class gap)")
            row["flags"].append("FTMO swap estimated: " + row["ftmo"]["swap"]["source"])
        if cls == "oil":
            for v in ("ic", "ftmo"):
                row[v]["swap"] = dict(row[v]["swap"], cap_positive=0.0)
            row["flags"].append("oil swap = today's swap as a share of price (follows the futures curve, not rates); "
                                "positive side capped at 0 (DESIGN A2)")
        if q == "HKD" or b == "HKD":
            row["flags"].append("HKD rate not in the policy table: swap model incomplete (HK50 is data only)")
        table[sym] = row

    # ---- spread add-ons
    addons = {}
    for sym in symbols:
        fname = FTMO_NAME.get(sym, sym)
        if asset_class(sym) == "fx" and fname in ft_f:
            log(f"spread add-on {sym} ...")
            addons[sym] = fx_addon(sym, ft_f[fname])
        else:
            addons[sym] = {"status": "not_measured_2020"}
        if sym in REPORT_SPREADS:
            ic_p, ft_p, pip = REPORT_SPREADS[sym]
            rep_bp = max(0.0, (ft_p - ic_p) * pip / prices[sym] * 1e4)
            addons[sym]["report_2025_26_bp"] = round(rep_bp, 4)
    sp25 = os.path.join(REPO, "data-checks", "spreads-2025-26.json")
    if os.path.isfile(sp25):
        for sym, r in json.load(open(sp25))["symbols"].items():
            if "bp_q25_50_75_95" not in r.get("ic", {}) or "bp_q25_50_75_95" not in r.get("ftmo", {}):
                continue
            ic_o, ft_o = r["ic"]["bp_q25_50_75_95"][1], r["ftmo"]["bp_q25_50_75_95"][1]
            add = max(0.0, ft_o - ic_o)
            add_h = []
            for hi, hf in zip(r["ic"]["by_ny_hour"], r["ftmo"]["by_ny_hour"]):
                if hi["n"] >= 1000 and hf["n"] >= 1000:
                    add_h.append(max(0.0, hf["bp_q25_50_75_95"][1] - hi["bp_q25_50_75_95"][1]))
                else:
                    add_h.append(add)                  # too few ticks in that hour (market mostly closed): the overall value
            pattern = (max(add_h) - min(add_h)) > add
            addons[sym] = {"status": "measured_2025_26", "ic_median_bp": ic_o, "ftmo_median_bp": ft_o,
                           "final_bp": round(add, 4), "hourly": pattern,
                           "addon_bp_by_ny_hour": [round(x, 4) for x in add_h] if pattern else None,
                           "source": "FTMO vs IC spreads 2025-07 -> 2026-10 (DESIGN A2, spreads only)"}
    for sym in symbols:
        a = addons[sym]
        if a.get("status") == "measured_2025_26":
            continue
        if a.get("status") == "measured":
            final = a["addon_bp"]
            src = "FTMO vs IC ticks %s -> %s" % tuple(a["window"])
            if "report_2025_26_bp" in a and a["report_2025_26_bp"] > final:
                final, src = a["report_2025_26_bp"], "feed report 2025-07 -> 2026-10 (larger than 2020-21)"
                a["hourly"] = False
                a["addon_bp_by_ny_hour"] = None
            a.update(final_bp=round(final, 4), source=src)
        elif "report_2025_26_bp" in a:
            a.update(final_bp=a["report_2025_26_bp"], source="feed report 2025-07 -> 2026-10 (flat)")
    # unmeasured: the most similar measured symbol, flagged
    measured = {s: a for s, a in addons.items() if "final_bp" in a}
    for sym in symbols:
        a = addons[sym]
        if "final_bp" in a:
            continue
        cls = asset_class(sym)
        if cls == "fx":
            # same quote currency, closest IC median spread in bp
            ccy = table[sym]["quote"]
            cands = [s for s in measured if asset_class(s) == "fx" and table[s]["quote"] == ccy] or \
                    [s for s in measured if asset_class(s) == "fx"]
            proxy = sorted(cands)[len(cands) // 2] if cands else None
            vals = [measured[s]["final_bp"] for s in cands]
            a.update(final_bp=round(float(np.median(vals)), 4), source=f"median of measured FX pairs quoted in {ccy}: {', '.join(sorted(cands))}")
        elif cls == "metal":
            a.update(final_bp=measured["XAUUSD"]["final_bp"], source="XAUUSD (bp of price)")
        elif cls == "oil":
            a.update(final_bp=measured["XTIUSD"]["final_bp"], source="XTIUSD (bp of price)")
        else:
            idx = [s for s in measured if asset_class(s) == "index"]
            a.update(final_bp=round(float(np.median([measured[s]["final_bp"] for s in idx])), 4),
                     source="median of measured indices: " + ", ".join(sorted(idx)))
        a["flag"] = "add-on not measured for this symbol"
        table[sym]["flags"].append("FTMO spread add-on from " + a["source"])
    for sym in symbols:
        table[sym]["ftmo"]["spread_addon_bp"] = addons[sym]["final_bp"]
        table[sym]["ftmo"]["spread_addon_bp_by_ny_hour"] = addons[sym].get("addon_bp_by_ny_hour")
        table[sym]["ftmo"]["spread_source"] = addons[sym]["source"]
        table[sym]["ic"]["spread_addon_bp"] = 0.0
        if sym in METALS or asset_class(sym) != "fx":
            pass
        if any(k in addons[sym]["source"] for k in ("2020", "report", "2025")):
            table[sym]["flags"].append("FTMO data starts 2020-04: before that the add-on assumes FTMO's markup over IC stayed the same")

    out = {
        "version": "v2",
        "built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "judged_on": "ftmo", "shown": ["ic"],
        "rules": {
            "spread": "fills on IC ticks; FTMO = bid - a/2, ask + a/2, a = add-on bp x mid (by New York hour where given); IC = raw ticks",
            "commission": "round trip, charged at the close, converted to price units of the symbol per unit",
            "swap": "per night held over 17:00 New York; triple on swap_3day; per unit = P x (carry - markup)/365 (%/yr), "
                    "carry long = r_base - r_quote, short = -(r_base - r_quote); oil: P x min(fixed_pct, 0)/365 (DESIGN A2)",
            "slippage": "limit 0; stop and market: one extra spread inside +-2.5 min of a high-impact release",
            "stress_G2": {"spread_mult": 1.5, "swap_mult_class_BC": 1.5, "positive_swap": 0.0},
        },
        "rates_now_2026_11": now,
        "swap_fit_quality": {"ic": icq, "ftmo": ftq},
        "flags": flags,
        "addon_detail": addons,
        "symbols": table,
    }
    json.dump(out, open(COSTS_JSON, "w"), indent=1)
    return out


def report(out, path=os.path.join(REPO, "data-checks", "cost-table.md")):
    """Readable summary of costs.json: per symbol, FTMO and IC round-trip cost in bp at the median IC spread, and swap."""
    from engine import store
    lines = ["# Cost table %s (`engine/costs.json`, built %s UTC)" % (out["version"], out["built_utc"]), "",
             "Judged on **FTMO**, IC shown (DESIGN §3.5). Spread add-on and commission in **basis points of price**, round trip.",
             "Swap = today's model value in %/yr of price (negative = a charge), long / short; history follows the policy rates.", "",
             "| symbol | class | IC spread bp (median 2024) | FTMO add-on bp | FTMO add-on source | comm. bp FTMO / IC | swap now FTMO L / S | swap now IC L / S |",
             "|---|---|---|---|---|---|---|---|"]
    for sym, r in out["symbols"].items():
        try:
            tk = store.load_ticks(sym, "2024-06", "2024-06")
            ok = tk.ask >= tk.bid
            mid = (tk.ask[ok] + tk.bid[ok]) / 2
            ic_bp = float(np.median((tk.ask[ok] - tk.bid[ok]) / mid * 1e4))
            px = float(np.median(mid))
        except Exception:
            ic_bp, px = float("nan"), None
        def comm_bp(v):
            c = r[v]["commission"]
            if c["type"] == "none" or not c["value"]:
                return 0.0
            if c["type"] == "usd_per_lot_round_trip":
                # USD per unit / (USD value of one unit of base): approximate with the price for USD-quoted, 1 for USD-based
                base_usd = px if r["quote"] == "USD" else (1.0 if r["base"] == "USD" else None)
                return None if base_usd is None or px is None else c["value"] / c["lot"] / base_usd * 1e4
            if c["type"] == "usd_per_million_notional_side":
                return 2 * c["value"] / 1e6 * 1e4
            return c["value"] / 100 * 1e4
        def sw(v):
            s = r[v]["swap"]
            if s.get("model") == "fixed_pct":
                cap = s.get("cap_positive")
                lo, sh = (min(s["long_pct"], cap), min(s["short_pct"], cap)) if cap is not None else (s["long_pct"], s["short_pct"])
                return "%.1f / %.1f (fixed%s)" % (lo, sh, ", capped at 0" if cap is not None else "")
            if s.get("model") != "rate_gap":
                return "n/a"
            rn = out["rates_now_2026_11"]
            rb = 0.0 if s["base"] is None else (rn.get(s["base"]) or 0.0)
            rq = rn.get(s["quote"])
            if rq is None:
                return "n/a"
            return "%.2f / %.2f" % (rb - rq - s["markup_long"], -(rb - rq) - s["markup_short"])
        cf, ci = comm_bp("ftmo"), comm_bp("ic")
        fmt = lambda x: "≈1.0" if x is None else "%.2f" % x
        lines.append("| %s | %s | %.2f | %.2f%s | %s | %s / %s | %s | %s |" % (
            sym, r["class"], ic_bp, r["ftmo"]["spread_addon_bp"], " (hourly)" if r["ftmo"].get("spread_addon_bp_by_ny_hour") else "",
            r["ftmo"]["spread_source"], fmt(cf), fmt(ci), sw("ftmo"), sw("ic")))
    q = out["swap_fit_quality"]
    lines += ["", "## Swap fit quality (markup %/yr, median and range across symbols)", "",
              "| venue | class | n | long median | long range | short median | short range |", "|---|---|---|---|---|---|---|"]
    for v in ("ic", "ftmo"):
        for cls, d in q[v].items():
            lines.append("| %s | %s | %d | %.2f | %.2f … %.2f | %.2f | %.2f … %.2f |" % (
                v, cls, d["n"], d["long_median"], *d["long_range"], d["short_median"], *d["short_range"]))
    lines += ["", "Policy rates now (2026-11): " + ", ".join("%s %s" % (k, v) for k, v in out["rates_now_2026_11"].items()
                                                         if not k.startswith("_")), "",
              "## Flags", ""] + ["- " + f for f in out["flags"]]
    per = sorted({f for r in out["symbols"].values() for f in r["flags"]})
    lines += ["", "### Per-symbol flags (distinct)", ""] + ["- " + f for f in per]
    open(path, "w").write("\n".join(lines) + "\n")
    return path


# ------------------------------------------------------------------ runtime (used by the engine)
def load(path=COSTS_JSON):
    return json.load(open(path))


def swap_rate_pct(costs, sym, venue, side, day):
    """Swap in %/yr of price for a side ('long' / 'short') on UTC days (datetime64[D]). Negative = a charge."""
    rates = json.load(open(RATES_JSON))
    s = costs["symbols"][sym][venue]["swap"]
    if s["model"] == "fixed_pct":
        v = s[side + "_pct"]
        if s.get("cap_positive") is not None:          # DESIGN A2: oil's positive swap capped at 0
            v = min(v, s["cap_positive"])
        return np.full(np.shape(day), v, dtype=float)
    carry = rate_at(rates, s["base"], day) - rate_at(rates, s["quote"], day)
    if side == "short":
        carry = -carry
    return carry - s["markup_" + side]


def commission_px(costs, sym, venue, base_usd, quote_usd):
    """Round-trip commission in price units per unit. base_usd: USD per unit of base (for metals and FX notional);
    quote_usd: USD per unit of quote currency."""
    row = costs["symbols"][sym]
    c = row[venue]["commission"]
    if c["type"] == "none" or c["value"] == 0:
        return 0.0 * base_usd
    if c["type"] == "usd_per_lot_round_trip":
        usd = c["value"] / c["lot"]
    elif c["type"] == "usd_per_million_notional_side":
        usd = 2 * c["value"] / 1e6 * base_usd
    elif c["type"] == "pct_notional_round_trip":
        usd = c["value"] / 100 * base_usd
    else:
        raise ValueError(c["type"])
    return usd / quote_usd


def main(argv=None):
    a = (argv or sys.argv[1:])
    if a[:1] == ["build"]:
        out = build()
        report(out)
        print(json.dumps({"swap_fit_quality": out["swap_fit_quality"], "flags": out["flags"],
                          "rates_now": out["rates_now_2026_11"]}, indent=1))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
