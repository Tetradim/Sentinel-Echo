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
