"""Data check for one FastBtExport tick folder, in one read-only pass: per-month tick counts and trading days, spreads,
crossed (ask < bid) and zero-spread ticks, timestamps that run backwards, silences over 6 h on weekdays, holes over 4 days,
months far thinner than their neighbours, and a check against meta.json's own counts.
Usage: data_check.py <export folder> <output folder>      → <output folder>/<folder name>.json"""
import json, os, sys
import numpy as np
import pandas as pd

folder, out = sys.argv[1], sys.argv[2]
name = os.path.basename(folder.rstrip("/"))
meta = json.load(open(os.path.join(folder, "meta.json")))
pip = meta["pip_size"]
M, gaps = {}, []
last = None
rows = bars = nonfinite = back = 0
first_ms = None
for chunk in pd.read_csv(os.path.join(folder, "ticks.csv.gz"), header=0, usecols=[0, 1, 2], names=["a", "b", "c"], chunksize=5_000_000, dtype=str, compression="gzip"):
    isbar = chunk["a"] == "B"
    bars += int(isbar.sum())
    t = chunk[~isbar]
    ms = pd.to_numeric(t["a"], errors="coerce").to_numpy()
    bid = pd.to_numeric(t["b"], errors="coerce").to_numpy()
    ask = pd.to_numeric(t["c"], errors="coerce").to_numpy()
    ok = np.isfinite(ms)
    ms, bid, ask = ms[ok].astype("int64"), bid[ok], ask[ok]
    if not len(ms):
        continue
    rows += len(ms)
    if first_ms is None:
        first_ms = int(ms[0])
    fin = np.isfinite(bid) & np.isfinite(ask)
    nonfinite += int(np.sum(~fin))
    full = np.concatenate([[last], ms]) if last is not None else ms
    d = np.diff(full)
    back += int(np.sum(d < 0))
    for i in np.where(d > 6 * 3_600_000)[0]:
        gaps.append((int(full[i]), int(full[i + 1])))
    last = int(ms[-1])
    ms, bid, ask = ms[fin], bid[fin], ask[fin]
    sp = np.round(ask - bid, 8)
    df = pd.DataFrame({"ym": pd.to_datetime(ms, unit="ms").strftime("%Y-%m"), "sp": sp, "day": ms // 86_400_000, "mid": (ask + bid) / 2})
    for k, g in df.groupby("ym"):
        m = M.setdefault(k, dict(n=0, days=set(), sp=[], mid=[], neg=0, zero=0, negsum=0.0, worst=0.0, negdays=set()))
        neg = g["sp"] < 0
        m["n"] += len(g)
        m["days"].update(g["day"].unique().tolist())
        m["neg"] += int(neg.sum())
        m["zero"] += int((g["sp"] == 0).sum())
        if neg.any():
            m["negsum"] += float(g.loc[neg, "sp"].sum())
            m["worst"] = min(m["worst"], float(g["sp"].min()))
            m["negdays"].update(g.loc[neg, "day"].unique().tolist())
        s = g.sample(min(len(g), 40_000), random_state=1)
        m["sp"].append(s["sp"].to_numpy())
        m["mid"].append(s["mid"].to_numpy())


def spans_saturday(a, b):
    r = pd.date_range(pd.to_datetime(a, unit="ms").normalize(), pd.to_datetime(b, unit="ms").normalize())
    return any(x.weekday() == 5 for x in r)


weekday, long_gaps = [], []
for a, b in gaps:
    h = (b - a) / 3_600_000
    rec = (str(pd.to_datetime(a, unit="ms"))[:16], str(pd.to_datetime(b, unit="ms"))[:16], round(h, 1))
    if h > 96:
        long_gaps.append(rec)
    elif not spans_saturday(a, b):
        weekday.append(rec)
table = []
for k in sorted(M):
    m = M[k]
    s, p = np.concatenate(m["sp"]), np.concatenate(m["mid"])
    table.append(dict(ym=k, ticks=m["n"], days=len(m["days"]), sp_med_pips=float(np.median(s) / pip), sp_p95_pips=float(np.quantile(s, .95) / pip),
                      sp_bp=float(np.median(s / p) * 1e4), crossed=m["neg"], crossed_share=m["neg"] / m["n"], zero_share=m["zero"] / m["n"],
                      crossed_mean_pips=(m["negsum"] / m["neg"] / pip) if m["neg"] else 0.0, crossed_worst_pips=m["worst"] / pip, crossed_days=len(m["negdays"])))
ticks = np.array([t["ticks"] for t in table])
thin = []
for i, t in enumerate(table):
    nb = np.r_[ticks[max(0, i - 3):i], ticks[i + 1:i + 4]]
    if 0 < i < len(table) - 1 and len(nb) and t["ticks"] < .4 * np.median(nb):
        thin.append(t["ym"])
res = dict(folder=name, symbol=meta["symbol"], pip=pip, rows=rows, meta_ticks=int(meta["tick_count"]), bars=bars, meta_bars=int(meta["bar_close_count"]),
           first=str(pd.to_datetime(first_ms, unit="ms"))[:16], last=str(pd.to_datetime(last, unit="ms"))[:16], nonfinite=nonfinite, backwards=back,
           crossed_total=int(sum(m["neg"] for m in M.values())), holes_over_4_days=long_gaps, weekday_silences_over_6h=weekday, thin_months=thin, months=table)
json.dump(res, open(os.path.join(out, name + ".json"), "w"), indent=1)
print(name, "done", rows, flush=True)
