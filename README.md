# Commodity Strategy Backtester

[![CI](https://github.com/Avinash186200/commodity-strategy-backtester/actions/workflows/ci.yml/badge.svg)](https://github.com/Avinash186200/commodity-strategy-backtester/actions/workflows/ci.yml) ![Python](https://img.shields.io/badge/python-3.11-blue) [![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## What problem this solves

A trading rule usually has settings to choose, such as a lookback length. If you choose them by looking at the whole price history, the backtest flatters you. This repo chooses them the way you would have to in real time: once a month, using only the past, and then it records how the choice did in the following month.

## Overview

A backtester for daily rule-based strategies on commodity contracts, with monthly walk-forward parameter selection. Each month it scores every parameter set on the previous five years, trades the best one for the next month only, and builds an out-of-sample record from those monthly picks.

I built the original version as a research pipeline. It ran a library of rule strategies (long and short versions) over a set of commodity contracts, with large parameter grids per strategy. That code, its price data and its results are proprietary and are not in this repo. This is a clean rewrite of the core method. It runs on **synthetic bid/ask price data with the same columns**, so you can clone it and reproduce every number below.

## At a glance

| | |
|---|---|
| **Input** | Daily bid/ask OHLC bars per symbol (`date`, `Symbol`, `askopen` ... `bidclose`) |
| **Method** | Rule signals at the close, next-open fills, one position at a time, ex-ante inverse-vol sizing, then a 60-month recency-weighted walk-forward Sharpe to pick parameters month by month |
| **Output** | Out-of-sample monthly portfolio returns, the per-month selections, and a "naive best-of-N" number shown side by side to make the selection bias visible |
| **Leakage controls** | Next-bar fills, signals tested against altered future bars, vol known before the fill, selection only on trades already closed, a pure-noise test in CI |
| **Status** | Engineering complete. Results below are synthetic only; no real-data performance is claimed |

## What you will learn

- How to write trading rules as signal functions that only use past bars, and how to test that with altered future bars.
- Why fills belong on the next bar's open, and how much the bid/ask spread and a small per-side cost matter.
- How inverse-volatility sizing works, and how to keep the volatility estimate free of look-ahead.
- How monthly walk-forward selection works, and why it must only use trades that have already closed.
- What selection bias looks like in numbers: the best of 114 settings on pure noise next to the honest walk-forward result.
- How to check a pipeline with a planted edge: it should find a real effect and report nothing on noise.

## Key concepts

- **Bid/ask bars.** Daily open, high, low and close for both the ask (buy) price and the bid (sell) price. The gap is the spread.
- **Signal at the close, fill at the next open.** The rule decides with day t's close. The trade happens at day t+1's open, because day t's close is gone once you have seen it.
- **Look-ahead bias.** Any use of data you would not have had when the decision was made.
- **Basis point (bp).** 0.01%. The default cost is 1 bp per side, on top of the spread.
- **Max hold.** If no exit signal comes within 15 bars, the trade is closed anyway.
- **Inverse-volatility sizing.** Trade a smaller position when the market is jumpy and a larger one when it is calm, so each trade carries about the same risk.
- **Combination (combo) and base.** A base is one (symbol, strategy, side). A combo is one base plus one parameter set. Here there are 18 bases and 114 combos.
- **Walk-forward selection.** At each month end, score every combo on the past 60 months, and trade the best one only in the next month.
- **Recency-weighted Sharpe.** Return divided by volatility over the 60-month window, with recent months weighted more. It is the score used to pick a combo.
- **Selection bias (best-of-N).** The best of many combos, picked after seeing all the data, looks better than it really is.
- **Planted edge.** A small, known pattern added to synthetic data, so you can check that the pipeline finds a real effect when one exists.

## How it works

```mermaid
flowchart LR
    A[Daily bid/ask bars<br/>data.py] --> B[Rule signals<br/>strategies.py]
    B --> C[Trade simulator<br/>next-open fills<br/>backtest.py]
    C --> D[Inverse-vol sizing<br/>sizing.py]
    D --> E[Monthly returns by exit month<br/>walkforward.py]
    E --> F[Walk-forward pick<br/>score on months up to m]
    F --> G[Trade month m+1<br/>equal-weight portfolio<br/>pipeline.py]
    C --> H[Naive best-of-N<br/>for contrast only]
```

```
D1 bid/ask bars ──► rule signals ──► trade simulator ──► inverse-vol sizing ──► monthly roll-up ──► walk-forward pick ──► OOS portfolio
  data.py            strategies.py     backtest.py        sizing.py             walkforward.py      walkforward.py        pipeline.py
```

1. **Signals.** Each rule decides at the close of day t, using bars up to t. Three are ported: a lagged N-day low/high break with an RSI exit, internal-bar-strength mean reversion, and a moving-average trend rule. Each has a long and a short version.
2. **Fills.** Entry and exit fill at the **next** open. Longs buy the ask and sell the bid, so the spread is always paid. A per-side cost (default 1 bp) is charged on top. If no exit signal comes within 15 bars, the trade is closed. Only one position per combination is open at a time.
3. **Sizing.** Each trade is scaled by `target_vol / vol`. The vol is the 90-day realised vol measured on the signal day, so it is known before the fill. Leverage is capped at 1.
4. **Monthly roll-up.** A trade's return is booked in the month it **exits**, because that is when its outcome is known.
5. **Walk-forward.** At the end of month m, every combination is scored with a recency-weighted Sharpe over the 60 months ending at m. The weights are 20% on the last 3 months, 20% on months 4-12, 25% on year 2, and 12/12/11% on years 3-5. The best combination is traded in month m+1, but only if its score is at least 1.0. Its trades that enter in m+1 form the out-of-sample record.
6. **Portfolio.** Equal weight across all (symbol, strategy, side) bases. A base with no pick in a month contributes zero.

## Results on synthetic data

These numbers come from synthetic prices, not real markets. The first row is pure noise; the second has a small reversal effect that I planted on purpose.

`python scripts/run_backtest.py` (seed 7, three symbols, 2004-2025, 114 parameter combinations across 18 bases, 204 out-of-sample months):

| Data | Walk-forward OOS Sharpe | OOS ann. return / vol | Max DD | OOS trades | Naive best-of-N full-sample Sharpe (median / max over 18 bases) |
|---|---|---|---|---|---|
| Pure noise (`--mean-reversion 0`) | -0.45 | -0.19% / 0.42% | -3.7% | 371 | 0.06 / 0.40 |
| Planted reversal (`--mean-reversion 0.15`) | 1.30 | +1.09% / 0.84% | -1.1% | 2,492 | 0.62 / 1.30 |

Returns are small in absolute terms because the portfolio is an equal-weight average over all 18 bases, and a base with no qualifying pick sits in cash that month. The Sharpe is the number to compare.

**Significance.** Over 204 out-of-sample months (17 years), a Sharpe of 1.30 has a t-statistic of roughly 1.30 x sqrt(17) = 5.4, well clear of noise; the -0.45 on pure noise is about -1.9, i.e. a cost drag, not a skill signal either way. I do not compute a deflated Sharpe here; the trial count (114) is printed so one can be applied. On real data, with far smaller true edges than the planted one, 17 years can easily be too short to separate skill from luck.

The noise row is the important one. Picking the best of the 114 combinations after the fact gives a Sharpe of up to 0.40 on data that has no edge at all. The walk-forward record on the same data is negative. When I plant a small reversal effect in the generator, the walk-forward finds it. The noise check is a test in CI, run over three seeds.

> **About the real data.** On the original proprietary data this pipeline was used to choose parameters for a portfolio of rule strategies. I don't publish those figures here. Most of the work I did on that code was speed and correctness (see below), not a performance study. The biases listed below were present in the original numbers, and the corrected version has not been run on a final hold-out. Treat this repo as a method, not a performance claim.

## Bias and leakage audit

I found these in the original research code and fixed them in this rewrite. The details are in [docs/methodology.md](docs/methodology.md).

| Issue | Effect | Fix |
|---|---|---|
| Entry and exit filled at the **close of the signal bar** | The trade used the price that created the signal. Optimistic, most of all for short-hold reversal rules | Fill at the next bar's open. `--fill same_close` is kept only to measure the gap |
| Portfolio vol-targeting window **included the same day's return** | Position size on day t used day t's move | Vol measured on the signal day, before the next-open fill. There is a test that changes future bars |
| Training rows for the trade-filter model were chosen by **entry** month < trade month | Trades still open at decision time had labels from the future | `training_trades()` keeps only trades that **exited** before the month starts |
| Every signal opened a new trade, even while one was already open | Exposure and trade counts were overstated. A later step removed the overlaps, but only in some reports | One position at a time, inside the simulator |
| Very large parameter grids, with full-sample stats reported per combination | Best-of-N selection bias | Walk-forward selection only. The naive best-of-N figure is printed next to it for contrast, along with the number of trials |
| Portfolio variants and holding horizons compared, and **the best per asset class kept** | A second layer of selection on the same data | One configuration, fixed in advance. The cross-horizon "pick the best" step was not ported |
| No exit signal after entry meant the trade was never closed, even when the max-hold limit fell inside the data | Losing trades with no exit signal dropped out of the record | The max-hold exit always applies. Only trades still open at the end of the data are dropped |

## Repo layout

```
src/commbt/
  data.py          synthetic bid/ask bars, with an optional planted reversal
  strategies.py    three rules (long and short) and their parameter grids
  backtest.py      trade simulator; vectorised exit matching (exit_positions_for)
  sizing.py        ex-ante volatility and inverse-vol sizing
  walkforward.py   recency weights, rolling weighted Sharpe, monthly selection, training_trades
  pipeline.py      end-to-end run, naive best-of-N, summary stats
scripts/
  run_backtest.py  command-line entry point; writes results/
tests/
  test_pipeline.py exit-matching parity, future-bar tests, fill timing, ex-ante vol,
                   selection timing, label-timing fix, noise test, planted-edge test
docs/
  README.md        index
  methodology.md   method notes and the bias audit in full
  walkthrough.md   a guided first run, and how to read each output
original/          the original research code (read-only)
results/           created by the script (git-ignored): summary.json, oos_monthly.csv, naive_best_of_n.csv
```

## Quick start

```bash
pip install -r requirements.txt
python -m pytest -q
python scripts/run_backtest.py                          # synthetic, pure noise
python scripts/run_backtest.py --mean-reversion 0.15    # synthetic, planted edge
```

Your own price file needs a `date` column, a `Symbol` column and the eight bid/ask OHLC columns. To try the CSV path first, write the synthetic bars to a file and run on that:

```bash
python -c "import sys; sys.path.insert(0, 'src'); from commbt.data import make_synthetic_prices; make_synthetic_prices().to_csv('your_d1.csv', index=False)"
python scripts/run_backtest.py --prices your_d1.csv --cost-bps 2
```

That is the pure-noise data with the per-side cost doubled to 2 bp. The walk-forward Sharpe goes from -0.45 to -0.62, and the OOS trade count drops from 371 to 320. Higher costs lower the scores, so fewer picks clear the 1.0 filter.

[docs/walkthrough.md](docs/walkthrough.md) goes through a first run step by step.

## Original research code

[`original/`](original/README.md) holds the code as I first wrote it for this project. It is kept so you can
read the first version alongside the maintained one; some of it contains the issues in the audit table above,
and comparing the two shows each fix.

## License

MIT

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [CHANGELOG](CHANGELOG.md).
