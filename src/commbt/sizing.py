"""Ex-ante inverse-volatility sizing."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ex_ante_vol(prices: pd.DataFrame, lookback: int = 90) -> pd.Series:
    """Annualised realised vol of mid-close returns, known at the close of each day.

    The value on day t uses returns up to and including day t's close. Trades
    fill on the next open, so using the signal-day value is strictly ex ante.
    (The original pipeline sized day t's exposure with a window that already
    contained day t's return; see docs/methodology.md.)
    """
    mid = (prices["askclose"] + prices["bidclose"]) / 2.0
    ret = mid.pct_change()
    return ret.rolling(lookback, min_periods=lookback).std() * np.sqrt(252)


def size_trades(
    trades: pd.DataFrame,
    prices: pd.DataFrame,
    target_vol: float = 0.10,
    lookback: int = 90,
    max_leverage: float = 1.0,
) -> pd.DataFrame:
    """Scale each trade's net return by ``target_vol / vol`` measured on its signal date."""
    vol = pd.Series(ex_ante_vol(prices, lookback).to_numpy(), index=prices["date"].to_numpy())
    v = vol.reindex(trades["signal_date"].to_numpy()).to_numpy()
    w = np.clip(target_vol / v, 0.0, max_leverage)
    out = trades.copy()
    out["weight"] = w
    out["sized_return"] = out["net_return"] * out["weight"]
    return out.dropna(subset=["sized_return"])
