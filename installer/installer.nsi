# Trading Bot Windows Installer Script
# Uses NSIS (Nullsoft Scriptable Install System)
# Run with: makensis installer.nsi

# ============================================================
# General Settings
# ============================================================
!define PRODUCT_NAME "Trading Bot"
!define PRODUCT_VERSION "1.0.0"
!define PRODUCT_PUBLISHER "Trading Bot"
!define PRODUCT_WEB_SITE "https://github.com/Tetradim/Sentinel-Echo"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\tradebot.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"

# Modern UI
!include "MUI2.nsh"

# MUI Settings
!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

# Welcome page
!insertmacro MUI_PAGE_WELCOME

# Directory page
!insertmacro MUI_PAGE_DIRECTORY

# Instfiles page
!insertmacro MUI_PAGE_INSTFILES

# Finish page
!define MUI_FINISHPAGE_RUN "$INSTDIR\start_tradebot.bat"
!define MUI_FINISHPAGE_RUN_TEXT "Start Trading Bot"
!insertmacro MUI_PAGE_FINISH

# Uninstaller pages
!insertmacro MUI_UNPAGE_INSTFILES

# Language files
!insertmacro MUI_LANGUAGE "English"

# ============================================================
# Installer Attributes
# ============================================================
Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "TradeBot-Setup-${PRODUCT_VERSION}.exe"
InstallDir "$PROGRAMFILES64\Trading Bot"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
ShowInstDetails show
ShowUnInstDetails show
RequestExecutionLevel admin

# ============================================================
# Installer Sections
# ============================================================
Section "MainSection" SEC01
    SetOutPath "$INSTDIR"
    SetOverwrite on

    # Copy all files
    File /r "publish\*.*"
    
    # Create data directories
    CreateDirectory "$INSTDIR\data"
    CreateDirectory "$INSTDIR\logs"
    CreateDirectory "$INSTDIR\config"

    # Create start script
    FileOpen $0 "$INSTDIR\start_tradebot.bat" w
    FileWrite $0 "@echo off$\r$\n"
    FileWrite $0 "echo Starting Trading Bot...$\r$\n"
    FileWrite $0 "cd /d "$INSTDIR"$\r$\n"
    FileWrite $0 "docker-compose up -d$\r$\n"
    FileWrite $0 "echo Trading Bot started!$\r$\n"
    FileWrite $0 "echo Open browser to http://localhost$\r$\n"
    FileWrite $0 "pause$\r$\n"
    FileClose $0

    # Create stop script
    FileOpen $0 "$INSTDIR\stop_tradebot.bat" w
    FileWrite $0 "@echo off$\r$\n"
    FileWrite $0 "echo Stopping Trading Bot...$\r$\n"
    FileWrite $0 "cd /d "$INSTDIR"$\r$\n"
    FileWrite $0 "docker-compose down$\r$\n"
    FileWrite $0 "pause$\r$\n"
    FileClose $0

    # Create config environment file
    FileOpen $0 "$INSTDIR\.env" w
    FileWrite $0 "# Trading Bot Environment Configuration$\r$\n"
    FileWrite $0 "# Edit these values before starting the bot$\r$\n"
    FileWrite $0 "$\r$\n"
    FileWrite $0 "# Discord Bot Token (required)$\r$\n"
    FileWrite $0 "DISCORD_BOT_TOKEN=your-discord-bot-token-here$\r$\n"
    FileWrite $0 "$\r$\n"
    FileWrite $0 "# Discord Channel IDs (comma separated)$$\r$\n"
    FileWrite $0 "DISCORD_CHANNEL_IDS=123456789$\r$\n"
    FileWrite $0 "$\r$\n"
    FileWrite $0 "# Database$\r$\n"
    FileWrite $0 "MONGO_USER=tradebot$\r$\n"
    FileWrite $0 "MONGO_PASSWORD=tradebot123$\r$\n"
    FileWrite $0 "DB_NAME=tradebot$\r$\n"
    FileWrite $0 "$\r$\n"
    FileWrite $0 "# Broker Settings (choose one or more)$\r$\n"
    FileWrite $0 "# IBKR$\r$\n"
    FileWrite $0 "IBKR_GATEWAY_URL=https://localhost:5000$\r$\n"
    FileWrite $0 "IBKR_ACCOUNT_ID=your-account-id$\r$\n"
    FileWrite $0 "$\r$\n"
    FileWrite $0 "# Alpaca$\r$\n"
    FileWrite $0 "ALPACA_API_KEY=your-alpaca-key$\r$\n"
    FileWrite $0 "ALPACA_API_SECRET=your-alpaca-secret$\r$\n"
    FileWrite $0 "ALPACA_PAPER=true$\r$\n"
    FileWrite $0 "$\r$\n"
    FileWrite $0 "# Security$\r$\n"
    FileWrite $0 "SECRET_KEY=change-this-to-random-string$\r$\n"
    FileWrite $0 "$\r$\n"
    FileWrite $0 "# Debug Mode$\r$\n"
    FileWrite $0 "DEBUG=false$\r$\n"
    FileClose $0

    # Create Windows shortcuts
    CreateDirectory "$SMPROGRAMS\Trading Bot"
    CreateShortCut "$SMPROGRAMS\Trading Bot\Start Trading Bot.lnk" "$INSTDIR\start_tradebot.bat"
    CreateShortCut "$SMPROGRAMS\Trading Bot\Stop Trading Bot.lnk" "$INSTDIR\stop_tradebot.bat"
    CreateShortCut "$SMPROGRAMS\Trading Bot\Configuration.lnk" "$INSTDIR\.env"
    CreateShortCut "$SMPROGRAMS\Trading Bot\Uninstall.lnk" "$INSTDIR\uninst.exe"
    CreateShortCut "$DESKTOP\Trading Bot.lnk" "$INSTDIR\start_tradebot.bat"

