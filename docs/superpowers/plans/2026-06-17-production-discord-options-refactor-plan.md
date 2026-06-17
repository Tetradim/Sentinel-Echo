# Production Discord Options Bot Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the Discord-to-options-order path into testable modules that can safely support live options execution, per-source customization, paper-shadow experimentation, and user-friendly setup.

**Architecture:** Move live trading behavior out of `backend/server.py` and into deep modules with narrow interfaces: ingestion, parsing, source policy, signal normalization, execution planning, broker execution, fill reconciliation, and position lifecycle. Broker truth must drive trade/position state; parsed alert text must never directly mutate portfolio state without an execution plan and reconciliation result.

**Tech Stack:** Python 3.11, FastAPI, discord.py, Pydantic, SQLite/MongoDB database abstraction, existing broker clients/adapters, `unittest` for current regression coverage.

---

## Code Review Findings First

### Critical: Live buy orders can create phantom open positions

**Files:** `backend/server.py:337-358`, `backend/fill_monitor.py:136-159`, `backend/fill_monitor.py:183-191`

`process_trade()` creates a live `Position` immediately after submitting the broker order, before the broker confirms any fill. If the broker later rejects, cancels, or times out, `fill_monitor` only updates the trade status and leaves the position open. That creates a false position that later sell alerts can act on.

**Refactor requirement:** Entry positions must be created only from a confirmed fill event, or inserted as `pending_open` and transitioned atomically by fill reconciliation. Rejected/cancelled orders must not leave open positions.

### Critical: Live sell fills do not reduce or close positions

**Files:** `backend/server.py:462-496`, `backend/fill_monitor.py:106-180`

The live exit path submits a sell order and starts `monitor_fill()`, but only passes `trade_id`, `order_id`, and `expected_qty`. The monitor has no `position_id`, no side-specific lifecycle plan, and no way to decrement `remaining_quantity`, set `closed_at`, or add realized P&L after a live fill. Simulated exits update positions; live exits do not.

**Refactor requirement:** Fill reconciliation must accept an order context containing side, position id, requested quantity, alert id, and price basis. A sell fill must atomically update both the sell trade and the position.

### High: Broker credentials are encrypted/decrypted inconsistently and `SecretStr` is passed to clients

**Files:** `backend/routes/settings.py:43-53`, `backend/routes/settings.py:318-324`, `backend/server.py:182-187`, `backend/server.py:297-301`, `backend/broker_clients/__init__.py:305-309`

The settings route encrypts `broker_configs` before persistence and decrypts them only for settings responses and the connection-check endpoint. The Discord execution path builds `Settings(**settings_dict)` directly from stored settings and then passes those broker configs to `get_broker_client()` without decrypting. In addition, `BrokerConfig` uses Pydantic `SecretStr`, and the legacy `broker_clients` headers use `self.config.api_key` directly. `str(SecretStr("real-key"))` is masked as `**********`, so clients can send masked or encrypted credentials.

**Refactor requirement:** Add a single `BrokerCredentialResolver` that decrypts configs and unwraps `SecretStr` before any broker adapter is constructed. No execution path should read broker credentials directly from raw settings.

### High: Fill truth is mostly unavailable in the active broker execution path

**Files:** `backend/fill_monitor.py:49-60`, `backend/broker_clients/__init__.py:642-654`

`fill_monitor` expects broker clients to expose `get_order_status()`, but the active `broker_clients` classes do not implement it. The monitor therefore marks live orders `unconfirmed` for missing status support. A bot that can submit orders but cannot reconcile fills is not production-ready for live options trading.

**Refactor requirement:** Broker execution must expose `submit_order()`, `get_order_status()`, `cancel_order()`, and optionally streaming updates. Adapters without status support must be disabled for live trading or forced to paper-only.

### High: `server.py` is a shallow module with too many live-trading responsibilities

**Files:** `backend/server.py:86-511`

