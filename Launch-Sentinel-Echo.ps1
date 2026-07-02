# Sentinel Echo Local Source Launcher
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
$Frontend = Join-Path $ProjectRoot "frontend"
$DesktopPath = [Environment]::GetFolderPath("Desktop")
if (-not $DesktopPath) { $DesktopPath = Join-Path $HOME "Desktop" }
$LogFile = Join-Path $DesktopPath "Sentinel-Echo.log"
$OwnedProcesses = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$BrowserProcess = $null
$BrowserProfileDir = $null
$BrowserProcessIds = @()
$BrowserWindowProcessIds = @()
$BrowserStartedAt = $null
$BrowserMonitorDisabled = $false
$ShutdownStarted = $false
$CleanupEventSubscription = $null
$CancelKeyPressHandler = $null
$LauncherWatchdogProcess = $null
$LauncherWatchdogStopFile = $null
$LauncherWatchdogScriptFile = $null
$VcRedistUrl = "https://aka.ms/vc14/vc_redist.x64.exe"
$DependencyRoot = if ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "Sentinel Echo\dependencies"
} else {
    Join-Path $ProjectRoot ".dependencies"
}

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

function Import-LauncherEnvFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }

    foreach ($line in Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        if ($trimmed -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') { continue }

        $name = $Matches[1]
        $value = $Matches[2].Trim()
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }

    Write-Status "Loaded local environment overrides: $Path"
}

function Set-DefaultEnvValue {
    param([string]$Name, [string]$Value)
    $current = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($current)) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
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

function Test-BackendCorsOk {
    param([string]$BackendUrl, [string]$FrontendOrigin)
    try {
        $headers = @{
            Origin = $FrontendOrigin
            "Access-Control-Request-Method" = "GET"
        }
        $response = Invoke-WebRequest -Uri "$BackendUrl/api/status" -Method Options -Headers $headers -UseBasicParsing -TimeoutSec 5
        return ($response.Headers["Access-Control-Allow-Origin"] -eq $FrontendOrigin)
    } catch {
        return $false
    }
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$Seconds = 60,
        [System.Diagnostics.Process]$Process = $null
    )
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if ($Process -and $Process.HasExited) { return $false }
        if (Test-HttpOk -Url $Url) { return $true }
        Start-Sleep -Milliseconds 750
    }
    return $false
}

function Test-VcRuntimeInstalled {
    $keys = @(
        "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
    )

    foreach ($key in $keys) {
        try {
            $runtime = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
            if ($runtime -and $runtime.Installed -eq 1) { return $true }
        } catch {
        }
    }
    return $false
}

function Invoke-DependencyDownload {
    param(
        [string]$Url,
        [string]$OutFile,
        [string]$Label
    )

    New-Item -ItemType Directory -Path (Split-Path -Parent $OutFile) -Force | Out-Null
    if (Test-Path -LiteralPath $OutFile) {
        Write-Status "$Label already downloaded"
        return $OutFile
    }

    Write-Status "Downloading $Label"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    } catch {
    }
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -TimeoutSec 180
    return $OutFile
}

function Ensure-InstalledRuntimeDependencies {
    if (Test-VcRuntimeInstalled) {
        Write-Status "Microsoft Visual C++ Runtime is installed" "OK"
        return
    }

    Write-Status "Microsoft Visual C++ Runtime was not found; installing it automatically" "WARN"
    $installer = Join-Path $DependencyRoot "vc_redist.x64.exe"
    Invoke-DependencyDownload -Url $VcRedistUrl -OutFile $installer -Label "Microsoft Visual C++ Runtime" | Out-Null
    $process = Start-Process -FilePath $installer -ArgumentList "/install", "/quiet", "/norestart" -Wait -PassThru
    if (-not (@(0, 3010, 1638) -contains $process.ExitCode)) {
        Write-Status "Microsoft Visual C++ Runtime installer exited with code $($process.ExitCode). Sentinel Echo will continue and report any startup error." "WARN"
    }
}

