# Consolidation Discord Options Bot Local Source Launcher
# Starts the FastAPI backend and Expo web frontend on separate localhost ports.

param(
    [int]$BackendPort = 8003,
    [int]$FrontendPort = 3003,
    [switch]$NoBrowser,
    [switch]$InstallDeps,
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
$ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }

$Backend = Join-Path $ProjectRoot "backend"
$Frontend = Join-Path $ProjectRoot "Frontend"
$DesktopPath = [Environment]::GetFolderPath("Desktop")
if (-not $DesktopPath) { $DesktopPath = Join-Path $HOME "Desktop" }
$LogFile = Join-Path $DesktopPath "Consolidation-Discord-Bot.log"
$OwnedProcesses = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$ShutdownStarted = $false
$CancelKeyPressHandler = $null

function Write-Status {
    param([string]$Message, [string]$Level = "INFO")
    $color = switch ($Level) {
        "OK" { "Green" }
        "WARN" { "Yellow" }
        "ERROR" { "Red" }
        default { "Cyan" }
    }
    Write-Host "[$Level] $Message" -ForegroundColor $color
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    Add-Content -Path $LogFile -Value "$timestamp [$Level] $Message" -Encoding UTF8
}

function Join-ProcessArguments {
    param([string[]]$Arguments)
    return (($Arguments | ForEach-Object {
        $arg = $_
        if ([string]::IsNullOrEmpty($arg)) {
            '""'
        } elseif ($arg -match '[\s"]') {
            '"' + $arg.Replace('"', '\"') + '"'
        } else {
            $arg
        }
    }) -join " ")
}

function Test-PortOpen {
    param([int]$Port)
    try {
        $client = New-Object Net.Sockets.TcpClient
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $connected = $async.AsyncWaitHandle.WaitOne(750, $false)
        if ($connected) { $client.EndConnect($async) }
        $client.Close()
        return $connected
    } catch {
        return $false
    }
}

function Wait-Port {
    param([int]$Port, [int]$Seconds = 60)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen -Port $Port) { return $true }
        Start-Sleep -Milliseconds 750
    }
    return $false
}

function Test-HttpOk {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300)
    } catch {
        return $false
    }
}

function Wait-HttpOk {
    param([string]$Url, [int]$Seconds = 60)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpOk -Url $Url) { return $true }
        Start-Sleep -Milliseconds 750
    }
    return $false
}

function Find-CommandPath {
    param([string[]]$Names)
    foreach ($name in $Names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Find-Python {
    foreach ($candidate in @(
        (Join-Path $Backend ".venv\Scripts\python.exe"),
        (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
    )) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return Find-CommandPath -Names @("python3.13.exe", "python3.12.exe", "python3.11.exe", "python.exe")
}

function Find-Npm {
    return Find-CommandPath -Names @("npm.cmd", "npm.exe", "npm")
}

function Start-OwnedProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [switch]$Visible
    )
    $startParams = @{
        FilePath = $FilePath
        WorkingDirectory = $WorkingDirectory
        PassThru = $true
    }
    if ($ArgumentList -and $ArgumentList.Count -gt 0) {
        $startParams.ArgumentList = Join-ProcessArguments -Arguments $ArgumentList
    }
    if (-not $Visible) {
        $startParams.WindowStyle = "Hidden"
    }
    $process = Start-Process @startParams
    $OwnedProcesses.Add($process)
    return $process
}

function Stop-ProcessTree {
    param([int]$ProcessId)
    try {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue)
        foreach ($child in $children) {
            Stop-ProcessTree -ProcessId $child.ProcessId
        }
        $current = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($current) {
            Write-Status "Stopping process $($current.ProcessName) ($($current.Id))"
            Stop-Process -Id $current.Id -Force -ErrorAction SilentlyContinue
        }
    } catch {
    }
}

function Stop-OwnedProcesses {
    for ($i = $OwnedProcesses.Count - 1; $i -ge 0; $i--) {
        Stop-ProcessTree -ProcessId $OwnedProcesses[$i].Id
    }
}

function Invoke-LauncherCleanup {
    if ($script:ShutdownStarted) { return }
    $script:ShutdownStarted = $true
    Stop-OwnedProcesses
}

function Register-LauncherShutdownHandlers {
    try {
        $script:CancelKeyPressHandler = [ConsoleCancelEventHandler]{
            param($sender, $eventArgs)
            $eventArgs.Cancel = $true
            Write-Status "Shutdown requested; stopping Consolidation bot" "WARN"
            Invoke-LauncherCleanup
            exit 0
        }
        [Console]::CancelKeyPress += $script:CancelKeyPressHandler
    } catch {
    }
}

