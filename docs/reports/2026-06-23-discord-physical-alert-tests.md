# Discord Physical Alert Test Report - 2026-06-23

Scope: Sentinel Echo Discord test channel `1518453268169101402`, Chrome bridge target `sentinel-echo`, simulation mode enabled.

## Results

- `CODX-FULL-20260622-1942-01` through `CODX-FULL-20260622-1942-30`: 30/30 were physically posted in Discord, seen by the Chrome bridge, parsed, accepted, inserted as alerts, requested simulated trades, linked trades, linked positions, and reconciled with zero alert-chain attention.
- `CODX-RELOAD-20260623-005623`: bridge reload smoke test passed with the same see/parse/accept/buy/reconcile chain.
- `CODX-TRAIL-20260623013431`: physically posted in Discord and used to test trailing-stop sell behavior. The bot bought one simulated SPY 744 PUT at `0.44`, recorded a peak at `0.60`, triggered the premium trailing stop at `0.51`, sold one simulated contract, closed the position, and recorded `7.00` realized P&L.
- `CODX-XDUP-20260623014358`: post-fix duplicate verification passed. One Discord post produced exactly one stored alert and one reconciled alert-chain row.

## Fixes From This Run

- Added deterministic trailing-stop evaluation and operator route: commit `5b11925`.
- Added Chrome bridge raw-alert fingerprint dedupe for Discord DOM re-renders: commit `eb64fe6`.
- Routed Chrome bridge ingestion through the shared duplicate-alert detector so direct Discord bot and bridge ingestion cannot both insert the same parsed alert: commit `54b5c07`.

## Verification

- Backend test suite after trailing-stop route: `328 passed, 1 warning, 41 subtests passed`.
- Backend test suite after bridge re-render dedupe: `329 passed, 1 warning, 41 subtests passed`.
- Backend test suite after cross-ingestion dedupe: `330 passed, 1 warning, 41 subtests passed`.
- Current Chrome bridge health was `healthy` on the Discord test channel after backend restart.
- Current live-readiness remained blocked, as intended, because live trading has not been armed and required live broker/source/security checks are incomplete.

## Live-Readiness Blockers Still Present

- `CREDENTIAL_KEY` is missing.
- Simulation mode is still enabled.
- Active broker is not configured or connected.
- Active broker does not currently prove order-status polling or cancel support.
- Take-profit and stop-loss OCO guards are not both enabled.
- Deterministic Sentinel Archive replay acceptance proof is still missing.
