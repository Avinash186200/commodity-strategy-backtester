"""Rule-based entry/exit signals.

Every signal is computed from bars up to and including the close of day t.
The backtester then fills on the *next* bar, so a signal never trades on
the price that produced it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder RSI using only past and current closes."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


def _mid(df: pd.DataFrame, field: str) -> pd.Series:
    """Mid price of one OHLC field from the bid and ask columns."""
    return (df[f"ask{field}"] + df[f"bid{field}"]) / 2.0


def lowest_close_rsi_exit(df: pd.DataFrame, side: str, p: dict[str, int]) -> tuple[pd.Series, pd.Series]:
    """Enter when close breaks the lagged N-day low (long) or high (short);
    exit when RSI crosses a threshold.

    Params: ``lookback``, ``lag``, ``rsi_period``, ``rsi_exit``.
    """
    close = _mid(df, "close")
    r = rsi(close, p["rsi_period"])
    if side == "Long":
        level = close.rolling(p["lookback"]).min().shift(p["lag"])
        entry = close < level
        exit_ = r > p["rsi_exit"]
    else:
        level = close.rolling(p["lookback"]).max().shift(p["lag"])
        entry = close > level
        exit_ = r < 100 - p["rsi_exit"]
    return entry.fillna(False), exit_.fillna(False)


def ibs_reversion(df: pd.DataFrame, side: str, p: dict[str, int]) -> tuple[pd.Series, pd.Series]:
    """Internal bar strength mean reversion.

    IBS = (close - low) / (high - low). Long when IBS is below ``entry_pct``/100,
    exit when it is above ``exit_pct``/100. Short is the mirror image.
    """
    hi, lo, cl = _mid(df, "high"), _mid(df, "low"), _mid(df, "close")
    ibs = (cl - lo) / (hi - lo).replace(0.0, np.nan)
    e, x = p["entry_pct"] / 100.0, p["exit_pct"] / 100.0
    if side == "Long":
        return (ibs < e).fillna(False), (ibs > x).fillna(False)
    return (ibs > 1 - e).fillna(False), (ibs < 1 - x).fillna(False)


def ma_trend(df: pd.DataFrame, side: str, p: dict[str, int]) -> tuple[pd.Series, pd.Series]:
    """Close above (long) / below (short) an N-day simple moving average."""
    cl = _mid(df, "close")
    ma = cl.rolling(p["ma_period"]).mean()
    above = cl > ma
    if side == "Long":
        return above.fillna(False), (~above).fillna(False)
    return (~above & ma.notna()), above.fillna(False)


@dataclass(frozen=True)
class StrategySpec:
    """A signal function and the parameter grid it is searched over."""

    name: str
    func: Callable[[pd.DataFrame, str, dict[str, int]], tuple[pd.Series, pd.Series]]
    grid: dict[str, list[int]]


STRATEGIES: dict[str, StrategySpec] = {
    "lowest_close_rsi_exit": StrategySpec(
        "lowest_close_rsi_exit", lowest_close_rsi_exit,
        {"lookback": [5], "lag": [1, 3, 5], "rsi_period": [2, 5], "rsi_exit": [50, 65]},
    ),
    "ibs_reversion": StrategySpec(
        "ibs_reversion", ibs_reversion,
        {"entry_pct": [15, 25], "exit_pct": [60, 75]},
    ),
    "ma_trend": StrategySpec(
        "ma_trend", ma_trend,
        {"ma_period": [50, 100, 200]},
    ),
}