`server.py` owns Discord bot construction, message intake, source overrides, duplicate filtering, DB inserts, buy sizing, correlation, broker execution, simulated fills, live pending state, fill monitor startup, exit planning, notifications, and app setup. A change to any trading behavior requires editing a file that also manages FastAPI and Discord lifecycle.

**Refactor requirement:** Keep `server.py` as composition only. Move behavior into modules with small public interfaces and full unit tests.

### Medium: Auto-trading state has split sources of truth

**Files:** `backend/server.py:161-163`, `backend/routes/settings.py:72-80`, `backend/routes/health.py:12-18`

Discord execution checks in-memory `bot_status["auto_trading_enabled"]`, while settings are persisted separately. After restart or out-of-band DB changes, the in-memory value can diverge from configured settings/runtime shutdown state.

**Refactor requirement:** Add `TradingModeResolver` that reads persisted settings plus runtime shutdown state for every execution decision. `bot_status` should display state, not authorize trades.

### Medium: Per-source customization is resolved but not fully applied

**Files:** `backend/source_config.py:6-14`, `backend/source_config.py:34-35`, `backend/server.py:193-197`

`source_config` supports `risk_multiplier`, `max_premium`, and `paper_only`, but only `paper_only` and `max_premium` affect execution. `risk_multiplier` is never applied to sizing, and parser format is stored but unused.

**Refactor requirement:** Source policy should produce an `ExecutionPolicy` that includes simulation mode, max premium, quantity multiplier, parser preset, allowed actions, ticker allow/deny lists, and live-trading eligibility.

### Medium: Custom parser pattern APIs do not affect `parse_alert()`

**Files:** `backend/routes/discord.py:118-180`, `backend/models/__init__.py:366-426`, `backend/utils/__init__.py:8-187`

The app exposes endpoints to customize alert patterns, but `parse_alert()` uses hardcoded keyword tuples and regexes. User-facing customization currently does not change parsing.

**Refactor requirement:** Replace global parser constants with a parser config loaded from settings/source policy. Add a parser workbench endpoint before enabling custom patterns for live execution.

### Medium: Duplicate route code exists under `backend/models/settings.py`

**Files:** `backend/models/settings.py:1-80`, `backend/routes/settings.py:1-80`

`backend/models/settings.py` contains route-layer code and appears unreferenced. It makes the model package misleading and creates a future risk of edits landing in the wrong file.

**Refactor requirement:** Remove the stale file after a search-confirmed no-import test, or move real model definitions into focused model modules and re-export from `backend/models/__init__.py`.

---

## Research Takeaways To Fold Into The Refactor

### Discord ingestion

Official Discord docs state that `MESSAGE_CONTENT` affects whether apps receive `content`, `embeds`, `attachments`, `components`, and poll fields, and apps without the intent receive empty values for content fields except in limited cases. The bot needs setup diagnostics for Message Content intent and should support message content, embeds, and attachments where legally available.

**Source:** https://docs.discord.com/developers/events/gateway

### Discord options alert competitors

DiscordAlertsTrader tracks messages from channels, parses analyst alerts, tracks analyst portfolios, follows live quotes to measure actual P&L, supports opening/closing/updating exits, supports embedded-message formatting, and has many custom analyst formats. It also has a no-API-key mode that only tracks/prints alerts.

**Source:** https://github.com/AdoNunes/DiscordAlertsTrader

### Split execution worker pattern

AutoTrader separates the Discord parser/server from the local brokerage client. The server listens to Discord and stores valid signals; the local client listens for those signals and places validated brokerage orders.

**Source:** https://github.com/ray310/AutoTrader

### Dry-run, backtesting, and operations maturity

Freqtrade exposes explicit command surfaces for trade, webserver, backtesting, analysis, configuration display, data conversion, strategy management, and lookahead/recursive analysis. The options bot should adopt the same operational posture: paper-first, shadow/live comparison, replay tests from historical alerts, and explicit config inspection.

**Source:** https://github.com/freqtrade/freqtrade

### Broker order tracking

Alpaca options are available live, but options level and buying-power validations matter. Alpaca also supports `client_order_id` for tracking and trade-update websockets for real-time order status.

