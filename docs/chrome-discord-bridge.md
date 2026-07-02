# Chrome Discord Bridge

Sentinel Echo accepts local Chrome bridge traffic at:

```text
POST /api/discord/chrome-bridge/message
POST /api/discord/chrome-bridge/heartbeat
GET  /api/discord/chrome-bridge/health
```

`message` payloads are preflighted before the normal Discord ingestion path:

- `chrome_bridge_require_source_override` defaults to `true`; bridge alerts must match a configured source override by channel id or channel name.
- Source overrides can restrict `allowed_channel_urls`, `allowed_author_ids`, and `min_parser_confidence`.
- Alerts below the required parser confidence, from an unapproved channel URL, or from an unapproved author are captured and published as `signal.observed`, but they are not inserted as trade alerts and no trade is requested.
- Every bridge alert decision is written as an operator event with action `bridge_alert_decision`.

Accepted `message` payloads flow through the existing Discord alert ingestion path, then append `signal.observed` with `contract_version: chrome.discord.message.v1`.

`heartbeat` payloads append `bridge.health` and feed live-readiness checks. The endpoints are local-only unless `CHROME_BRIDGE_ALLOW_REMOTE=1` is set.
