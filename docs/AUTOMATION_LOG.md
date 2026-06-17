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
