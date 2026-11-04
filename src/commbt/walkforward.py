"""Monthly walk-forward parameter selection.

For every (symbol, strategy, side) "base" there are many parameter combos.
At the end of each month m, each combo is scored with a recency-weighted
Sharpe over the 60 months ending at m, using only trades that have
*exited* by the end of m. The best combo (if it clears ``min_sharpe``) is
traded in month m+1: its trades that *enter* in m+1 are the out-of-sample
record.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

DEFAULT_BUCKETS: tuple[tuple[int, float], ...] = (
    # (months in bucket, total weight), newest first
    (3, 0.20), (9, 0.20), (12, 0.25), (12, 0.12), (12, 0.12), (12, 0.11),
)


def recency_weights(buckets: tuple[tuple[int, float], ...] = DEFAULT_BUCKETS) -> np.ndarray:
    """Per-month weights, oldest first, summing to 1."""
    w = np.concatenate([np.full(n, tot / n) for n, tot in buckets])[::-1]
    return w / w.sum()


def monthly_by_exit(trades: pd.DataFrame, value_col: str = "sized_return") -> pd.Series:
    """Sum of trade returns per calendar month of exit (a trade's P&L is known at exit)."""
    if trades.empty:
        return pd.Series(dtype=float)
    m = pd.to_datetime(trades["exit_date"]).dt.to_period("M")
    return trades.groupby(m)[value_col].sum()


def weighted_sharpe(monthly: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Rolling recency-weighted annualised Sharpe; one value per full window."""
    win = sliding_window_view(monthly, len(weights), axis=0)  # (n-w+1, combos, w)
    mean = (win * weights).sum(axis=-1)
    std = np.sqrt((((win - mean[..., None]) ** 2) * weights).sum(axis=-1))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(std > 0, mean / std * np.sqrt(12), np.nan)


@dataclass
class Selection:
    base: str
    trade_month: pd.Period
    combo: str
    score: float


def select_and_trade(
    combo_trades: dict[str, pd.DataFrame],
    months: pd.PeriodIndex,
    min_sharpe: float = 1.0,
    weights: np.ndarray | None = None,
) -> tuple[list[Selection], pd.DataFrame]:
    """Walk-forward selection for one base.

    ``combo_trades`` maps combo id -> sized trade log. Returns the monthly
    selections and the concatenated out-of-sample trades.
    """
    weights = recency_weights() if weights is None else weights
    w = len(weights)
    names = list(combo_trades)
    mat = np.column_stack([
        monthly_by_exit(combo_trades[c]).reindex(months, fill_value=0.0).to_numpy(float) for c in names
    ])
    if len(months) < w + 1:
        return [], pd.DataFrame()
    scores = weighted_sharpe(mat, weights)  # row i -> window ending at months[i + w - 1]
    selections: list[Selection] = []
    oos = []
    for i in range(scores.shape[0] - 1):
        row = scores[i]
        if np.all(np.isnan(row)):
            continue
        j = int(np.nanargmax(row))
        if row[j] < min_sharpe:
            continue
        trade_month = months[i + w]  # month after the window's last month
        sel = Selection("", trade_month, names[j], float(row[j]))
        selections.append(sel)
        t = combo_trades[names[j]]
        mask = pd.to_datetime(t["entry_date"]).dt.to_period("M") == trade_month
        if mask.any():
            part = t.loc[mask].copy()
            part["combo"] = names[j]
            part["trade_month"] = trade_month
            oos.append(part)
    return selections, (pd.concat(oos, ignore_index=True) if oos else pd.DataFrame())


def training_trades(trades: pd.DataFrame, trade_month: pd.Period) -> pd.DataFrame:
    """Trades whose outcome is known before ``trade_month`` starts.

    The original data builder for the trade filter model selected training
    rows by *entry* month < trade month, which includes trades still open at
    the decision time (their labels come from the future). This filters on
    *exit* date instead.
    """
    cutoff = trade_month.start_time
    return trades.loc[pd.to_datetime(trades["exit_date"]) < cutoff]
