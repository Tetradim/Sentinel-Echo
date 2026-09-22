# Configurable Core and Runner Exits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone Core / Runners tab and a broker-backed policy that preserves configurable runner contracts from selected ordinary exits while giving those runners independent catastrophic-stop and tiered-trailing rules.

**Architecture:** Add `backend/core_runner_policy.py` as the pure allocation and decision boundary. The coordinated exit engine will update runner state, cap protected exits by target remaining quantity, and evaluate runner-only exits before returning a decision. Existing JSON position persistence will hold runner state without a schema migration. The frontend will use a focused normalization module and standalone Expo Router screen backed by the existing `/api/settings` contract.

**Tech Stack:** Python 3, FastAPI, Pydantic, SQLite JSON records, unittest/pytest, React Native Web, Expo Router, TypeScript, Node test runner.

---

### Task 1: Settings Contract and Validation

**Files:**
- Modify: `backend/models/__init__.py`
- Modify: `backend/database/abstraction.py`
- Modify: `backend/database_sqlite.py`
- Modify: `backend/routes/settings.py`
- Test: `backend/tests/test_options_exit_policy.py`
- Test: `backend/tests/test_settings_source_overrides.py`

- [ ] **Step 1: Write failing settings-default and validation tests**

Add tests asserting that `Settings()` exposes the complete runner policy and that `/api/settings` validation rejects unordered trail tiers, allocation percentages above 100, invalid allocation modes, and negative catastrophic stops while accepting zero as disabled.

```python
def test_core_runner_defaults_are_exposed():
    settings = Settings()
    assert settings.core_runner_enabled is False
    assert settings.core_runner_allocation_mode == "greater_of"
    assert settings.core_runner_allocation_percent == 20.0
    assert settings.core_runner_activation_mfe_percent == 100.0
    assert settings.core_runner_catastrophic_stop_percent == 65.0
    assert settings.core_runner_trailing_tiers[-1] == {"mfe_percent": 1000.0, "trail_percent": 20.0}

def test_zero_catastrophic_stop_is_valid():
    update = SettingsUpdate(core_runner_catastrophic_stop_percent=0)
    assert update.core_runner_catastrophic_stop_percent == 0
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_options_exit_policy.py backend/tests/test_settings_source_overrides.py -q`

Expected: failures because the runner fields and tier normalizer do not exist.

- [ ] **Step 3: Add backend settings fields and defaults**

Add the same fields to `Settings`, `SettingsUpdate`, `RiskManagementSettingsUpdate`, `_default_settings()`, and the legacy SQLite initializer:

```python
core_runner_enabled: bool = False
core_runner_allocation_mode: str = "greater_of"
core_runner_allocation_percent: float = 20.0
core_runner_fixed_contracts: int = 1
core_runner_min_contracts: int = 1
core_runner_max_contracts: int = 2
core_runner_allow_single_contract: bool = False
core_runner_activation_mfe_percent: float = 100.0
core_runner_reserve_candidates_from_profit: bool = True
core_runner_loss_ladder_consumes_candidates: bool = True
core_runner_protect_loss_ladder: bool = True
core_runner_protect_hard_stop: bool = True
core_runner_protect_break_even: bool = True
core_runner_protect_profit_stages: bool = True
core_runner_protect_ordinary_trailing: bool = True
core_runner_protect_reversal_warning: bool = True
core_runner_protect_contextual_trims: bool = True
core_runner_confirmed_reversal_exits: bool = True
core_runner_catastrophic_stop_percent: float = 65.0
core_runner_catastrophic_confirmations: int = 2
core_runner_catastrophic_confirmation_interval_seconds: float = 3.0
core_runner_trailing_enabled: bool = True
core_runner_trailing_mode: str = "tiered"
core_runner_fixed_trailing_percent: float = 35.0
core_runner_trailing_tiers: list[dict[str, float]] = [
    {"mfe_percent": 100.0, "trail_percent": 35.0},
    {"mfe_percent": 300.0, "trail_percent": 30.0},
    {"mfe_percent": 500.0, "trail_percent": 25.0},
    {"mfe_percent": 1000.0, "trail_percent": 20.0},
]
core_runner_min_trailing_cents: float = 0.0
core_runner_spread_multiplier: float = 2.0
core_runner_trailing_confirmations: int = 2
core_runner_trailing_confirmation_interval_seconds: float = 3.0
core_runner_minimum_activation_seconds: int = 0
core_runner_require_fresh_high: bool = False
core_runner_allow_floor_to_move_down: bool = False
core_runner_analyst_override_percent: float = 80.0
core_runner_explicit_full_exit_overrides: bool = True
core_runner_contextual_full_exit_overrides: bool = False
core_runner_zero_dte_liquidation_enabled: bool = True
core_runner_zero_dte_liquidation_time: str = "15:40"
```

