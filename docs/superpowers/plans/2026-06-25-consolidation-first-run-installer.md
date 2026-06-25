# Consolidation First-Run Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an installed Windows launcher and setup artifact that repair missing runtime dependencies on first launch.

**Architecture:** The existing launcher remains the source checkout entrypoint. Installed packages are detected by `ConsolidationBot.exe`; that path repairs VC++ runtime, starts the packaged backend, serves the exported frontend from FastAPI `/app/`, and opens the local UI.

**Tech Stack:** PowerShell, FastAPI, Expo web export, PyInstaller, Inno Setup, pytest static checks.

---

### Task 1: Static tests

**Files:**
- Create: `backend/tests/test_windows_installer_bootstrap_static.py`

- [ ] Add tests for launcher installed/source mode detection, runtime dependency repair, packaged frontend serving, workflow packaging, and README instructions.
- [ ] Run `python -m pytest backend/tests/test_windows_installer_bootstrap_static.py -q` and confirm it fails before implementation.

### Task 2: Packaged backend and frontend

**Files:**
- Modify: `backend/server.py`
- Modify: `frontend/constants/config.ts`
- Create: `windows_entrypoint.py`

- [ ] Mount packaged static files at `/app`.
- [ ] Make frontend config use same-origin backend when served from `/app/`.
- [ ] Add a Windows entrypoint that imports `backend/server.py` and starts uvicorn after all routes load.

### Task 3: Launcher and workflow

**Files:**
- Modify: `Launch-Consolidation-Bot.bat`
- Modify: `Launch-Consolidation-Bot.ps1`
- Modify: `.github/workflows/build.yml`
- Modify: `README.md`

- [ ] Harden the batch wrapper for partial extracts.
- [ ] Add installed launcher mode with VC++ runtime repair and `/api/health` wait.
- [ ] Package `ConsolidationBot.exe`, exported frontend static files, and launcher pair.
- [ ] Build/upload `ConsolidationBot-Setup-<version>.exe`.
- [ ] Document beta installer and support logs.
