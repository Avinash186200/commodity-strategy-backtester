"""End-to-end: grid backtest -> sizing -> walk-forward selection -> portfolio stats."""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .backtest import FillMode, simulate
from .sizing import size_trades
from .strategies import STRATEGIES
from .walkforward import monthly_by_exit, select_and_trade


def annualised_sharpe(monthly: pd.Series) -> float:
    """Sharpe of a monthly return series, annualised with sqrt(12)."""
    s = monthly.std(ddof=1)
    return float(monthly.mean() / s * np.sqrt(12)) if s and np.isfinite(s) and s > 0 else float("nan")


def param_grid(grid: dict[str, list[int]]) -> list[dict[str, int]]:
    """Cartesian product of a parameter grid, one dict per combination."""
    keys = list(grid)
    return [dict(zip(keys, vals)) for vals in itertools.product(*(grid[k] for k in keys))]


@dataclass
class PipelineResult:
    """Outputs of :func:`run`: OOS monthly returns and trades, naive best-of-N per base, trial count."""

    oos_monthly: pd.Series
    oos_trades: pd.DataFrame
    insample_best: pd.DataFrame
    n_trials: int


def run(
    prices: pd.DataFrame,
    strategies: list[str] | None = None,
    sides: tuple[str, ...] = ("Long", "Short"),
    max_hold: int = 15,
    cost_bps: float = 1.0,
    target_vol: float = 0.10,
    min_sharpe: float = 1.0,
    fill: FillMode = "next_open",
) -> PipelineResult:
    """Backtest every combo, select walk-forward, and build the equal-weight OOS portfolio.

    Also returns, per base, the Sharpe of the combo that looks best over the
    *full* sample. That number is what a naive best-of-N report would show;
    it is there only to measure selection bias, not as a result.
    """
    strategies = strategies or list(STRATEGIES)
    months = pd.period_range(prices["date"].min(), prices["date"].max(), freq="M")
    oos_parts, insample_rows = [], []
    n_trials = 0
    for sym, px in prices.groupby("Symbol"):
        px = px.sort_values("date").reset_index(drop=True)
        for strat, side in itertools.product(strategies, sides):
            spec = STRATEGIES[strat]
            base = f"{sym}|{strat}|{side}"
            combos: dict[str, pd.DataFrame] = {}
            for p in param_grid(spec.grid):
                n_trials += 1
                t = simulate(px, spec, side, p, max_hold=max_hold, cost_bps=cost_bps, fill=fill)
                t = size_trades(t, px, target_vol=target_vol)
                combos[f"{base}|" + "_".join(f"{k}{v}" for k, v in p.items())] = t
            full = {c: annualised_sharpe(monthly_by_exit(t).reindex(months, fill_value=0.0)) for c, t in combos.items()}
            best = max(full, key=lambda c: -np.inf if np.isnan(full[c]) else full[c])
            insample_rows.append({"base": base, "best_combo": best, "full_sample_sharpe": full[best]})
            _, oos = select_and_trade(combos, months, min_sharpe=min_sharpe)
            if not oos.empty:
                oos["base"] = base
                oos_parts.append(oos)
    oos_trades = pd.concat(oos_parts, ignore_index=True) if oos_parts else pd.DataFrame(
        columns=["exit_date", "sized_return", "base"])
    n_bases = len(insample_rows)
    first_oos = months[60] if len(months) > 60 else months[-1]
    oos_months = months[months >= first_oos]
    oos_monthly = (monthly_by_exit(oos_trades).reindex(oos_months, fill_value=0.0) / n_bases
                   if not oos_trades.empty else pd.Series(0.0, index=oos_months))
    return PipelineResult(oos_monthly, oos_trades, pd.DataFrame(insample_rows), n_trials)


def summarise(monthly: pd.Series) -> dict[str, float]:
    """Headline stats for a monthly return series."""
    eq = (1 + monthly).cumprod()
    dd = float((eq / eq.cummax() - 1).min()) if len(eq) else float("nan")
    return {
        "months": int(len(monthly)),
        "ann_return": float(monthly.mean() * 12),
        "ann_vol": float(monthly.std(ddof=1) * np.sqrt(12)),
        "sharpe": annualised_sharpe(monthly),
        "max_drawdown": dd,
    }
