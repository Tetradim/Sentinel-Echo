# Consolidation first-run installer design

Date: 2026-06-25

## Goal

Windows beta testers should install the Discord options bot from `ConsolidationBot-Setup-<version>.exe`, double-click the installed shortcut, and have runtime dependencies handled automatically on first launch.

## Design

- Keep the existing source launcher behavior for developers and the bot suite.
- Extend `Launch-Consolidation-Bot.ps1` with an installed-package path when `ConsolidationBot.exe` exists beside the launcher.
- The installed launcher checks/downloads the Visual C++ Runtime, starts `ConsolidationBot.exe` with local SQLite mode, waits for `/api/health`, and opens the bundled UI at `/app/`.
- Add packaged static mounting to `backend/server.py`, and update frontend backend URL detection so a UI served from `/app/` calls the same local backend origin.
- Replace the frontend-only Windows workflow with a PyInstaller + Inno Setup workflow that packages the backend, exported Expo web UI, and launcher pair into `ConsolidationBot-Setup-<version>.exe`.

## Non-goals

- No MongoDB or Redis installation for the beta installer; local SQLite/in-memory paths remain the installer default.
- No broker credential wizard changes.
- No macOS installer redesign.
