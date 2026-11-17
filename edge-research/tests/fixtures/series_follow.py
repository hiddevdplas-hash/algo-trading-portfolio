"""Test strategy (tests/test_context.py): short when the last released VIX close is above 20, long otherwise, on the first bar
after each new VIX value; every bar stopped at 1.5 x its range."""
import numpy as np


def intents(bars, params, ctx):
    n = len(bars["c"])
    v = ctx["series"]["vix:VIX:close"]
    assert len(ctx["series"]["calendar:quarterly_expiry"]["dates_ms"]) > 0
    fresh = np.r_[False, v["release_ms"][1:] != v["release_ms"][:-1]] & np.isfinite(v["value"])
    side = np.where(fresh, np.where(v["value"] > 20, -1, 1), 0)
    rng = np.abs(bars["h"] - bars["l"])
    return {"side": side.astype(np.int64), "sl_dist": np.maximum(rng * 1.5, ctx["tick"] * 10), "hold_ms": np.full(n, 3_600_000.0)}
