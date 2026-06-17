# Automation Log

## 2026-06-17 20:08 UTC

- Researched current Discord bot and Alpaca options automation references. Key production takeaway: Discord alert ingestion must account for Message Content intent behavior and rich embed payloads, while broker examples should remain paper-first until live execution is explicitly configured and verified.
- Added `backend/discord_alert_text.py` to normalize Discord message content plus embed author, title, description, fields, and footer into one parseable alert string.
- Updated the Discord message handler to parse that combined alert text and store it as `raw_message`, allowing embed-only trade alerts to enter the existing parser, source override, duplicate detection, and execution flow.
- Added `backend/tests/test_discord_alert_text.py` to lock the embed-only alert behavior.
