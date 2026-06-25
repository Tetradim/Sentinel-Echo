# Consolidation Discord Options Bot

Consolidation is a Discord-driven options trading and testing bot. It listens to analyst alerts, parses options contracts, applies source policy and risk controls, records alerts, and can either simulate trades or submit broker orders when live trading is explicitly configured.

It also includes a preview-only bridge to the Sentinel Simulation Engine so recorded Discord alerts and market context can be replayed through Consolidation without inserting alerts or sending broker orders.

## Safety Boundary

This project can place broker orders when all of the following are true:

- `SIMULATION_MODE=false`
- `CONSOLIDATION_BOT_ROLE=live_executioner`
- auto trading is enabled
- a source override allows automatic live execution
- the active broker is configured
- the active broker supports order-status polling
- no runtime shutdown is active

Defaults keep the bot operational while preserving live-money gates:

- `SIMULATION_MODE=true`
- `CONSOLIDATION_BOT_ROLE` defaults to `paper_shadow`, which blocks live arming and broker submission
- `auto_trading_enabled=true`
- Discord intake only starts when a token and channel IDs are configured
- setup diagnostics report missing live-trading prerequisites
- parser preview and Simulation Engine replay preview do not mutate trading state

Do not enable live trading until Discord parsing, source policy, broker credentials, order-status polling, and risk settings have been verified with real sample alerts.

## Repository

```text
C:\Users\Lite OS\Documents\Codex\2026-06-17\files-mentioned-by-the-user-readme\work\Consolidation
```

## Current Capability Map

| Area | Implemented capability |
| --- | --- |
| Discord intake | `discord.py` bot can monitor configured channels, ignore self messages, parse content plus embeds, and process alerts. |
| Alert parsing | Extracts ticker, strike, option type, expiration, entry/exit price, alert type, sell percentage, and average-down intent. |
| Parser preview | `/api/discord/parse-preview` evaluates raw alert text, source policy, parser confidence, warnings, and execution preview without inserting records. |
| Custom patterns | Saved and preview-only buy, sell, partial sell, average down, stop loss, take profit, ignore, ticker regex, and case-sensitivity settings. |
| Source policy | Per-channel or per-name overrides for enable/disable, paper-only, paper-shadow, manual confirmation, allowed actions, risk multiplier, max premium, max contracts, ticker allow/block lists, and notes. |
| Alert persistence | Parsed alerts are stored with processing and execution status. |
| Position sizing | Uses default quantity, max position size, and source risk multiplier, then applies max-contract limits. |
| Risk controls | Duplicate alert checks, max positions per ticker, source policy, shutdown counters, stop loss, take profit, trailing stop, averaging down, and premium buffer settings. |
| Simulated trading | In simulation mode, buy and sell alerts create local trades and positions without a broker. |
| Live order submission | Live buy and sell paths use broker clients, deterministic client order IDs, pending trade records, and fill monitoring. |
| Fill monitoring | Polls broker status, reconciles filled, partial, rejected, cancelled, expired, unconfirmed, and timeout states. |
| Fill reconciliation | Updates trade, alert, and position truth from broker fill data and avoids duplicate reconciliation. |
| Paper shadow | Live-capable sources can record simulated shadow entries/exits alongside live behavior without sending shadow orders. |
| Broker configuration | Stores broker credentials, supports encrypted credential storage when `CREDENTIAL_KEY` is configured, and masks secrets in responses. |
| Broker diagnostics | Broker switch/check endpoints and setup diagnostics report whether a broker is configured and whether order status is supported. |
| Profiles | Multiple profiles with active brokers and per-broker risk/trading settings. |
| Operator lab | Safe endpoints and UI screen for creating simulated test alerts and simulated exits. |
| Notifications | Optional SMS/Twilio notification settings, test notification endpoint, notification log, and trade/shutdown notification hooks. |
| Analytics | Heatmap, time series, advanced metrics, daily/weekly reports, tax report, and performance endpoints. |
| Frontend | Expo/React Native Web dashboard with Dashboard, Alerts, Trades, Positions, Lab, Strikes, Trading, Risk, Discord, Broker, Profiles, and Settings tabs. |
| Simulation Engine bridge | Fetches `simulation.consolidation.replay.v1` events and previews them through Consolidation parser/source policy in `preview_only_no_trades` mode. |
| Chrome Discord bridge | Optional local-only unpacked Chrome extension can forward visible Discord Web messages into Consolidation when a bot cannot be invited. |
| Local launcher | Windows launcher starts FastAPI backend and Expo web frontend on local ports with optional dependency installation and smoke test. |

## Architecture

