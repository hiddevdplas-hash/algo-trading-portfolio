"""Test strategy (tests/test_e2e_route.py): the null random entries, except no intent at all on XBRUSD (like a module keyed on a
symbol name the store doesn't use)."""
import numpy as np

from strategies.null_random import intents as _base


def intents(bars, params, ctx):
    out = dict(_base(bars, params, ctx))
    if ctx["symbol"] == "XBRUSD":
        out["side"] = np.zeros(len(bars["open_ms"]), int)
    return out