**Sources:** https://docs.alpaca.markets/us/docs/options-trading and https://docs.alpaca.markets/us/docs/working-with-orders

---

## Target Module Tree

```text
backend/
  server.py                         # FastAPI + Discord lifecycle composition only
  discord_ingestion.py              # Discord message -> IntakeMessage/IntakeAlert
  discord_alert_text.py             # message/embed/attachment text normalization
  alert_parser.py                   # configurable parser engine
  alert_parser_config.py            # parser presets and user pattern validation
  source_policy.py                  # source overrides -> ExecutionPolicy
  trading_mode.py                   # persisted settings + runtime state -> mode decision
  trading_orchestrator.py           # normalized signal -> execution workflow
  execution_plan.py                 # signal + policy + positions -> entry/exit plan
  order_execution.py                # broker credential resolution + broker adapter calls
  fill_reconciliation.py            # order status/fill event -> trade + position updates
  position_lifecycle.py             # pure position transition helpers
  broker_clients/
    __init__.py                     # compatibility exports only during migration
    base.py                         # legacy interface if kept
    alpaca.py, tradier.py, ibkr.py  # one broker per file if legacy path remains
  brokers/
    base.py                         # canonical adapter interface
    registry.py                     # broker capability registry
  models/
    __init__.py                     # re-export only
    settings.py                     # Pydantic settings models only
    trading.py                      # Alert/Trade/Position/OrderContext
    discord.py                      # Discord parser/source models
  tests/
    test_discord_ingestion.py
    test_alert_parser_config.py
    test_source_policy.py
    test_trading_mode.py
    test_execution_plan.py
    test_order_execution.py
    test_fill_reconciliation.py
    test_position_lifecycle.py
```

---

## Phase 1: Stop Live-State Incorrectness Before Broad Cleanup

### Task 1.1: Add fill reconciliation tests before changing code

**Files:**
- Create: `backend/tests/test_fill_reconciliation.py`
- Read: `backend/server.py:337-358`
- Read: `backend/fill_monitor.py:106-180`
- Read: `backend/database/abstraction.py:651-747`

- [ ] Write `test_rejected_entry_order_does_not_leave_open_position`.
- [ ] Write `test_filled_entry_order_creates_open_position_from_fill_price`.
- [ ] Write `test_filled_exit_order_reduces_remaining_quantity_and_closes_when_zero`.
- [ ] Run: `python -m unittest backend.tests.test_fill_reconciliation -v`
- [ ] Expected before implementation: tests fail because no reconciliation module exists.

### Task 1.2: Create `backend/fill_reconciliation.py`

**Interface:**

```python
@dataclass(frozen=True)
class OrderContext:
    trade_id: str
    order_id: str
    side: Literal["BUY", "SELL"]
    ticker: str
    strike: float
    option_type: str
    expiration: str
    requested_quantity: int
    position_id: str | None = None
    alert_id: str | None = None
    simulated: bool = False

async def reconcile_order_update(db, context: OrderContext, update: BrokerOrderUpdate) -> ReconciliationResult:
    ...
```

**Rules:**
- BUY `filled`: update trade to `executed`, create/open position using actual filled quantity and average fill price.
- BUY `partial`: update trade to `partial`; create/update position only for filled quantity if business decision accepts partials.
- BUY `rejected/cancelled`: mark trade failed; do not create an open position.
- SELL `filled`: update sell trade to `executed`, decrement position, calculate realized P&L from actual fill price, close at zero.
- SELL `rejected/cancelled`: mark sell trade failed; leave position unchanged.
- All transitions are idempotent by `trade_id + order_id + status + filled_qty`.

### Task 1.3: Slim `backend/fill_monitor.py`

**Modify:** `backend/fill_monitor.py`

**New responsibility:** polling only. It should call broker `get_order_status()` and pass each result to `fill_reconciliation.reconcile_order_update()`.

**Remove from this file:**
- Direct `_mark_trade_executed()`
- Direct `_mark_trade_failed()`
- Direct `_mark_trade_unconfirmed()`
- Hardcoded notification side `"BUY"`

