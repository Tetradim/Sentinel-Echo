# One Closes The Other Lifecycle

Status: reusable launcher feature pattern, inspected from Sentinel Pulse on 2026-06-22 and implemented in Sentinel Echo on 2026-06-22.

Source implementation:

- `C:\Users\Lite OS\Documents\Codex\2026-05-22\based-on-my-analysis-of-the\Sentinel-Pulse-branch-audit\Launch-Sentinel-Pulse.ps1`
- `C:\Users\Lite OS\Documents\Codex\2026-05-22\based-on-my-analysis-of-the\Sentinel-Pulse-branch-audit\Launch-Sentinel-Pulse-Local.ps1`
- `C:\Users\Lite OS\Documents\Codex\2026-05-22\based-on-my-analysis-of-the\Sentinel-Pulse-branch-audit\backend\tests\test_launcher_sentinel_echo_static.py`
- Sentinel Pulse README sections: `v1.0.5 - Local Launcher Lifecycle Alignment` and `Local Launcher Lifecycle`

## Purpose

"One closes the other" means the local operator UI and its launcher-owned process stack share one lifecycle. If the dedicated browser window is closed, the launcher shuts down the bot services it started. If the launcher window or `cmd.exe`/PowerShell host is closed, the dedicated browser profile and owned service process trees are closed.

The goal is to prevent beta testers and operators from leaving stale backend servers, frontend dev servers, MongoDB instances, browser app windows, and occupied ports running after they believe the bot is stopped.

This is process lifecycle functionality. It is not an options trading OCO order feature.

## Behavior Contract

A bot launcher that implements this feature should provide these guarantees:

- Starting the launcher creates a single lifecycle group for the launcher, backend, frontend, optional local database, browser app window, and watchdog.
- Every child service process started by the launcher is recorded in an owned-process list.
- The browser is opened as a dedicated Edge/Chrome app window using a temporary `--user-data-dir`, not the user's normal browser profile.
- The launcher records browser profile processes and visible browser window process IDs.
- Closing the dedicated browser window causes the foreground launcher loop to cleanly shut down all launcher-owned services.
- Pressing Ctrl+C or closing the launcher host triggers cleanup of the browser window and all owned process trees.
- If the launcher process disappears unexpectedly, a hidden watchdog process closes the browser profile and owned processes.
- Cleanup is idempotent so duplicate shutdown signals do not race or fail noisily.
- Temporary watchdog scripts, stop files, and browser profile directories are removed during cleanup.

## Sentinel Pulse Mechanism

Sentinel Pulse implements the pattern with these moving parts:

- `$OwnedProcesses`: stores every service process returned by `Start-OwnedProcess`.
- `Start-OwnedProcess`: wraps `Start-Process -PassThru`, applies hidden window style by default, and records the process handle.
- `Stop-ProcessTree`: recursively stops children found with `Win32_Process` before stopping the parent PID.
- `Stop-OwnedProcesses`: walks `$OwnedProcesses` in reverse order and stops each process tree.
- `Start-BrowserWindow`: finds Edge or Chrome, creates a temp profile directory, launches `--new-window --app=<url> --user-data-dir=<temp-profile> --no-first-run --disable-background-mode`, then records profile/window PIDs.
- `Get-BrowserProfileProcesses`, `Get-BrowserWindowProcesses`, `Update-BrowserProcessIds`, `Wait-BrowserProfileProcesses`, and `Wait-BrowserWindowProcesses`: identify the dedicated browser tree by temp profile directory and visible window handles.
- `Test-BrowserWindowClosed`: detects that the previously observed dedicated browser window is gone and returns true to trigger shutdown.
- `Stop-BrowserWindow`: closes the dedicated browser profile processes with `CloseMainWindow()`, then force-stops leftovers and removes the temp profile.
- `Register-LauncherShutdownHandlers`: hooks `PowerShell.Exiting` and `[Console]::CancelKeyPress` into `Invoke-LauncherCleanup`.
- `Start-LauncherShutdownWatchdog`: writes a temporary watchdog PowerShell script and starts it hidden. The watchdog watches the parent launcher PID, then closes browser/profile processes and owned service PIDs if the parent exits without normal cleanup.
- `Invoke-LauncherCleanup`: guarded by `$ShutdownStarted`, stops the watchdog, closes the browser window, stops owned process trees, and ends transcript logging.
- Foreground loop: checks every owned process for unexpected exit and calls `Test-BrowserWindowClosed` once per second. Browser close breaks the loop and enters `finally`.
- `finally { Invoke-LauncherCleanup }`: ensures normal failures and browser-close exits still clean up.