- [ ] **Step 4: Normalize structured runner values in the settings route**

Implement `_normalize_runner_trailing_tiers()` with one-to-ten rows, strictly increasing MFE, and 1–100 trail widths. Extend `_normalize_loss_ladder()` so every row accepts `allocation_target` in `core_only`, `runners_only`, `core_then_runners`, or `entire_position`, defaulting to `core_only` without breaking old rows.

- [ ] **Step 5: Run settings tests and verify GREEN**

Run the Task 1 test command. Expected: all pass.

### Task 2: Pure Core/Runner Policy

**Files:**
- Create: `backend/core_runner_policy.py`
- Create: `backend/tests/test_core_runner_policy.py`

- [ ] **Step 1: Write failing allocation and activation tests**

Cover percent, fixed, greater-of, minimum/maximum, single-contract behavior, candidate consumption, and immediate versus MFE activation.

```python
def test_greater_of_allocation_reserves_twenty_percent_or_one():
    state = update_runner_state(position(original_quantity=8, remaining_quantity=8), settings(), bid=1.0, now=NOW)
    assert state.updates["core_runner_candidate_quantity"] == 1

def test_candidate_becomes_dedicated_at_configured_mfe():
    state = update_runner_state(position(entry_price=1, highest_executable_bid=2), settings(), bid=2, now=NOW)
    assert state.updates["core_runner_activated"] is True
    assert state.protected_quantity == 1
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_core_runner_policy.py -q`

Expected: import failure because the module does not exist.

- [ ] **Step 3: Implement allocation and persisted state helpers**

Create immutable result types and functions with these interfaces:

```python
@dataclass(frozen=True)
class RunnerState:
    enabled: bool
    candidate_quantity: int
    dedicated_quantity: int
    protected_quantity: int
    core_quantity: int
    activated: bool
    mfe_percent: float
    updates: dict[str, Any]

def update_runner_state(position, settings, *, bid, now=None) -> RunnerState: ...
def protected_quantity_for_trigger(state, settings, trigger) -> int: ...
def cap_exit_quantity(decision, state, settings) -> dict[str, Any]: ...
```

Persist original allocation, candidate quantity, dedicated quantity, activation time/MFE, and derived core quantity. Master switch off must return the incoming decision unchanged.

- [ ] **Step 4: Write failing runner-exit tests**

Cover disabled catastrophic stop at zero, confirmed catastrophic stop, fixed trail, tier selection, monotonic floor, two-breach confirmation, new-high reset, and spread/minimum-cent distance.

- [ ] **Step 5: Implement runner exit evaluation**

```python
def evaluate_runner_exit(position, settings, state, *, bid, ask, now=None) -> dict[str, Any] | None:
    """Return a runner-only exit or None; always include position_updates."""
```

Return triggers `runner_catastrophic_stop` and `runner_trailing_stop`, quantity equal to the currently dedicated runner quantity, allocation target `runners_only`, and a target remaining quantity that leaves the current core untouched.

- [ ] **Step 6: Run runner-policy tests and verify GREEN**

Run the Task 2 test command. Expected: all pass.

### Task 3: Coordinated Exit Integration

**Files:**
- Modify: `backend/options_exit_policy.py`
- Modify: `backend/tests/test_options_exit_policy.py`
- Modify: `backend/bot_managed_exits.py`
- Modify: `backend/tests/test_bot_managed_exits.py`