```text
Discord channel
      |
      v
discord.py listener
      |
      v
discord_ingestion.handle_discord_message
      |
      +--> parser and custom source policy
      |
      +--> alert record
      |
      +--> simulation trade or live broker order
                  |
                  v
            fill monitor
                  |
                  v
        trade, alert, position reconciliation

FastAPI routes expose settings, alerts, trades, positions, brokers,
profiles, operator lab, analytics, diagnostics, and Simulation Engine replay preview.
```

## Quick Start: Windows Beta Installer

For non-technical beta testers, download and run `ConsolidationBot-Setup-<version>.exe` from the Windows release artifact.

After installation, double-click **Consolidation Discord Options Bot** from the Desktop or Start Menu. The installed launcher downloads missing runtime dependencies on first launch, including the Microsoft Visual C++ Runtime when Windows does not already have it. The installed beta build runs the packaged backend with local SQLite mode and serves the bundled dashboard from the same local app.

Installed beta testers do not need to install Python, Node.js, npm, MongoDB, or Redis. If startup fails, send a screenshot of the launcher window and the Desktop log file named `Consolidation-Discord-Bot.log`.

Default installed URLs:

| Service | URL |
| --- | --- |
| App dashboard | `http://127.0.0.1:8003/app/` |
| FastAPI backend | `http://127.0.0.1:8003` |
| Health check | `http://127.0.0.1:8003/api/health` |

## Quick Start: Local Windows Launcher

From the repository root:

```powershell
.\Launch-Consolidation-Bot.bat
```

Or run the PowerShell launcher directly:

```powershell
.\Launch-Consolidation-Bot.ps1
```

Default local ports:

| Service | URL |
| --- | --- |
| FastAPI backend | `http://127.0.0.1:8003` |
| Expo web frontend | `http://127.0.0.1:3003` |
| Health check | `http://127.0.0.1:8003/api/health` |

Useful flags:

```powershell
.\Launch-Consolidation-Bot.ps1 -InstallDeps
.\Launch-Consolidation-Bot.ps1 -NoBrowser
.\Launch-Consolidation-Bot.ps1 -BackendPort 8003 -FrontendPort 3003
.\Launch-Consolidation-Bot.ps1 -SmokeTest
```

The launcher:

1. Creates or reuses `backend\.venv`.
2. Installs backend and frontend dependencies when requested or missing.
3. Uses SQLite for local desktop mode.
4. Starts the FastAPI backend.
5. Starts the Expo web frontend.
6. Verifies backend health and CORS.
7. Opens the browser unless `-NoBrowser` is used.
8. Writes a local launcher log to the Desktop.

## macOS Beta Installer

MacBook beta testers can install the local source build with the bundled macOS installer script. It creates the backend virtual environment, installs frontend dependencies, uses local SQLite mode, and adds a double-click launcher to the Desktop.

Prerequisites:

- macOS with Python 3.11+ on `PATH`
- Node.js with `npm`

From the repository root:

```bash
chmod +x install-macos.sh
./install-macos.sh
```

After installation, double-click `Consolidation Discord Bot.command` on the Desktop. The launcher starts the backend on `8003`, starts the Expo web frontend on `3003`, and opens the dashboard. Logs are written to `~/Desktop/Consolidation-Discord-Bot.log`.

Manual launch options:

```bash
./install-macos.sh --launch
./install-macos.sh --launch --install-deps
./install-macos.sh --launch --backend-port 8003 --frontend-port 3003 --no-browser
```

## Manual Local Start