**Tests:**
- Update `backend/tests/test_fill_monitor.py` to assert the monitor delegates status updates to reconciliation.
- Add timeout test for `unconfirmed` status with no position mutation.

### Task 1.4: Update live buy and sell paths to pass order context

**Modify:** `backend/server.py` initially, then move to `backend/trading_orchestrator.py` in Phase 2.

**Rules:**
- Live buy path inserts `Trade(status="pending")`.
- Live buy path does not insert `Position(status="open")` before fill.
- Live sell path passes `position_id` into `OrderContext`.
- Live sell path must not mark alert `trade_executed=True` until submission succeeds; final executed state is fill-driven.

---

## Phase 2: Split `server.py` Into Deep Modules

### Task 2.1: Create `backend/discord_ingestion.py`

**Current source:** `backend/server.py:100-165`

**New interface:**

```python
async def handle_discord_message(message, channel_ids: list[str], deps: DiscordIngestionDeps) -> None:
    ...
```

**Responsibilities:**
- Ignore bot's own messages.
- Enforce configured channel allowlist.
- Build alert text from content/embeds.
- Load settings through one dependency.
- Resolve source policy.
- Parse the alert with source-specific parser config.
- Insert alert record.
- Call trading orchestrator only when trading mode allows it.

**Tests:**
- `test_ignores_unconfigured_channel`
- `test_embed_only_message_becomes_alert`
- `test_disabled_source_inserts_no_trade`
- `test_bot_status_is_not_used_as_authority_for_trading`

### Task 2.2: Leave `backend/server.py` as composition only

**Modify:** `backend/server.py`

**Keep:**
- FastAPI app setup.
- Middleware.
- Router inclusion.
- Discord bot factory wiring.
- Lifespan database initialization.

**Move out:**
- `_load_settings_sync`
- `process_trade`
- `process_exit_alert`
- source policy application
- alert persistence
- risk checks
- broker execution

**Acceptance check:** after refactor, `server.py` should not import `broker_clients`, `risk`, `notifications`, `fill_monitor`, or `trade_lifecycle` directly.

### Task 2.3: Create `backend/trading_orchestrator.py`

**Current source:** `backend/server.py:170-511`

**New interface:**

```python
async def handle_trade_signal(signal: ParsedAlert, context: SignalContext, deps: TradingDeps) -> TradeDecision:
    ...
```

**Responsibilities:**
- Resolve trading mode.
- Apply risk sizing.
- Run duplicate/correlation checks.
- Build entry or exit execution plan.
- Persist pending trades.
- Submit orders through `order_execution`.
- Start fill monitor with `OrderContext`.
- Notify user of submitted/failed/simulated outcomes.

**Tests:**
- Buy signal in simulation creates simulated trade and position.
- Buy signal in live mode creates pending trade only.
- Sell signal in simulation reduces position.
- Sell signal in live mode submits order and leaves position unchanged until fill reconciliation.
- Correlation block marks alert processed but not executed.

---

## Phase 3: Make Parser Customization Real

### Task 3.1: Rename and deepen parser module

**Modify:** `backend/utils/__init__.py`
**Create:** `backend/alert_parser.py`
**Create:** `backend/alert_parser_config.py`

**Plan:**
- Move `parse_alert()`, regexes, and keyword tuples out of `utils`.
- Keep `utils.parse_alert` as compatibility re-export for one release.
- Add `ParserConfig` with buy/sell/average-down/ignore keywords, ticker regex, expiration formats, and price patterns.
- Add source-specific parser preset lookup from `source_policy`.

**Tests:**
- Existing `backend/tests/test_alert_parsing.py` must pass unchanged.
- Add `test_custom_buy_keyword_parses_entry`.
- Add `test_ignore_pattern_skips_watchlist`.
- Add `test_parser_preset_can_parse_embed_text`.

**2026-06-17 progress:** fixed current parser keyword checks to use token-boundary matching, reducing false-positive exits from substrings such as `TRIMMER`, `WITHOUT`, and `CALLS`. Full parser module extraction remains open.

