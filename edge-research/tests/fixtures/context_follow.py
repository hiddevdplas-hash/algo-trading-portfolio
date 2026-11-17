"""Test strategy (tests/test_context.py): trades the traded symbol in the direction of the context symbol's last closed bar, on
the traded bars where a new context bar has closed."""
import numpy as np

def intents(bars, params, ctx):
    n = len(bars["c"])
    cx = ctx["context"][params["ctx"]]
    up = cx["c"] > cx["o"]
    fresh = np.r_[False, cx["close_ms"][1:] != cx["close_ms"][:-1]]          # act only when a new context bar has closed
    side = np.where(fresh & up, 1, np.where(fresh & ~up & np.isfinite(cx["c"]), -1, 0))
    atr = np.abs(bars["h"] - bars["l"])
    return {"side": side.astype(np.int64), "sl_dist": np.maximum(atr * 1.5, ctx["tick"] * 10), "hold_ms": np.full(n, 3_600_000.0)}