Backend:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
$env:HOST = "127.0.0.1"
$env:PORT = "8003"
$env:USE_SQLITE = "true"
$env:DATABASE_PATH = "data\consolidation.sqlite3"
.\backend\.venv\Scripts\python.exe -m backend.run
```

Frontend:

```powershell
cd frontend
npm install
$env:EXPO_PUBLIC_BACKEND_URL = "http://127.0.0.1:8003"
npm run web -- --port 3003
```

## Docker Start

```bash
cp .env.example .env
docker-compose up -d
docker-compose logs -f
```

Use Docker when you want MongoDB, Prometheus, and nginx managed as a stack.

## Environment Variables

### Required For Discord Intake

| Variable | Purpose |
| --- | --- |
| `DISCORD_BOT_TOKEN` | Bot token from Discord Developer Portal. |
| `DISCORD_CHANNEL_IDS` | Comma-separated channel IDs to monitor. |
| `DISCORD_GUILD_ID` | Optional guild ID. |
| `CONSOLIDATION_USE_OPENCLAW_DISCORD` | Optional fallback toggle. Defaults to `true`; set to `false` to prevent reading local OpenClaw Discord config. |
| `OPENCLAW_HOME` | Optional OpenClaw config directory. Defaults to the current user's `.openclaw` folder. |

Discord intake starts when token and channel IDs are available from explicit Consolidation env vars. If either is missing and `CONSOLIDATION_USE_OPENCLAW_DISCORD` is not disabled, Consolidation falls back to the local OpenClaw `.env` token and enabled Discord channel IDs in `openclaw.json`. Explicit Consolidation env vars always win over OpenClaw values.

### Server And Security

| Variable | Purpose |
| --- | --- |
| `HOST` | Backend host, usually `127.0.0.1` locally. |
| `PORT` | Backend port, default launcher port is `8003`. |
| `API_KEY` | Optional API key. When set, requests need `X-API-Key` except `/api/health`. |
| `ADMIN_API_KEY` | Required by sensitive admin operations such as resetting shutdown loss counters. |
| `SECRET_KEY` | Application secret. |
| `ALLOWED_ORIGINS` | Comma-separated CORS allow-list. |
| `CREDENTIAL_KEY` | 32-byte hex key for encrypting stored broker credentials. |

### Data

| Variable | Purpose |
| --- | --- |
| `USE_SQLITE` | Enables local SQLite mode when true. |
| `DATABASE_PATH` | SQLite database path, usually `data\consolidation.sqlite3`. |
| `MONGO_URL` | MongoDB URL for server deployments. |
| `DB_NAME` | Mongo database name. |
| `REDIS_URL` | Redis URL for stack deployments. |

### Frontend

| Variable | Purpose |
| --- | --- |
| `EXPO_PUBLIC_BACKEND_URL` | Backend API base URL used by the frontend. |
| `EXPO_PUBLIC_API_KEY` | Optional frontend API key header value. |
| `EXPO_PUBLIC_DEMO_MODE` | Enables frontend demo mode where supported. |

### Trading

| Variable | Purpose |
| --- | --- |
| `SIMULATION_MODE` | Keep true until live execution is proven safe. |
| `CONSOLIDATION_BOT_ROLE` | Deployment role gate. Defaults to `paper_shadow`; live arming and live broker submission require `live_executioner`. Supported non-live roles are `portfolio_ops`, `paper_shadow`, and `replay_audit`. |
| `DEFAULT_QUANTITY` | Default contracts for buys. |
| `MAX_POSITION_SIZE` | Max premium allocation per position. |
| `PRICE_BUFFER` | Entry price buffer default. |

### Alpaca Paper Bootstrap

For local broker smoke testing, put Alpaca paper credentials and `CREDENTIAL_KEY`
in ignored `.env.local`, then run:

```bash
python backend/alpaca_paper_settings.py --env-file .env.local
```

The bootstrap only accepts `https://paper-api.alpaca.markets` or its `/v2`
endpoint, normalizes the saved broker base URL for the existing adapter, stores
credentials through the repo encryption helper when `CREDENTIAL_KEY` is present,
and keeps `simulation_mode=true` plus `auto_trading_enabled=true`.

After bootstrapping, run the configured broker preflight:

```bash
python backend/broker_readiness_preflight.py --env-file .env.local --broker alpaca
```

The preflight is read-only. It refuses unsafe execution flags, checks the saved
broker connection, and counts open orders without submitting, replacing, or
cancelling orders. Any open broker order blocks the preflight until it is
reconciled or cancelled by an operator-owned workflow.

### Simulation Engine Bridge

| Variable | Purpose |
| --- | --- |
| `SIMULATION_ENGINE_REPLAY_URL` | Simulation Engine replay endpoint. Default: `http://127.0.0.1:9200/api/consolidation/replay/events`. |

## Discord Setup

1. Create an app in the Discord Developer Portal.
2. Add a bot user.
3. Enable Message Content Intent.
4. Invite the bot to the server.
5. Grant view channel and read message history permissions.
6. Copy the bot token.
7. Set `DISCORD_BOT_TOKEN`.
8. Set `DISCORD_CHANNEL_IDS`.
9. Start Consolidation.
10. Check `/api/diagnostics/setup`.

If OpenClaw is already configured on the same machine, Consolidation can reuse:

- `C:\Users\Lite OS\.openclaw\.env` for `DISCORD_BOT_TOKEN`
- `C:\Users\Lite OS\.openclaw\openclaw.json` for enabled Discord channel IDs

This is a runtime fallback only. The token is not copied into the repo, not printed in diagnostics, and not written to the README. Set `CONSOLIDATION_USE_OPENCLAW_DISCORD=false` to force Consolidation to ignore OpenClaw.

The fallback is used by automatic backend startup and by the `/api/discord/start` route, so the UI start button can launch the listener even when the saved Consolidation settings are empty.

## Chrome Discord Bridge

Use this only when the normal Discord bot cannot be invited to a private server but you can personally view the alert channel in Discord Web.

The reusable local bridge lives here:

```text
tools\chrome-discord-bridge
```

Install it as an unpacked Chrome extension:

1. Start Consolidation locally.
2. Open `chrome://extensions`.
3. Enable Developer mode.
4. Click Load unpacked.
5. Select `tools\chrome-discord-bridge`.
6. Open Discord Web in Chrome.
7. Click the extension icon and enable forwarding.

