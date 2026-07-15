# Sentinel Echo live-functional repair log

Branch: `codex/live-order-reconciliation`
PR: #5
Review scope: live-money options alert execution, fill reconciliation, position management and restart recovery. Security, paper trading and release gates are secondary to functional execution.

## Verified baseline before this repair cycle

- Echo Live Readiness: passing at `5c527b550105119d474b015416fe344ae8f49826`.
- Build Windows Executable: passing at the same commit.

## Findings from post-fix review

### P0 — broker submission happens before durable intent creation

Both entry and exit paths call the broker before inserting the pending trade. A crash or database failure after broker acceptance can create an orphan live order that startup recovery cannot discover.

Planned fix:

1. Insert durable `submitting` intent with deterministic client order ID before the broker call.
2. Update it with broker order ID after acknowledgement.
3. On ambiguous submission, query by client order ID instead of issuing a second order.
4. Start the monitor only after acknowledgement is durable.

### P0 — exits use the global active broker instead of position ownership

An existing position may be held at a different broker than the current settings selection.

Planned fix:

- Route every exit through immutable `position.broker` and `position.account_id` fields.
- Group exit plans by broker/account and reconcile held quantity before submission.

### P0 — option symbols are not canonical OCC symbols

Alpaca and Tradier duplicate date formatting and can emit an eight-digit date segment for a four-digit year.

Planned fix:

- Add one OCC symbol builder that accepts all supported input formats and always emits `YYMMDD` plus padded strike.
- Remove duplicated symbol construction.

### P0/P1 — unsupported brokers remain selectable

Only Alpaca and Tradier expose the complete submit/status path in the reviewed factory. IBKR submits but lacks the required status/recovery contract; other clients are explicitly unimplemented.

Planned fix:

- Restrict live selection to fully implemented brokers.
- Add IBKR only after status, lookup-by-client-ID, positions, open orders and cancellation are complete.

### P1 — no broker-wide startup reconciliation

Recovery resumes locally known pending trades but does not discover unknown broker orders or positions.

Planned fix:

- Fetch broker open orders and positions before Discord processing.
- Match broker order ID/client order ID and reconstruct missing local records.

### P1 — exit quantity is not atomically reserved

Concurrent alerts can plan sells from the same remaining quantity.

Planned fix:

- Atomically reserve contracts before submission and release/consume reservations through the order lifecycle.

### P1 — submission is marked as trade execution

The alert path sets `trade_executed` after receiving an order ID rather than after a positive fill.

Planned fix:

- Separate submitted, partial, filled, cancelled, rejected and expired states.

### P1 — no quote-aware repricing or autonomous position-risk supervisor

Alert prices can be stale and the fill monitor watches orders, not live option positions.

Planned fix:

- Add bid/ask/spread/quote-age checks and bounded cancel-replace.
- Add broker-native OCO/brackets or a durable option-position risk supervisor.

## Repair order

1. Pre-submit durable order intent and ambiguous-submit recovery.
2. Correct exit broker/account ownership.
3. Canonical OCC symbols.
4. Live broker capability restriction.
5. Atomic exit reservations and startup broker reconciliation.
6. Quote-aware execution and autonomous exits.
7. Full workflow run and source review.

## Status

In progress.