function Write-ProcessLogTail {
    param(
        [string]$Path,
        [string]$Label,
        [int]$Lines = 80
    )
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $tail = @(Get-Content -LiteralPath $Path -Tail $Lines -ErrorAction SilentlyContinue)
    if ($tail.Count -eq 0) { return }
    Write-Status "$Label log tail: $Path" "ERROR"
    foreach ($line in $tail) {
        Write-Host "[$Label] $line" -ForegroundColor DarkGray
        Add-Content -Path $LogFile -Value "[$Label] $line" -Encoding UTF8
    }
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

function Find-BrowserExecutable {
    $candidates = @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }

    foreach ($name in @("msedge.exe", "chrome.exe")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Get-BrowserProfileProcesses {
    if (-not $BrowserProfileDir) { return @() }
    try {
        return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($BrowserProfileDir, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 } |
            ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
    } catch {
        return @()
    }
}

function Get-BrowserWindowProcesses {
    return @(Get-BrowserProfileProcesses | Where-Object { $_.MainWindowHandle -and $_.MainWindowHandle -ne 0 })
}

function Update-BrowserProcessIds {
    $profileProcesses = @(Get-BrowserProfileProcesses)
    if ($profileProcesses.Count -gt 0) {
        $script:BrowserProcessIds = @($profileProcesses | Select-Object -ExpandProperty Id)
    }
    $windowProcesses = @($profileProcesses | Where-Object { $_.MainWindowHandle -and $_.MainWindowHandle -ne 0 })
    if ($windowProcesses.Count -gt 0) {
        $script:BrowserWindowProcessIds = @($windowProcesses | Select-Object -ExpandProperty Id)
    }
    return $profileProcesses
}

function Wait-BrowserProfileProcesses {
    param([int]$Seconds = 10)

    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        $profileProcesses = @(Update-BrowserProcessIds)
        if ($profileProcesses.Count -gt 0) { return $profileProcesses }
        Start-Sleep -Milliseconds 250
    }
    return @(Update-BrowserProcessIds)
}

function Wait-BrowserWindowProcesses {
    param([int]$Seconds = 10)

    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        Update-BrowserProcessIds | Out-Null
        $windowProcesses = @(Get-BrowserWindowProcesses)
        if ($windowProcesses.Count -gt 0) {
            $script:BrowserWindowProcessIds = @($windowProcesses | Select-Object -ExpandProperty Id)
            return $windowProcesses
        }
        Start-Sleep -Milliseconds 250
    }
    Update-BrowserProcessIds | Out-Null
    return @(Get-BrowserWindowProcesses)
}

function Test-BrowserWindowClosed {
    if ($BrowserMonitorDisabled) { return $false }
    if (-not $BrowserProcess -and -not $BrowserProfileDir -and $BrowserProcessIds.Count -eq 0 -and $BrowserWindowProcessIds.Count -eq 0) { return $false }

    $profileProcesses = @(Update-BrowserProcessIds)
    $windowProcesses = @(Get-BrowserWindowProcesses)
    if ($windowProcesses.Count -gt 0) {
        $script:BrowserWindowProcessIds = @($windowProcesses | Select-Object -ExpandProperty Id)
        return $false
    }

    $knownWindowProcesses = @($BrowserWindowProcessIds | ForEach-Object {
        $process = Get-Process -Id $_ -ErrorAction SilentlyContinue
        if ($process -and $process.MainWindowHandle -and $process.MainWindowHandle -ne 0) { $process }
    })
    if ($knownWindowProcesses.Count -gt 0) { return $false }
    if ($BrowserWindowProcessIds.Count -gt 0) { return $true }

    $knownProcesses = @($BrowserProcessIds | ForEach-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
    if ($knownProcesses.Count -gt 0) { return $false }
    if ($BrowserProcessIds.Count -gt 0) { return $true }

    if ($BrowserProfileDir -and $BrowserStartedAt) {
        $elapsed = ((Get-Date) - $BrowserStartedAt).TotalSeconds
        if ($elapsed -lt 15 -and $profileProcesses.Count -gt 0) { return $false }
        if ($profileProcesses.Count -gt 0) { return $true }
    }

    if ($BrowserProcess -and $BrowserProcess.HasExited) {
        return $true
    }
    return $false
}

function Start-BrowserWindow {
    param([string]$Url)

    $browserExe = Find-BrowserExecutable
    if ($browserExe) {
        Write-Status "Opening dedicated browser window"
        $script:BrowserProfileDir = Join-Path ([System.IO.Path]::GetTempPath()) "Sentinel-Echo-Browser-$PID"
        $script:BrowserStartedAt = Get-Date
        New-Item -ItemType Directory -Path $script:BrowserProfileDir -Force | Out-Null
        $browserArgs = Join-ProcessArguments -Arguments @("--new-window", "--app=$Url", "--user-data-dir=$script:BrowserProfileDir", "--no-first-run", "--disable-background-mode")
        $process = Start-Process -FilePath $browserExe -ArgumentList $browserArgs -PassThru
        Wait-BrowserProfileProcesses -Seconds 10 | Out-Null
        Wait-BrowserWindowProcesses -Seconds 10 | Out-Null
        return $process
    }

    Write-Status "Opening default browser without close monitoring" "WARN"
    $script:BrowserMonitorDisabled = $true
    Start-Process $Url | Out-Null
    return $null
}

function Start-OwnedProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$StandardOutputPath,
        [string]$StandardErrorPath,
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
    if ($StandardOutputPath) {
        $startParams.RedirectStandardOutput = $StandardOutputPath
    }
    if ($StandardErrorPath) {
        $startParams.RedirectStandardError = $StandardErrorPath
    }
    if (-not $Visible) {
        $startParams.WindowStyle = "Hidden"
    }
    $process = Start-Process @startParams
    $OwnedProcesses.Add($process)
    return $process
}

