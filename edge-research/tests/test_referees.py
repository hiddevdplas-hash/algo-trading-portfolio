"""Referee plumbing: the committed cBots are what the generator writes; indicator seeding as documented."""
import math
import os

from tests.referees import make_cbots, referees as RF


def test_cbots_up_to_date(tmp_path, monkeypatch):
    monkeypatch.setattr(make_cbots, "OUT", str(tmp_path))
    make_cbots.main()
    for f in os.listdir(tmp_path):
        assert open(os.path.join(tmp_path, f)).read() == open(os.path.join(make_cbots.REPO, "cTrader-Bots", f)).read(), f


def test_atr_seed_and_wilder():
    h = [2.0] * 20; l = [1.0] * 20; c = [1.5] * 20
    h[16] = 4.0
    a = RF.atr(h, l, c, 2, n=14)
    assert all(math.isnan(x) for x in a[:15]) and a[15] == 1.0
    assert a[16] == (1.0 * 13 + 3.0) / 14                       # TR = max(h - l, |h - prev c|, |l - prev c|) = 3.0


def test_ema_and_grid():
    e = RF.ema([1.0, 2.0, 3.0], 0, 3)
    assert e == [1.0, 1.5, 2.25]
    g = RF.Grid("EURUSD")
    assert g.rt(1.084444) == 108444 / 1e5 and g.rt(1.084445) == 108445 / 1e5 and g.rt(0.0012349) == 123 / 1e5
