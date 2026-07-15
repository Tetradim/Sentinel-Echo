# Sentinel Echo Frontend ↔ Backend Function Audit

Date: 2026-07-15  
Branch audited: `codex/live-order-reconciliation`  
Purpose: verify that visible Echo controls use the repaired live option-order lifecycle and that autonomous backend functions have operator visibility.

## Status definitions

- **Connected** — the screen calls a registered backend route and consumes its real response.
- **Fixed in this branch** — a broken or dangerous UI/backend connection was repaired.
- **Partial** — useful state is connected, but an important operation or field remains absent.
- **Backend-only by design** — automatic execution machinery should be observed, not manually imitated.
- **Legacy / unregistered** — code exists but is not mounted in the production API.
- **Not connected** — no working route/screen path exists.

## Critical findings fixed

1. **The Positions Sell button called a nonexistent route.**
   - UI called `POST /api/positions/{id}/sell`.
   - The registered backend exposed only `POST /api/sell-position/{id}`.
   - Result: the visible control could return 404.

2. **The old sell handler did not submit a broker order.**
   - It immediately reduced local quantity and calculated realized P&L.
   - Result: the UI could claim a position was sold while the broker still held it.
   - Fix: both paths now call one durable live exit function.

3. **The UI claimed completion before broker fill.**
   - Old success message was based on a local database update.
   - Fix: live response says `submitted`, returns broker/client order IDs, and explains that position state changes only after fills.

4. **Backend failures silently produced demo positions.**
   - This made an unavailable backend look like a populated portfolio.
   - Fix: demo data is used only when `DEMO_MODE` is explicitly enabled. Normal failures show a backend-unavailable message.

5. **Repaired live lifecycle functions had no frontend visibility.**
   - Journal, ambiguous deliveries, fill monitors, inventory recovery, autonomous supervisor and working trades were log-only.
   - Fix: `/api/live-operations` plus a visible Live Operations screen.

6. **Broker Config called two nonexistent routes.**
   - UI uses `/api/broker/switch/{id}` and `/api/broker/check/{id}`.
   - Fix: production routes now back those exact paths.
   - Live switching refuses incomplete adapters; Alpaca and Tradier are the complete live option lifecycles.

## Detailed function matrix

