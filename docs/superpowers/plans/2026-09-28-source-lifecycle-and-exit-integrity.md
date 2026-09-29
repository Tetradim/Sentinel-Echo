# Source Lifecycle and Exit Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Homebrew card revisions actionable, preserve exact position ownership through every SELL, make percentage exits correct for small positions, support source-specific behavior, and retain post-exit opportunity telemetry.

**Architecture:** Keep Discord parsing deterministic and convert structured card revisions into explicit lifecycle actions before normal ingestion. Persist broker order ownership on every trade, evaluate loss ladders as cumulative quantity targets, and extend source overrides without creating a second execution path. The existing exit worker will collect bounded post-exit quote telemetry without submitting orders for closed positions.

**Tech Stack:** Python 3.11, FastAPI/Pydantic, SQLite/aiosqlite, React Native Web/TypeScript, unittest/pytest, Node test runner.

---

### Task 1: Structured Homebrew lifecycle actions

**Files:**
- Modify: `backend/structured_alert_cards.py`
- Modify: `backend/card_ingestion.py`
- Modify: `backend/discord_ingestion.py`
- Test: `backend/tests/test_structured_alert_cards.py`
- Test: `backend/tests/test_card_ingestion.py`

- [ ] Add failing tests proving a new filled card is a buy, each newly appended trim is an incremental trim, stop/manual/close rows are full exits, edited rows are deduplicated, and stop/BE metadata updates the exact source position.
- [ ] Run the focused tests and confirm the expected failures.
- [ ] Parse Money Glitch result rows and stable row identities while retaining source-reported quantity, stop, target, open quantity, peak, and net fields as audit metadata.
- [ ] Resolve edited actions to the exact card campaign and persist source stop updates before the trim-listening gate.
- [ ] Run the focused tests to green.

### Task 2: Source-specific trim and profile controls

**Files:**
- Modify: `backend/source_config.py`
- Modify: `backend/discord_ingestion.py`
- Modify: `backend/server.py`
- Modify: `frontend/app/discord-settings.tsx`
- Test: `backend/tests/test_source_config.py`
- Test: `backend/tests/test_discord_ingestion.py`
- Test: `frontend/tests/discordSettingsPersistence.test.cjs`

- [ ] Add failing tests for inherited/enabled/disabled source trim handling and source exit-profile propagation.
- [ ] Run the focused tests and confirm the expected failures.
- [ ] Add normalized source controls for trim handling and `standard`/`swing` exit profiles, display them in Behaviors, and persist them through source overrides.
- [ ] Apply source trim policy during ingestion and persist the selected exit profile on entry trades and positions.
- [ ] Run backend and frontend focused tests to green.

### Task 3: Broker-backed SELL ownership

**Files:**
- Modify: `backend/models/__init__.py`
- Modify: `backend/server.py`
- Modify: `backend/bot_managed_exits.py`
- Modify: `backend/fill_reconciliation.py`
- Test: `backend/tests/test_live_order_submission_status.py`
- Test: `backend/tests/test_bot_managed_exits.py`
- Test: `backend/tests/test_fill_reconciliation.py`

- [ ] Add failing tests requiring every persisted SELL to contain `position_id` and requiring legacy pending SELL recovery to infer only one exact reserved position.
- [ ] Run the focused tests and confirm the expected failures.
- [ ] Persist `position_id` before broker submission and repair legacy pending records only when contract, broker, and reservation uniquely agree.
- [ ] Run the focused tests to green.

### Task 4: Quantity-aware cumulative loss ladder

**Files:**
- Modify: `backend/options_exit_policy.py`
- Modify: `backend/fill_reconciliation.py`
- Test: `backend/tests/test_options_exit_policy.py`

- [ ] Add failing tests for cumulative ladder targets, gap-through behavior, prior ladder fills, and one-contract positions that wait for the configured terminal stop instead of rounding a partial rung to a full exit.
- [ ] Run the focused tests and confirm the expected failures.
- [ ] Persist cumulative ladder quantities and submit only the difference between the deepest triggered target and already executed ladder quantity.
- [ ] Reset cumulative state on a fresh entry campaign and verify DCA does not erase completed risk reductions.
- [ ] Run the focused tests to green.

### Task 5: Source-reported stops and post-exit telemetry

**Files:**
- Modify: `backend/options_exit_policy.py`
- Modify: `backend/bot_managed_exits.py`
- Modify: `backend/database/abstraction.py`
- Modify: `backend/database_sqlite.py`
- Modify: `backend/models/__init__.py`
- Test: `backend/tests/test_options_exit_policy.py`
- Test: `backend/tests/test_bot_managed_exits.py`

- [ ] Add failing tests proving explicit card stop/BE values override the generic stop for that campaign and closed positions collect quote-only telemetry until the configured horizon without placing orders.
- [ ] Run the focused tests and confirm the expected failures.
- [ ] Evaluate explicit source stops ahead of discretionary automatic exits while preserving mandatory liquidation and broker quantity checks.
- [ ] Add configurable post-exit telemetry controls, update closed-position maximum bid and elapsed-high fields, and emit auditable telemetry events only.
- [ ] Run the focused tests to green.

### Task 6: Recommended source configuration and regression verification

**Files:**
- Modify: `backend/database/abstraction.py`
- Modify: `backend/database_sqlite.py`
- Modify: `frontend/app/runner-settings.tsx` only if preset serialization requires it
- Test: relevant settings and preset suites

- [ ] Add failing tests that presets preserve source behavior choices and that source risk settings survive normalization.
- [ ] Run the focused tests and confirm the expected failures.
- [ ] Apply local active settings: Mike alerts unchanged, Homebrew max three contracts with card stops/closes enabled and trims disabled, mirror analysis and swing sources at 50% risk, swing source exit profile enabled, coordinated activation 15%, width 18%, and five-cent minimum unchanged.
- [ ] Run all backend and frontend tests plus frontend build.
- [ ] Review the complete diff, commit the implementation, and push the current branch to `origin`.

### Task 7: Credential-sanitized evidence archive

**Files:**
- Create: an export directory outside tracked source
- Create: a ZIP containing reports, captures, logs, source manifests, and sanitized database exports

- [ ] Inventory retained Echo databases, Discord captures, logs, reports, and current source/configuration metadata.
- [ ] Export every database table needed for audit while removing broker credentials, Discord tokens, API keys, encrypted secret blobs, and unrelated secret-bearing settings.
- [ ] Copy retained text logs and captures through a secret-redaction pass and generate a manifest containing hashes, source paths, date coverage, and redaction notes.
- [ ] Scan the completed archive contents for known credential patterns and fail packaging if any are found.
- [ ] Create the ZIP, verify it opens, and report its absolute path and SHA-256 hash.
