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