| Backend capability / route | Backend implementation | Frontend implementation | Status | Finding / action |
|---|---|---|---|---|
| Health and bot status | health route/status object | Dashboard status cards | Connected | Dashboard polls backend and displays bot/Discord/broker state. |
| Portfolio summary | `GET /api/portfolio` | Dashboard summary | Connected | Visible portfolio totals come from database abstraction. |
| Alerts list | `GET /api/alerts` | `app/alerts.tsx`, dashboard recent alerts | Connected | Explicit `DEMO_MODE` may supply demo data; normal backend errors should remain errors. |
| Trades list | `GET /api/trades` | `app/trades.tsx`, dashboard recent trades | Connected | Trade rows include pending/partial/executed states. Other screens should avoid interpreting submission as fill. |
| Positions list | `GET /api/positions` | `app/positions.tsx` | Fixed in this branch | No silent demo fallback during normal backend failure. |
| Manual full/partial position exit | `POST /api/positions/{position_id}/sell` | Positions `Submit Exit` modal | Fixed in this branch | Uses position-owner broker, deterministic ID, journalled client, live quote, broker order ID and fill monitor. |
| Legacy manual exit alias | `POST /api/sell-position/{position_id}` | Older clients | Legacy / compatibility | Now calls the same durable exit path instead of mutating position immediately. |
| Live exit result | manual exit route response | Positions alert/submission banner | Fixed in this branch | Shows submitted/already-working/filled, requested quantity, broker and order ID. |
| Duplicate unresolved exit prevention | journal active-exit lookup | Positions receives `already_working` | Connected | UI does not create a second sell while an earlier exit is unresolved. |
| Current broker option quote | patched Alpaca/Tradier clients | Indirectly used by exit UI | Backend-only by design | UI supplies a reference/slippage boundary; backend chooses the broker-quote-based limit. |
| Quote/spread/age rejection | `option_execution_quote_patch.py` | Error returned to exit modal | Connected as feedback | UI reports non-executable, stale or over-cap quotes without claiming submission. |
| Durable pre-submit journal | `live_order_journal.py`, routing wrapper | Live Operations journal | Fixed in this branch | Operator can see client ID, broker order ID, status, quantities and errors. |
| Ambiguous submission recovery | journal + client-order lookup | Live Operations unresolved list | Fixed in this branch | Same deterministic ID remains visible; no retry button creates a new ID. |
| Fill monitoring | `fill_monitor.py` | Live Operations monitor count and trade/position updates | Fixed in this branch | Monitor tasks are visible; fill application remains automatic. |
| Partial/final fill reconciliation | `fill_reconciliation_v2.py` | Trades/positions plus journal status | Connected | Frontend sees resulting trade/position quantities; no manual fill control exists. |
| Position supervisor | `option_position_supervisor.py` | Live Operations supervisor status; Risk settings configure thresholds | Fixed in this branch | Runs take-profit, stop-loss and trailing exits on broker quotes. |
| Position supervisor settings | settings/risk routes | `app/risk-settings.tsx` | Connected | Existing toggles and thresholds drive the supervisor. |
| Aged-order cancel/reprice | `option_order_expiry_patch.py` and continuation patch | Live Operations journal status | Connected as status | Automatic; no manual cancel/reprice button yet. |
| Explicit exit continuation | `explicit_exit_continuation_patch.py` | Journal/trade status | Connected as status | Outstanding quantity continues after cancellation. |
| Broker inventory reconciliation | `broker_inventory_reconciliation.py` | Live Operations inventory timestamp/counts, Positions data | Fixed in this branch | Broker positions and unknown working orders are imported before Discord starts. |
| Imported broker position ownership | inventory reconciler | Positions broker badge | Connected | Broker is visible; broker account ID is not yet displayed. |
| Live operations summary | `GET /api/live-operations` | `app/live-operations.tsx` | Fixed in this branch | Shows active journal, unresolved orders, monitors, supervisor, working trades and inventory. |
| Live order lookup | `GET /api/live-operations/order/{client_order_id}` | No direct search control | Partial | Backend route exists; current screen lists records but does not provide ID search. |
| Supported live brokers | `GET /api/live-brokers` | Backend action boundary; no dedicated capability card yet | Partial | Alpaca/Tradier are enforced. Broker catalog still displays configuration forms for incomplete adapters. |
| Broker switch | `POST /api/broker/switch/{broker_id}` | `app/broker-config.tsx` | Fixed in this branch | Exact UI path now exists. In live mode incomplete adapters are rejected. |
| Broker connection check | `POST /api/broker/check/{broker_id}` | Broker Config Check Connection | Fixed in this branch | Calls configured client and reports whether complete live lifecycle is supported. |
| Legacy active broker route | `POST /api/active-broker/{broker_id}` | Other/older callers | Connected | Existing backend route remains. |
| Broker catalog | `GET /api/brokers` | Broker Config tabs | Partial | Catalog includes incomplete adapters. Descriptions should eventually carry explicit `live_execution_supported` metadata. |
| Settings retrieval/update | `GET/PUT /api/settings` | Settings, broker config and several dedicated screens | Connected | Main settings round-trip through backend. |
| Trading toggle | settings route | Trading settings screen/dashboard | Connected | Controls backend status/settings. |
| Premium buffer | settings routes | Trading settings | Connected | Used before broker quote-aware final pricing. |
| Averaging down | settings routes | Trading/risk settings | Connected | Settings visible; strategy execution behavior remains alert-driven. |
| Take-profit/stop-loss | risk settings routes | Risk screen | Connected | Directly consumed by autonomous supervisor. |
| Trailing stop | trailing settings routes | Risk screen | Connected | Percent/premium configuration is visible. |
| Auto-shutdown/loss counters | settings routes | Risk/settings screens | Connected | Runtime counters and reset path exist. |
| Discord token/channel settings | Discord routes | `app/discord-settings.tsx` | Connected | Production lifespan starts Discord only after recovery. |
| Discord status/start/stop | Discord routes | Dashboard/settings controls | Connected | Visible lifecycle. |
| Profiles | profile routes | `app/profiles.tsx` | Connected | Profile configuration is available. Verify per-profile broker settings do not imply unsupported live adapters. |
| Strike selection configuration | strike settings endpoints | `app/strike-selection.tsx` | Connected | Configuration surface exists; contract construction uses the canonical backend OCC builder. |
| Notifications | notification functions | Trade/fill notifications | Backend-only by design | No dedicated UI status endpoint in the reviewed production router. |
| Startup journal recovery | `runtime_app.py`, recovery function | Live Operations after startup | Backend-only with status | Must complete before Discord ingestion; no manual start button. |
| Startup fill-monitor recovery | `resume_pending_fill_monitors` | Live Operations monitor count | Backend-only with status | Automatically resumes nonterminal broker orders. |
| Startup inventory recovery | inventory reconciler | Live Operations inventory panel | Backend-only with status | Runs before journal reconstruction and Discord ingestion. |
| `trading_v2.py` simulation handlers | unregistered route module | No production screen | Legacy / unregistered | Should not be mounted; it locally mutates simulated positions and is not the repaired live path. |

