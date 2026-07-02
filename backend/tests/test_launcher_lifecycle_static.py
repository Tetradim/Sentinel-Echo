from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "Launch-Sentinel-Echo.ps1"


def read_launcher() -> str:
    return LAUNCHER.read_text(encoding="utf-8")


def test_launcher_tracks_dedicated_browser_window() -> None:
    text = read_launcher()

    for expected in [
        "$BrowserProcess = $null",
        "$BrowserProfileDir = $null",
        "$BrowserProcessIds = @()",
        "$BrowserWindowProcessIds = @()",
        "$BrowserStartedAt = $null",
        "$BrowserMonitorDisabled = $false",
        "function Find-BrowserExecutable",
        "function Start-BrowserWindow",
        "function Get-BrowserProfileProcesses",
        "function Get-BrowserWindowProcesses",
        "function Wait-BrowserProfileProcesses",
        "function Wait-BrowserWindowProcesses",
        "function Test-BrowserWindowClosed",
        "function Stop-BrowserWindow",
        "--user-data-dir=$script:BrowserProfileDir",
        "--disable-background-mode",
    ]:
        assert expected in text
    assert "Start-Process $frontendUrl" not in text


def test_launcher_has_external_shutdown_watchdog() -> None:
    text = read_launcher()

    for expected in [
        "$LauncherWatchdogProcess = $null",
        "$LauncherWatchdogStopFile = $null",
        "$LauncherWatchdogScriptFile = $null",
        "function Start-LauncherShutdownWatchdog",
        "function Stop-LauncherShutdownWatchdog",
        "$ParentProcessId",
        "Get-ProfileProcesses",
        "Stop-ProcessTreeById",
        "Start-Process -FilePath \"powershell.exe\"",
        "-WindowStyle Hidden",
        "Start-LauncherShutdownWatchdog",
        "Stop-LauncherShutdownWatchdog",
    ]:
        assert expected in text


def test_launcher_closes_services_when_browser_or_launcher_closes() -> None:
    text = read_launcher()

    for expected in [
        "Register-EngineEvent -SourceIdentifier PowerShell.Exiting",
        "[Console]::CancelKeyPress",
        "Stop-LauncherShutdownWatchdog",
        "Stop-BrowserWindow",
        "Stop-OwnedProcesses",
        "Test-BrowserWindowClosed",
        "Browser window closed; shutting down Sentinel Echo",
        "finally {",
        "Invoke-LauncherCleanup",
    ]:
        assert expected in text


def test_launcher_loads_local_env_before_backend_start() -> None:
    text = read_launcher()

    for expected in [
        "function Import-LauncherEnvFile",
        "function Set-DefaultEnvValue",
        'Import-LauncherEnvFile -Path (Join-Path $ProjectRoot ".env.local")',
        'Set-DefaultEnvValue -Name "HOST" -Value "127.0.0.1"',
        'Set-DefaultEnvValue -Name "USE_SQLITE" -Value "true"',
    ]:
        assert expected in text
