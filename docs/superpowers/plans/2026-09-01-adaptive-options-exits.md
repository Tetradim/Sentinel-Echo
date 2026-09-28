# Adaptive Options Exits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic reversal-aware exits, adaptive percentage trailing, mandatory 0DTE liquidation, and auditable profitability telemetry to Echo's broker-confirmed position worker.

**Architecture:** A pure `market_exit_intelligence` module calculates state and evidence. `bot_managed_exits` fetches Alpaca context, persists state, applies precedence, and submits existing Echo-managed SELL orders. Fill reconciliation owns durable one-shot stage completion.

**Tech Stack:** Python 3.11, FastAPI/Pydantic, asyncio/aiohttp, SQLite/Mongo abstraction, React Native/Expo, Node test runner.

---

### Task 1: Pure market intelligence

**Files:**
- Create: `backend/market_exit_intelligence.py`
- Create: `backend/tests/test_market_exit_intelligence.py`

- [x] Write failing tests for reversal persistence, missing context, adaptive bounds, and telemetry threshold hits.
- [x] Run the focused test and confirm missing-module failure.
- [x] Implement immutable decisions plus pure calculation helpers.
- [x] Rerun the focused tests and confirm they pass.

### Task 2: Worker integration and quote reuse

**Files:**
- Modify: `backend/broker_clients/__init__.py`
- Modify: `backend/bot_managed_exits.py`
- Modify: `backend/tests/test_alpaca_entry_context.py`
- Modify: `backend/tests/test_bot_managed_exits.py`

- [x] Add failing tests for context fetch, persisted state, quantities, precedence, and fresh-bid pricing.
- [x] Expose a general Alpaca option-market-context method while preserving the Phase 1 entry alias.
- [x] Refresh each open position with midpoint, bid, ask, bars, and calculated state before exit evaluation.
- [x] Submit warning and confirmed reversal decisions through the existing fill monitor.
- [x] Run the focused worker and broker tests.

### Task 3: 0DTE and one-shot stages

**Files:**
- Modify: `backend/bot_managed_exits.py`
- Modify: `backend/fill_reconciliation.py`
- Modify: `backend/tests/test_bot_managed_exits.py`
- Modify: `backend/tests/test_fill_reconciliation.py`

- [x] Add failing tests for cutoff evaluation, expiring BUY cancellation, full-position liquidation, and completed partial stages.
- [x] Add New York cutoff parsing and mandatory decision precedence.
- [x] Cancel matching expiring BUY orders before evaluating positions.
- [x] Persist `take_profit_stage_completed` and `reversal_warning_completed` after fills.
- [x] Prevent completed partial stages from firing again and run focused tests.

### Task 4: Settings and operator controls

**Files:**
- Modify: `backend/models/__init__.py`
- Modify: `backend/database/abstraction.py`
- Modify: `backend/database_sqlite.py`
- Modify: `backend/routes/settings.py`
- Modify: `frontend/utils/riskSettingsState.ts`
- Modify: `frontend/app/risk-settings.tsx`
- Modify: `frontend/tests/riskSettingsState.test.cjs`
- Modify: `frontend/tests/riskSettingsPersistence.test.cjs`

- [x] Add failing backend tests for validated defaults and invalid cutoff/count/range values.
- [x] Add settings defaults and request validation.
- [x] Add failing frontend load/save tests for the exact snake-case fields.
- [x] Add a compact Intelligence tab and validation.
- [x] Run focused backend and frontend settings tests.

### Task 5: Verification and documentation

**Files:**
- Modify: `docs/smart-entry-sizing.md`
- Modify: `README.md`

- [x] Document precedence, defaults, telemetry, degraded-data behavior, and Phase 1 interaction.
- [x] Run the full backend test suite.
- [x] Run all frontend tests, TypeScript, lint, and Expo web export.
- [x] Run `git diff --check` and review the scoped diff without reverting unrelated worktree changes.
