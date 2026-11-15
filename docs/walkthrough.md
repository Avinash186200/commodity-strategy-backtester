# Walkthrough: a first run

This is a guided first run. It assumes you know Python but not trading. Read the "Key concepts" list in the
[README](../README.md#key-concepts) first if a term is new. All numbers below come from running the code on
synthetic data.

## 1. Set up and run the tests

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q
```

You should see `13 passed`. Read `tests/test_pipeline.py` from the top. Each test checks one promise:

- `test_exit_positions_match_loop` checks that the fast `searchsorted` exit matching gives the same answer as a
  plain Python loop. This is how I made the original faster without changing its output.
- `test_signals_do_not_use_future_bars` changes every bar after t by +50% and checks that no signal at or before
  t moves.
- `test_fill_is_after_signal_and_one_position_at_a_time` checks next-open fills and that trades never overlap.
- `test_ex_ante_vol_ignores_future` checks that the sizing volatility on day t does not depend on later days.
- `test_selection_uses_only_past_exits` plants a huge win that exits in month 70 and checks that it can first
  change the pick for month 71.
- `test_pure_noise_has_no_oos_edge` and `test_planted_edge_is_recovered` are the two end-to-end checks.

## 2. Run on pure noise

```bash
python scripts/run_backtest.py
```

It prints `results/summary.json`:

| Field | Value | What it means |
|---|---|---|
| `n_trials` | 114 | Combos run: 19 parameter sets across the 3 strategies (12 + 4 + 3), x 2 sides x 3 symbols |
| `n_bases` | 18 | (symbol, strategy, side) groups. The walk-forward picks one combo per base per month |
| `oos_trades` | 371 | Trades taken by the monthly picks, out of sample |
| `walk_forward_oos.months` | 204 | Out-of-sample months, 2009-01 to 2025-12. The first 60 months are only used for scoring |
| `walk_forward_oos.sharpe` | -0.45 | The honest number. Negative: on noise you just pay costs |
| `walk_forward_oos.ann_return` / `ann_vol` | -0.19% / 0.42% | Small, because the portfolio averages over 18 bases and most sit in cash in a given month |
| `walk_forward_oos.max_drawdown` | -3.7% | Worst peak-to-trough fall of the out-of-sample equity curve |
| `naive_best_of_n_full_sample_sharpe_median` | 0.06 | Per base, the best combo chosen after seeing all the data. The median across bases |
| `naive_best_of_n_full_sample_sharpe_max` | 0.40 | The best of all 114, chosen the same way |

The data has no edge, so any positive number is luck. The naive best of 114 shows 0.40. The walk-forward record on
the same data shows -0.45. That gap is selection bias, measured.

## 3. Run with a planted edge

```bash
python scripts/run_backtest.py --mean-reversion 0.15
```

This adds a small negative autocorrelation to daily returns: a down day tends to be followed by a slight up day.
The reversal rules have something real to find now. The walk-forward Sharpe is 1.30 on 2,492 out-of-sample trades.
A pipeline that only reported noise would be useless, so this run matters as much as the first.

## 4. Look at the files

- `results/oos_monthly.csv`: one row per out-of-sample month. The first column is the month, `oos_return` is the
  portfolio return. On the noise run, 125 of the 204 months have a non-zero return; in the rest no base had a pick
  with trades.
- `results/naive_best_of_n.csv`: one row per base with the combo that looks best over the full sample. On the noise
  run the top one is `COMM_A|ma_trend|Short|ma_period50` at 0.40. It is printed so you can see the bias, not as a
  result.
- `results/summary.json`: the table above.

## 5. Try changing one thing

Each row is one command. I ran them while writing this page. Add `--out somewhere_else` if you want to keep
`results/` as it is.

| Command | OOS trades | Walk-forward Sharpe | Note |
|---|---|---|---|
| `python scripts/run_backtest.py` | 371 | -0.45 | Default: noise, 1 bp per side |
| `python scripts/run_backtest.py --min-sharpe 0` | 3,460 | -0.58 | No score filter: some combo is always traded. Max drawdown grows to -14.0% |
| `python scripts/run_backtest.py --fill same_close` | 363 | -0.22 | The original's fill rule. Not tradable; kept only to measure the gap |
| `python scripts/run_backtest.py --seed 1` | 396 | -0.23 | Another noise draw |
| `python scripts/run_backtest.py --seed 2` | 581 | -0.18 | Another noise draw |
| `python scripts/run_backtest.py --mean-reversion 0.15` | 2,492 | 1.30 | Planted edge |
| `python scripts/run_backtest.py --mean-reversion 0.15 --cost-bps 5` | 1,817 | 0.72 | Same edge, 5 bp per side: costs eat nearly half of it |
| `python scripts/run_backtest.py --mean-reversion 0.15 --fill same_close` | 2,570 | 1.21 | Same edge, original fill rule |

Two things to notice. First, every noise run is negative after selection, while its naive best-of-N stays
positive (0.38 to 0.40 at the max). Second, the same-close fill does not look better here. My synthetic open sits
close to the prior close, so the two fill rules see similar prices. On real data with overnight gaps the
difference can be large, which is why the methodology does not quote a figure for it.

## 6. Where to go next

- [methodology.md](methodology.md) has the full method and the bias audit.
- `src/commbt/backtest.py` holds the fill rules and the vectorised exit matching. It is short and worth reading.
- `training_trades` in `src/commbt/walkforward.py` is a one-line fix for a label leak. Its docstring explains the
  bug.
