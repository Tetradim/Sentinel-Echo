# Consolidation Discord Chrome Bridge

This unpacked Chrome extension observes messages rendered in Discord Web and forwards them to the local Consolidation backend:

```text
http://127.0.0.1:8003/api/discord/chrome-bridge/message
```

Use this only for Discord channels you can personally view in Chrome when the normal Discord bot cannot be invited to the private server.

## Install

1. Start Consolidation locally.
2. Open `chrome://extensions`.
3. Enable **Developer mode**.
4. Click **Load unpacked**.
5. Select this folder: `tools/chrome-discord-bridge`.
6. Open Discord Web in Chrome.
7. Click the extension icon and enable **Forward visible Discord messages**.

## Behavior

- Only messages rendered in the current Discord page can be observed.
- By default, enabling the extension primes currently visible messages as already seen and forwards only future messages.
- Use the popup checkbox only when you intentionally want to forward messages already visible at enable time.
- Messages are deduped by Discord DOM message id before forwarding.
- The backend endpoint only accepts local requests by default.
- Consolidation parses the text through its existing Discord ingestion path.
- Source policy still applies. Use `chrome_bridge_channel_ids` or source overrides keyed by the observed Discord channel id/name when needed.

## Safety

Keep Consolidation in simulation mode or manual-confirm mode until you have validated real alerts in parser preview. This bridge does not use a Discord user token and does not send messages back into the private server.
