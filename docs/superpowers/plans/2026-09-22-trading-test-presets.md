# Trading Test Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five complete, review-before-save trading experiment presets to Echo's Core / Runners tab and activate No Downside Stop for today's session.

**Architecture:** A pure TypeScript preset module owns immutable complete settings patches, matching, and diff generation. The existing runner screen owns the unsaved selection and combines the selected preset patch with its visible runner state only when Save is pressed. The existing validated settings API persists and audits the update.

**Tech Stack:** TypeScript 5.9, React Native Web, Expo Router, Node test runner, FastAPI/Pydantic settings API.

---

### Task 1: Preset Contract

**Files:**
- Create: `frontend/utils/tradingTestPresets.ts`
- Create: `frontend/tests/tradingTestPresets.test.cjs`

- [ ] **Step 1: Write failing preset tests**

Test that five stable preset IDs exist, every preset preserves sell-alert listening and both 0DTE controls, Full Take Profit enables only the +50% legacy target, and No Downside Stop disables ladders/stops while retaining staged profit and runner trailing.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `node --test tests/tradingTestPresets.test.cjs`

Expected: FAIL because `tradingTestPresets.ts` does not exist.

- [ ] **Step 3: Implement immutable preset definitions and helpers**

Export `TRADING_TEST_PRESETS`, `getTradingTestPreset`, `applyTradingTestPreset`, `diffTradingTestPreset`, and `matchesTradingTestPreset`. Clone arrays and nested objects whenever a payload is returned so form edits cannot mutate the definitions.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `node --test tests/tradingTestPresets.test.cjs`

Expected: all preset contract tests pass.

### Task 2: Draft and Review UI

**Files:**
- Modify: `frontend/app/runner-settings.tsx`
- Modify: `frontend/tests/runnerSettingsPersistence.test.cjs`

- [ ] **Step 1: Add failing source-contract tests**

Assert that the runner screen renders Trading test presets, keeps a selected preset in draft state, displays a field-change review, and only submits the preset payload inside the existing Save callback.

- [ ] **Step 2: Run the focused UI test and verify RED**

Run: `node --test tests/runnerSettingsPersistence.test.cjs`

Expected: FAIL because the preset UI and draft payload do not exist.

- [ ] **Step 3: Implement preset selection and review**

Load the complete settings response alongside normalized runner state. On selection, apply the preset to local raw settings and update the runner form. Render compact preset buttons, risk badges, a Draft only banner, and changed-field rows. Clear the selected preset to Custom draft after a manual runner edit.

- [ ] **Step 4: Merge the preset only during Save**

When a preset draft exists, PUT its complete payload merged with `toRunnerSettingsPayload(settings)`. Without a preset, retain the existing runner-only save behavior. On successful save, update the local baseline and display the activated preset name.

- [ ] **Step 5: Run focused UI tests and verify GREEN**

Run: `node --test tests/runnerSettingsPersistence.test.cjs tests/tradingTestPresets.test.cjs tests/runnerSettingsState.test.cjs`

Expected: all tests pass.

### Task 3: Verification and Today's Activation

**Files:**
- No production file changes expected.

- [ ] **Step 1: Run all frontend tests**

Run: `npm run test:ui`

Expected: all tests pass.

- [ ] **Step 2: Run static and build checks**

Run: `npx tsc --noEmit`

Run: `npm run build`

Expected: both commands exit zero.

- [ ] **Step 3: Run backend settings tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_settings_source_overrides.py backend/tests/test_database_sqlite_serialization.py -q`

Expected: all tests pass.

- [ ] **Step 4: Start Echo with its normal launcher**

Verify `http://127.0.0.1:8003/api/health` responds and the configured Alpaca endpoint is `https://paper-api.alpaca.markets/v2` before changing active settings.

- [ ] **Step 5: Apply No Downside Stop through the settings API**

PUT the exact `no_downside_stop` payload to `/api/settings`, then GET settings and verify loss ladder off, legacy stop off, coordinated thresholds at 100, runner catastrophic stop zero, runner trailing on, sell-alert listening on, and both 0DTE controls on.

- [ ] **Step 6: Inspect the app at desktop and mobile widths**

Confirm preset controls fit, text does not overlap, and selection remains local until Save.

## Self-Review

- Spec coverage: preset definitions, review-before-save, complete conflicting-control reset, operational invariants, tests, and today's activation are each covered.
- Placeholder scan: no deferred implementation steps or unspecified tests remain.
- Type consistency: preset IDs and helper names are defined in Task 1 and consumed unchanged in Task 2.