function Get-PortOwnerProcess {
    param([int]$Port)
    try {
        $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $connection) { return $null }
        return Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)" -ErrorAction SilentlyContinue
    } catch {
        return $null
    }
}

function Start-BackendAndWait {
    param(
        [string]$PythonPath,
        [string]$ProjectRoot,
        [string]$BackendUrl,
        [int]$BackendPort,
        [string]$DesktopPath,
        [string]$FrontendOrigin
    )
    Write-Status "Starting backend on port $BackendPort"
    $backendOutLog = Join-Path $DesktopPath "Sentinel-Echo-Backend.out.log"
    $backendErrLog = Join-Path $DesktopPath "Sentinel-Echo-Backend.err.log"
    Remove-Item -LiteralPath $backendOutLog, $backendErrLog -ErrorAction SilentlyContinue
    $backendProcess = Start-OwnedProcess `
        -FilePath $PythonPath `
        -ArgumentList @("-m", "backend.run") `
        -WorkingDirectory $ProjectRoot `
        -StandardOutputPath $backendOutLog `
        -StandardErrorPath $backendErrLog
    if (-not (Wait-HttpOk -Url "$BackendUrl/api/health" -Seconds 90 -Process $backendProcess)) {
        if ($backendProcess.HasExited) {
            Write-Status "Backend process exited before health check completed. Exit code: $($backendProcess.ExitCode)" "ERROR"
        }
        Write-ProcessLogTail -Path $backendErrLog -Label "backend stderr"
        Write-ProcessLogTail -Path $backendOutLog -Label "backend stdout"
        throw "Backend did not become healthy at $BackendUrl/api/health."
    }
    if (-not (Test-BackendCorsOk -BackendUrl $BackendUrl -FrontendOrigin $FrontendOrigin)) {
        Write-ProcessLogTail -Path $backendErrLog -Label "backend stderr"
        Write-ProcessLogTail -Path $backendOutLog -Label "backend stdout"
        throw "Backend is healthy but does not allow frontend origin $FrontendOrigin."
    }
    Write-Status "Backend logs: $backendOutLog ; $backendErrLog"
    Write-Status "Backend is ready" "OK"
}

function Start-InstalledSentinelEcho {
    param(
        [string]$InstalledExe,
        [string]$BackendUrl,
        [int]$BackendPort,
        [string]$DataDir
    )

    Ensure-InstalledRuntimeDependencies
    if (Test-PortOpen -Port $BackendPort) {
        if (Test-HttpOk -Url "$BackendUrl/api/health") {
            Write-Status "Sentinel Echo is already running on port $BackendPort" "OK"
            return
        }
        throw "Backend port $BackendPort is already in use by another service."
    }

    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    Set-DefaultEnvValue -Name "HOST" -Value "127.0.0.1"
    $env:PORT = "$BackendPort"
    Set-DefaultEnvValue -Name "USE_SQLITE" -Value "true"
    $env:DATABASE_PATH = Join-Path $DataDir "sentinel-echo.sqlite3"
    $env:ALLOWED_ORIGINS = "http://localhost:$BackendPort,http://127.0.0.1:$BackendPort"
    $env:BROWSER = "none"

    Write-Status "Starting packaged SentinelEcho.exe on port $BackendPort"
    Start-OwnedProcess -FilePath $InstalledExe -ArgumentList @() -WorkingDirectory $ProjectRoot | Out-Null
    if (-not (Wait-HttpOk -Url "$BackendUrl/api/health" -Seconds 90)) {
        throw "Packaged backend did not become healthy at $BackendUrl/api/health."
    }
    Write-Status "Packaged backend is ready" "OK"
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

function Start-LauncherShutdownWatchdog {
    if ($script:LauncherWatchdogProcess -and -not $script:LauncherWatchdogProcess.HasExited) { return }

    $watchdogName = "Sentinel-Echo-Watchdog-$PID"
    $script:LauncherWatchdogStopFile = Join-Path ([System.IO.Path]::GetTempPath()) "$watchdogName.stop"
    $script:LauncherWatchdogScriptFile = Join-Path ([System.IO.Path]::GetTempPath()) "$watchdogName.ps1"
    if (Test-Path -LiteralPath $script:LauncherWatchdogStopFile) {
        Remove-Item -LiteralPath $script:LauncherWatchdogStopFile -Force -ErrorAction SilentlyContinue
    }

    $watchdogScript = @'
param(
    [int]$ParentProcessId,
    [string]$BrowserProfileDir,
    [string]$OwnedProcessIds,
    [string]$StopFile,
    [string]$LogFile
)

function Write-WatchdogLog {
    param([string]$Message)
    if (-not $LogFile) { return }
    try {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
        Add-Content -Path $LogFile -Value "$timestamp [WATCHDOG] $Message" -Encoding UTF8
    } catch {
    }
}

function Get-ProfileProcesses {
    if (-not $BrowserProfileDir) { return @() }
    try {
        return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($BrowserProfileDir, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 } |
            ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
    } catch {
        return @()
    }
}

function Stop-ProcessTreeById {
    param([int]$ProcessId)
    try {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue)
        foreach ($child in $children) {
            Stop-ProcessTreeById -ProcessId $child.ProcessId
        }
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    } catch {
    }
}

try {
    while ($true) {
        if ($StopFile -and (Test-Path -LiteralPath $StopFile)) { exit 0 }
        $parent = Get-Process -Id $ParentProcessId -ErrorAction SilentlyContinue
        if (-not $parent) { break }
        Start-Sleep -Seconds 1
    }

    Write-WatchdogLog "Launcher process $ParentProcessId ended; closing browser and owned processes"
    $profileProcesses = @(Get-ProfileProcesses)
    foreach ($process in $profileProcesses) {
        try { $process.CloseMainWindow() | Out-Null } catch {}
    }
    Start-Sleep -Milliseconds 750
    foreach ($process in $profileProcesses) {
        Stop-ProcessTreeById -ProcessId $process.Id
    }

    foreach ($idText in @($OwnedProcessIds -split ",")) {
        if (-not $idText) { continue }
        $id = 0
        if ([int]::TryParse($idText, [ref]$id)) {
            Stop-ProcessTreeById -ProcessId $id
        }
    }

    if ($BrowserProfileDir -and (Test-Path -LiteralPath $BrowserProfileDir)) {
        Remove-Item -LiteralPath $BrowserProfileDir -Recurse -Force -ErrorAction SilentlyContinue
    }
} catch {
    Write-WatchdogLog $_.Exception.Message
}
'@

    Set-Content -Path $script:LauncherWatchdogScriptFile -Value $watchdogScript -Encoding UTF8
    $ownedIds = @($OwnedProcesses | ForEach-Object { $_.Id }) -join ","
    $watchdogArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $script:LauncherWatchdogScriptFile,
        "-ParentProcessId", "$PID",
        "-BrowserProfileDir", "$BrowserProfileDir",
        "-OwnedProcessIds", $ownedIds,
        "-StopFile", $script:LauncherWatchdogStopFile,
        "-LogFile", $LogFile
    )
    $script:LauncherWatchdogProcess = Start-Process -FilePath "powershell.exe" -ArgumentList (Join-ProcessArguments -Arguments $watchdogArgs) -WindowStyle Hidden -PassThru
}

function Stop-LauncherShutdownWatchdog {
    if ($script:LauncherWatchdogStopFile) {
        New-Item -ItemType File -Path $script:LauncherWatchdogStopFile -Force -ErrorAction SilentlyContinue | Out-Null
    }
    if ($script:LauncherWatchdogProcess -and -not $script:LauncherWatchdogProcess.HasExited) {
        try {
            $script:LauncherWatchdogProcess.WaitForExit(2000) | Out-Null
            if (-not $script:LauncherWatchdogProcess.HasExited) {
                Stop-Process -Id $script:LauncherWatchdogProcess.Id -Force -ErrorAction SilentlyContinue
            }
        } catch {
        }
    }
    if ($script:LauncherWatchdogScriptFile -and (Test-Path -LiteralPath $script:LauncherWatchdogScriptFile)) {
        Remove-Item -LiteralPath $script:LauncherWatchdogScriptFile -Force -ErrorAction SilentlyContinue
    }
    if ($script:LauncherWatchdogStopFile -and (Test-Path -LiteralPath $script:LauncherWatchdogStopFile)) {
        Remove-Item -LiteralPath $script:LauncherWatchdogStopFile -Force -ErrorAction SilentlyContinue
    }
}

function Stop-BrowserWindow {
    $profileProcesses = @(Get-BrowserProfileProcesses)
    try {
        foreach ($current in $profileProcesses) {
            Write-Status "Closing browser window ($($current.Id))" "INFO"
            $current.CloseMainWindow() | Out-Null
        }
        Start-Sleep -Milliseconds 500
        foreach ($current in $profileProcesses) {
            $remaining = Get-Process -Id $current.Id -ErrorAction SilentlyContinue
            if ($remaining) {
                Stop-Process -Id $remaining.Id -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
    }

    if ($profileProcesses.Count -eq 0 -and $BrowserProcess) {
        try {
            $current = Get-Process -Id $BrowserProcess.Id -ErrorAction SilentlyContinue
            if ($current) {
                Write-Status "Closing browser window ($($current.Id))" "INFO"
                $current.CloseMainWindow() | Out-Null
                Start-Sleep -Milliseconds 500
                $current = Get-Process -Id $BrowserProcess.Id -ErrorAction SilentlyContinue
                if ($current) {
                    Stop-Process -Id $current.Id -Force -ErrorAction SilentlyContinue
                }
            }
        } catch {
        }
    }

    if ($BrowserProfileDir -and (Test-Path -LiteralPath $BrowserProfileDir)) {
        try { Remove-Item -LiteralPath $BrowserProfileDir -Recurse -Force -ErrorAction SilentlyContinue } catch {}
    }
}

function Invoke-LauncherCleanup {
    if ($script:ShutdownStarted) { return }
    $script:ShutdownStarted = $true
    Stop-LauncherShutdownWatchdog
    Stop-BrowserWindow
    Stop-OwnedProcesses
}

function Register-LauncherShutdownHandlers {
    try {
        $script:CleanupEventSubscription = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
            Invoke-LauncherCleanup
        }
    } catch {
    }

    try {
        $script:CancelKeyPressHandler = [ConsoleCancelEventHandler]{
            param($sender, $eventArgs)
            $eventArgs.Cancel = $true
            Write-Status "Shutdown requested; stopping Sentinel Echo" "WARN"
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
    $browserArgs = Join-ProcessArguments -Arguments @("--user-data-dir=C:\Users\Lite OS\AppData\Local\Temp\Sentinel-Echo-Browser-1234")
    if (-not $browserArgs.Contains('"--user-data-dir=C:\Users\Lite OS\AppData\Local\Temp\Sentinel-Echo-Browser-1234"')) {
        throw "Browser argument smoke test failed."
    }
    Write-Status "Launcher smoke test passed" "OK"
    exit 0
}

Register-LauncherShutdownHandlers

try {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Sentinel Echo" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Status "Project root: $ProjectRoot"
    Write-Status "Launcher log: $LogFile"
    Import-LauncherEnvFile -Path (Join-Path $ProjectRoot ".env.local")

    $installedExe = Join-Path $ProjectRoot "SentinelEcho.exe"
    if (Test-Path -LiteralPath $installedExe) {
        Write-Host "  Sentinel Echo - Installed App" -ForegroundColor Cyan
        $backendUrl = "http://127.0.0.1:$BackendPort"
        $frontendUrl = "$backendUrl/app/"
        $dataDir = Join-Path $ProjectRoot "data"
        Start-InstalledSentinelEcho `
            -InstalledExe $installedExe `
            -BackendUrl $backendUrl `
            -BackendPort $BackendPort `
            -DataDir $dataDir

        if (-not $NoBrowser) {
            $BrowserProcess = Start-BrowserWindow -Url $frontendUrl
        }
        Start-LauncherShutdownWatchdog

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
            if (Test-BrowserWindowClosed) {
                Write-Status "Browser window closed; shutting down Sentinel Echo" "OK"
                break
            }
            Start-Sleep -Seconds 1
        }
        exit 0
    }

    function Start-SourceSentinelEcho {
        Write-Status "Starting Sentinel Echo - Local Source"
    }
    Start-SourceSentinelEcho

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

    Set-DefaultEnvValue -Name "HOST" -Value "127.0.0.1"
    $env:PORT = "$BackendPort"
    Set-DefaultEnvValue -Name "USE_SQLITE" -Value "true"
    if (-not $env:DATABASE_PATH) {
        $env:DATABASE_PATH = Join-Path $dataDir "sentinel-echo.sqlite3"
    }
    $env:EXPO_PUBLIC_BACKEND_URL = $backendUrl
    $env:ALLOWED_ORIGINS = "http://localhost:$FrontendPort,http://127.0.0.1:$FrontendPort"
    $env:BROWSER = "none"

    $frontendOrigin = "http://127.0.0.1:$FrontendPort"
    if (Test-PortOpen -Port $BackendPort) {
        if ((Test-HttpOk -Url "$backendUrl/api/health") -and (Test-BackendCorsOk -BackendUrl $backendUrl -FrontendOrigin $frontendOrigin)) {
            Write-Status "Backend port $BackendPort is already open and compatible" "WARN"
        } else {
            $owner = Get-PortOwnerProcess -Port $BackendPort
            if ($owner -and $owner.CommandLine -match "backend\.run|backend\.server") {
                Write-Status "Stopping stale backend on port $BackendPort (PID $($owner.ProcessId))" "WARN"
                Stop-ProcessTree -ProcessId $owner.ProcessId
                Start-Sleep -Seconds 2
                if (Test-PortOpen -Port $BackendPort) {
                    throw "Backend port $BackendPort is still open after stopping stale backend."
                }
                Start-BackendAndWait `
                    -PythonPath $venvPython `
                    -ProjectRoot $ProjectRoot `
                    -BackendUrl $backendUrl `
                    -BackendPort $BackendPort `
                    -DesktopPath $DesktopPath `
                    -FrontendOrigin $frontendOrigin
            } else {
                $ownerText = if ($owner) { "PID $($owner.ProcessId): $($owner.CommandLine)" } else { "unknown process" }
                throw "Backend port $BackendPort is in use by $ownerText, but it is not compatible with this launcher."
            }
        }
    } else {
        Start-BackendAndWait `
            -PythonPath $venvPython `
            -ProjectRoot $ProjectRoot `
            -BackendUrl $backendUrl `
            -BackendPort $BackendPort `
            -DesktopPath $DesktopPath `
            -FrontendOrigin $frontendOrigin
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
        $BrowserProcess = Start-BrowserWindow -Url $frontendUrl
    }
    Start-LauncherShutdownWatchdog

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
        if (Test-BrowserWindowClosed) {
            Write-Status "Browser window closed; shutting down Sentinel Echo" "OK"
            break
        }
        Start-Sleep -Seconds 1
    }
} catch {
    Write-Status $_.Exception.Message "ERROR"
    exit 1
} finally {
    Invoke-LauncherCleanup
}
