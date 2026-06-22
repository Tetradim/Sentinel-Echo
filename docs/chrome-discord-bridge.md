# Chrome Discord Bridge

Consolidation accepts local Chrome bridge traffic at:

```text
POST /api/discord/chrome-bridge/message
POST /api/discord/chrome-bridge/heartbeat
GET  /api/discord/chrome-bridge/health
```

`message` payloads flow through the existing Discord alert ingestion path, then append `signal.observed` with `contract_version: chrome.discord.message.v1`.

`heartbeat` payloads append `bridge.health` and feed live-readiness checks. The endpoints are local-only unless `CHROME_BRIDGE_ALLOW_REMOTE=1` is set.
