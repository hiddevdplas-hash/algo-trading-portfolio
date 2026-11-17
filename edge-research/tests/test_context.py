"""DESIGN A14.1: context symbols (engine/inputs.py, runner). Alignment on the real store, staleness, the declared list, and a run
through the real runner on a temporary ledger."""
import json
import os
import time

import numpy as np
import pytest

from engine import data, inputs as IN, runner as R

H1 = 3_600_000


def test_alignment_is_last_closed_context_bar():
    t = data.bars("EURUSD", "h1")
    sel = (t["open_ms"] >= R.month_ms("2019-01")) & (t["close_ms"] <= R.month_ms("2019-03", end=True))
    close = t["close_ms"][sel]
    a = IN.context(["US500"], "h1", close, R.month_ms("2024-12", end=True))["US500"]
    raw = data.bars("US500", "h1")
    cc = raw["close_ms"]
    holes = IN.holes("US500")
    assert len(a["c"]) == len(close)
    for i in range(len(close)):
        j = np.searchsorted(cc, close[i], side="right") - 1
        assert j + 1 == len(cc) or cc[j + 1] > close[i]                     # no later-closing bar exists before the decision
        if np.isnan(a["c"][i]):                                             # only inside a data hole
            assert a["close_ms"][i] == -1 and a["age_ms"][i] == -1
            assert any(raw["open_ms"][j] <= s < close[i] for s, _ in holes) or any(raw["open_ms"][j] < s <= close[i] for s, _ in holes)
            continue
        assert a["close_ms"][i] == cc[j] <= close[i] and a["age_ms"][i] == close[i] - cc[j]
        assert a["c"][i] == raw["c"][j] and a["o"][i] == raw["o"][j] and a["h"][i] == raw["h"][j]
    age = a["age_ms"][a["age_ms"] >= 0]
    assert age.min() == 0 and age.max() >= 48 * H1                           # weekends: US500 shut while EURUSD reopens (stale)
    assert set(a) == {"open_ms", "close_ms", "age_ms", "o", "h", "l", "c"}  # no tick volume, nothing unaligned


def test_data_hole_is_nan_never_stale():
    """A14.1.2: XTIUSD's Sep-Nov 2017 outages (A8.8) and the 10-19 Oct 2014 hole give NaN, not the last value before them."""
    holes = IN.holes("XTIUSD")
    assert any(np.datetime64(int(s), "ms").astype("datetime64[M]") == np.datetime64("2017-09") for s, _ in holes)
    s0, e0 = [h for h in holes if h[0] >= R.month_ms("2017-09")][0]
    b = data.bars("EURUSD", "m15")
    inside = b["close_ms"][(b["close_ms"] > s0) & (b["close_ms"] <= e0)]
    a = IN.context(["XTIUSD"], "m15", inside, R.month_ms("2024-12", end=True))["XTIUSD"]
    assert len(inside) and np.isnan(a["c"]).all() and (a["close_ms"] == -1).all()
    after = b["close_ms"][b["close_ms"] > e0 + 2 * H1][:5]                  # fresh again once a bar after the hole has closed
    a = IN.context(["XTIUSD"], "m15", after, R.month_ms("2024-12", end=True))["XTIUSD"]
    assert np.isfinite(a["c"]).all() and (a["close_ms"] > e0).all()
    b = data.bars("US500", "h1")                                            # FX context in the FX quarantine: NaN
    c = b["close_ms"][(b["close_ms"] > R.month_ms("2015-06")) & (b["close_ms"] < R.month_ms("2015-06") + 5 * 24 * H1)]
    a = IN.context(["EURUSD"], "h1", c, R.month_ms("2024-12", end=True))["EURUSD"]
    assert len(c) and np.isnan(a["c"]).all()
    us = IN.holes("US500")
    assert any(R.month_ms("2014-10") <= s < R.month_ms("2014-11") and e - s > 5 * 24 * H1 for s, e in us)   # Oct 2014