SectionEnd

# ============================================================
# Section Descriptions
# ============================================================
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC01} "Install Trading Bot application files"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

# ============================================================
# Uninstaller Section
# ============================================================
Section "Uninstall"
    # Stop docker containers
    ExecWait 'docker-compose down'

    # Remove files
    RMDir /r "$INSTDIR"

    # Remove shortcuts
    Delete "$SMPROGRAMS\Trading Bot\Start Trading Bot.lnk"
    Delete "$SMPROGRAMS\Trading Bot\Stop Trading Bot.lnk"
    Delete "$SMPROGRAMS\Trading Bot\Configuration.lnk"
    Delete "$SMPROGRAMS\Trading Bot\Uninstall.lnk"
    RMDir "$SMPROGRAMS\Trading Bot"
    Delete "$DESKTOP\Trading Bot.lnk"

    # Remove registry keys
    DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"
    DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"

    # Optionally remove Docker data (ask user)
    MessageBox MB_YESNO "Remove all trading data and Docker volumes?" IDNO skip_data
        ExecWait 'docker-compose down -v'
        RMDir /r "$APPDATA\tradebot"
    skip_data:

SectionEnd

# ============================================================
# Installer Functions
# ============================================================
Function .onInit
    # Check for Docker
    nsis_exec::execToLog 'docker --version'
    Pop $0
    StrCmp $0 "0" docker_ok
    
    MessageBox MB_OK|MB_ICONEXCLAMATION "Docker is required but not installed.$\r$\n$\r$\nPlease install Docker Desktop from https://docker.com"
    Abort
    
    docker_ok:

FunctionEnd

# ============================================================
# Uninstaller Functions
# ============================================================
Function un.onInit
    MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 "Are you sure you want to uninstall Trading Bot?" IDYES +2
    Abort
FunctionEnd

Function un.onUninstSuccess
    HideWindow
    MessageBox MB_ICONINFORMATION|MB_OK "Trading Bot was successfully removed from your computer."
FunctionEnd