import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from commbt.backtest import exit_positions_for, simulate  # noqa: E402
from commbt.data import PRICE_COLUMNS, make_synthetic_prices  # noqa: E402
from commbt.pipeline import run  # noqa: E402
from commbt.sizing import ex_ante_vol  # noqa: E402
from commbt.strategies import STRATEGIES  # noqa: E402
from commbt.walkforward import recency_weights, select_and_trade, training_trades  # noqa: E402


@pytest.fixture(scope="module")
def one_symbol():
    px = make_synthetic_prices(symbols=("COMM_A",), start="2010-01-01", end="2016-12-31", seed=3)
    return px.reset_index(drop=True)


def test_synthetic_schema():
    px = make_synthetic_prices(symbols=("X",), start="2020-01-01", end="2020-03-31")
    assert list(px.columns) == ["date", "Symbol", *PRICE_COLUMNS]
    assert (px["askclose"] > px["bidclose"]).all()
    assert (px["askhigh"] >= px["asklow"]).all()


def test_exit_positions_match_loop():
    rng = np.random.default_rng(0)
    flag = rng.random(500) < 0.05
    opens = np.sort(rng.choice(480, 60, replace=False))
    fast = exit_positions_for(opens, flag, max_hold=15, inclusive=True)
    for o, f in zip(opens, fast):
        later = [i for i in range(o, len(flag)) if flag[i]]
        expected = min(later[0], o + 15) if later else o + 15
        assert f == expected


@pytest.mark.parametrize("name", list(STRATEGIES))
def test_signals_do_not_use_future_bars(one_symbol, name):
    """Changing bars after t must not change any signal at or before t."""
    spec = STRATEGIES[name]
    params = {k: v[0] for k, v in spec.grid.items()}
    cut = 1000
    full_e, full_x = spec.func(one_symbol, "Long", params)
    altered = one_symbol.copy()
    altered.loc[cut + 1:, PRICE_COLUMNS] *= 1.5
    alt_e, alt_x = spec.func(altered, "Long", params)
    assert full_e.iloc[: cut + 1].equals(alt_e.iloc[: cut + 1])
    assert full_x.iloc[: cut + 1].equals(alt_x.iloc[: cut + 1])


def test_fill_is_after_signal_and_one_position_at_a_time(one_symbol):
    spec = STRATEGIES["ibs_reversion"]
    t = simulate(one_symbol, spec, "Long", {"entry_pct": 25, "exit_pct": 60})
    assert len(t) > 20
    assert (t["entry_date"] > t["signal_date"]).all()
    assert (t["exit_date"] > t["entry_date"]).all()
    assert (t["entry_date"].iloc[1:].to_numpy() > t["exit_date"].iloc[:-1].to_numpy()).all()
    assert (t["net_return"] < t["gross_return"]).all()


def test_ex_ante_vol_ignores_future(one_symbol):
    v = ex_ante_vol(one_symbol, 90)
    altered = one_symbol.copy()
    altered.loc[501:, "askclose"] *= 3
    altered.loc[501:, "bidclose"] *= 3
    v2 = ex_ante_vol(altered, 90)
    pd.testing.assert_series_equal(v.iloc[:501], v2.iloc[:501])


def test_selection_uses_only_past_exits():
    """A combo that only pays off in month m must not be picked for month m."""
    months = pd.period_range("2000-01", "2007-12", freq="M")
    rng = np.random.default_rng(1)

    def trades(rets):
        ends = months.to_timestamp(how="end").normalize()
        return pd.DataFrame({"signal_date": ends - pd.Timedelta(days=3), "entry_date": ends - pd.Timedelta(days=2),
                             "exit_date": ends, "sized_return": rets})

    noise = rng.normal(0, 0.01, len(months))
    spike = noise.copy()
    target = 70
    spike[target] = 10.0  # huge win exiting in month 70 only
    sels, _ = select_and_trade({"noise": trades(noise), "spike": trades(spike)}, months, min_sharpe=-99)
    picked = {s.trade_month: s.combo for s in sels}
    # the spike is unknown until month 70 ends, so month 70 itself is selected without it
    assert picked[months[target]] == "noise"   # ties go to the first combo
    assert picked[months[target + 1]] == "spike"
    assert len(recency_weights()) == 60
    assert np.isclose(recency_weights().sum(), 1.0)


def test_training_trades_exclude_open_labels():
    t = pd.DataFrame({"entry_date": pd.to_datetime(["2020-01-10", "2020-01-28", "2020-02-03"]),
                      "exit_date": pd.to_datetime(["2020-01-20", "2020-02-05", "2020-02-10"])})
    tr = training_trades(t, pd.Period("2020-02", "M"))
    assert len(tr) == 1  # the 28 Jan trade was still open on 1 Feb


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_pure_noise_has_no_oos_edge(seed):
    px = make_synthetic_prices(symbols=("A", "B"), start="2004-01-01", end="2019-12-31", seed=seed)
    res = run(px, strategies=["ibs_reversion", "ma_trend"])
    oos = res.oos_monthly
    sharpe = oos.mean() / oos.std() * np.sqrt(12) if oos.std() > 0 else 0.0
    assert abs(sharpe) < 1.0


def test_planted_edge_is_recovered():
    px = make_synthetic_prices(symbols=("A", "B"), start="2004-01-01", end="2019-12-31",
                               seed=5, mean_reversion=0.25)
    res = run(px, strategies=["ibs_reversion"])
    oos = res.oos_monthly
    assert oos.mean() / oos.std() * np.sqrt(12) > 1.0
