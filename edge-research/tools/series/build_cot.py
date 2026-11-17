"""DESIGN A14 §2: CFTC COT raw zips (../data/cftc-cot, approved 2026-11-17) -> research series store (../data/series-2014-2024/cot).

Per report (legacy / disagg / tff) one <report>.npz: code (CFTC contract market code), asof_day (days since 1970-01-01), release_ms
(engine.series.cot_release_ms: the actual release, later candidate when unsure), cols (numeric column names), values (float64, NaN
where blank or not a number); plus <report>.json: market names per code, source files with sha256, rows read, rows cut (release at
or after 2025-01-01 00:00 UTC: never stored), max release. Raw files stay outside the store. Rebuild = same output.

  ~/.venvs/fastbt/bin/python -m tools.series.build_cot
"""
import csv, datetime as dt, hashlib, io, json, os, sys, zipfile

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from engine import series as S  # noqa: E402

RAW = os.path.expanduser("~/Projects/Algo Trading/data/cftc-cot")
OUT = os.path.join(S.SERIES_ROOT, "cot")
PATTERNS = {"legacy": "deacot", "disagg": "fut_disagg_txt_", "tff": "fut_fin_txt_"}


def build(report, raw=RAW, out=OUT):
    files = sorted(f for f in os.listdir(raw) if f.startswith(PATTERNS[report]) and f.endswith(".zip"))
    rows, names, src, n_read, cut = [], {}, [], 0, []
    header0 = None
    for f in files:
        p = os.path.join(raw, f)
        src.append({"file": f, "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest()})
        with zipfile.ZipFile(p) as z:
            for member in z.namelist():
                rd = csv.reader(io.TextIOWrapper(z.open(member), encoding="latin-1", newline=""))
                header = [h.strip() for h in next(rd)]
                header0 = header0 or header
                ai, ci, ni, yi = S._asof_col(header), S._code_col(header), 0, S._yymmdd_col(header)
                if [h for k, h in enumerate(header) if k != ai] != [h for k, h in enumerate(header0) if k != S._asof_col(header0)]:
                    raise ValueError(f"{f}: columns differ from the first file's (other than the as-of label)")
                for row in rd:
                    if len(row) < len(header):
                        continue
                    n_read += 1
                    a = dt.date.fromisoformat(row[ai].strip()[:10])
                    if row[yi].strip() != a.strftime("%y%m%d"):
                        raise ValueError(f"{f}: as-of {row[ai]!r} vs YYMMDD {row[yi]!r}")
                    rel = S.cot_release_ms(a)
                    code = row[ci].strip()
                    if rel >= S.RESEARCH_END_MS:
                        cut.append([code, str(a), rel])
                        continue
                    names.setdefault(code, row[ni].strip())
                    rows.append((code, (a - dt.date(1970, 1, 1)).days, rel, row))
    num = [i for i, h in enumerate(header0) if i not in (S._asof_col(header0), S._code_col(header0), S._yymmdd_col(header0), 0)
           and not h.lower().startswith(("as of", "as_of", "cftc_", "cftc ", "market", "report_date"))]

    def f(x):
        x = x.strip()
        try:
            return float(x)
        except ValueError:
            return np.nan
    rows.sort(key=lambda r: (r[0], r[1]))
    keys = [(r[0], r[1]) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{report}: a (code, as-of) appears twice")
    os.makedirs(out, exist_ok=True)
    vals = np.array([[f(r[3][i]) for i in num] for r in rows], dtype=np.float64)
    np.savez_compressed(os.path.join(out, report + ".npz"), code=np.array([r[0] for r in rows]),
                        asof_day=np.array([r[1] for r in rows], np.int32), release_ms=np.array([r[2] for r in rows], np.int64),
                        cols=np.array([header0[i] for i in num]), values=vals)
    meta = {"report": report, "source_files": src, "rows_read": n_read, "rows_stored": len(rows), "rows_cut": len(cut),
            "cut_rule": "release_ms >= 2025-01-01 00:00 UTC (never stored)", "cut_asofs": sorted({c[1] for c in cut}),
            "max_release_utc": dt.datetime.fromtimestamp(max(r[2] for r in rows) / 1000, dt.timezone.utc).isoformat(),
            "first_asof": str(dt.date(1970, 1, 1) + dt.timedelta(days=min(r[1] for r in rows))),
            "markets": names, "vintage": "current (CFTC history files re-posted after release; DESIGN A14 §2.3, not point-in-time)",
            "built_with_engine_series": hashlib.sha256(open(S.__file__, "rb").read()).hexdigest()[:12]}
    json.dump(meta, open(os.path.join(out, report + ".json"), "w"), indent=1)
    return meta


if __name__ == "__main__":
    for r in PATTERNS:
        m = build(r)
        print(r, m["rows_read"], m["rows_stored"], m["rows_cut"], m["cut_asofs"], m["max_release_utc"], m["first_asof"], len(m["markets"]))
