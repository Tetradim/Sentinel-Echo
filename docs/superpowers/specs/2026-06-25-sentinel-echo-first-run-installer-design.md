# Sentinel Echo first-run installer design

Date: 2026-06-25

## Goal

Windows beta testers should install the Discord options bot from `SentinelEcho-Setup-<version>.exe`, double-click the installed shortcut, and have runtime dependencies handled automatically on first launch.

## Design

- Keep the existing source launcher behavior for developers and the bot suite.
- Extend `Launch-Sentinel-Echo.ps1` with an installed-package path when `SentinelEcho.exe` exists beside the launcher.
- The installed launcher checks/downloads the Visual C++ Runtime, starts `SentinelEcho.exe` with local SQLite mode, waits for `/api/health`, and opens the bundled UI at `/app/`.
- Add packaged static mounting to `backend/server.py`, and update frontend backend URL detection so a UI served from `/app/` calls the same local backend origin.
- Replace the frontend-only Windows workflow with a PyInstaller + Inno Setup workflow that packages the backend, exported Expo web UI, and launcher pair into `SentinelEcho-Setup-<version>.exe`.

## Non-goals

- No MongoDB or Redis installation for the beta installer; local SQLite/in-memory paths remain the installer default.
- No broker credential wizard changes.
- No macOS installer redesign.
