# S/R Watch Controlled Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a controlled, operator-confirmed path that turns a ready Edge S/R directive plan into Consolidation's existing alert/trade processing flow.

**Architecture:** Edge S/R directives still enter Consolidation as advisory events. Consolidation validates and plans them, then requires an explicit confirmation token before building synthetic alert inputs for the existing `process_trade` path. Broker execution remains governed by Consolidation settings, source policy, risk checks, and fill reconciliation.

**Tech Stack:** Python, FastAPI, Pydantic, pytest, existing Consolidation `Alert` model and `process_trade` function.

---

## Task 1: Execution Request Builder

**Files:**
- Create: `backend/edge_sr_action_request.py`
- Test: `backend/tests/test_edge_sr_action_request.py`

- [ ] **Step 1: Write failing tests**

Create tests proving:

```python
request = build_edge_sr_action_request(plan, source_config={"sr_watch_enabled": True})
self.assertEqual(request["parsed"]["alert_type"], "sell")
self.assertEqual(request["alert"].ticker, "AAPL")
```

Add a scale-in test proving `request_scale_in` maps to a buy alert and carries `_edge_sr_directive_id` and `_source_config`.

- [ ] **Step 2: Run red test**

Run: `python -m pytest backend/tests/test_edge_sr_action_request.py -q`

Expected: FAIL with missing module.

- [ ] **Step 3: Implement builder**

Create `backend/edge_sr_action_request.py` with:

```python
def build_edge_sr_action_request(plan: dict, *, source_config: dict) -> dict:
    ...
```

The function only accepts `plan["status"] == "ready"`. For `close_position`, build an `Alert` with `alert_type="sell"` and `sell_percentage=100.0`. For `request_scale_in`, build an `Alert` with `alert_type="buy"`. Both parsed dictionaries include `_source_config`, `_edge_sr_directive_id`, and `_edge_sr_reason_code`.

- [ ] **Step 4: Verify green**

Run: `python -m pytest backend/tests/test_edge_sr_action_request.py -q`

Expected: PASS.

## Task 2: Confirmed Execute Route

**Files:**
- Modify: `backend/routes/edge_sr.py`
- Modify: `backend/routes/__init__.py`
- Modify: `backend/server.py`
- Test: `backend/tests/test_edge_sr_execute_route.py`

- [ ] **Step 1: Write failing route tests**

Create route tests that inject a fake executor and assert:

```python
response = client.post(
    "/edge/sr/directives/execute",
    headers={"X-Edge-SR-Execution-Confirm": "EXECUTE EDGE SR DIRECTIVE"},
    json={...},
)
self.assertEqual(response.json()["status"], "submitted")
```

Add tests proving missing confirmation returns `409`, non-ready plans are not executed, and missing executor returns `503`.

- [ ] **Step 2: Run red test**

Run: `python -m pytest backend/tests/test_edge_sr_execute_route.py -q`

Expected: FAIL because route is missing.

- [ ] **Step 3: Implement route**

Add to `backend/routes/edge_sr.py`:

```python
EXECUTION_CONFIRMATION = "EXECUTE EDGE SR DIRECTIVE"
@router.post("/directives/execute")
async def execute_edge_sr_directive(...):
    ...
```

The route builds a plan exactly like preview, requires `X-Edge-SR-Execution-Confirm`, requires plan status `ready`, builds the action request, and calls an injected async executor. It returns `submitted` plus the plan and alert id. It must not silently execute without the confirmation header.

- [ ] **Step 4: Wire executor**

Expose `set_executor` from `routes.edge_sr`. Update `routes/__init__.py` exports. In `server.py`, call `set_edge_sr_executor(process_trade)` after defining routes or during module setup after `process_trade` exists.

- [ ] **Step 5: Verify green**

Run:

```powershell
python -m pytest backend/tests/test_edge_sr_execute_route.py backend/tests/test_edge_sr_route.py backend/tests/test_edge_sr_action_request.py -q
```

Expected: PASS.

## Task 3: Documentation and Verification

**Files:**
- Modify: `docs/EDGE_SR_WATCH.md`

- [ ] **Step 1: Document controlled execution**

Document:

- Confirmation header.
- Existing broker/risk path reuse.
- `close_position` and `request_scale_in` mappings.
- No bypass of source/risk/fill reconciliation.

- [ ] **Step 2: Run focused tests**

Run:

```powershell
python -m pytest backend/tests/test_edge_sr_action_request.py backend/tests/test_edge_sr_execute_route.py backend/tests/test_edge_sr_route.py backend/tests/test_edge_sr_execution.py backend/tests/test_edge_sr_directives.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit and push**

Commit message:

```bash
git commit -m "feat: add controlled edge sr execution"
```

Push with normal fast-forward only.

## Acceptance Criteria

- [ ] Ready S/R plans can be transformed into existing `Alert` and parsed-alert inputs.
- [ ] Close directives map to sell alerts for full close.
- [ ] Scale-in directives map to buy alerts with Edge metadata.
- [ ] Execute route requires explicit operator confirmation.
- [ ] Execute route uses injected executor and does not bypass existing broker/risk/fill logic.
- [ ] Missing confirmation, missing executor, and non-ready plans do not execute.
- [ ] Focused tests pass.