Default Consolidation target:

```text
POST http://127.0.0.1:8003/api/discord/chrome-bridge/message
```

The backend endpoint:

- accepts local requests only by default
- dedupes repeated DOM events by message event ID
- converts the observed Chrome message into a Discord-like message object
- uses `discord_ingestion.handle_discord_message`
- applies the same parser, source policy, auto-trading, simulation, and manual-confirm controls as normal Discord intake

The extension defaults to future messages only when enabled. It can forward already-visible messages only when you explicitly enable that popup option. The bridge does not use a Discord user token and does not post into the private server. It can only see messages currently rendered in Chrome, so keep it for local testing and operator-supervised workflows.

The extension can forward the same observed alert to multiple local bots. Use the popup's **Bot targets JSON** field:

```json
[
  {
    "id": "consolidation",
    "name": "Consolidation",
    "enabled": true,
    "messageUrl": "http://127.0.0.1:8003/api/discord/chrome-bridge/message",
    "heartbeatUrl": "http://127.0.0.1:8003/api/discord/chrome-bridge/heartbeat",
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
  }
]
```

Use Discord channel URLs from the browser address bar. The bridge normalizes message URLs down to the channel URL and only captures a channel when at least one enabled target matches it. If a target has no channel filters, it receives every observed Discord channel.

Optional settings:

| Setting | Purpose |
| --- | --- |
| `chrome_bridge_channel_ids` | Optional list or comma-separated string of allowed observed channel IDs. When unset, the incoming observed channel ID is accepted. |
| `CHROME_BRIDGE_ALLOW_REMOTE` | Set to `true` only if you intentionally want to accept non-local bridge requests. |

## Alert Parsing

The parser supports common options alert language:

```text
BTO SPY 500C 6/21 @ 1.25
BUY SPY 500 CALLS 6/21 @ 1.25
STC SPY 500C 6/21 @ 1.40
SELL 50% SPY 500 CALLS 6/21 @ 1.40
AVG DOWN SPY 500C 6/21
```

Parsed fields include:

- ticker
- strike
- option type
- expiration
- alert type
- entry or exit price
- sell percentage

Embed-only alerts are supported through `discord_alert_text.py`, which combines message content, embed author, title, description, fields, and footer into one parseable string.

## Parser Preview

Use:

```text
POST /api/discord/parse-preview
```

Preview returns:

- raw text
- parsed alert
- source config
- skip reason
- confidence
- warnings
- parser metadata
- execution preview
- estimated quantity and premium cost for buy-style alerts

Preview does not insert alerts, create trades, or call brokers.

## Custom Alert Patterns

Configurable parser pattern groups:

- `buy_patterns`
- `sell_patterns`
- `partial_sell_patterns`
- `average_down_patterns`
- `stop_loss_patterns`
- `take_profit_patterns`
- `ignore_patterns`
- `ticker_pattern`
- `case_sensitive`

Validation protects against:

- empty patterns
- oversized patterns
- invalid ticker regex
- ticker regex without a capture group
- unsafe nested quantifier shapes
- overly broad wildcard quantifiers

## Source Overrides

Source overrides are keyed by channel ID or channel name. Channel ID wins first, then channel name.

Supported fields:

| Field | Purpose |
| --- | --- |
| `enabled` | Disable all alerts from the source when false. |
| `paper_only` | Force source alerts into simulation mode. |
| `paper_shadow` | Create linked simulated shadow records for live-capable alerts. |
| `require_manual_confirm` | Insert alerts but do not request automatic trade execution. |
| `allowed_actions` | Restrict to buy, sell, trim, close, or average_down. |
| `ticker_allowlist` | Only allow listed tickers. |
| `ticker_blocklist` | Block listed tickers. |
| `max_premium` | Block buy/average-down alerts above this option premium. |
| `risk_multiplier` | Adjust quantity sizing for the source. |
| `max_contracts` | Cap contracts from this source. |
| `notes` | Operator notes. |

Skip reasons are surfaced in parser preview and ingestion results.

## Trading Lifecycle

### Discord Ingestion

`discord_ingestion.handle_discord_message`:

1. Skips self messages.
2. Skips unmonitored channels.
3. Builds combined alert text from content and embeds.
4. Parses alert text.
5. Resolves source config.
6. Applies source skip policy.
7. Applies duplicate detection.
8. Inserts alert.
9. Requests trade processing only when allowed.

### Buy Alerts

In simulation mode:

1. Calculate quantity.
2. Create a simulated trade.
3. Create an open position.
4. Mark the alert processed and executed.

In live mode:

1. Calculate quantity.
2. Apply source limits.
3. Run correlation checks.
4. Apply premium buffer when enabled.
5. Build deterministic broker-safe client order ID.
6. Submit broker order.
7. Store pending or failed trade.
8. Start fill monitoring when broker submission succeeds.
9. Let fill reconciliation update final alert/trade/position state.