def test_before_first_context_bar_and_period_end():
    raw = data.bars("DE40", "h4")                                           # DE40 starts 2021-09 in the store
    close = np.array([R.month_ms("2015-03"), raw["close_ms"][5], R.month_ms("2030-01")], np.int64)
    a = IN.context(["DE40"], "h4", close, R.month_ms("2024-12", end=True))["DE40"]
    assert a["close_ms"][0] == -1 and np.isnan(a["c"][0])
    assert a["close_ms"][1] == raw["close_ms"][5]
    assert a["close_ms"][2] <= R.month_ms("2024-12", end=True)               # nothing past the period end


def test_card_row_and_checks():
    assert IN.card_context("| x | y |\n") is None
    assert IN.card_context("| context symbols | none |\n") == []
    assert IN.card_context("| context symbols (A14.1) | US500, UK100 |\n") == ["US500", "UK100"]
    with pytest.raises(ValueError, match="not in the research store"):
        IN.card_context("| context symbols | US500, EU50 |\n")
    with pytest.raises(ValueError, match="at most 3"):
        IN.card_context("| context symbols | US500, UK100, DE40, JP225 |\n")
    with pytest.raises(ValueError, match="twice"):
        IN.card_context("| context symbols | US500 |\n| context symbols | UK100 |\n")
    with pytest.raises(ValueError, match="never traded"):
        IN.check_context(["US500"], ["US500", "EURUSD"])


CARD = ("| data-mined | no |\n| seen family | no |\n| source overlap | no |\n| source overlap, why | test |\n| grid size | 1 |\n"
        "| context symbols | US500 |\n")


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    runs = os.path.join(R.REPO, "runs", "_ctx", f"{time.strftime('%Y%m%d%H%M%S')}-{os.getpid()}-{time.time_ns()}")
    os.makedirs(runs, exist_ok=True)
    monkeypatch.setattr(R, "LEDGER", str(tmp_path / "ledger"))
    monkeypatch.setattr(R, "QUEUE", str(tmp_path / "queue"))
    monkeypatch.setattr(R, "RUNS", runs)
    cards = os.path.join(R.REPO, "runs", "_test_cards")
    os.makedirs(cards, exist_ok=True)
    open(os.path.join(cards, "ctx.md"), "w").write(CARD)
    open(os.path.join(cards, "noctx.md"), "w").write(CARD.replace("| context symbols | US500 |\n", ""))
    return tmp_path


def _job(**kw):
    j = {"idea_id": "IDEA-CTX", "card": "runs/_test_cards/ctx.md", "lane": "market logic", "stage": "screen",
         "strategy": "tests/fixtures/context_follow.py:intents", "symbols": ["EURUSD"], "timeframe": "h1",
         "period": ["2019-01", "2019-03"], "class": "A", "params": {"ctx": "US500"}, "context": ["US500"], "modes": ["M0"]}
    j.update(kw)
    return j


def test_runner_validates_the_declared_list(sandbox):
    R.validate(_job(), require_committed=False)
    with pytest.raises(ValueError, match="differs from the card"):
        R.validate(_job(context=["UK100"]), require_committed=False)
    with pytest.raises(ValueError, match="differs from the card"):
        R.validate(_job(context=[]), require_committed=False)                 # card declares US500, job leaves it out
    with pytest.raises(ValueError, match="differs from the card"):
        R.validate(_job(card="runs/_test_cards/noctx.md"), require_committed=False)
    with pytest.raises(ValueError, match="never traded"):
        R.validate(_job(symbols=["EURUSD", "US500"]), require_committed=False)
    j = R.validate(_job(card="runs/_test_cards/noctx.md", context=[]), require_committed=False)   # no row, no context: as before
    assert not j.get("context")


