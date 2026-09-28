# Sentinel Link Source Auto-Enrollment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Link-enrolled Discord channels trade through Echo without a second manual source override.

**Architecture:** Link adds enrollment mode to its existing per-message bridge payload. Echo validates that proof at the existing localhost bridge boundary and creates a default source policy before normal parsing and execution checks.

**Tech Stack:** Chrome Manifest V3 JavaScript, FastAPI/Pydantic, Python unittest, Node test runner.

---

### Task 1: Link Enrollment Proof

**Files:**
- Modify: `Sentinel-Link/extensions/copy-repost/src/content.js`
- Test: `Sentinel-Link/extensions/copy-repost/test/content-runtime.test.js`

- [ ] Add failing tests requiring `listen` and `listen-only` messages to include their saved source mode.
- [ ] Run the focused Node test and confirm the contract is absent.
- [ ] Derive the mode from existing saved URL lists and include it in `chromeBridgePayload`.
- [ ] Run the focused test and the complete copy-repost suite.

### Task 2: Echo Auto-Enrollment

**Files:**
- Modify: `backend/routes/discord.py`
- Modify: `backend/source_config.py`
- Test: `backend/tests/test_chrome_bridge.py`
- Test: `backend/tests/test_source_config.py`

- [ ] Add failing tests for valid Link enrollment, preservation of manual overrides, incomplete conversation rejection, and untrusted bridge rejection.
- [ ] Run the focused tests and confirm the new expectations fail.
- [ ] Extend the bridge payload with `source_mode` and validate Link enrollment proof.
- [ ] Auto-create a normalized default source policy before source resolution without overwriting an existing policy.
- [ ] Preserve the strict override gate for payloads without trusted Link enrollment.
- [ ] Run focused and full backend bridge/source tests.

### Task 3: Runtime Verification

**Files:**
- No production files beyond Tasks 1-2.

- [ ] Run Sentinel Link's complete test suite.
- [ ] Run Echo's bridge, card, parsing, settings-source, and source-config suites.
- [ ] Restart Echo so the running backend loads the contract.
- [ ] Verify health and use a non-trading conversational bridge payload to confirm auto-enrollment plus `unparsed` rejection.
- [ ] Confirm Homebrew's source policy exists and no broker order was created by verification.