## Copy Checklist

When inserting this feature into another bot launcher:

1. Define launcher-owned ports and health checks before starting services.
2. Replace direct service `Start-Process` calls with `Start-OwnedProcess`.
3. Track only processes launched by the current launcher, except explicitly validated stale port owners for the same bot.
4. Add browser state variables: `$BrowserProcess`, `$BrowserProfileDir`, `$BrowserProcessIds`, `$BrowserWindowProcessIds`, `$BrowserStartedAt`, and `$BrowserMonitorDisabled`.
5. Add dedicated browser helpers from Sentinel Pulse: browser executable discovery, profile-process lookup, visible-window lookup, browser start, browser-close detection, and browser cleanup.
6. Open the UI with a dedicated temp browser profile and `--app=<url>` so the launcher can distinguish bot UI processes from personal browser windows.
7. Add shutdown state variables and handlers: `$ShutdownStarted`, `$CleanupEventSubscription`, and `$CancelKeyPressHandler`.
8. Add hidden watchdog state: `$LauncherWatchdogProcess`, `$LauncherWatchdogStopFile`, and `$LauncherWatchdogScriptFile`.
9. Start the watchdog after all owned processes are started and the browser profile path is known.
10. Stop the watchdog first during normal cleanup so it does not fight the foreground cleanup path.
11. Extend the foreground loop to fail fast if an owned process exits unexpectedly and to break if `Test-BrowserWindowClosed` returns true.
12. Put `Invoke-LauncherCleanup` in a `finally` block.
13. Add static tests that assert the launcher contains browser tracking, visible-window close detection, console shutdown cleanup, external watchdog cleanup, process-tree stopping, and process-argument quoting.

## Safety Boundaries

- Do not broadly kill all `chrome`, `msedge`, `node`, `python`, or `powershell` processes.
- Do not close a user's normal browser profile. Only close the dedicated profile created by this launcher.
- Do not kill unrelated services on a port unless the launcher has verified they belong to the same bot and are safe to replace.
- Preserve explicit flags such as `-NoBrowser` so headless runs do not require browser monitoring.
- Keep live trading disabled by default. Launcher lifecycle cleanup is separate from broker/source arming.
- Log every cleanup action with PID and label so beta testers can report what stopped.

## Sentinel Echo Insertion Notes

`Launch-Sentinel-Echo.ps1` now implements this pattern for the Sentinel Echo operator UI:

- `$OwnedProcesses`
- `Start-OwnedProcess`
- `Stop-ProcessTree`
- `Stop-OwnedProcesses`
- dedicated Edge/Chrome app-window launch with a temporary profile
- browser process/window PID tracking
- browser-close detection that shuts down launcher-owned services
- `Stop-BrowserWindow`
- hidden parent-process watchdog for unexpected launcher host exit
- `Invoke-LauncherCleanup`
- `Register-LauncherShutdownHandlers`
- foreground loop checking owned-process exits
- foreground loop checking dedicated browser-window closure
- `finally { Invoke-LauncherCleanup }`

Regression coverage:

- `backend/tests/test_launcher_lifecycle_static.py`

The launcher preserves `-NoBrowser` for headless runs. When a supported browser executable is available, it opens `http://127.0.0.1:$FrontendPort` in a dedicated app window. Closing that app window logs `Browser window closed; shutting down Sentinel Echo` and enters normal cleanup. Closing the launcher host or pressing Ctrl+C closes the dedicated browser profile and stops the owned backend/frontend process trees.

## Acceptance Tests To Copy

Minimum static checks for a Windows launcher:

- Launcher defines browser tracking state variables.
- Launcher starts Edge/Chrome with `--app=<url>` and `--user-data-dir=<temp-profile>`.
- Launcher records profile processes and visible browser window processes.
- Launcher detects visible browser window close and logs a bot-specific shutdown message.
- Launcher registers `PowerShell.Exiting` and `[Console]::CancelKeyPress` handlers.
- Launcher starts a hidden watchdog PowerShell process.
- Watchdog receives parent PID, browser profile path, owned process IDs, stop file, and log file.
- Cleanup stops watchdog, browser profile processes, owned process trees, and temporary files.
- `-NoBrowser` disables browser launch and browser-close monitoring.
- Process arguments with paths containing spaces are quoted correctly.
