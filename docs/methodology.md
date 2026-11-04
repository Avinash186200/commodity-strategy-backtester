# Methodology and bias audit

## Problem

A library of daily rule strategies, each with a parameter grid, has to be turned into a live portfolio. Choosing parameters on the full history and reporting that history is the classic overfitting trap (Bailey, Borwein, López de Prado and Zhu, "The Probability of Backtest Overfitting", 2015). The original pipeline tried to avoid it with a monthly walk-forward, and that is the part I kept. But several other leaks were left in the steps around it.

## Data contract

| Field | Used for |
|---|---|
| `date`, `Symbol` | Bar index, one series per symbol |
| `askopen/high/low/close` | Long entries, short exits |
| `bidopen/high/low/close` | Long exits, short entries |
| Mid of bid/ask | Signals and volatility |

## Timing rules

- **Signals** at bar t use bars up to and including t. Tests change every bar after t by +50% and check that no signal at or before t changes.
- **Fills** happen at the open of bar t+1. An exit signal can come from the close of the fill bar onward. The exit then fills at the following open.
- **Sizing vol** on the signal day uses returns up to that close. It is known before the fill.
- **Monthly P&L** is booked by exit month.
- **Selection** at the end of month m uses only trades that exited by the end of m. It affects only trades that enter in month m+1. A test plants a huge win that exits in month 70 and checks that it can first change the pick for month 71, not month 70.

## Walk-forward score

For each combination, the monthly returns over the 60 months ending at m are combined with recency weights (newest first): 3 months at 20% total, 9 months at 20%, then 12-month blocks at 25%, 12%, 12% and 11%. The score is the weighted mean divided by the weighted standard deviation, times sqrt(12). A month with no exits counts as zero. The best combination per base is traded if its score is at least 1.0.

## Findings in the original code

1. **Same-bar fills.** Entries were filled at the close of the bar whose close fired the signal, and exits at the close of the exit-signal bar. That price is not tradable once you have seen it. The fix is to fill at the next open. On my synthetic data the gap between the two modes is small, because the generator's open sits close to the prior close. On real data with overnight gaps the effect is larger and unknown, so I don't quote a figure.
2. **Vol-targeting look-ahead.** The portfolio scaler on day d used a window that ended on day d, including that day's return. The fix is to use the vol known at the signal close.
3. **Label leakage in the trade-filter data.** Training sets for a downstream trade-filter model took every trade with entry month before the trade month. Trades entered late in the prior month and still open had outcomes the model could not have known. The fix is to filter on exit date (`training_trades`).
4. **Overlapping positions.** The simulator opened a trade on every signal bar. The one-position-at-a-time filter existed only as an option in a later reporting step. The fix is to enforce it in the simulator.
5. **Best-of-N.** Grids ran to thousands of combinations per strategy, and per-combination full-sample summaries were written out next to the walk-forward ones. The fix is to report only walk-forward numbers. The pipeline still computes the naive figure, so the bias is visible. On pure noise, the best of 114 combinations shows a Sharpe of 0.40, while the walk-forward record is -0.45.
6. **Variant and horizon selection.** Several portfolio variants (no hold rule, a minimum-hold rule, minimum-hold plus a model filter) and two holding horizons were compared. A combined book then picked whichever horizon did best for each asset class. That is a second selection layer that the walk-forward does not protect against. The fix is to fix one configuration in advance. That step was not ported.
7. **Missing forced exits.** When there was no exit signal at all after an entry, the trade was marked as never closed and dropped, even if the max-hold exit fell inside the data. The fix is that the max-hold exit always applies.

Costs: the original trade-level P&L paid the bid/ask spread. Commission, financing and slippage were added only at the portfolio stage. Here the spread plus a per-side cost is charged on every trade, before any selection, so selection sees net returns.

## What was dropped

- The per-strategy notebooks. I kept three representative rules.
- The multi-process runners, memory-budget schedulers and benchmark scripts. They were for speed on large grids, and the result is the same.
- The reporting suite (many spreadsheet and chart files per portfolio) and the mark-to-market engine.
- The cross-horizon combination script.
- All data, results and environment-specific paths.

My main engineering contribution to the original was replacing a per-trade exit-matching loop (O(trades x bars)) with one `searchsorted` call, and vectorising the rolling weighted Sharpe. Both were checked against the old code for identical output. Both survive here: `exit_positions_for` and `weighted_sharpe`. The parity test against a plain loop is in `tests/`.

## Limitations

- Synthetic data only. Real performance is not claimed.
- Each month's pick is a different combination, so a trade from last month's pick can still be open when this month's pick enters. The original had the same overlap across months. I left it as is and flag it here.
- No deflated Sharpe is computed. The trial count is reported so a reader can apply one.
