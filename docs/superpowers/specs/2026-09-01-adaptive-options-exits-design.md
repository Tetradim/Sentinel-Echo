# Adaptive Options Exits Design

## Scope

Implement the approved second and third Echo intelligence phases without importing
Sentinel Edge, Pulse, or Flare. Echo continues to accept valid Discord options
alerts. The intelligence layer manages only positions already confirmed by the
broker.

The same package also closes three lifecycle gaps demonstrated by retained trading
evidence: same-day options reaching exercise, repeated partial take-profit orders,
and sell limits based on stale marks instead of the current option bid.

## Components

### Market exit intelligence

`backend/market_exit_intelligence.py` is a pure calculation module. It consumes the
position, recent underlying one-minute bars, the exact option bid and ask, current
time, and settings. It produces:

- direction-relative market alignment;
- premium midpoint and spread;
- premium drawdown from Echo's broker-confirmed peak;
- persistent reversal conflict count;
- `held`, `warning`, or `confirmed` reversal state;
- an effective adaptive trailing percentage and calculation evidence;
- MFE, MAE, and counterfactual stop/trailing threshold updates.

No market-data error may itself create a sell. Missing or invalid context returns a
held decision and preserves the last valid state.

### Reversal-aware exits

Reversal exits are enabled independently from trailing stops. Defaults:

- warning after two consecutive strong conflicts;
- confirmation after four consecutive strong conflicts;
- option premium must be at least 12 percent below the recorded peak;
- warning sells 25 percent once;
- confirmation sells all remaining contracts.

Agreement resets the conflict count. Mixed context reduces the count by one. The
warning stage is persisted on the position and cannot submit repeatedly after a
fill or restart. Explicit analyst sells, pending broker sells, and mandatory 0DTE
liquidation outrank reversal intelligence.

### Adaptive trailing

Adaptive trailing runs only when both the existing trailing stop and adaptive
trailing are enabled, and only for percentage trails. It starts from the configured
trailing percentage and adjusts for:

- option bid/ask spread;
- short premium volatility from recent midpoint marks;
- direction-relative underlying alignment;
- time remaining on same-day and next-day contracts.

The effective result is clamped to configurable minimum and maximum percentages,
defaulting to 8 and 35. A supportive trend or noisy premium widens the trail. A
conflicting trend or approaching 0DTE cutoff tightens it. Premium-based fixed-cent
trails keep their existing behavior.

### Mandatory 0DTE liquidation

At the configurable default cutoff of 15:40 America/New_York, Echo:

1. Cancels open BUY orders for contracts expiring that day.
2. Submits a full SELL for each Echo-managed expiring broker position.
3. Uses the latest valid option bid as the sell limit when available.
4. Keeps reconciling until the broker no longer reports the position.

The liquidation decision runs before every automatic price trigger and cannot be
reduced by partial-take-profit or reversal percentages.

### Telemetry

Each position stores aggregate MFE/MAE, a short bounded premium-mark history,
alignment and reversal state, effective trailing distance, and first-hit records for
counterfactual fixed stops at -20/-30/-40/-50 percent and trailing widths at
10/15/20 percent. Operator events are emitted only when reversal state changes,
liquidation begins, or the effective trailing distance changes materially.

## Order and fill behavior

Bot-managed SELL orders prefer a fresh bid from the intelligence snapshot. The
existing fill monitor remains responsible for partial and final fill reconciliation.
When a `take_profit` or `reversal_warning` SELL fills, reconciliation persists the
completed stage on the position. A completed partial stage cannot fire again.

## Operator controls

The Risk screen gets an `Intelligence` tab containing reversal, adaptive trailing,
and 0DTE settings. Existing Stop Loss, Take Profit, Break Even, and Trailing controls
remain unchanged. Invalid percentages, confirmation counts, or cutoff times are
rejected by both frontend validation and Pydantic request models.

## Testing

- Pure deterministic tests cover CALL/PUT reversal inversion, persistence, missing
  context, adaptive bounds, spread/volatility/time adjustments, and telemetry.
- Worker tests cover precedence, fresh-bid sell pricing, stage persistence, pending
  sell dedupe, 0DTE entry cancellation, and full liquidation quantity.
- Fill reconciliation tests prove take-profit and warning stages become one-shot.
- Settings and UI tests prove defaults, validation, load, and persistence.
- The full backend suite, frontend tests, TypeScript check, lint, web export, and
  whitespace validation run before completion.

## Non-goals

- No profitability guarantee or opaque prediction model.
- No dark-pool, whale, Edge, Pulse, or Flare integration.
- No broker-side bracket or broker-side trailing order.
- No automatic re-entry or alert veto based on market sentiment.

