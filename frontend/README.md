# Sentinel Echo Frontend

Expo web dashboard for the Sentinel Echo. The dashboard connects to the FastAPI backend for bot status, Discord alert review, broker configuration, positions, trades, risk controls, and source-specific settings.

## Local Launcher

The recommended Windows entrypoint is the repository-root launcher:

```powershell
cd ..
.\Launch-Sentinel-Echo.bat
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

## Development Notes

- Main screens live in `app/`.
- Shared API setup lives in `utils/api.ts`.
- The settings screens include Discord setup, alert parser configuration, broker settings, and risk controls.
- Keep `SIMULATION_MODE=true` on the backend while validating Discord alert parsing and broker configuration.
