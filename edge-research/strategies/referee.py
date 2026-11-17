"""The 5 referee strategies (tests/referees/referees.py) behind the runner's strategy interface; params: {"ref": "R1"..."R5"}.
A referee is fixed to its symbol, timeframe and dates (runlists/REFEREES.md): a job with another symbol or timeframe is refused.
Only the direct IC run (tests/referees/referees.py) is comparable with cTrader; through the runner, class rules and news modes apply."""
from tests.referees import referees as RF


def intents(bars, params, ctx):
    sp = RF.SPECS[params["ref"]]
    if ctx["symbol"] != sp["symbol"] or ctx["timeframe"] != sp["tf"]:
        raise ValueError(f"referee {params['ref']} is {sp['symbol']} {sp['tf']}, not {ctx['symbol']} {ctx['timeframe']}")
    I, flat = RF.intents(params["ref"], bars, RF.Grid.from_ctx(ctx))
    I["flat_ms"] = flat
    return I
