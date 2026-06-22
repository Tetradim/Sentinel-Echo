# Live Trading Safety and Operator Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add live-trading arming, readiness gates, panic stop, audit events, reconciliation visibility, broker capabilities, typed frontend API contracts, and UI cleanup.

**Architecture:** Extend the existing FastAPI route/database/operator-event surfaces. Keep runtime safety state in `runtime_state`, keep secrets out of audit payloads, and centralize frontend route calls in a typed API client before migrating critical screens.

**Tech Stack:** Python FastAPI, Pydantic, existing async database abstraction, React Native Web, Expo Router, Node test runner, Playwright UI audit.

---

## File Map

- Create `backend/broker_capabilities.py`: broker capability registry and lookup helpers.
- Create `backend/operator_audit.py`: sanitized append-only operator audit helper.
- Create `backend/live_readiness.py`: readiness evaluator shared by diagnostics, live arm, and execution.
- Create `backend/live_arming.py`: runtime live arm/disarm helpers.
- Create `backend/reconciliation.py`: alert/trade/position chain summary builder.
- Modify `backend/database/abstraction.py`: runtime state arming fields for SQLite/Mongo.
- Modify `backend/models/__init__.py`: request models for live arm, panic stop, and reconciliation rows if useful.
- Modify `backend/routes/operator.py`: live readiness, arm/disarm, panic stop, reconciliation endpoints.
- Modify `backend/routes/health.py`: use capability/readiness helpers in setup diagnostics.
- Modify `backend/routes/settings.py`, `backend/routes/brokers.py`, `backend/routes/trading.py`: audit state-changing actions.
- Modify `backend/server.py`: block live broker placement unless runtime live arming is active.
- Create backend tests for safety core, audit events, capabilities, reconciliation, and live-execution gate.
- Create `frontend/utils/apiClient.ts`: typed route contract wrapper around `api`.
- Create `frontend/utils/liveSafetyDigest.ts`: frontend digest for live readiness/arming state.
- Create `frontend/utils/reconciliationDigest.ts`: digest helpers for reconciliation attention states.
- Modify `frontend/app/index.tsx`, `frontend/app/operator-lab.tsx`, `frontend/app/trading-settings.tsx`, `frontend/app/_layout.tsx`, `frontend/app/discord-settings.tsx`: expose safety controls and accessibility fixes.
- Create/update frontend tests for API client route contracts, live safety digest, reconciliation digest, and no raw critical endpoint construction.
- Modify `scripts/ui_full_audit.py`: click arm/disarm/panic/reconciliation controls in local simulated mode.

## Task 1: Broker Capabilities

**Files:**
- Create: `backend/broker_capabilities.py`
- Modify: `backend/routes/health.py`
- Test: `backend/tests/test_broker_capabilities.py`

- [ ] **Step 1: Write failing tests**

```python
def test_known_broker_capabilities_expose_order_status_and_cancel_support(self):
    from broker_capabilities import get_broker_capabilities
    alpaca = get_broker_capabilities("alpaca")
    self.assertTrue(alpaca["supports_options"])
    self.assertTrue(alpaca["supports_order_status"])
    self.assertTrue(alpaca["supports_cancel_order"])
    self.assertEqual(alpaca["auth_mode"], "api_key")

def test_unknown_broker_capabilities_are_safe(self):
    from broker_capabilities import get_broker_capabilities
    unknown = get_broker_capabilities("unknown")
    self.assertFalse(unknown["supports_live_trading"])
    self.assertFalse(unknown["supports_order_status"])
```

- [ ] **Step 2: Run test to verify failure**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_broker_capabilities -v`

Expected: import failure for `broker_capabilities`.

- [ ] **Step 3: Implement registry**

Create `backend/broker_capabilities.py` with a frozen registry for `ibkr`, `alpaca`, `tradier`, `tradestation`, `thinkorswim`, `webull`, `robinhood`, `td_ameritrade`, and a safe unknown fallback.

- [ ] **Step 4: Run test to verify pass**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_broker_capabilities -v`

Expected: all tests pass.

## Task 2: Runtime Arming State

**Files:**
- Modify: `backend/database/abstraction.py`
- Test: `backend/tests/test_live_arming.py`

- [ ] **Step 1: Write failing tests**

```python
def test_default_runtime_state_is_unarmed(self):
    from database.abstraction import _default_runtime_state
    state = _default_runtime_state()
    self.assertFalse(state["live_trading_armed"])
    self.assertEqual(state["live_trading_armed_until"], "")
```

