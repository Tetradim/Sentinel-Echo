param(
    [int]$BackendPort = 8003,
    [int]$FrontendPort = 3003
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DataDir = Join-Path $RepoRoot "data"
$DatabasePath = Join-Path $DataDir "ui-audit.sqlite3"
$BackendOut = Join-Path $DataDir "ui-audit-backend.out.log"
$BackendErr = Join-Path $DataDir "ui-audit-backend.err.log"
$FrontendOut = Join-Path $DataDir "ui-audit-frontend.out.log"
$FrontendErr = Join-Path $DataDir "ui-audit-frontend.err.log"
$BuildLog = Join-Path $DataDir "ui-audit-frontend-build.log"
$Python = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
$FrontendDir = Join-Path $RepoRoot "frontend"
$ServeMain = Join-Path $FrontendDir "node_modules\serve\build\main.js"

function Assert-PortFree {
    param([int]$Port)
    $listeners = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.State -eq "Listen" }
    if ($listeners) {
        $owners = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
        throw "Port $Port is already in use by process id(s): $($owners -join ', ')"
    }
}

function Wait-For-Port {
    param(
        [int]$Port,
        [string]$Name,
        [int]$TimeoutSeconds = 45
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $client = [System.Net.Sockets.TcpClient]::new()
            $client.Connect("127.0.0.1", $Port)
            $client.Close()
            Write-Host "$Name ready on port $Port"
            return
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    throw "$Name did not become ready on port $Port within $TimeoutSeconds seconds"
}

function Stop-ProcessIfRunning {
    param($Process)
    if ($Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        $Process.WaitForExit(5000) | Out-Null
    }
}

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
Remove-Item -LiteralPath $DatabasePath -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $BackendOut, $BackendErr, $FrontendOut, $FrontendErr, $BuildLog -ErrorAction SilentlyContinue

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Backend Python virtualenv not found at $Python"
}
if (-not (Test-Path -LiteralPath $ServeMain)) {
    throw "serve package not found at $ServeMain"
}

Assert-PortFree -Port $BackendPort
Assert-PortFree -Port $FrontendPort

$env:EXPO_PUBLIC_BACKEND_URL = "http://127.0.0.1:$BackendPort"
$env:EXPO_PUBLIC_DEMO_MODE = "false"
Write-Host "Building frontend for backend $env:EXPO_PUBLIC_BACKEND_URL"
Push-Location $FrontendDir
try {
    & npm.cmd run build *> $BuildLog
    if ($LASTEXITCODE -ne 0) {
        Write-Host "--- frontend build log tail ---"
        Get-Content -LiteralPath $BuildLog -Tail 120 -ErrorAction SilentlyContinue
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}

$backend = $null
$frontend = $null
$exitCode = 0

try {
    $env:PORT = "$BackendPort"
    $env:HOST = "127.0.0.1"
    $env:USE_SQLITE = "true"
    $env:DATABASE_PATH = "data/ui-audit.sqlite3"
    $env:API_KEY = ""
    $env:SENTINEL_ECHO_USE_OPENCLAW_DISCORD = "false"
    $env:DISCORD_BOT_TOKEN = ""
    $env:DISCORD_CHANNEL_IDS = ""
    $env:ALLOWED_ORIGINS = "http://localhost:$FrontendPort,http://127.0.0.1:$FrontendPort,http://localhost:3000,http://127.0.0.1:3000,http://localhost:3003,http://127.0.0.1:3003,http://localhost:5173,http://127.0.0.1:5173"

    Write-Host "Starting backend on port $BackendPort"
    $backend = Start-Process `
        -FilePath $Python `
        -ArgumentList @("-m", "backend.run") `
        -WorkingDirectory $RepoRoot `
        -RedirectStandardOutput $BackendOut `
        -RedirectStandardError $BackendErr `
        -WindowStyle Hidden `
        -PassThru
    Wait-For-Port -Port $BackendPort -Name "Backend"

    $node = (Get-Command node -ErrorAction Stop).Source
    $serveArgs = @("`"$ServeMain`"", "dist", "-l", "$FrontendPort", "-s")

    Write-Host "Starting frontend on port $FrontendPort"
    $frontend = Start-Process `
        -FilePath $node `
        -ArgumentList $serveArgs `
        -WorkingDirectory $FrontendDir `
        -RedirectStandardOutput $FrontendOut `
        -RedirectStandardError $FrontendErr `
        -WindowStyle Hidden `
        -PassThru
    Wait-For-Port -Port $FrontendPort -Name "Frontend"

    $env:BACKEND_URL = "http://127.0.0.1:$BackendPort"
    $env:FRONTEND_URL = "http://127.0.0.1:$FrontendPort"

    & $Python (Join-Path $RepoRoot "scripts\ui_full_audit.py")
    $exitCode = $LASTEXITCODE
} finally {
    Stop-ProcessIfRunning -Process $frontend
    Stop-ProcessIfRunning -Process $backend
}

if ($exitCode -ne 0) {
    Write-Host "--- backend stderr tail ---"
    Get-Content -LiteralPath $BackendErr -Tail 120 -ErrorAction SilentlyContinue
    Write-Host "--- frontend stderr tail ---"
    Get-Content -LiteralPath $FrontendErr -Tail 80 -ErrorAction SilentlyContinue
    exit $exitCode
}
