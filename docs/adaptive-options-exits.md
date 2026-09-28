# Adaptive Options Exits

Echo manages exits with its own SELL orders. It does not create broker-side
brackets or broker-side trailing stops.

## Decision Order

For each broker-confirmed option position, Echo applies this order:

1. Ignore the position while an earlier SELL remains pending.
2. At the configured 0DTE cutoff, cancel unfilled same-day BUY orders and sell
   the full remaining quantity.
3. Evaluate take profit, stop loss, and break even.
4. Evaluate persistent market reversal.
5. Evaluate the configured fixed or adaptive trailing stop.

Analyst SELL alerts continue through the alert execution path. Pending-order
deduplication prevents the automatic exit worker from placing a competing SELL.

## Reversal Exits

Reversal evaluation combines direction-aware underlying bars with deterioration
in the exact option premium. CALL and PUT direction is inverted automatically.
By default, two consecutive qualifying conflicts sell 25 percent once. Four
qualifying conflicts sell the full remainder. A qualifying conflict also requires
the option midpoint to have fallen at least 12 percent from Echo's recorded peak.

Agreement resets the conflict count. Mixed evidence reduces it by one. Missing
market context never creates a reversal SELL.

## Adaptive Trailing

Adaptive trailing only runs when both **Trailing Stop** and **Adaptive Trailing**
are enabled and the trailing type is percentage. The configured trailing width is
adjusted for bid/ask spread, short premium volatility, underlying alignment, and
time to expiration, then clamped to the configured minimum and maximum. Defaults
are 8 and 35 percent.

Turning off the existing Trailing Stop switch turns off adaptive trailing too.
Fixed-cent trailing keeps its existing behavior.

## 0DTE Liquidation

The default cutoff is `15:40` America/New_York. At and after the cutoff, Echo
cancels open BUY orders expiring that day and submits a full SELL for every
broker-confirmed same-day option position it manages. Equities and later-dated
options are not selected by this rule.

## Persisted Evidence

Each valid observation stores the current bid, ask, midpoint, spread, reversal
score and state, conflict count, effective trailing width, MFE, MAE, a bounded
premium history, and first-hit records for fixed-stop and trailing alternatives.
This supports later parameter comparisons without changing live decisions.

If the option quote-context request fails, Echo clears the stale quote and
adaptive width, marks context unavailable, and retains the broker's fresh
position mark for ordinary configured exits.

## Controls

The controls are under **Risk Management > Intelligence**:

| Setting | Default |
| --- | ---: |
| Reversal-aware exits | On |
| Warning observations | 2 |
| Confirmed observations | 4 |
| Warning trim | 25% |
| Required premium drawdown | 12% |
| Adaptive trailing | On |
| Adaptive trailing minimum | 8% |
| Adaptive trailing maximum | 35% |
| Mandatory 0DTE liquidation | On |
| 0DTE cutoff | 15:40 ET |

Completed partial take-profit and reversal-warning stages are persisted after
their requested SELL quantity fills, so they do not repeat after a restart.