- [ ] **Step 2: Run test to verify failure**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_live_arming -v`

Expected: missing `live_trading_armed`.

- [ ] **Step 3: Add fields**

Add `live_trading_armed`, `live_trading_armed_until`, `live_trading_armed_by`, and `live_trading_arm_reason` to `_default_runtime_state`, Mongo updates, SQLite schema, row mapping, and allowed update columns.

- [ ] **Step 4: Run test to verify pass**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_live_arming -v`

Expected: all tests pass.

## Task 3: Audit Helper

**Files:**
- Create: `backend/operator_audit.py`
- Modify: `backend/routes/operator.py`
- Test: `backend/tests/test_operator_audit.py`

- [ ] **Step 1: Write failing tests**

```python
def test_audit_sanitizes_secret_fields(self):
    from operator_audit import sanitize_audit_details
    result = sanitize_audit_details({"api_key": "secret", "nested": {"password": "pw"}, "safe": "ok"})
    self.assertEqual(result["api_key"], "[redacted]")
    self.assertEqual(result["nested"]["password"], "[redacted]")
    self.assertEqual(result["safe"], "ok")
```

- [ ] **Step 2: Run test to verify failure**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_operator_audit -v`

Expected: import failure for `operator_audit`.

- [ ] **Step 3: Implement helper**

Create `record_operator_event(db, category, action, summary, severity="info", details=None)` and `sanitize_audit_details(details)`.

- [ ] **Step 4: Replace local operator event helper**

Update `backend/routes/operator.py` to use `record_operator_event`.

- [ ] **Step 5: Run test to verify pass**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_operator_audit backend.tests.test_operator_route_contracts -v`

Expected: all tests pass.

## Task 4: Live Readiness and Arming Endpoints

**Files:**
- Create: `backend/live_readiness.py`
- Create: `backend/live_arming.py`
- Modify: `backend/routes/operator.py`
- Modify: `backend/routes/health.py`
- Test: `backend/tests/test_live_readiness.py`
- Test: `backend/tests/test_live_arming.py`

- [ ] **Step 1: Write failing tests**

Tests must cover readiness blockers for missing API key on non-local bind, missing credential key, simulation mode, disabled auto trading, missing broker config, unsupported order status, no live source, and shutdown state.

- [ ] **Step 2: Run test to verify failure**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_live_readiness backend.tests.test_live_arming -v`

Expected: import or endpoint failures.

- [ ] **Step 3: Implement readiness evaluator**

Return `ready_for_live`, `blocking_issues`, `warnings`, and `checks`. Use existing settings, runtime state, broker capabilities, and source override normalization.

- [ ] **Step 4: Implement arming helpers and routes**

Add `GET /api/operator/live-readiness`, `POST /api/operator/live-arm`, and `POST /api/operator/live-disarm`.

- [ ] **Step 5: Run test to verify pass**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_live_readiness backend.tests.test_live_arming backend.tests.test_setup_diagnostics -v`

Expected: all tests pass.

## Task 5: Panic Stop

**Files:**
- Modify: `backend/routes/operator.py`
- Test: `backend/tests/test_panic_stop.py`

- [ ] **Step 1: Write failing tests**

Test that panic stop disables settings auto trading, clears live arming, sets runtime shutdown, records critical audit event, and reports unsupported broker cancellation when no pending order source exists.

- [ ] **Step 2: Run test to verify failure**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_panic_stop -v`

Expected: missing route/helper failure.

- [ ] **Step 3: Implement route**

Add `POST /api/operator/panic-stop` returning `auto_trading_enabled`, `live_trading_armed`, `shutdown_triggered`, `cancellation_attempts`, and `warnings`.

- [ ] **Step 4: Run test to verify pass**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_panic_stop backend.tests.test_operator_route_contracts -v`

Expected: all tests pass.

## Task 6: Live Execution Gate

**Files:**
- Modify: `backend/server.py`
- Test: `backend/tests/test_live_order_submission_status.py`

- [ ] **Step 1: Write failing test**

Add a test where `simulation_mode=False`, `auto_trading_enabled=True`, but runtime arming is false; assert no broker order is placed and alert is marked not executed.

- [ ] **Step 2: Run test to verify failure**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_live_order_submission_status -v`

Expected: broker order is currently placed without live arming.

- [ ] **Step 3: Enforce gate**

Before live broker placement, read runtime state and require active non-expired arming when `settings.simulation_mode` is false.

- [ ] **Step 4: Run test to verify pass**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_live_order_submission_status -v`

Expected: all tests pass.

## Task 7: Reconciliation API

**Files:**
- Create: `backend/reconciliation.py`
- Modify: `backend/routes/operator.py`
- Test: `backend/tests/test_reconciliation.py`

- [ ] **Step 1: Write failing tests**

Test a linked alert/trade/position chain and a broken unconfirmed order chain with an `attention_reason`.

