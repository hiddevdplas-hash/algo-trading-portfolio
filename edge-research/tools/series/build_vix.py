"""DESIGN A14 §2 (user approval 2026-11-17): CBOE VIX / VIX3M / VIX9D daily history (../data/vix-yields, raw) -> research series store
(../data/series-2014-2024/vix/<NAME>.npz): day (days since 1970-01-01), release_ms = 16:15 New York on that day (the close is
public then; the later candidate), open / high / low / close. Values released at or after 2025-01-01 00:00 UTC are never stored.
Not revised after publication (CBOE). <NAME>.json: source sha256, rows read / stored / cut, max release.

  ~/.venvs/fastbt/bin/python -m tools.series.build_vix
"""
import csv, datetime as dt, hashlib, json, os, sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from engine import series as S  # noqa: E402

RAW = os.path.expanduser("~/Projects/Algo Trading/data/vix-yields")


def build(name, raw=RAW, out=None):
    out = out or os.path.join(S.SERIES_ROOT, "vix")
    p = os.path.join(raw, f"{name}_History.csv")
    rows, n, cut = [], 0, 0
    with open(p, newline="") as fh:
        rd = csv.reader(fh)
        header = [h.strip().upper() for h in next(rd)]
        if header[:5] != ["DATE", "OPEN", "HIGH", "LOW", "CLOSE"]:
            raise ValueError(f"{p}: columns {header}")
        for row in rd:
            if not row:
                continue
            n += 1
            d = dt.datetime.strptime(row[0].strip(), "%m/%d/%Y").date()
            rel = S.ny_ms(d, 16, 15)
            if rel >= S.RESEARCH_END_MS:
                cut += 1
                continue
            rows.append(((d - dt.date(1970, 1, 1)).days, rel, *[float(x) for x in row[1:5]]))
    rows.sort()
    if len({r[0] for r in rows}) != len(rows):
        raise ValueError(f"{name}: a day appears twice")
    a = np.array(rows)
    os.makedirs(out, exist_ok=True)
    np.savez_compressed(os.path.join(out, name + ".npz"), day=a[:, 0].astype(np.int32), release_ms=a[:, 1].astype(np.int64),
                        open=a[:, 2], high=a[:, 3], low=a[:, 4], close=a[:, 5])
    meta = {"series": name, "source": os.path.basename(p), "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(),
            "rows_read": n, "rows_stored": len(rows), "rows_cut": cut, "cut_rule": "release_ms >= 2025-01-01 00:00 UTC",
            "release_rule": "16:15 New York on the day (later candidate)", "revised": "no (CBOE daily history)",
            "first_day": str(dt.date(1970, 1, 1) + dt.timedelta(days=int(a[0, 0]))),
            "max_release_utc": dt.datetime.fromtimestamp(int(a[:, 1].max()) / 1000, dt.timezone.utc).isoformat()}
    json.dump(meta, open(os.path.join(out, name + ".json"), "w"), indent=1)
    return meta


if __name__ == "__main__":
    for nm in S.VIX_NAMES:
        m = build(nm)
        print(nm, m["rows_read"], m["rows_stored"], m["rows_cut"], m["first_day"], m["max_release_utc"])
