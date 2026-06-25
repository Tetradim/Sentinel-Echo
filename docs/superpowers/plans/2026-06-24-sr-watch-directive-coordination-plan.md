# S/R Watch Directive Coordination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Consolidation read Edge S/R directive events and convert validated directives into safe, non-broker execution plans for operator review or later execution wiring.

**Architecture:** Consolidation remains the broker authority. Edge emits `edge.sr.directive.v1` events; Consolidation reads the shared append-only JSONL event bus, validates each directive, matches it against current open positions, applies source policy/idempotency/time gates, and returns a plan. No broker order is placed by this slice.

**Tech Stack:** Python, FastAPI, pytest, existing Consolidation source config, existing Edge JSONL event bus contract.

---

## Task 1: Shared Edge Event Bus Reader

**Files:**
- Create: `backend/edge_event_bus.py`
- Test: `backend/tests/test_edge_event_bus.py`

- [ ] **Step 1: Write failing event-bus reader tests**

Create `backend/tests/test_edge_event_bus.py` with tests that write JSONL events to a temporary directory and assert:

```python
events = recent_edge_sr_directive_events(root=Path(temp_dir), target_bot="consolidation")
self.assertEqual([event["event_id"] for event in events], ["evt-2", "evt-1"])
```

The fixture must include one `edge.sr.directive.v1` event for `consolidation`, one for another bot, and one unrelated event type.

- [ ] **Step 2: Run red test**

Run: `python -m pytest backend/tests/test_edge_event_bus.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'edge_event_bus'`.

- [ ] **Step 3: Implement reader**

Create `backend/edge_event_bus.py` with:

```python
def recent_edge_sr_directive_events(*, root: Path | None = None, limit: int = 100, target_bot: str = "consolidation") -> list[dict[str, Any]]:
    ...
```

The function reads newest `*.jsonl` files first, parses valid JSON lines, filters `event_type == "edge.sr.directive.v1"`, requires `target_bot` in `target_bots`, skips malformed JSON, and returns at most `limit` events newest-first.

- [ ] **Step 4: Verify green**

Run: `python -m pytest backend/tests/test_edge_event_bus.py -q`

Expected: PASS.

## Task 2: S/R Directive Execution Planner

**Files:**
- Create: `backend/edge_sr_execution.py`
- Test: `backend/tests/test_edge_sr_execution.py`

- [ ] **Step 1: Write failing planner tests**

Create `backend/tests/test_edge_sr_execution.py` with tests for:

```python
plan = build_edge_sr_execution_plan(directive, positions=[position], source_config={"sr_watch_enabled": True, "sr_watch_auto_act": True})
self.assertEqual(plan["status"], "ready")
self.assertEqual(plan["action"], "close_position")
self.assertEqual(plan["order_intent"]["side"], "SELL")
```

Additional tests must assert that disabled auto-action returns `operator_review_required`, duplicate directive ids are rejected when an idempotency helper is supplied, scale-ins after a configured cutoff are blocked, and adverse close directives are still allowed after the cutoff.

- [ ] **Step 2: Run red test**

Run: `python -m pytest backend/tests/test_edge_sr_execution.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'edge_sr_execution'`.

- [ ] **Step 3: Implement planner**

Create `backend/edge_sr_execution.py` with:

```python
def build_edge_sr_execution_plan(payload, *, positions, source_config, now=None, idempotency=None, max_age_seconds=300) -> dict:
    ...
```

The planner must call `validate_edge_sr_directive`, reject invalid or duplicate directives, require `sr_watch_enabled`, match positions by id or full contract identity, require `sr_watch_auto_act` before returning `ready`, block only `request_scale_in` after `sr_watch_stop_trading_after_time`, and return order intents without placing orders.

- [ ] **Step 4: Verify green**

Run: `python -m pytest backend/tests/test_edge_sr_execution.py backend/tests/test_edge_sr_directives.py -q`

Expected: PASS.

## Task 3: Preview API Route

**Files:**
- Create: `backend/routes/edge_sr.py`
- Modify: `backend/routes/__init__.py`
- Modify: `backend/server.py`
- Test: `backend/tests/test_edge_sr_route.py`

- [ ] **Step 1: Write failing route tests**

Create `backend/tests/test_edge_sr_route.py` with a FastAPI test app that includes `routes.edge_sr.router`. Assert:

```python
response = client.post("/edge/sr/directives/preview", json={"payload": directive, "positions": [position], "source_config": source_config})
self.assertEqual(response.status_code, 200)
self.assertEqual(response.json()["plan"]["status"], "ready")
```

Also assert `GET /edge/sr/events` returns only Consolidation-targeted S/R events from a temp `BOT_EVENT_BUS_DIR`.

- [ ] **Step 2: Run red test**

Run: `python -m pytest backend/tests/test_edge_sr_route.py -q`

Expected: FAIL with missing route/module.

- [ ] **Step 3: Implement route**

Create `backend/routes/edge_sr.py` with:

```python
router = APIRouter(prefix="/edge/sr", tags=["Edge S/R Watch"])
@router.get("/events")
async def get_edge_sr_events(limit: int = 100): ...
@router.post("/directives/preview")
async def preview_edge_sr_directive(request: EdgeSrDirectivePreviewRequest): ...
```

The preview endpoint uses supplied positions/source config for deterministic tests. If positions are omitted and the route has a DB instance, it reads open and partial positions. The endpoint returns a plan and never executes broker orders.

- [ ] **Step 4: Register route**

Update `backend/routes/__init__.py` to export and initialize the route DB. Update `backend/server.py` to include the router under the existing `/api` router.

- [ ] **Step 5: Verify green**

Run: `python -m pytest backend/tests/test_edge_sr_route.py backend/tests/test_edge_sr_execution.py backend/tests/test_edge_event_bus.py -q`

Expected: PASS.

## Task 4: Documentation and Verification

**Files:**
- Modify: `docs/EDGE_SR_WATCH.md`

- [ ] **Step 1: Document the coordination slice**

Add a section for:

- Shared event reader.
- Preview endpoint.
- Planner statuses.
- Explicit non-execution boundary.

- [ ] **Step 2: Run focused tests**

Run:

```powershell
python -m pytest backend/tests/test_edge_event_bus.py backend/tests/test_edge_sr_execution.py backend/tests/test_edge_sr_route.py backend/tests/test_edge_sr_directives.py backend/tests/test_source_config_sr_watch.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit and push**

Commit message:

```bash
git commit -m "feat: add edge sr directive coordination"
```

Push with a normal fast-forward push only.

## Acceptance Criteria

- [ ] Consolidation can read only targeted `edge.sr.directive.v1` events from the shared Edge event bus.
- [ ] Consolidation can produce a guarded execution plan for close and scale-in directives.
- [ ] Duplicate, stale, invalid, disabled, and unmatched directives are blocked before execution.
- [ ] Scale-ins respect stop-trading-after-time while protective closes remain allowed.
- [ ] A preview API exists for operator/UI inspection and does not place broker orders.
- [ ] Focused tests pass.