- [ ] **Step 2: Run test to verify failure**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_reconciliation -v`

Expected: import or route failure.

- [ ] **Step 3: Implement builder**

Build rows from existing `get_alerts`, `get_trades`, and `get_positions`, keyed by `alert_id` and `trade_ids`.

- [ ] **Step 4: Add route**

Expose `GET /api/operator/reconciliation`.

- [ ] **Step 5: Run test to verify pass**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_reconciliation backend.tests.test_operator_route_contracts -v`

Expected: all tests pass.

## Task 8: Typed Frontend API Client

**Files:**
- Create: `frontend/utils/apiClient.ts`
- Test: `frontend/tests/apiClientContracts.test.cjs`

- [ ] **Step 1: Write failing test**

Read `frontend/utils/apiClient.ts` and assert exported functions include critical route strings for live readiness, arm, disarm, panic stop, reconciliation, sell position, close trade, update trade price, broker switch, and broker check.

- [ ] **Step 2: Run test to verify failure**

Run: `npm.cmd run test:ui` from `frontend`.

Expected: missing file or missing route strings.

- [ ] **Step 3: Implement client**

Wrap `api.get/post/put` calls in named functions using relative `/api/...` paths and optional params/payloads.

- [ ] **Step 4: Run test to verify pass**

Run: `npm.cmd run test:ui` from `frontend`.

Expected: all frontend tests pass.

## Task 9: Frontend Live Safety and Reconciliation Digest

**Files:**
- Create: `frontend/utils/liveSafetyDigest.ts`
- Create: `frontend/utils/reconciliationDigest.ts`
- Test: `frontend/tests/liveSafetyDigest.test.cjs`
- Test: `frontend/tests/reconciliationDigest.test.cjs`

- [ ] **Step 1: Write failing digest tests**

Test blocker prioritization, armed expiration labeling, panic stop visibility, reconciliation attention counting, and all-clear state.

- [ ] **Step 2: Run test to verify failure**

Run: `npm.cmd run test:ui` from `frontend`.

Expected: missing modules.

- [ ] **Step 3: Implement digest modules**

Export pure functions with no React dependencies so Node tests can import them after TypeScript stripping.

- [ ] **Step 4: Run test to verify pass**

Run: `npm.cmd run test:ui` from `frontend`.

Expected: all frontend tests pass.

## Task 10: Frontend Safety UI and Accessibility Fixes

**Files:**
- Modify: `frontend/app/index.tsx`
- Modify: `frontend/app/operator-lab.tsx`
- Modify: `frontend/app/trading-settings.tsx`
- Modify: `frontend/app/_layout.tsx`
- Modify: `frontend/app/discord-settings.tsx`
- Test: `frontend/tests/operatorLabScreen.test.cjs`
- Test: `frontend/tests/operatorNavigation.test.cjs`
- Test: `frontend/tests/liveDataFallbackPolicy.test.cjs`

- [ ] **Step 1: Write/update tests**

Assert UI source contains `Arm Live`, `Disarm`, `Panic Stop`, `Reconciliation`, accessibility labels for switches/sidebar, and no critical raw route strings outside `apiClient.ts`.

- [ ] **Step 2: Run test to verify failure**

Run: `npm.cmd run test:ui` from `frontend`.

Expected: source assertions fail.

- [ ] **Step 3: Implement UI**

Add a live safety panel and reconciliation panel using existing compact operator card styles. Add accessible labels to switches and sidebar buttons. Make Discord action colors visible.

- [ ] **Step 4: Run test to verify pass**

Run: `npm.cmd run test:ui` from `frontend`.

Expected: all frontend tests pass.

## Task 11: Full Verification

**Files:**
- Modify: `scripts/ui_full_audit.py`
- Verify: backend, frontend, Playwright UI audit.

- [ ] **Step 1: Extend audit harness**

Click live readiness, arm/disarm with intentionally blocked local state, panic stop, and reconciliation refresh. Assert panic stop leaves auto trading disabled.

- [ ] **Step 2: Run backend tests**

Run: `backend\.venv\Scripts\python.exe -m unittest discover backend\tests -v`

Expected: 0 failures.

- [ ] **Step 3: Run frontend tests**

Run: `npm.cmd run test:ui` from `frontend`.

Expected: 0 failures.

- [ ] **Step 4: Run UI audit**

Run: `.\scripts\run_ui_full_audit.ps1 -BackendPort 8103 -FrontendPort 3103`

Expected: script exits 0, no unexpected browser/page errors.

## Self-Review

- Spec coverage: all acceptance criteria map to tasks 1-11.
- Placeholder scan: no placeholder tasks remain; each task has files, tests, commands, and expected output.
- Type consistency: runtime arming names are consistent across design and plan.
