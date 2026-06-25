"""Static checks for Windows first-run installer support."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_BAT = ROOT / "Launch-Consolidation-Bot.bat"
LAUNCHER_PS1 = ROOT / "Launch-Consolidation-Bot.ps1"
BUILD_WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
README = ROOT / "README.md"
SERVER = ROOT / "backend" / "server.py"
FRONTEND_CONFIG = ROOT / "frontend" / "constants" / "config.ts"
WINDOWS_ENTRYPOINT = ROOT / "windows_entrypoint.py"


def test_launcher_supports_installed_and_source_modes():
    batch = LAUNCHER_BAT.read_text(encoding="utf-8")
    script = LAUNCHER_PS1.read_text(encoding="utf-8")

    assert "Launch-Consolidation-Bot.ps1" in batch
    assert "ConsolidationBot-Setup" in batch
    assert "if not exist" in batch.lower()
    assert "Consolidation Discord Options Bot - Installed App" in script
    assert "ConsolidationBot.exe" in script
    assert "Start-InstalledConsolidationBot" in script
    assert "Start-SourceConsolidationBot" in script
    assert "Ensure-InstalledRuntimeDependencies" in script
    assert "Test-VcRuntimeInstalled" in script
    assert "vc_redist.x64.exe" in script
    assert "/api/health" in script
    assert "/app/" in script


def test_packaged_backend_serves_exported_frontend():
    server = SERVER.read_text(encoding="utf-8")
    frontend_config = FRONTEND_CONFIG.read_text(encoding="utf-8")
    entrypoint = WINDOWS_ENTRYPOINT.read_text(encoding="utf-8")

    assert "StaticFiles" in server
    assert "def find_packaged_static_dir" in server
    assert "sys._MEIPASS" in server
    assert 'app.mount("/app"' in server
    assert "window.location.pathname.startsWith('/app')" in frontend_config
    assert "return window.location.origin" in frontend_config
    assert "import server" in entrypoint
    assert "uvicorn.run(server.app" in entrypoint


def test_build_workflow_creates_installer_not_frontend_only_zip():
    workflow = BUILD_WORKFLOW.read_text(encoding="utf-8")

    assert "Build Windows Executable" in workflow
    assert "npx expo export --platform web" in workflow
    assert "python -m PyInstaller" in workflow
    assert "windows_entrypoint.py" in workflow
    assert "ConsolidationBot.exe" in workflow
    assert "Launch-Consolidation-Bot.bat" in workflow
    assert "Launch-Consolidation-Bot.ps1" in workflow
    assert "ConsolidationBot-Setup-{#MyAppVersion}" in workflow
    assert 'Filename: "{app}\\Launch-Consolidation-Bot.bat"' in workflow
    assert "Minionguyjpro/Inno-Setup-Action" in workflow
    assert "python -m http.server 8080" not in workflow


def test_readme_documents_beta_installer_first_run_behavior():
    readme = README.read_text(encoding="utf-8")

    assert "ConsolidationBot-Setup-<version>.exe" in readme
    assert "downloads missing runtime dependencies on first launch" in readme
    assert "Visual C++ Runtime" in readme
    assert "Consolidation-Discord-Bot.log" in readme
    assert "Python, Node.js, npm, MongoDB, or Redis" in readme