### Exit Alerts

Exit alerts are `sell`, `trim`, and `close`.

Exit planning matches open or partial positions by:

- ticker
- strike when present
- option type when present
- expiration when present

It calculates quantity from sell percentage and requires an exit price from the alert or current position.

In live mode, simulated and `:paper_shadow` positions are excluded from real broker exits.

### Fill Monitoring

The fill monitor polls broker order status and handles:

- filled
- partial
- rejected
- cancelled
- expired
- unknown
- error
- unconfirmed
- timeout

Fill reconciliation updates:

- trade status
- filled quantity
- average fill price
- position open, partial, or closed state
- alert processed and execution result flags

### Paper Shadow

When a source has `paper_shadow=true` and the bot is not already in simulation mode:

- live buy alerts can also create simulated shadow trade and position records
- live exit alerts can update matching shadow positions without sending those positions to a broker

This is useful for comparing live behavior against local simulated tracking.

## Risk And Safety Controls

Implemented controls include:

- auto trading toggle
- simulation mode
- duplicate alert blocking
- max positions per ticker
- source enable/disable
- allowed actions
- ticker allow/block lists
- max premium by source
- risk multiplier by source
- max contracts by source
- premium buffer
- averaging down settings
- take profit settings
- stop loss settings
- trailing stop settings
- auto shutdown settings
- runtime loss counters
- admin-protected loss counter reset
- setup diagnostics
- broker order-status support check

Setup diagnostics:

```text
GET /api/diagnostics/setup
```

Reports:

- Discord token/channel readiness
- source override counts and validity
- paper-only, paper-shadow, manual-confirm, and auto-live source counts
- active broker configuration
- order-status support
- auto trading state
- simulation mode
- shutdown state
- warnings

No tokens or broker secrets are returned.

## Broker Support Levels

The repo contains configuration metadata for several brokers. Live execution requires order-status polling in the current server path.

| Broker | Config UI/metadata | Connection check | Place order implementation | Order status polling | Live execution path |
| --- | --- | --- | --- | --- | --- |
| Alpaca | Yes | Yes | Yes | Yes | Supported when configured. |
| Tradier | Yes | Yes | Yes | Yes | Supported when configured. |
| IBKR | Yes | Yes | Has order submission logic | No current status polling | Blocked by live order-status requirement. |
| TD Ameritrade/Schwab | Yes | Token/account check logic | Not fully implemented | No | Not live-ready. |
| Thinkorswim/Schwab | Yes | Token/account check logic | Not fully implemented | No | Not live-ready. |
| TradeStation | Yes | Token/account check logic | Not fully implemented | No | Not live-ready. |
| Webull | Yes | Not implemented | Not implemented | No | Not live-ready. |
| Robinhood | Yes | Not implemented | Not implemented | No | Not live-ready. |
| Wealthsimple | Yes | Login check logic | Not implemented | No | Not live-ready. |

Use `/api/diagnostics/setup` before live trading. If active broker order status is unsupported, live execution is not considered ready.

## Frontend Tabs

| Tab | Route | Purpose |
| --- | --- | --- |
| Dashboard | `/` | Bot status, portfolio summary, readiness, recent activity. |
| Alerts | `/alerts` | Alert list and processing status. |
| Trades | `/trades` | Trade list, filters, close/update actions. |
| Positions | `/positions` | Open/partial/closed positions and position actions. |
| Lab | `/operator-lab` | Safe test alert and simulated exit workflows. |
| Strikes | `/strike-selection` | Strike selection workbench with strategy modes and mock chain data. |
| Trading | `/trading-settings` | Order, buffer, quantity, and trade-management settings. |
| Risk | `/risk-settings` | Risk-management settings and toggles. |
| Discord | `/discord-settings` | Discord connection, parser patterns, and alert policy controls. |
| Broker | `/broker-config` | Broker credentials, active broker, and connection checks. |
| Profiles | `/profiles` | Profile creation, activation, broker toggles, and per-broker settings. |
| Settings | `/settings` | General settings, notification controls, and operational settings. |

## Simulation Engine Replay Bridge

The bridge consumes the Simulation Engine contract:

```text
simulation.consolidation.replay.v1
```

Configure:

```powershell
$env:SIMULATION_ENGINE_REPLAY_URL = "http://127.0.0.1:9200/api/consolidation/replay/events"
```

Fetch raw replay events:

```text
GET /api/simulation-engine/replay-events
```

Preview replay events through Consolidation:

```text
POST /api/simulation-engine/replay-preview
```

Preview mode:

```text
preview_only_no_trades
```

The preview:

- fetches recorded events from the Simulation Engine
- parses the alert text with Consolidation parser logic
- applies current source policy
- includes Simulation Engine market snapshot and price drift context
- reports whether the alert would insert
- reports whether it would request a trade under current settings
- does not insert alerts
- does not create trades
- does not contact brokers

Example request:

```json
{
  "channel_id": "123456789",
  "since": "2026-06-19T14:30:00+00:00",
  "limit": 100
}
```

## API Reference

All routes below are under `/api`.

### Health

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Basic health status. |
| GET | `/status` | Runtime bot status. |
| GET | `/diagnostics/setup` | Live-readiness diagnostics without secrets. |

### Discord

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/discord/start` | Start Discord bot thread from saved settings. |
| POST | `/discord/stop` | Stop Discord bot. |
| POST | `/discord/test-connection` | Report whether Discord bot is configured/running/connected. |
| POST | `/discord/parse-preview` | Parse and policy-check text without side effects. |
| POST | `/discord/chrome-bridge/message` | Local-only intake for visible Discord Web messages observed by the Chrome bridge. |
| GET | `/discord/alert-patterns` | Read alert patterns. |
| PUT | `/discord/alert-patterns` | Update alert patterns. |
| POST | `/discord/alert-patterns/reset` | Reset patterns to defaults. |
| POST | `/discord/alert-patterns/{pattern_type}/add` | Add one pattern. |
| POST | `/discord/alert-patterns/{pattern_type}/remove` | Remove one pattern. |

### Trading

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/alerts` | List alert history. |
| POST | `/test-alert` | Create safe test alert/trade/position records. |
| GET | `/trades` | List trades. |
| POST | `/trades/{trade_id}/close` | Close a trade. |
| PUT | `/trades/{trade_id}/price` | Update current trade price. |
| GET | `/positions` | List positions. |
| POST | `/sell-position/{position_id}` | Sell a position. |
| POST | `/positions/{position_id}/sell` | Sell a position with submitted details. |
| GET | `/portfolio` | Portfolio summary. |

### Operator Lab

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/operator/events` | Recent operator events. |
| POST | `/operator/test-alert` | Create simulated test alert/trade/position and log event. |
| POST | `/operator/simulate-exit` | Simulate selling an open position and log event. |

### Settings

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/settings` | Read settings with decrypted runtime values and masked response secrets where applicable. |
| PUT | `/settings` | Update settings and encrypt broker credentials before persistence. |
| GET | `/source-overrides` | Read source policy overrides. |
| PUT | `/source-overrides` | Update and validate source policy overrides. |
| GET | `/correlation-settings` | Read max positions per ticker. |
| PUT | `/correlation-settings` | Update max positions per ticker. |
| POST | `/toggle-trading` | Toggle auto trading. |
| POST | `/toggle-premium-buffer` | Toggle premium buffer. |
| GET | `/premium-buffer-settings` | Read premium buffer config. |
| PUT | `/premium-buffer-settings` | Update premium buffer amount. |
| POST | `/toggle-averaging-down` | Toggle averaging down. |
| GET | `/averaging-down-settings` | Read averaging down config. |
| PUT | `/averaging-down-settings` | Update averaging down config. |
| POST | `/toggle-take-profit` | Toggle take profit. |
| POST | `/toggle-stop-loss` | Toggle stop loss. |
| GET | `/risk-management-settings` | Read take-profit/stop-loss config. |
| PUT | `/risk-management-settings` | Update take-profit/stop-loss config. |
| POST | `/toggle-trailing-stop` | Toggle trailing stop. |
| GET | `/trailing-stop-settings` | Read trailing stop config. |
| PUT | `/trailing-stop-settings` | Update trailing stop config. |
| POST | `/toggle-auto-shutdown` | Toggle auto shutdown. |
| GET | `/auto-shutdown-settings` | Read shutdown config and runtime counters. |
| PUT | `/auto-shutdown-settings` | Update shutdown config. |
| POST | `/reset-loss-counters` | Admin-protected reset of shutdown counters. |
| GET | `/notification-settings` | Read notification settings with masked secrets. |
| PUT | `/notification-settings` | Update notification settings. |
| POST | `/notification-settings/test` | Send test SMS notification. |
| GET | `/notification-log` | Read in-memory notification log. |
| POST | `/check-broker-connection` | Check active broker connection. |

