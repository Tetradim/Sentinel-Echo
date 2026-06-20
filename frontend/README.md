# Consolidation Discord Bot Frontend

Expo web dashboard for the Consolidation Discord options bot. The dashboard connects to the FastAPI backend for bot status, Discord alert review, broker configuration, positions, trades, risk controls, and source-specific settings.

## Local Launcher

The recommended Windows entrypoint is the repository-root launcher:

```powershell
cd ..
.\Launch-Consolidation-Bot.bat
```

Default local ports:

| Service | URL |
|---------|-----|
| Backend API | `http://127.0.0.1:8003` |
| Frontend web UI | `http://127.0.0.1:3003` |

The launcher sets `EXPO_PUBLIC_BACKEND_URL=http://127.0.0.1:8003` before starting Expo web.

## Manual Frontend Run

```powershell
npm install
$env:EXPO_PUBLIC_BACKEND_URL = "http://127.0.0.1:8003"
npm run web -- --port 3003
```

Use the backend health endpoint to confirm the API is reachable:

```powershell
Invoke-RestMethod http://127.0.0.1:8003/api/health
```

## Backend URL

The frontend resolves its API base URL from:

```text
EXPO_PUBLIC_BACKEND_URL
```

If the variable is not set, [constants/config.ts](constants/config.ts) falls back to `http://localhost:8003`.

## Current Dashboard Coverage

The latest frontend build is wired for the production Discord/options readiness flow:

- Dashboard readiness summarizes broker, Discord, automation, shutdown, and exit-guard state.
- Discord settings support parser previews, source-specific policy editing, custom ticker validation, paper-only, paper-shadow, manual-confirm, premium caps, contract caps, risk multipliers, and ticker/action allow or block lists.
- Broker, profile, settings, positions, trades, alerts, risk, and trading settings screens include digest helpers that surface load failures and actionable next steps.
- Live data failures stay visible instead of silently falling back to demo data.
- Operator navigation and retry actions are available across the main screens.

Useful backend checks while validating the UI:

```powershell
Invoke-RestMethod http://127.0.0.1:8003/api/health
Invoke-RestMethod http://127.0.0.1:8003/api/diagnostics/setup
```

## Development Notes

- Main screens live in `app/`.
- Shared API setup lives in `utils/api.ts`.
- Screen readiness and digest helpers live in `utils/*Digest.ts` and `utils/dashboardReadiness.ts`.
- The settings screens include Discord setup, alert parser configuration, broker settings, and risk controls.
- Keep `SIMULATION_MODE=true` on the backend while validating Discord alert parsing and broker configuration.