## Backend functions intentionally not exposed as direct controls

The following should remain automatic or status-only:

- journal `begin`, acknowledge and broker-status reduction;
- client-order ambiguous lookup;
- cumulative fill delta calculation;
- trade/position application markers;
- active fill monitor registry;
- broker inventory import/closure;
- autonomous stop/profit/trailing evaluation;
- cancel/reprice scheduling;
- explicit exit continuation;
- position-owner broker selection.

A button that manually marks these complete would recreate synthetic-fill and wrong-broker failures.

## Remaining UI gaps

1. **Broker capability labels** — Broker Config still shows all legacy adapters similarly. It should consume `/api/live-brokers` and visibly mark only Alpaca/Tradier as complete live lifecycles.
2. **Manual order cancellation** — Live Operations is read-only. There is no deliberate cancel action for a selected broker order.
3. **Journal search** — order lookup endpoint exists, but the UI has no client-order-ID search field.
4. **Broker account ownership** — Positions shows broker but not `broker_account_id` or OCC symbol.
5. **Quote detail history** — latest execution quote is stored but the Live screen does not expand bid, ask, spread, quote age and repricing attempts.
6. **Immediate inventory refresh** — reconciliation runs on startup; no operator button triggers an on-demand broker inventory sync.
7. **Supervisor cycle telemetry** — running/stopped is visible, but last cycle duration, checked positions and submitted exits are not persisted as a status record.
8. **Other demo-enabled screens** — Alerts, Trades, Dashboard and Settings still contain explicit `DEMO_MODE` paths. They are acceptable only when the build explicitly enables demo mode and must never activate on ordinary fetch failure.
9. **Assignments/exercises/multi-leg positions** — no UI or complete backend lifecycle exists for these cases.

## Files changed by this audit

- `backend/routes/trading.py`
- `backend/routes/live_operations.py`
- `backend/routes/live_broker_operations.py`
- `backend/routes/__init__.py`
- `backend/runtime_app.py`
- `frontend/app/positions.tsx`
- `frontend/app/live-operations.tsx`
- `frontend/app/_layout.tsx`
- `backend/tests/test_frontend_live_operations_wiring.py`
- `.github/workflows/live-readiness.yml`

## Verification boundary

The contract tests prove that the visible source paths and production route mounting remain present. They do not replace a real browser run against configured Alpaca/Tradier accounts. Live verification must confirm that the submitted order ID appears in the UI, partial fills update quantity once, restart resumes the monitor, and broker inventory restores the same position owner.