def test_runner_run_with_context(sandbox):
    j = R.validate(_job(), require_committed=False)
    j["job_id"] = "JCTX0001"
    os.makedirs(os.path.join(R.QUEUE, "pending"), exist_ok=True)
    json.dump(j, open(os.path.join(R.QUEUE, "pending", "JCTX0001.json"), "w"))
    assert R.run_batch(workers=2, log=lambda s: None) == 1
    row = [json.loads(x) for x in open(next(iter(sorted((sandbox / "ledger").glob("*.jsonl")))))][0]
    assert row["context"] == ["US500"] and row["data_hash"] == R.data_hash(["EURUSD", "US500"]) != R.data_hash(["EURUSD"])
    assert row["metrics"]["M0"]["trades"] > 0
    # the module saw exactly the aligned values (rebuilt here independently)
    b = data.bars("EURUSD", "h1")
    end = R.month_ms("2019-03", end=True)
    close = b["close_ms"][b["close_ms"] <= end]
    exp = IN.context(["US500"], "h1", close, end)["US500"]
    log = np.load(os.path.join(R.REPO, row["run_path"], "EURUSD_M0.npz"))
    bar = log["bar"].astype(int)
    assert len(bar) > 20
    assert (exp["close_ms"][bar] <= close[bar]).all()                         # context bar closed at or before the decision
    fresh = np.r_[False, exp["close_ms"][1:] != exp["close_ms"][:-1]]
    want = np.where(exp["c"] > exp["o"], 1, -1)
    assert fresh[bar].all() and (log["side"] == want[bar]).all()               # the entries follow exactly the aligned bars


def test_fx_context_runs_fx2015_on_every_symbol():
    from engine import pipeline as P
    assert P.fx_idea(["US500"], ["EURUSD"]) == (True, True)
    assert P.fx_idea(["EURUSD"], ["US500"]) == (True, False)
    assert P.fx_idea(["US500"], ["UK100"]) == (False, False)
    q = R.month_ms("2015-06")
    log = {"symbol": np.array(["US500", "EURUSD", "US500"]), "entry_t": np.array([q, q, R.month_ms("2016-01")], np.int64),
           "r_net_ftmo": np.zeros(3)}
    assert list(P.fx_quarantine_mask(log)) == [False, True, False]
    assert list(P.fx_quarantine_mask(log, every_symbol=True)) == [True, True, False]


def test_runner_outside_series(sandbox):
    """A14 §2: the job's series equal the card's row; ctx["series"] holds point-in-time values; the row records them."""
    card = CARD.replace("| context symbols | US500 |\n", "| outside series | vix:VIX:close; calendar:quarterly_expiry |\n")
    open(os.path.join(R.REPO, "runs", "_test_cards", "ser.md"), "w").write(card)
    j = _job(card="runs/_test_cards/ser.md", context=[], series=["vix:VIX:close", "calendar:quarterly_expiry"],
             strategy="tests/fixtures/series_follow.py:intents", params={})
    R.validate(j, require_committed=False)
    with pytest.raises(ValueError, match="differ from the card"):
        R.validate(dict(j, series=["vix:VIX:close"]), require_committed=False)
    with pytest.raises(ValueError):
        R.validate(dict(j, series=["vix:VIX:volume"]), require_committed=False)
    j = R.validate(j, require_committed=False)
    j["job_id"] = "JSER0001"
    os.makedirs(os.path.join(R.QUEUE, "pending"), exist_ok=True)
    json.dump(j, open(os.path.join(R.QUEUE, "pending", "JSER0001.json"), "w"))
    assert R.run_batch(workers=2, log=lambda s: None) == 1
    row = [json.loads(x) for f in sorted((sandbox / "ledger").glob("*.jsonl")) for x in open(f)][-1]
    assert row["series"] == ["vix:VIX:close", "calendar:quarterly_expiry"] and "context" not in row
    assert row["data_hash"] != R.data_hash(["EURUSD"]) and row["metrics"]["M0"]["trades"] > 0
    from engine import series as SR
    b = data.bars("EURUSD", "h1")
    close = b["close_ms"][b["close_ms"] <= R.month_ms("2019-03", end=True)]
    a = SR.outside(["vix:VIX:close"], close)["vix:VIX:close"]
    log = np.load(os.path.join(R.REPO, row["run_path"], "EURUSD_M0.npz"))
    bar = log["bar"].astype(int)
    assert (a["release_ms"][bar] < close[bar]).all()                       # every decision saw only released values
    assert (log["side"] == np.where(a["value"][bar] > 20, -1, 1)).all()