- [ ] **Step 1: Write failing integration tests**

Add scenarios proving:

```python
def test_profit_stage_cannot_sell_below_candidate_reserve(): ...
def test_final_loss_ladder_closes_core_but_preserves_dedicated_runner(): ...
def test_ordinary_trail_becomes_hold_when_only_protected_runner_remains(): ...
def test_runner_catastrophic_stop_has_risk_exit_priority(): ...
def test_runner_trail_sells_only_dedicated_quantity(): ...
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_options_exit_policy.py backend/tests/test_bot_managed_exits.py -q`

- [ ] **Step 3: Integrate runner state with coordinated decisions**

At the beginning of `evaluate_coordinated_exit`, update runner state using the fresh executable bid. Merge its updates into every hold or exit result. Evaluate runner catastrophic/trailing exits before ordinary discretionary trailing but after mandatory worker-level 0DTE liquidation.

Before returning any existing `_exit()` decision, pass it through `cap_exit_quantity()`. A fully suppressed decision becomes a hold with `exit_trigger` recorded in `core_runner_suppressed_trigger`; a partially capped decision includes:

```python
{
    "quantity": capped_quantity,
    "target_remaining_quantity": remaining - capped_quantity,
    "exit_allocation_target": "core_only",
}
```

- [ ] **Step 4: Extend pending-order priority and replacement**

Assign runner catastrophic stop the emergency priority and runner trailing stop the ordinary risk priority. Persist allocation target and target remaining quantity on exit trades. Replacement must occur when an older SELL would cross below a newly protected runner target.

- [ ] **Step 5: Run coordinated integration tests and verify GREEN**

Run the Task 3 test command. Expected: all pass.

### Task 4: Fill and Startup Reconciliation

**Files:**
- Modify: `backend/fill_reconciliation.py`
- Modify: `backend/reconciliation.py`
- Modify: `backend/tests/test_fill_reconciliation.py`
- Modify: `backend/tests/test_trade_lifecycle.py`

- [ ] **Step 1: Write failing fill tests**

Test successful, partial, late, and externally reconciled fills:

```python
def test_core_only_fill_does_not_reduce_dedicated_runner(): ...
def test_runner_only_fill_reduces_dedicated_quantity(): ...
def test_partial_fill_recomputes_core_from_broker_remainder(): ...
def test_startup_caps_runner_quantity_to_broker_position(): ...
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_fill_reconciliation.py backend/tests/test_trade_lifecycle.py -q`

- [ ] **Step 3: Reconcile allocation from broker-authoritative quantity**

For core-only fills, preserve dedicated runners while calculating `core_runner_core_quantity = remaining - dedicated`. For runner-only fills, reduce dedicated and candidate quantities by the confirmed fill. For entire-position fills, cap all logical quantities to broker remaining. Startup reconciliation must never create contracts or assign more runners than Alpaca holds.

- [ ] **Step 4: Run fill and lifecycle tests and verify GREEN**

Run the Task 4 test command. Expected: all pass.

### Task 5: Analyst Exit Protection and Audit Data

**Files:**
- Modify: `backend/server.py`
- Modify: `backend/tests/test_alert_parsing.py`
- Modify: `backend/tests/test_settings_source_overrides.py`
- Modify: `backend/routes/operator.py`
- Modify: `backend/tests/test_operator_route_contracts.py`

- [ ] **Step 1: Write failing analyst-exit tests**