### Brokers

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/brokers` | List broker metadata and risk warnings. |
| GET | `/active-broker` | Read active broker. |
| POST | `/active-broker/{broker_id}` | Set active broker. |
| POST | `/broker/switch/{broker_id}` | Switch active broker. |
| POST | `/broker/check/{broker_id}` | Check one broker and close temporary client. |

### Profiles

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/profiles` | List profiles. |
| GET | `/profiles/active` | Get active profile. |
| POST | `/profiles` | Create profile. |
| PUT | `/profiles/{profile_id}` | Update profile metadata. |
| POST | `/profiles/{profile_id}/activate` | Activate profile. |
| DELETE | `/profiles/{profile_id}` | Delete profile. |
| POST | `/profiles/{profile_id}/brokers/{broker_type}/toggle` | Toggle broker in profile. |
| GET | `/profiles/{profile_id}/active-brokers` | List active brokers for profile. |
| GET | `/profiles/{profile_id}/settings` | Read profile settings. |
| PUT | `/profiles/{profile_id}/settings` | Update profile settings. |
| POST | `/profiles/{profile_id}/settings/toggle/{setting_name}` | Toggle profile setting. |
| GET | `/profiles/{profile_id}/brokers/{broker_id}/settings` | Read broker settings for profile. |
| PUT | `/profiles/{profile_id}/brokers/{broker_id}/settings` | Update broker settings for profile. |
| POST | `/profiles/{profile_id}/brokers/{broker_id}/settings/toggle/{setting_name}` | Toggle broker setting for profile. |
| GET | `/profiles/{profile_id}/all-broker-settings` | Read all broker settings for profile. |

### Analytics

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/heatmap` | Heatmap data. |
| GET | `/time-series` | Time-series analytics. |
| GET | `/metrics/advanced` | Advanced metrics. |
| GET | `/reports/daily` | Daily report. |
| GET | `/reports/weekly` | Weekly report. |
| GET | `/reports/tax` | Tax report data. |
| GET | `/performance` | Performance summary. |

### Simulation Engine

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/simulation-engine/replay-events` | Fetch recorded replay events from Simulation Engine. |
| POST | `/simulation-engine/replay-preview` | Preview replay events through Consolidation without side effects. |

## Data Storage

| Mode | Storage |
| --- | --- |
| Local launcher | SQLite at `data\consolidation.sqlite3`. |
| Docker/server mode | MongoDB configured by `MONGO_URL` and `DB_NAME`. |
| Runtime status | In-memory plus persisted settings/runtime fields where implemented. |
| Launcher logs | Desktop `Consolidation-Discord-Bot.log`. |

Broker credentials are encrypted before persistence only when `CREDENTIAL_KEY` is a valid 32-byte hex key. Missing or malformed keys block live readiness and live broker order submission; legacy plaintext setup flows may still run for compatibility, so configure this key before storing production broker secrets.

## Project Structure

```text
Consolidation/
  backend/
    server.py                 FastAPI app, Discord bot lifecycle, trade processing
    discord_ingestion.py      Discord alert ingestion pipeline
    discord_alert_text.py     Message plus embed text extraction
    source_config.py          Per-source policy normalization and checks
    order_execution.py        Broker config resolution and client order IDs
    fill_monitor.py           Broker order polling
    fill_reconciliation.py    Trade/alert/position reconciliation
    trade_lifecycle.py        Exit planning
    paper_shadow.py           Paper-shadow records
    simulation_replay.py      Simulation Engine replay client and preview builder
    routes/                   FastAPI route modules
    broker_clients/           Legacy broker client implementations
    brokers/                  Broker metadata and adapter registry
    database_sqlite.py        Local SQLite persistence
    database/                 Database abstraction
    tests/                    Backend unit tests
  frontend/
    app/                      Expo Router screens
    components/               Shared UI components
    utils/                    API client, digests, validation helpers
    tests/                    Node tests for frontend logic
  scripts/
    ui_full_audit.py          Playwright UI audit harness
    tradebot_cli.py           CLI helpers and dashboard route helpers
  Launch-Consolidation-Bot.ps1
  docker-compose.yml
  nginx/
  prometheus/
```

## Development Commands

Backend tests:

```powershell
python -m unittest discover backend/tests -v
```

Targeted Simulation Engine bridge tests:

```powershell
python -m unittest backend.tests.test_simulation_replay -v
```

Frontend tests:

```powershell
cd frontend
npm run test:ui
```

Frontend lint:

```powershell
cd frontend
npm run lint
```

Launcher smoke test:

```powershell
.\Launch-Consolidation-Bot.ps1 -SmokeTest
```

UI audit script:

```powershell
.\scripts\run_ui_full_audit.ps1
```

## Common Workflows

### Test Parsing Without Trading

1. Start backend and frontend.
2. Open Discord tab.
3. Paste an analyst alert into parse preview.
4. Review parser confidence, warnings, source config, skip reason, and execution preview.
5. Adjust parser patterns or source overrides.

### Build A Safe Source

1. Add a source override keyed by channel ID.
2. Start with `paper_only=true` or `require_manual_confirm=true`.
3. Add ticker allow/block lists if needed.
4. Add max premium and max contract caps.
5. Use parse preview with real historical alerts.
6. Only then consider automatic execution.

### Replay Simulation Engine Data

