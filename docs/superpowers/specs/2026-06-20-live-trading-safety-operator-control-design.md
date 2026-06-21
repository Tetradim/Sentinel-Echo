# Live Trading Safety and Operator Control Design

## Goal

Make live trading harder to misconfigure by adding an explicit arming flow, readiness gates, append-only operator audit events, panic stop, reconciliation visibility, typed frontend API contracts, broker capability metadata, and removal of confusing demo or stale control paths.

## Scope

This design covers the current Consolidation bot in one repo:

- Backend FastAPI routes and trading services.
- SQLite/Mongo database abstraction.
- React Native Web operator screens.
- Existing test and Playwright UI audit harnesses.

It does not add new broker integrations or guarantee broker-side cancel support for brokers that do not expose it. Broker actions that cannot be automated must report a clear capability gap.

## Current Context

The app already has useful primitives:

- `backend/routes/health.py` exposes setup diagnostics.
- `backend/routes/operator.py` records operator events in `operator_events`.
- `backend/fill_monitor.py` and `backend/fill_reconciliation.py` track order/fill/position outcomes.
- `backend/order_execution.py` resolves configured broker clients.
- `backend/database/abstraction.py` has runtime state and operator event methods.
- Frontend screens already consume live endpoints and have digest tests around readiness, trades, positions, settings, and route contracts.

The design extends those primitives instead of creating parallel systems.

## Approach

Use an incremental safety-core approach:

1. Backend safety and audit foundations first.
2. Frontend typed API client and UI affordances second.
3. Reconciliation dashboard and service extraction third.

This gives the operator immediate risk reduction before the larger UI and refactor work lands.

## Backend Architecture

### Runtime Arming State

Add live arming fields to runtime state:

- `live_trading_armed`: boolean.
- `live_trading_armed_until`: ISO timestamp or empty string.
- `live_trading_armed_by`: operator label, default `local_operator`.
- `live_trading_arm_reason`: short reason string.

Live arming is runtime state, not settings, because it is temporary operational state. Restarting the bot should return to safe unarmed behavior unless the stored `armed_until` is still valid and the runtime state explicitly says armed.

### Readiness Gate

Create a backend readiness evaluator that returns:

- `ready_for_live`: boolean.
- `blocking_issues`: list of machine-readable issue codes and human summaries.
- `warnings`: non-blocking warnings.
- `checks`: structured sections for API auth, credential key, broker capability, broker connection/configuration, source policy, simulation mode, max position size, order status support, notification health, and shutdown state.

The readiness gate is used by:

- `POST /api/operator/live-arm`.
- `POST /api/toggle-trading`.
- Any live auto-trade path before broker order placement.
- `/api/diagnostics/setup` so the dashboard and setup pages report the same truth.

### Live Arming Flow

Add endpoints:

- `GET /api/operator/live-readiness`
- `POST /api/operator/live-arm`
- `POST /api/operator/live-disarm`

`live-arm` requires:

- `duration_minutes` between 1 and 480.
- `confirmation` matching a fixed phrase such as `ARM LIVE TRADING`.
- readiness gate with zero blockers.

When live arming succeeds, it updates runtime state and writes an operator audit event. When it fails, it returns HTTP 409 with the blockers and writes an audit event with severity `warning`.

### Panic Stop

Add `POST /api/operator/panic-stop`.

It must:

- Set `auto_trading_enabled=false` in settings.
- Set `live_trading_armed=false` and `shutdown_triggered=true` in runtime state.
- Attempt broker order cancellation only if the active broker exposes cancel support and pending order IDs can be found.
- Return a summary with cancellation attempts, unsupported capabilities, and resulting runtime state.
- Write an operator audit event with severity `critical`.

The first version can disable automation and record cancel support gaps even if no pending-order table exists yet.

### Append-Only Operator Audit

Use the existing `operator_events` table/collection as the audit stream. Add helper functions so all state-changing routes can record consistent events:

- settings updates,
- broker switches,
- bot start/stop,
- auto-trading toggles,
- live arm/disarm,
- panic stop,
- trade close/update,
- position sell,
- operator lab actions.

Events must include category, action, severity, summary, timestamp, and sanitized details. Secrets are never logged.

### Reconciliation API

Add `GET /api/operator/reconciliation`.

It returns linked rows from alerts, trades, and positions:

- alert metadata,
- trade/order status,
- order ID/client order ID,
- fill status where available,
- position status,
- simulated/live flag,
- attention reason when a chain is broken or unconfirmed.

The first version derives this from existing alert/trade/position records without creating a new orders table. Later order tables can plug into the same response shape.

### Broker Capabilities

Add a small capability registry:

- `supports_options`
- `supports_order_status`
- `supports_cancel_order`
- `supports_live_trading`
- `supports_paper_trading`
- `requires_gateway`
- `auth_mode`

Use this registry in diagnostics, broker check responses, readiness checks, and frontend broker summaries.

### Service Extraction

Extract backend live execution decisions into focused service modules:

- `backend/operator_audit.py` for audit event helpers.
- `backend/live_readiness.py` for readiness checks.
- `backend/live_arming.py` for arming/disarming semantics.
- `backend/reconciliation.py` for alert/trade/position chain summaries.
- `backend/broker_capabilities.py` for capability metadata.

Keep `backend/server.py` behavior-compatible while moving decision logic out of it gradually.

## Frontend Architecture

### Typed API Client

Replace scattered endpoint strings with a central typed client in `frontend/utils/apiClient.ts`.

The client exports functions such as:

- `getSettings`
- `updateSettings`
- `toggleTrading`
- `getLiveReadiness`
- `armLiveTrading`
- `disarmLiveTrading`
- `panicStop`
- `getReconciliation`
- `sellPosition`
- `closeTrade`
- `updateTradePrice`
- `switchBroker`
- `checkBroker`

Screens should import functions from this client instead of constructing route strings inline.

### Live Safety UI

Update Dashboard and Trading Settings:

- Show readiness blockers before live controls.
- Replace plain live toggles with an explicit arming panel.
- Show armed/unarmed state, expiration, active broker, simulation mode, and source-policy summary.
- Add a visible panic stop button with confirmation.

### Reconciliation View

Add an operator reconciliation section or screen that displays:

- alert,
- order/trade,
- fill,
- position,
- attention state.

Use existing layout patterns and keep it operational, not marketing-style.

### Accessibility and UI Cleanup

Fix known UI audit issues:

- add accessible labels to switches and sidebar buttons,
- make Discord Settings hidden actions visible or remove them,
- remove stale/unavailable actions or label them as unavailable.

## Data Flow

1. Operator opens Dashboard.
2. Frontend loads status, settings, diagnostics, and live readiness.
3. If the operator requests live arming, the frontend posts confirmation and duration.
4. Backend runs readiness checks, updates runtime state on success, and appends audit event.
5. Discord ingestion and live order placement check settings plus runtime arming before placing real orders.
6. Panic stop disables automation, disarms live trading, triggers runtime shutdown state, attempts supported cancellations, and appends audit event.
7. Reconciliation endpoint lets the operator inspect alert-to-position state after every action.

## Error Handling

- Readiness failures return HTTP 409 with blockers.
- Panic stop returns HTTP 200 when automation is disabled even if broker cancellation is unsupported; unsupported cancellation is reported in the response.
- API client methods surface backend messages and never replace live data with demo data.
- Audit logging failures should not hide failed state changes, but they should be logged and returned as warnings when possible.

## Testing

Backend tests:

- readiness gate blocks live arm when auth/credential/broker/source/simulation checks fail,
- live arm succeeds only with confirmation and no blockers,
- live disarm clears runtime state,
- panic stop disables auto trading and disarms live state,
- live trade processing rejects real broker placement when not armed,
- broker capability registry feeds diagnostics,
- reconciliation response links alerts/trades/positions and flags broken chains,
- state-changing endpoints append sanitized operator events.

Frontend tests:

- typed client contains route contracts used by screens,
- live safety digest prioritizes blockers and armed expiration,
- no screen constructs critical API paths inline,
- panic stop and arm controls require explicit confirmation state,
- reconciliation digest flags attention states,
- existing no-demo-fallback test remains enforced.

End-to-end audit:

- full UI audit must click live-safety controls in simulated/local mode without placing live orders,
- panic stop must leave `auto_trading_enabled=false`,
- no unexpected browser console/page errors.

## Rollout Order

1. Backend safety core: capabilities, readiness, arming, panic stop, audit helpers.
2. Enforce live arming in auto-trade execution.
3. Typed frontend API client and route cleanup.
4. Live safety UI and panic stop controls.
5. Reconciliation API and view.
6. UI audit accessibility cleanup.
7. Gradual service extraction from `backend/server.py`.

## Acceptance Criteria

- Live broker order placement is impossible unless simulation mode is off, auto trading is enabled, readiness passes, and live trading is armed.
- Every safety-relevant state change writes an operator event without secrets.
- Panic stop can be triggered from the UI and disables automated live trading.
- Operator can inspect alert/order/fill/position reconciliation from the UI.
- Frontend critical routes are centralized in the typed API client.
- Full backend tests, frontend tests, and UI audit pass.