### Task 3.2: Add parser workbench endpoint

**Modify:** `backend/routes/discord.py`

**Endpoint:**

```text
POST /api/discord/parse-preview
```

**Input:**
- raw alert text
- optional source key
- optional parser config override

**Output:**
- normalized alert
- confidence
- warnings
- execution preview: paper/live, quantity, max premium skip reason

**Reason:** Users need safe customization before live trading. Pattern changes should be testable without placing orders.

**2026-06-17 progress:** added the first read-only workbench slice at `POST /discord/parse-preview`. It parses raw alert text, applies configured action/ignore pattern settings plus validated request-scoped parser overrides for preview, resolves source policy, reports policy skip reasons, previews simulation mode, and estimates buy quantity. Bulk alert-pattern updates now reuse the same empty/length validation. Preview now returns parser `confidence` and user-facing `warnings` for fallback buy assumptions, default source policy use, disabled/shutdown states, paper-only sources, invalid source config, ignore matches, unparsed alerts, and `max_contracts` quantity caps. Preview-only custom action canonicalization now replaces the matched keyword with the canonical action so keywords such as `SCALE` do not become fake tickers. Remaining work: extract the configurable parser engine, then wire the same validated parser config into live ingestion.

---

## Phase 4: Centralize Source Policy And User Customization

### Task 4.1: Replace `backend/source_config.py` with `backend/source_policy.py`

**Current source:** `backend/source_config.py`

**New interface:**

```python
def resolve_execution_policy(settings: dict, source: SourceIdentity, alert: dict | None = None) -> ExecutionPolicy:
    ...
```

**ExecutionPolicy fields:**
- `source_key`
- `source_name`
- `enabled`
- `paper_only`
- `parser_preset`
- `risk_multiplier`
- `max_premium`
- `allowed_actions`
- `allowed_tickers`
- `blocked_tickers`
- `max_contracts`
- `require_manual_confirm`
- `paper_shadow`
- `notes`

**Tests:**
- Source id wins over channel name.
- Disabled source blocks all actions.
- Paper-only forces simulation.
- [x] Risk multiplier changes quantity.
- [x] Max contracts caps source quantity.
- Buy over max premium is skipped.
- Sell is still allowed when max premium only applies to entries.

### Task 4.2: Validate source overrides in `backend/routes/settings.py`

**Current source:** `backend/routes/settings.py:57-68`

**Plan:**
- [ ] Replace raw `Dict[str, Dict[str, Any]]` with a Pydantic model.
- [x] Reject invalid action names.
- [x] Reject negative max premium and zero/negative risk multiplier.
- [x] Normalize action names plus ticker allow/block lists before persistence.
- [x] Add `require_manual_confirm` so a source can be parsed and recorded without automatic trade execution.
- [x] Add `paper_shadow` so a source can be marked for live-plus-paper comparison.
- [ ] Reject invalid regex strings when parser-specific fields move into source policy.
- [x] Return normalized source overrides so the frontend can display exactly what will run.

**2026-06-17 progress:** implemented an incremental validation slice in `backend/source_config.py`, `backend/routes/settings.py`, and the buy sizing path. Source overrides now support `allowed_actions`, `ticker_allowlist`, `ticker_blocklist`, `max_contracts`, `require_manual_confirm`, `paper_shadow`, and applied `risk_multiplier`; invalid action names, malformed ticker entries, and non-positive numeric risk controls fail fast at the API boundary. Manual-confirm sources still insert parsed alerts but suppress automatic execution requests, and parse preview reports the same gate. Paper-shadow sources are visible in parse preview and setup diagnostics; actual shadow persistence remains in Feature 7.1.

---

## Phase 5: Unify Broker Execution

### Task 5.1: Pick one broker interface

**Current sources:**
- `backend/broker_clients/__init__.py`
- `backend/brokers/base.py`
- `backend/brokers/registry.py`
- `backend/brokers/*.py`

**Decision:** Use `backend/brokers/base.py` as canonical, but extend it for options.

