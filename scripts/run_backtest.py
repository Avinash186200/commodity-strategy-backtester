"""Run the full walk-forward pipeline on synthetic data or a user-supplied price file.

Examples:
    python scripts/run_backtest.py                              # synthetic, pure noise
    python scripts/run_backtest.py --mean-reversion 0.15        # synthetic with a planted edge
    python scripts/run_backtest.py --prices my_d1.csv           # your own bid/ask D1 data
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from commbt.data import make_synthetic_prices  # noqa: E402
from commbt.pipeline import run, summarise  # noqa: E402


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prices", type=Path, help="CSV with date, Symbol and bid/ask OHLC columns")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--mean-reversion", type=float, default=0.0, help="synthetic only: planted AR(1) reversal")
    ap.add_argument("--cost-bps", type=float, default=1.0, help="per side, on top of the bid/ask spread")
    ap.add_argument("--min-sharpe", type=float, default=1.0)
    ap.add_argument("--fill", choices=["next_open", "same_close"], default="next_open")
    ap.add_argument("--out", type=Path, default=Path("results"))
    args = ap.parse_args(argv)

    if args.prices:
        prices = pd.read_csv(args.prices, parse_dates=["date"])
    else:
        prices = make_synthetic_prices(seed=args.seed, mean_reversion=args.mean_reversion)

    res = run(prices, cost_bps=args.cost_bps, min_sharpe=args.min_sharpe, fill=args.fill)
    oos = summarise(res.oos_monthly)
    report = {
        "n_trials": res.n_trials,
        "n_bases": int(len(res.insample_best)),
        "oos_trades": int(len(res.oos_trades)),
        "walk_forward_oos": oos,
        "naive_best_of_n_full_sample_sharpe_median": float(res.insample_best["full_sample_sharpe"].median()),
        "naive_best_of_n_full_sample_sharpe_max": float(res.insample_best["full_sample_sharpe"].max()),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    res.oos_monthly.rename("oos_return").to_csv(args.out / "oos_monthly.csv")
    res.insample_best.to_csv(args.out / "naive_best_of_n.csv", index=False)
    (args.out / "summary.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()
