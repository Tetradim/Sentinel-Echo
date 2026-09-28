# Coordinated Options Exit Lifecycle Implementation Plan

**Goal:** Prepare Echo for the September 3 options-alert test with loss-budget entry sizing and a restart-safe, premium-aware exit state machine.

**Architecture:** Keep Discord parsing and broker submission intact. Add pure policy functions for deterministic sizing and exit decisions, persist lifecycle state on positions, and let the existing bot-managed exit worker own automated sell submission and reconciliation.

**Tech stack:** FastAPI, Pydantic, SQLite abstraction, React Native/TypeScript, unittest/pytest, Node test runner.

## Task 1: Loss-budget sizing

**Files:** `backend/risk.py`, `backend/server.py`, `backend/routes/discord.py`, `backend/tests/test_risk_sizing.py`

1. Add failing tests for normal/high-risk budget caps and the one-contract minimum.
2. Extend `calculate_position_size` with optional loss-budget inputs while preserving existing callers.
3. Apply the cap before alignment/risk-language reductions in both execution paths.
4. Persist sizing telemetry and verify focused tests.

## Task 2: Premium-aware policy

**Files:** `backend/options_exit_policy.py`, `backend/tests/test_options_exit_policy.py`

1. Add failing tests for low/medium/high premium and 0DTE profiles.
2. Add deterministic premium profile selection, whole-contract staged quantities, quote freshness, hard-stop, floor, target, trailing, and reversal decisions.
3. Verify all policy boundary tests.

## Task 3: Persist position lifecycle

**Files:** `backend/models/__init__.py`, `backend/fill_reconciliation.py`, `backend/database_sqlite.py`, `backend/database/abstraction.py`, `backend/tests/test_fill_reconciliation.py`, `backend/tests/test_database_sqlite_serialization.py`

1. Add failing tests for entry policy state, staged-fill transitions, profit-floor arming, reopen reset, and serialization.
2. Add backward-compatible position/settings fields with defaults.
3. Update fill reconciliation to advance lifecycle only from confirmed broker fills.
4. Verify focused persistence and reconciliation tests.

## Task 4: Integrate the worker and reservation

**Files:** `backend/bot_managed_exits.py`, `backend/trailing_stop_engine.py`, `backend/tests/test_bot_managed_exits.py`

1. Add failing tests for decision priority, fresh executable bids, stage quantities, permanent floor, final trail, and duplicate reservation suppression.
2. Route coordinated positions through the new policy evaluator.
3. Persist the high-water mark and reservation before submitting a sell; clear it after failed submission or terminal reconciliation.
4. Keep explicit analyst exits and 0DTE liquidation as overrides.
5. Verify worker and lifecycle tests.

## Task 5: Settings and test profile

**Files:** `backend/models/__init__.py`, `backend/database_sqlite.py`, `backend/database/abstraction.py`, `frontend/utils/riskSettingsState.ts`, `frontend/app/risk-settings.tsx`, relevant backend/frontend tests

1. Add coordinated-lifecycle controls and premium-profile values to settings contracts and UI state.
2. Disable conflicting legacy switches when the coordinated lifecycle is enabled.
3. Update persisted SQLite settings for the September 3 profile without changing credentials or broker endpoint.
4. Verify settings API and frontend persistence tests.

## Task 6: Full verification

1. Run focused backend tests after each slice.
2. Run the full backend suite.
3. Run frontend tests, lint, and build/type checking.
4. Inspect the final diff for accidental secret, generated-file, or unrelated changes.
5. Leave Echo stopped for the scheduled pre-market monitor unless a smoke-test start is required; report the exact test results and effective profile.