1. Run Sentinel Simulation Engine on port `9200`.
2. Record or import Discord alerts and option market data there.
3. Use its Consolidation Replay panel to verify events.
4. Set `SIMULATION_ENGINE_REPLAY_URL` in Consolidation.
5. Call `/api/simulation-engine/replay-preview`.
6. Review what Consolidation would parse and whether it would request trades.

### Live Trading Readiness Check

Consolidation keeps live-readiness evidence as explicit gates. Auto trading can
stay enabled for paper/live-readiness testing, but `/api/operator/live-readiness`
does not report ready until every gate has current evidence.

1. Configure Discord token and channel IDs.
2. Configure source overrides for the alert channels that may request trades.
3. Configure Alpaca paper or another broker with order-status and cancel support.
4. Confirm `auto_trading_enabled=true`.
5. Keep paper validation isolated from real-money accounts.
6. Call `POST /api/broker/check/alpaca` or the active broker check route.
7. Call `GET /api/operator/live-readiness`.
8. Run drill endpoints and record evidence until all readiness gates pass.

Readiness gate endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/operator/readiness-gates` | Return required gate definitions and latest evidence state. |
| `POST` | `/api/operator/readiness-gates/{gate_key}/evidence` | Record operator or drill evidence for a gate. |
| `POST` | `/api/operator/drills/partial-fill` | Apply a synthetic broker partial-fill update through reconciliation. |
| `POST` | `/api/operator/drills/reconnect` | Close and recreate the active broker client and verify both connections. |
| `POST` | `/api/operator/monitoring/paper-session-snapshot` | Record a healthy paper-monitoring snapshot and promote multi-session or market-transition gates when evidence is sufficient. |

Current local Alpaca paper status on 2026-06-24:

| Gate | Status |
| --- | --- |
| Paper-mode burn-in | Passed from current paper-session evidence. |
| Partial-fill broker behavior | Passed through `/api/operator/drills/partial-fill`. |
| Disconnect/reconnect drill | Passed through `/api/operator/drills/reconnect`. |
| Live monitoring evidence | Passed with API, Discord, and Alpaca paper health visible. |
| Controlled operator access review | Passed for local API-key protected testing. |
| Operator signoff | Passed from explicit operator authorization in the test thread. |
| Market-transition validation | Open until a healthy open/closed market-state transition is observed. |
| Multi-session paper monitoring | Open until healthy snapshots exist for at least two distinct market sessions. |

The live-readiness loop should keep recording paper-session snapshots across
market boundaries. Do not mark the two open gates passed manually; let the
monitoring endpoint promote them only after the evidence exists.

## Refactor Plan

Near-term refactors should preserve Consolidation as a standalone Discord
options execution bot and avoid absorbing Sentinel Edge or Sentinel Pulse roles.

1. Extract operator readiness gates from `routes/operator.py` into a small
   `readiness_evidence.py` service so route handlers stay thin.
2. Split broker drills into `broker_drills.py`, keeping Alpaca paper checks,
   reconnect checks, and synthetic partial-fill drills reusable from tests and
   scheduled monitoring.
3. Move paper-session monitoring into a dedicated service that can query a
   broker market clock, normalize sessions, and reject stale or unhealthy
   snapshots consistently.
4. Keep live-readiness rules centralized in `live_readiness.py`; route, health,
   and arming code should only supply status/evidence.
5. Add a durable operator monitoring table or collection if readiness evidence
   grows beyond append-only event scans.
6. Keep README and diagnostics aligned: every blocking code should have an
   operator-visible remediation step.

## Known Limitations

- Live execution currently requires broker order-status support.
- Alpaca and Tradier are the live-ready broker paths in the current server flow.
- IBKR order submission logic exists, but live server execution rejects brokers without order-status polling.
- Several broker adapters are configuration/check placeholders and are not live-order-ready.
- Discord `/discord/test-connection` reports bot runtime state; it is not a full REST permission diagnostic.
- Runtime bot status and notification log reset when the process restarts.
- Simulation Engine replay preview is read-only and does not insert alerts or trades.
- Some frontend strike-selection data is a workbench/mock chain rather than live option chain data.
- Market-transition and multi-session paper-monitoring gates require real
  market-time evidence and cannot be completed instantly.

## Roadmap Candidates

These are planned or candidate improvements, not guaranteed current behavior:

- Full REST diagnostics for Discord token and channel access.
- More broker order-status implementations.
- Live option-chain backed strike selection.
- Historical per-analyst performance scoring.
- More robust multi-leg strategy execution.
- Persistent notification log.
- End-to-end Simulation Engine replay UI inside Consolidation.
- Broader frontend coverage for all tabs and settings.

## Support

Repository:

```text
https://github.com/Tetradim/Consolidation
```

For local development, prefer the launcher and local SQLite mode first. Move to Docker/MongoDB only after the local workflow is verified.