if ($SmokeTest) {
    Write-Status "Running launcher smoke test"
    $backendArgs = Join-ProcessArguments -Arguments @("-m", "backend.run")
    if (-not $backendArgs.Contains("backend.run")) {
        throw "Backend argument smoke test failed."
    }
    $frontendArgs = Join-ProcessArguments -Arguments @("run", "web", "--", "--port", "3003")
    if (-not $frontendArgs.Contains("--port") -or -not $frontendArgs.Contains("3003")) {
        throw "Frontend argument smoke test failed."
    }
    Write-Status "Launcher smoke test passed" "OK"
    exit 0
}

Register-LauncherShutdownHandlers

try {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Consolidation Discord Options Bot" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Status "Project root: $ProjectRoot"
    Write-Status "Launcher log: $LogFile"

    if (-not (Test-Path $Backend)) { throw "Backend folder not found: $Backend" }
    if (-not (Test-Path $Frontend)) { throw "Frontend folder not found: $Frontend" }
    if (-not (Test-Path (Join-Path $Backend "requirements.txt"))) { throw "Backend requirements.txt not found." }
    if (-not (Test-Path (Join-Path $Frontend "package.json"))) { throw "Frontend package.json not found." }

    $venvPath = Join-Path $Backend ".venv"
    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        $python = Find-Python
        if (-not $python) { throw "Python was not found. Install Python 3.11+ and rerun." }
        Write-Status "Creating backend virtual environment"
        & $python -m venv $venvPath
        $InstallDeps = $true
    }

    if ($InstallDeps) {
        Write-Status "Installing backend dependencies"
        & $venvPython -m pip install --upgrade pip
        & $venvPython -m pip install -r (Join-Path $Backend "requirements.txt")
    }

    $npm = Find-Npm
    if (-not $npm) { throw "npm was not found. Install Node.js/npm and rerun." }
    if ($InstallDeps -or -not (Test-Path (Join-Path $Frontend "node_modules"))) {
        Write-Status "Installing frontend dependencies"
        Start-OwnedProcess -FilePath $npm -ArgumentList @("install") -WorkingDirectory $Frontend -Visible | Wait-Process
    }

    $backendUrl = "http://127.0.0.1:$BackendPort"
    $frontendUrl = "http://127.0.0.1:$FrontendPort"
    $dataDir = Join-Path $ProjectRoot "data"
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

    $env:HOST = "127.0.0.1"
    $env:PORT = "$BackendPort"
    $env:USE_SQLITE = "true"
    if (-not $env:DATABASE_PATH) {
        $env:DATABASE_PATH = Join-Path $dataDir "consolidation.sqlite3"
    }
    $env:EXPO_PUBLIC_BACKEND_URL = $backendUrl
    $env:BROWSER = "none"

    if (-not (Test-PortOpen -Port $BackendPort)) {
        Write-Status "Starting backend on port $BackendPort"
        Start-OwnedProcess -FilePath $venvPython -ArgumentList @("-m", "backend.run") -WorkingDirectory $ProjectRoot | Out-Null
        if (-not (Wait-HttpOk -Url "$backendUrl/api/health" -Seconds 90)) {
            throw "Backend did not become healthy at $backendUrl/api/health."
        }
        Write-Status "Backend is ready" "OK"
    } else {
        Write-Status "Backend port $BackendPort is already open" "WARN"
    }

    if (-not (Test-PortOpen -Port $FrontendPort)) {
        Write-Status "Starting Expo web frontend on port $FrontendPort"
        Start-OwnedProcess -FilePath $npm -ArgumentList @("run", "web", "--", "--port", "$FrontendPort") -WorkingDirectory $Frontend | Out-Null
        if (-not (Wait-Port -Port $FrontendPort -Seconds 90)) {
            throw "Frontend did not open port $FrontendPort."
        }
        Write-Status "Frontend is ready" "OK"
    } else {
        Write-Status "Frontend port $FrontendPort is already open" "WARN"
    }

    if (-not $NoBrowser) {
        Start-Process $frontendUrl | Out-Null
    }

    Write-Host ""
    Write-Host "Ready: $frontendUrl" -ForegroundColor Green
    Write-Host "Backend: $backendUrl" -ForegroundColor Gray
    Write-Host "Database: $env:DATABASE_PATH" -ForegroundColor Gray
    Write-Host "Close this window or press Ctrl+C to stop processes started by this launcher." -ForegroundColor Gray
    Write-Host ""

    while ($true) {
        foreach ($process in @($OwnedProcesses)) {
            if ($process.HasExited) {
                throw "Process $($process.Id) exited unexpectedly."
            }
        }
        Start-Sleep -Seconds 1
    }
} catch {
    Write-Status $_.Exception.Message "ERROR"
    exit 1
} finally {
    Invoke-LauncherCleanup
}
