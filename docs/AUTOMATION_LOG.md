# Automation Log

## 2026-06-17 20:08 UTC

- Researched current Discord bot and Alpaca options automation references. Key production takeaway: Discord alert ingestion must account for Message Content intent behavior and rich embed payloads, while broker examples should remain paper-first until live execution is explicitly configured and verified.
- Added `backend/discord_alert_text.py` to normalize Discord message content plus embed author, title, description, fields, and footer into one parseable alert string.
- Updated the Discord message handler to parse that combined alert text and store it as `raw_message`, allowing embed-only trade alerts to enter the existing parser, source override, duplicate detection, and execution flow.
- Added `backend/tests/test_discord_alert_text.py` to lock the embed-only alert behavior.

## 2026-06-17 20:56 UTC

- Researched current Discord/options automation references. Key production takeaway: mature Discord alert traders expose analyst/channel configuration as a first-class control surface, and broker docs continue to emphasize explicit order-state tracking over assuming order placement equals execution.
- Added source override normalization for `allowed_actions`, `ticker_allowlist`, and `ticker_blocklist` so users can make a Discord source entry-only, exit-only, or ticker-scoped before live trading.
- Updated the `/source-overrides` settings route to reject invalid actions and persist normalized values that the frontend can display exactly as the bot will enforce them.
- Added tests for action gating, ticker allow/block lists, and route-level validation.
- Applied source `risk_multiplier` to buy sizing so per-channel sizing changes affect order quantity while still respecting the global max-position dollar cap.

## 2026-06-17 21:20 UTC

- Researched current Discord alert trader and trading-bot UX references. Key production takeaway: users need a dry-run/parser workbench surface before live alerts can safely become orders.
- Added a read-only `/discord/parse-preview` endpoint that parses raw alert text, resolves source policy, reports skip reasons, previews simulation mode, and estimates buy quantity without inserting alerts or touching broker execution.
- Added tests for successful preview, policy-block preview, and missing-text validation.
- Tightened source override validation so explicit non-positive `max_premium` and `risk_multiplier` values fail fast instead of being silently ignored or defaulted.
- Extended parse preview to apply configured alert-pattern settings for custom action keywords and ignore patterns, keeping the behavior workbench-only until the live parser config refactor is complete.
- Added per-source `max_contracts` support so preview and live buy sizing enforce a hard contract ceiling after risk sizing and source multipliers are applied.
- Added request-scoped parser pattern overrides to parse preview so users can test a keyword change without saving it to bot settings.
- Added shared validation for saved alert-pattern lists and preview-only pattern overrides so empty or oversized parser keywords fail fast.
- Fixed parser keyword matching to use token boundaries, preventing substrings like `TRIMMER`, `WITHOUT`, or `CALLS` from being misread as exit/all-out signals.
- Added source ticker-list validation so malformed allow/block entries such as numeric or multi-word symbols fail before they can affect live alert policy.

## 2026-06-17 21:41 UTC

- Researched Discord alert trader parser/customization references. Key production takeaway: mature Discord alert bots handle many analyst-specific formats, so parser previews must explain confidence and protect against custom keyword edge cases before those rules are used live.
- Extended `/discord/parse-preview` with top-level `confidence` and `warnings` fields. Preview now warns when the parser assumed a buy action, when no source override matched, when auto trading/shutdown/source policy prevents execution, and when `max_contracts` caps quantity.
- Added parser metadata confidence levels: configured action or ignore pattern matches are high confidence, built-in action keyword matches are medium confidence, fallback parser assumptions are low confidence, and unparsed alerts are none.
- Fixed preview-only custom action canonicalization so a configured keyword such as `SCALE` is replaced with `SELL` instead of prepending `SELL` to the message, preventing the custom keyword from being misread as the ticker.
- Added per-source `require_manual_confirm` support. Sources with this flag still parse and insert alerts, but Discord ingestion will not automatically call trade execution, and parse preview reports `manual confirmation required` with a user-facing warning.

## 2026-06-17 22:02 UTC

- Researched Alpaca order-tracking references. Key production takeaway: live broker orders should carry deterministic client-side IDs so retries, broker queries, and execution logs can reconcile an alert intent with the broker order.
- Added `build_client_order_id()` in `backend/order_execution.py` to produce broker-safe, deterministic IDs from alert side, alert id, and optional position id while staying under Alpaca's 128-character limit.
- Passed deterministic client order IDs from the live buy and sell paths. Sell IDs include the position id to avoid collisions when one exit alert matches multiple open positions.
- Extended the legacy broker client order interface with an optional `client_order_id`; Alpaca now includes it in the `/v2/orders` payload.

## 2026-06-17 22:05 UTC

- Researched Alpaca fill-status references. Key production takeaway: the bot should poll or stream broker order state and use broker fill fields, not order-submission success, as the source of position truth.
- Added `AlpacaClient.get_order_status()` to the active legacy broker path so live Alpaca orders can feed the existing fill monitor and reconciliation flow.
- Mapped Alpaca `partially_filled` to the bot's canonical `partial` status and normalized `filled_qty`, `filled_avg_price`, and rejection/cancellation reasons for fill reconciliation.

## 2026-06-17 22:07 UTC

- Researched Tradier order-status references. Key production takeaway: Tradier exposes `exec_quantity`, `avg_fill_price`, and rejection details on account order lookup, so the bot can use the same fill-monitor path for Tradier live options orders.
- Added `TradierClient.get_order_status()` to the active legacy broker path and normalized `partially_filled` to `partial`, `exec_quantity` to `filled_qty`, and `avg_fill_price` to the canonical fill price field.
- Added Tradier API error extraction so failed status lookups return a usable reason to fill reconciliation instead of silently looking like an unknown fill.

## 2026-06-17 22:10 UTC

- Researched Discord Message Content intent setup references. Key production takeaway: users need a setup surface that distinguishes code-requested intents from Developer Portal approval and shows broker/source/trading readiness before live arming.
- Added a read-only `GET /diagnostics/setup` health endpoint that reports Discord token/channel state, Message Content intent request status, source override counts, broker order-status support, trading mode, and actionable warnings.
- Wired health routes into database initialization so diagnostics can inspect persisted settings without returning Discord tokens or broker credentials.

## 2026-06-17 22:14 UTC

- Researched dry-run and paper-trading practices. Key production takeaway: paper-shadow should be configurable per source and visible in previews before it is trusted as part of live execution.
- Added per-source `paper_shadow` normalization so users can mark a source for live-plus-paper comparison without blocking normal alert policy.
- Extended `/discord/parse-preview` with `would_create_paper_shadow` and a warning when paper-shadow recording is enabled for a live-capable source.
- Extended setup diagnostics with a paper-shadow source count so users can confirm which source overrides are configured for shadow experimentation.

## 2026-06-17 22:17 UTC

- Continued paper-shadow implementation from the dry-run research. Key production takeaway: live comparison requires persisted simulated records, not only a preview flag.
- Added `backend/paper_shadow.py` to build linked simulated trade and position records for live buy alerts.
- Wired live buy processing to persist paper-shadow entry records when the source has `paper_shadow` enabled and the bot is not already in simulation mode.

## 2026-06-17 22:21 UTC

- Audited the sell/trim/close lifecycle after adding paper-shadow entry records. Key production takeaway: live broker exits must never target simulated shadow positions.
- Added an `include_simulated` control to exit planning and wired live exit processing to exclude simulated and `:paper_shadow` positions when the bot is not in simulation mode.
- Added regression coverage proving live exit plans ignore paper-shadow positions while simulation-mode planning can still include simulated positions.
