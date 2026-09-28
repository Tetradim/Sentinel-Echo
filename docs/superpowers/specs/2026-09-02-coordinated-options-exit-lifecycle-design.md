# Coordinated Options Exit Lifecycle

## Objective

Make every valid Discord option entry use one broker-backed lifecycle that sizes the entry by acceptable loss, records the broker fill, and manages the remaining contracts through hard loss protection, staged profit-taking, a permanent profit floor, reversal response, and a final trailing exit.

Echo continues to follow valid analyst entries. Market intelligence changes size and exit behavior; it does not veto the entry.

## Entry sizing

- Start with the source/default contract quantity.
- Estimate loss per contract as `entry premium * 100 * hard-stop percent`.
- Cap contracts to `floor(max loss dollars / estimated loss per contract)`, with one contract as the minimum for a valid entry.
- Use a 35% hard-stop estimate for normal alerts.
- Use a 50% hard-stop estimate and a 25% size cap for explicit high-risk, lotto, or gamble language.
- Preserve the existing maximum-position-value cap and market-alignment reduction.
- Persist the sizing inputs and the alert risk profile on the trade/position for auditability.

## Premium-aware policy

The entry fill premium selects the policy for the life of the position:

| Position | Trail activation | Trail width | Break-even activation |
| --- | ---: | ---: | ---: |
| Premium below $0.30 or 0DTE | +25% and at least $0.05 | 18%, at least $0.04 | +25% |
| Premium $0.30-$1.00 | +20% | 15% | +20% |
| Premium above $1.00 | +12% | 10% | +12% |

The executable option bid drives exits. Quotes older than 15 seconds cannot trigger discretionary exits.

## Position state machine

Each position persists:

- risk profile and premium tier
- original and remaining quantity
- highest executable bid
- first and second profit-stage completion
- profit-floor armed state and price
- trailing armed state
- reversal reduction completion
- active exit reservation/order metadata

Transitions:

1. `OPEN`: enforce the profile hard stop and track the high-water mark.
2. At +25%, sell 50% of original quantity.
3. After that fill, permanently arm a floor at entry plus one cent.
4. At +35%, sell another 25% of original quantity.
5. Trail all remaining contracts using the premium profile.
6. Two opposing market confirmations may reduce 25% while profitable. A confirmed persistent reversal may close the remainder.
7. An explicit analyst sell overrides the state machine and sells the requested share of the current broker-backed position.
8. The 0DTE liquidation deadline overrides all discretionary rules.

Small positions use whole-contract floor rounding while preserving a final runner whenever quantity permits.

## Execution integrity

- A persisted exit reservation is acquired before order submission and cleared on terminal failure/cancel/fill.
- Pending broker sell orders suppress additional automated exits.
- Order timeout is followed by cancel confirmation and broker reconciliation; a late fill must still create or update the local position.
- Local state is reconciled from Alpaca positions/orders on startup and during the worker cycle.
- The existing repeated-entry-with-appended-commentary guard remains active; DCA requires an explicit newest instruction to add.

## Defaults for the September 3 test

- Coordinated lifecycle enabled.
- Maximum acceptable loss per normal entry: $500.
- Normal hard stop: -35%.
- High-risk hard stop: -50% and size cap: 25%.
- Staged profit targets: +25%/50% and +35%/25%.
- Legacy independent take-profit, bracket, break-even, stop-loss, and trailing-stop switches disabled so they cannot conflict with the coordinated lifecycle.
- Adaptive reversal intelligence enabled with warning at two opposing confirmations and confirmation at four.
- 0DTE liquidation enabled at 3:40 PM Eastern.

## Observability

Every sizing decision, state transition, reservation, order submission, fill, cancel, stale-quote hold, and broker/local reconciliation writes structured context to the existing trade logs. The API exposes the effective policy and persisted lifecycle state for the UI and next-day review.
