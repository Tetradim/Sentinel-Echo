# Local Discord Alert Bridge

This unpacked Chrome extension observes messages rendered in selected Discord Web channels and forwards them to one or more local bot backends.

The default target remains Consolidation:

```text
http://127.0.0.1:8003/api/discord/chrome-bridge/message
http://127.0.0.1:8003/api/discord/chrome-bridge/heartbeat
```

Use this only for Discord channels you can personally view in Chrome when the normal Discord bot cannot be invited to the private server.

## Install

1. Start the local bot backend that should receive alerts.
2. Open `chrome://extensions`.
3. Enable **Developer mode**.
4. Click **Load unpacked**.
5. Select this folder: `tools/chrome-discord-bridge`.
6. Open Discord Web in Chrome.
7. Click the extension icon and enable **Forward visible Discord messages**.
8. After updating this folder, click **Reload** on the extension in `chrome://extensions`.

## Multi-Bot Targets

The popup includes a **Bot targets JSON** field. Each target can listen to all Discord channels or only specific channel URLs/IDs.

All updated bots use the same endpoint suffixes:

```text
POST /api/discord/chrome-bridge/message
POST /api/discord/chrome-bridge/heartbeat
GET  /api/discord/chrome-bridge/health
```

Known local target roots:

| Bot | Target root |
| --- | --- |
| Consolidation | `http://127.0.0.1:8003/api/discord/chrome-bridge` |
| Simulation Engine | `http://127.0.0.1:9200/api/discord/chrome-bridge` |
| Tandem Suite | `http://127.0.0.1:8005/api/discord/chrome-bridge` |
| Sentinel Edge | `http://127.0.0.1:<edge-port>/api/discord/chrome-bridge` |
| Sentinel Pulse | `http://127.0.0.1:<pulse-port>/api/discord/chrome-bridge` |
| Auto-Crypto | `http://127.0.0.1:<auto-crypto-port>/api/discord/chrome-bridge` |
| Darkpool Monitor | `http://127.0.0.1:<darkpool-port>/api/discord/chrome-bridge` |

```json
[
  {
    "id": "consolidation",
    "name": "Consolidation",
    "enabled": true,
    "messageUrl": "http://127.0.0.1:8003/api/discord/chrome-bridge/message",
    "heartbeatUrl": "http://127.0.0.1:8003/api/discord/chrome-bridge/heartbeat",
    "apiKey": "",
    "allowedChannelUrls": [
      "https://discord.com/channels/111111111111111111/222222222222222222"
    ]
  },
  {
    "id": "sentinel-edge",
    "name": "Sentinel Edge",
    "enabled": true,
    "messageUrl": "http://127.0.0.1:8010/api/discord/chrome-bridge/message",
    "heartbeatUrl": "http://127.0.0.1:8010/api/discord/chrome-bridge/heartbeat",
    "allowedChannelIds": ["333333333333333333"]
  },
  {
    "id": "crypto-bot",
    "name": "Crypto Bot",
    "enabled": false,
    "messageUrl": "http://127.0.0.1:8020/api/discord/chrome-bridge/message",
    "heartbeatUrl": "http://127.0.0.1:8020/api/discord/chrome-bridge/heartbeat"
  }
]
```

Notes:

- `allowedChannelUrls` should use Discord channel URLs, not invite URLs.
- A URL such as `https://discord.com/channels/<guild>/<channel>/<message>` is normalized to `https://discord.com/channels/<guild>/<channel>`.
- If a target has no `allowedChannelUrls` or `allowedChannelIds`, it receives messages from every Discord channel the extension observes.
- A message can be forwarded to multiple enabled targets when their filters match the same channel.
- If one target is down but another target accepts the message, the bridge reports partial success and schedules retry supervision without blocking the successful target.

## Behavior

- Only messages rendered in the current Discord page can be observed.
- The extension forwards only from Discord channel URLs that match at least one enabled target.
- By default, enabling the extension primes currently visible messages as already seen and forwards only future messages.
- Use the popup checkbox only when you intentionally want to forward messages already visible at enable time.
- Switching Discord channels primes the newly visible messages by default, so old channel history is not replayed unless existing-message forwarding is enabled.
- Messages are deduped by Discord DOM message id before forwarding.
- Consolidation's backend endpoint only accepts local requests by default.
- Consolidation parses the text through its existing Discord ingestion path.
- Every accepted visible Discord message is also appended to the Cross Bot Event Bus as `signal.observed`.
- Alert captures are permanently appended to market-day `.txt` files under `backend/data/alert-capture` by default.
- The extension sends page heartbeats every 30 seconds and service-worker heartbeats every minute. Consolidation records `bridge.health` events and emits `openclaw.attention.requested` when the bridge goes stale or reports forwarding errors.
- The service worker supervises matching open Discord tabs every minute. When forwarding, heartbeat, or content-script health checks fail, it re-injects the bridge content script and retries with exponential backoff from 5 seconds up to 5 minutes.
- Chrome cannot let an extension restart itself after the user disables/uninstalls it or closes all matching Discord tabs. In those cases the supervisor records a disabled/no-tab/no-matching-tab heartbeat once the extension is running again.
- Source policy still applies in each bot. In Consolidation, use `chrome_bridge_channel_ids` or source overrides keyed by the observed Discord channel id/name when needed.

## Cross Bot Event Bus

Consolidation exposes local-only event bus endpoints that other bots can adopt:

```text
POST /api/bus/events
GET /api/bus/events?limit=100
```

The event stream is append-only JSONL under `backend/data/event-bus` by default. The shared event shape is versioned as `bot-event.v1` and is meant for Sentinel Edge to publish strategic action/state changes without blocking each bot's fast local execution loop.

## Safety

Keep Consolidation in simulation mode or manual-confirm mode until you have validated real alerts in parser preview. This bridge does not use a Discord user token and does not send messages back into the private server.
