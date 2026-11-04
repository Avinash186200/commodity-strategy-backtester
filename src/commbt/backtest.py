"""Trade simulation for one (symbol, strategy, side, params) combination."""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from .strategies import StrategySpec

FillMode = Literal["next_open", "same_close"]


def exit_positions_for(
    open_positions: np.ndarray, exit_flag: np.ndarray, max_hold: int, inclusive: bool = True
) -> np.ndarray:
    """Vectorised "first exit signal after entry, else forced exit after max_hold bars".

    Replaces the original O(trades x bars) Python loop with one
    ``searchsorted``. Returns the bar index on which the exit is *decided*
    (the signal bar). It can be ``>= len(exit_flag)`` when the trade is
    still open at the end of the data; callers drop those.
    """
    cand = np.flatnonzero(exit_flag)
    start = open_positions if inclusive else open_positions + 1
    if len(cand) == 0:
        return open_positions + max_hold
    k = np.searchsorted(cand, start)
    nxt = np.where(k < len(cand), cand[np.clip(k, 0, len(cand) - 1)], np.iinfo(np.int64).max)
    return np.minimum(nxt, open_positions + max_hold)


def simulate(
    prices: pd.DataFrame,
    spec: StrategySpec,
    side: str,
    params: dict[str, int],
    max_hold: int = 15,
    cost_bps: float = 1.0,
    fill: FillMode = "next_open",
) -> pd.DataFrame:
    """Run one combination on one symbol's bars and return its trade log.

    ``prices`` must hold a single symbol, sorted by date. One position at a
    time: a new entry is only taken after the previous trade has exited.
    Longs buy the ask and sell the bid (shorts the reverse), so the spread is
    always paid; ``cost_bps`` is charged on top, per side.

    ``fill="next_open"`` (default) fills both entry and exit at the open of
    the bar after the signal. ``fill="same_close"`` reproduces the original
    research code, which traded at the close of the signal bar itself; it is
    kept only so the audit can measure the difference.
    """
    df = prices.reset_index(drop=True)
    entry_sig, exit_sig = spec.func(df, side, params)
    entry_sig, exit_sig = entry_sig.to_numpy(bool), exit_sig.to_numpy(bool)
    n = len(df)
    lag = 1 if fill == "next_open" else 0
    px_field = "open" if fill == "next_open" else "close"
    buy = df[f"ask{px_field}"].to_numpy(float)
    sell = df[f"bid{px_field}"].to_numpy(float)
    dates = df["date"].to_numpy()

    sig_bars = np.flatnonzero(entry_sig)
    entry_bars = sig_bars + lag
    # exit decided at a close on or after the fill bar (strictly after for same-close fills)
    exit_sig_bars = exit_positions_for(entry_bars, exit_sig, max_hold, inclusive=(lag == 1))
    exit_bars = exit_sig_bars + lag

    rows = []
    last_exit = -1
    for s, e, x in zip(sig_bars, entry_bars, exit_bars):
        if x >= n or e <= last_exit:
            continue
        last_exit = x
        if side == "Long":
            gross = sell[x] / buy[e] - 1.0
        else:
            gross = sell[e] / buy[x] - 1.0
        rows.append((dates[s], dates[e], dates[x], gross, gross - 2 * cost_bps / 1e4, x - e))
    out = pd.DataFrame(rows, columns=["signal_date", "entry_date", "exit_date",
                                      "gross_return", "net_return", "bars_held"])
    return out