**Canonical interface:**

```python
class BrokerAdapter(ABC):
    async def check_connection(self) -> bool: ...
    async def submit_order(self, order: BrokerOrder) -> BrokerOrder: ...
    async def get_order_status(self, broker_order_id: str) -> BrokerOrderStatus: ...
    async def cancel_order(self, broker_order_id: str) -> bool: ...
    async def get_quote(self, symbol: str) -> float: ...
```

**Migration rule:** `broker_clients` becomes compatibility wrappers or is removed after all call sites use `brokers.registry.get_broker_adapter()`.

### Task 5.2: Create `backend/order_execution.py`

**Responsibilities:**
- Resolve active broker.
- Decrypt broker configs.
- Unwrap `SecretStr`.
- Enforce broker capability flags: options support, live support, fill-status support.
- Generate `client_order_id`.
- Submit order.
- Return `SubmittedOrder` with broker id, broker order id, client order id, status, and error.

**Tests:**
- Encrypted broker config decrypts before adapter creation.
- `SecretStr` values are unwrapped.
- Live execution is rejected if adapter lacks order status support.
- Paper execution can use adapters without live status if no real order is sent.
- [x] Client order id is stable for duplicate alert fingerprint.

**2026-06-17 progress:** added deterministic `build_client_order_id()` and passed IDs from live buy/sell submission paths. The legacy Alpaca client now includes `client_order_id` in order payloads. Full `SubmittedOrder` abstraction and broker registry migration remain open.

### Task 5.3: Add order status support for Alpaca first

**Modify:** `backend/brokers/alpaca_adapter.py`

**Plan:**
- Use Alpaca option contract symbol formatting in one helper.
- Add `client_order_id` to order payload.
- [x] Implement `get_order_status()` with `/v2/orders/{id}`.
- Optionally add streaming adapter for trade updates after polling path is stable.

**Tests:**
- Request payload includes `client_order_id`.
- [x] Filled/partial Alpaca order fields map to canonical status payloads consumed by `fill_monitor`.
- Rejected order maps to error reason.

**2026-06-17 progress:** added `get_order_status()` to the active legacy Alpaca client so live Alpaca orders satisfy the existing order-status capability gate. It maps `partially_filled` to `partial` and normalizes fill quantity, average fill price, and rejection/cancellation reason fields.

**2026-06-17 progress:** added `get_order_status()` to the active legacy Tradier client as well. It maps `partially_filled` to `partial`, normalizes `exec_quantity` and `avg_fill_price`, and surfaces Tradier API error descriptions as fill-monitor reasons.

---

## Phase 6: Model And Database Cleanup

### Task 6.1: Split `backend/models/__init__.py`

**Create:**
- `backend/models/trading.py`
- `backend/models/settings.py`
- `backend/models/discord.py`
- `backend/models/brokers.py`

**Modify:**
- `backend/models/__init__.py` re-exports public classes only.

**Remove:**
- Stale route code currently in `backend/models/settings.py`.

**Tests:**
- `python -c "from models import Settings, Alert, Trade, Position"` succeeds.
- `rg "from models.settings|import models.settings" backend` returns no stale route imports before removal.

### Task 6.2: Add atomic database lifecycle methods

**Modify:** `backend/database/abstraction.py`

**New methods:**
- `insert_pending_order_trade(trade)`
- `create_position_from_fill(trade_id, fill)`
- `apply_exit_fill(position_id, trade_id, fill)`
- `mark_order_rejected(trade_id, reason)`
- `record_order_event(order_event)`

**Why:** Fill reconciliation needs atomic trade/position updates. Callers should not hand-roll `$set`/`$push` mutations.

**Tests:**
- SQLite and Mongo implementations pass the same lifecycle test suite.
- Applying the same fill event twice is idempotent.
- Rejected entry order never creates an open position.

### Task 6.3: Retire or isolate `backend/database_sqlite.py`

**Current source:** sync SQLite helper used by the Discord thread.

