# Edge S/R Watch Integration

Consolidation owns broker execution, position state, and risk controls. Edge S/R Watch may provide advisory directives, but those directives must be validated and translated before any execution path can act.

## Source Settings

Each source override now supports these S/R Watch keys:

- `sr_watch_enabled`: default `false`.
- `sr_watch_replace_orb`: default `true`; when enabled, this source can use S/R Watch instead of ORB gating.
- `sr_watch_auto_act`: default `false`; execution automation remains opt-in.
- `sr_watch_strict_gating`: default `false`; when true, missing or failing pre-entry S/R checks block entries.
- `sr_watch_strict_0dte_exits`: default `true`.
- `sr_watch_stop_trading_after_time_enabled`: default `false`.
- `sr_watch_stop_trading_after_time`: default `15:30`.
- `sr_watch_scale_in_sizing_mode`: default `buying_power_fraction`.
- `sr_watch_scale_in_fraction`: default `0.25`.
- `sr_watch_break_even_stop_enabled`: default `false`.
- `sr_watch_pre_close_trailing_enabled`: default `false`.

## Directive Validation

`edge_sr_directives.validate_edge_sr_directive` validates `edge.sr.directive.v1` payloads and returns structured internal intents. It requires full option contract identity for close and scale-in directives:

- underlying
- option side
- expiry
- strike
- quantity
- directive id

The validator does not create orders. It rejects invalid schema/actions, missing contract identity, stale directives when `created_at` exceeds the allowed age, and invalid scale-in sizing hints.

## Ingestion Hook

`discord_ingestion.handle_discord_message` accepts an optional `sr_pre_entry_gate` dependency. The hook runs only for entry alerts when the resolved source has `sr_watch_enabled=true`. Disabled sources continue through the existing ingestion path.

When strict gating is enabled, missing gate dependencies or gate exceptions block entries. Without strict gating, failures are recorded on the parsed alert and the existing path proceeds.

## Directive Coordination

`edge_event_bus.recent_edge_sr_directive_events` reads the shared Edge JSONL event bus and returns only `edge.sr.directive.v1` events targeted to `consolidation`. Malformed records, unrelated event types, and directives for other bots are ignored.

`edge_sr_execution.build_edge_sr_execution_plan` validates a directive, checks idempotency when supplied, matches an open or partial position, applies source policy, and returns one of these statuses:

- `ready`: the directive is valid and auto-action policy allows a non-executing order intent.
- `operator_review_required`: S/R Watch is enabled but `sr_watch_auto_act` is off.
- `blocked`: policy or position state prevents the directive from moving forward.
- `rejected`: schema, stale-event, duplicate, or unsupported-action validation failed.

`request_scale_in` is blocked after `sr_watch_stop_trading_after_time` when that cutoff is enabled. Protective `close_position` directives are still allowed after the cutoff.

The preview API exposes this layer without placing orders:

- `GET /api/edge/sr/events`
- `POST /api/edge/sr/directives/preview`

The preview endpoint accepts supplied positions and source config for deterministic tests. If positions are omitted in the running app, it reads open and partial positions from the configured database. The endpoint returns a plan only; it does not call broker clients, create trades, or mutate positions.

## Controlled Execution

`POST /api/edge/sr/directives/execute` submits a ready plan into Consolidation's existing alert/trade processing path. It requires the header:

`X-Edge-SR-Execution-Confirm: EXECUTE EDGE SR DIRECTIVE`

Without that exact confirmation value, the route returns `409` and does not call the executor. If the plan is not `ready`, the route returns `not_submitted` with the plan. If the executor is not configured, it returns `503`.

Action mapping:

- `close_position` builds a synthetic sell alert with `sell_percentage=100.0`.
- `request_scale_in` builds a synthetic buy alert and preserves the Edge sizing hint in parsed metadata.

Both paths include `_edge_sr_directive_id`, `_edge_sr_reason_code`, `_edge_sr_position_id`, and `_source_config` in the parsed alert passed to the executor. The route is intentionally a bridge into the existing `process_trade` flow, so it does not bypass auto-trading settings, source policy, broker configuration, risk checks, order placement rules, fill monitoring, or fill reconciliation.