Cover contextual trim protection, contextual full-exit setting, explicit 80% override, explicit full-exit override, and exact contract identity. Assert audit details include requested quantity, protected quantity, permitted quantity, and target remaining quantity.

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_alert_parsing.py backend/tests/test_settings_source_overrides.py backend/tests/test_operator_route_contracts.py -q`

- [ ] **Step 3: Apply the shared runner cap to Discord exits**

Reuse `update_runner_state()` and `cap_exit_quantity()` rather than implementing a second protection algorithm. Treat an explicit, fully identified contract alert at or above the configured override percentage according to `core_runner_explicit_full_exit_overrides`; contextual text follows its separate toggle.

- [ ] **Step 4: Expose runner state in operator responses**

Return original/core/candidate/dedicated quantities, activation state, runner MFE, tier, trail width/floor, confirmations, and catastrophic configuration. Do not expose broker credentials.

- [ ] **Step 5: Run analyst and API tests and verify GREEN**

Run the Task 5 test command. Expected: all pass.

### Task 6: Frontend State and Standalone Tab

**Files:**
- Create: `frontend/utils/runnerSettingsState.ts`
- Create: `frontend/app/runner-settings.tsx`
- Modify: `frontend/utils/operatorNavigation.ts`
- Modify: `frontend/app/_layout.tsx`
- Modify: `frontend/app/index.tsx`
- Create: `frontend/tests/runnerSettingsState.test.cjs`
- Create: `frontend/tests/runnerSettingsPersistence.test.cjs`
- Modify: `frontend/tests/operatorNavigation.test.cjs`

- [ ] **Step 1: Write failing frontend state and navigation tests**

Test string-boolean normalization, zero catastrophic stop preservation, tier parsing, request serialization, and the `Runners` operator route.

```javascript
assert.equal(state.enabled, true);
assert.equal(state.catastrophicStopPercent, 0);
assert.deepEqual(state.trailingTiers, [{ mfe_percent: 100, trail_percent: 35 }]);
assert.match(screen, /core_runner_catastrophic_stop_percent/);
assert.match(navigation, /runner-settings/);
```

- [ ] **Step 2: Run frontend tests and verify RED**

Run: `npm test -- --test-name-pattern="runner|operator navigation"` from `frontend`.

- [ ] **Step 3: Implement normalized state and payload serialization**

Export `DEFAULT_RUNNER_SETTINGS`, `normalizeRunnerSettings()`, `validateRunnerSettings()`, and `toRunnerSettingsPayload()`. Validation mirrors backend constraints and keeps zero values intact.

- [ ] **Step 4: Build the Core / Runners screen**

The first viewport contains the master switch, allocation mode segmented control, allocation percentage/fixed/min/max inputs, activation MFE, and a live allocation example. Subsequent full-width sections contain protection switches, catastrophic stop, editable trail tiers, confirmation controls, analyst overrides, and expiration handling. Use Ionicons, compact 6px-radius panels, no nested cards, and inline validation next to the affected control.

Load with `GET /api/settings`; save only after a successful load using `PUT /api/settings`. Disable dependent controls when the master switch or runner trailing switch is off. Display `Full premium at risk` when catastrophic stop is zero.

- [ ] **Step 5: Register the standalone tab**

Add `runner-settings` to `OperatorRouteName`, `OPERATOR_TABS`, `_layout.tsx` labels and stack, and dashboard quick settings with label `Runners` and a `git-branch-outline`/`git-branch` icon.

- [ ] **Step 6: Run frontend tests and verify GREEN**

Run: `npm run test:ui` and `npx tsc --noEmit` from `frontend`. Expected: all tests and type checking pass.

### Task 7: Full Regression and Runtime Verification

**Files:**
- Modify only files required by failures attributable to this feature.

- [ ] **Step 1: Run backend regression tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests -q`

Expected: all backend tests pass.

- [ ] **Step 2: Run frontend regression tests and build**

Run from `frontend`:

```powershell
npm run test:ui
npx tsc --noEmit
npm run build
```

Expected: tests, type checking, and Expo web export pass.

- [ ] **Step 3: Start Echo and verify API persistence**

Start the normal launcher, read `/api/health`, then round-trip a non-trading runner configuration through `/api/settings`. Restore the intended recommended profile after the round trip. Confirm no order endpoint is called.

- [ ] **Step 4: Verify the UI visually**

Open the Runners tab at desktop and mobile widths. Confirm fields do not overlap, tier rows remain stable, zero-stop warning is visible, switches disable the correct controls, and saved settings survive refresh.

- [ ] **Step 5: Record final effective settings**

Report the active Core/Runner profile and explicitly state that the feature does not create broker-side brackets or trailing orders; Echo continues submitting its own SELL orders.