**Plan:**
- Prefer async `database/abstraction.py`.
- If Discord must run in a separate loop/thread, submit DB work to the app loop with a `ThreadsafeDatabaseBridge`.
- Mark `database_sqlite.py` as migration-only or remove once no production path imports it.

---

## Phase 7: Add Research-Backed Features After The Refactor

### Feature 7.1: Paper-shadow mode

Every live-eligible alert should optionally create:
- the actual live execution plan
- [ ] a parallel paper-shadow execution plan
- a comparison record of live fill vs paper fill vs alert price

**Reason:** Freqtrade-style dry-run discipline and DiscordAlertsTrader-style actual P&L tracking.

**2026-06-17 progress:** first backend slice added per-source `paper_shadow` configuration plus parse-preview and setup-diagnostics visibility. Execution-time shadow trade/position persistence and live-vs-paper comparison records remain open.

### Feature 7.2: Analyst/source scorecards

Track per-source:
- alert count
- parse confidence
- skipped reasons
- paper P&L
- live P&L
- average slippage from alert price
- win rate by strategy/action

**Reason:** DiscordAlertsTrader emphasizes analyst portfolio/stat tracking.

### Feature 7.3: Setup diagnostics wizard

Add an endpoint and UI workflow that checks:
- [x] Discord token present
- [x] Message Content intent requested in code and portal check required
- monitored channel ids valid
- bot can see messages/embeds
- active broker connected
- [x] broker supports options/fill status
- [x] paper/live mode explicitly armed

**Reason:** Discord docs make Message Content intent a common failure point, and live options require explicit broker readiness.

**2026-06-17 progress:** added `GET /diagnostics/setup` as the first backend slice. It reports Discord token/channel state, source override counts, broker order-status support, auto-trading/simulation/shutdown state, and actionable warnings without exposing secrets. UI workflow and live Discord permission checks remain open.

### Feature 7.4: Execution preview before arming live trading

For any sample alert, show:
- parsed fields
- matched source policy
- action
- estimated quantity
- estimated max cost
- broker capability decision
- live/paper/shadow result
- exact skip reason if blocked

### Feature 7.5: Local execution worker mode

Keep Discord/FastAPI alert ingestion separate from broker credentials and broker sessions:
- Server stores validated signals.
- Local worker polls/streams execution queue.
- Worker holds broker credentials and places orders.

**Reason:** AutoTrader’s split server/client design reduces exposure of broker credentials and allows the execution side to run near the trader’s authenticated broker environment.

### Feature 7.6: Order idempotency and replay

Add:
- alert fingerprint
- execution intent id
- [x] broker `client_order_id`
- order event log
- replay command from historical alerts

**Reason:** Alpaca supports client order IDs and order-update tracking. Replayable alerts make parser and execution changes safer.

**2026-06-17 progress:** first slice landed for broker `client_order_id`: IDs are deterministic by side plus alert id, and sell orders include position id to avoid multi-position exit collisions.

---

## Execution Order

1. Fill reconciliation correctness.
2. Broker credential resolver and canonical broker execution.
3. `server.py` split into ingestion/orchestrator modules.
4. Configurable parser and parser preview.
5. Source policy expansion and validation.
6. Model/database cleanup.
7. Paper-shadow and scorecards.
8. Local execution worker mode.

---

## Verification Gates

Run these before each commit:

```powershell
& 'C:\Users\Lite OS\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s backend\tests -v
& 'C:\Users\Lite OS\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m compileall -q backend
git diff --check
```

Add these before live-trading release:

```powershell
& 'C:\Users\Lite OS\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest backend.tests.test_fill_reconciliation backend.tests.test_order_execution backend.tests.test_source_policy -v
```

Manual paper checks before live:
- Start Discord bot with Message Content intent enabled in Developer Portal and in code.
- Send plain-text buy alert.
- Send embed-only buy alert.
- Send trim/sell alert for a simulated open position.
- Confirm paper-shadow creates a shadow record for a live-eligible alert.
- Confirm broker connection check uses decrypted credentials and never returns secrets in API responses.
- Confirm live arming refuses adapters without `get_order_status()`.
