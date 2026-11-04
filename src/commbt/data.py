"""Synthetic daily bid/ask price data with the same columns as the original master file."""
from __future__ import annotations

import numpy as np
import pandas as pd

PRICE_COLUMNS = [
    "askopen", "askhigh", "asklow", "askclose",
    "bidopen", "bidhigh", "bidlow", "bidclose",
]


def make_synthetic_prices(
    symbols: tuple[str, ...] = ("COMM_A", "COMM_B", "COMM_C"),
    start: str = "2004-01-01",
    end: str = "2025-12-31",
    annual_vol: float = 0.20,
    spread_bps: float = 3.0,
    mean_reversion: float = 0.0,
    seed: int = 7,
) -> pd.DataFrame:
    """Generate a long-format D1 bid/ask OHLC table.

    Columns: ``date, Symbol`` plus :data:`PRICE_COLUMNS`. Mid prices follow a
    geometric random walk. ``mean_reversion`` > 0 adds a small negative
    autocorrelation to daily returns, which gives the short-term
    mean-reversion rules something real to find. With ``mean_reversion=0``
    the series is pure noise and no rule should have an edge.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, end)
    n = len(dates)
    daily_vol = annual_vol / np.sqrt(252)
    frames = []
    for i, sym in enumerate(symbols):
        eps = rng.normal(0.0, daily_vol, n)
        ret = eps.copy()
        for t in range(1, n):
            ret[t] = eps[t] - mean_reversion * ret[t - 1]
        mid_close = 100.0 * (1 + i) * np.exp(np.cumsum(ret))
        mid_open = np.r_[mid_close[0], mid_close[:-1]] * np.exp(rng.normal(0, daily_vol * 0.2, n))
        span = np.abs(rng.normal(0, daily_vol, n)) * mid_close
        mid_high = np.maximum(mid_open, mid_close) + span
        mid_low = np.minimum(mid_open, mid_close) - span
        half = mid_close * spread_bps / 2e4
        df = pd.DataFrame({"date": dates, "Symbol": sym})
        for side, sign in (("ask", 1.0), ("bid", -1.0)):
            df[f"{side}open"] = mid_open + sign * half
            df[f"{side}high"] = mid_high + sign * half
            df[f"{side}low"] = mid_low + sign * half
            df[f"{side}close"] = mid_close + sign * half
        frames.append(df)
    return pd.concat(frames, ignore_index=True)
