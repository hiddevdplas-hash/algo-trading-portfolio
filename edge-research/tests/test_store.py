"""Research store codec: exact round trip, and the cut-off rule."""
import numpy as np

from engine import store


def test_round_trip_random_columns():
    rng = np.random.default_rng(1)
    n = 100_000
    cols = {"t": np.cumsum(rng.integers(0, 5_000, n)) + 1_420_070_400_000,
            "bid": 110_000 + np.cumsum(rng.integers(-3, 4, n)),
            "spread": rng.integers(-2, 40, n),
            "close100": np.where(rng.random(n) < 0.01, -1, 17_000_000_000_000_000 + rng.integers(0, 3, n)),
            "big": rng.integers(-2**62, 2**62, n)}
    back = store.decode_month(store.encode_month(cols, level=3))
    for k, v in cols.items():
        assert np.array_equal(back[k], v)


def test_empty_and_single():
    for n in (0, 1):
        cols = {"t": np.arange(n, dtype=np.int64), "bid": np.arange(n, dtype=np.int64)}
        back = store.decode_month(store.encode_month(cols, level=3))
        assert all(len(v) == n for v in back.values())


def test_price_grid_exact():
    px = np.array([1.35351, 0.99999, 141.051, 1.0, 0.00001])
    i = store._price_int(px, 5)
    assert np.array_equal(i / 10**5, px)


def test_cutoff_constants():
    assert store.CUTOFF_MS == 1_735_689_600_000            # 2025-01-01 00:00 UTC
    assert store.RESEARCH_START_MS == 1_414_800_000_000    # 2014-11-01 00:00 UTC
