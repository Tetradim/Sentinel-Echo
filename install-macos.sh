#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Consolidation Discord Options Bot"
DESKTOP_COMMAND_NAME="Consolidation Discord Bot.command"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"
LOG_FILE="${HOME}/Desktop/Consolidation-Discord-Bot.log"
BACKEND_PORT=8003
FRONTEND_PORT=3003
INSTALL_DEPS=0
NO_BROWSER=0
LAUNCH=0
PREPARE_ONLY=0

usage() {
  cat <<USAGE
Usage:
  ./install-macos.sh                 Install dependencies and create a Desktop launcher
  ./install-macos.sh --launch        Start ${APP_NAME}

Options:
  --backend-port PORT    FastAPI backend port (default: ${BACKEND_PORT})
  --frontend-port PORT   Expo web frontend port (default: ${FRONTEND_PORT})
  --install-deps         Reinstall Python and npm dependencies before launch
  --no-browser           Do not open the browser automatically
  --prepare-only         Install dependencies without starting the app
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --launch) LAUNCH=1 ;;
    --install-deps) INSTALL_DEPS=1 ;;
    --no-browser) NO_BROWSER=1 ;;
    --prepare-only) PREPARE_ONLY=1 ;;
    --backend-port)
      BACKEND_PORT="${2:?Missing value for --backend-port}"
      shift
      ;;
    --backend-port=*) BACKEND_PORT="${1#*=}" ;;
    --frontend-port)
      FRONTEND_PORT="${2:?Missing value for --frontend-port}"
      shift
      ;;
    --frontend-port=*) FRONTEND_PORT="${1#*=}" ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
  shift
done

log() {
  mkdir -p "$(dirname "$LOG_FILE")"
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

require_macos() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This installer is intended for macOS." >&2
    exit 1
  fi
}

find_python() {
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
    then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

require_node() {
  command -v node >/dev/null 2>&1 || {
    echo "Node.js is required. Install Node.js 20+ from https://nodejs.org/ or Homebrew." >&2
    exit 1
  }
  command -v npm >/dev/null 2>&1 || {
    echo "npm is required with Node.js." >&2
    exit 1
  }
}

prepare_runtime() {
  local python_bin
  python_bin="$(find_python)" || {
    echo "Python 3.11+ is required." >&2
    exit 1
  }
  require_node

  local venv_dir="${BACKEND_DIR}/.venv"
  local venv_python="${venv_dir}/bin/python"
  if [[ ! -x "$venv_python" ]]; then
    log "Creating backend virtual environment"
    "$python_bin" -m venv "$venv_dir"
    INSTALL_DEPS=1
  fi

  if [[ "$INSTALL_DEPS" -eq 1 || ! -d "${venv_dir}/lib" ]]; then
    log "Installing backend dependencies"
    "$venv_python" -m pip install --upgrade pip
    "$venv_python" -m pip install -r "${BACKEND_DIR}/requirements.txt"
  fi

  if [[ "$INSTALL_DEPS" -eq 1 || ! -d "${FRONTEND_DIR}/node_modules" ]]; then
    log "Installing frontend dependencies"
    (cd "$FRONTEND_DIR" && npm install)
  fi
}

create_desktop_launcher() {
  local desktop_dir="${HOME}/Desktop"
  local command_path="${desktop_dir}/${DESKTOP_COMMAND_NAME}"
  mkdir -p "$desktop_dir"
  cat > "$command_path" <<EOF
#!/usr/bin/env bash
cd "$ROOT_DIR"
exec "$ROOT_DIR/install-macos.sh" --launch
EOF
  chmod +x "$command_path"
  log "Desktop launcher created: ${command_path}"
}

wait_url() {
  local url="$1"
  local seconds="${2:-60}"
  local start
  start="$(date +%s)"
  while (( "$(date +%s)" - start < seconds )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

launch_app() {
  prepare_runtime
  if [[ "$PREPARE_ONLY" -eq 1 ]]; then
    log "Preparation complete"
    return 0
  fi

  local backend_url="http://127.0.0.1:${BACKEND_PORT}"
  local frontend_url="http://127.0.0.1:${FRONTEND_PORT}"
  local db_path="${ROOT_DIR}/data/consolidation.sqlite3"
  local venv_python="${BACKEND_DIR}/.venv/bin/python"
  local pids=()

  mkdir -p "$(dirname "$db_path")"

  log "Starting backend on ${backend_url}"
  (
    cd "$ROOT_DIR"
    HOST=127.0.0.1 \
    PORT="$BACKEND_PORT" \
    USE_SQLITE=true \
    DATABASE_PATH="$db_path" \
    FRONTEND_URL="$frontend_url" \
    "$venv_python" -m backend.run
  ) >> "$LOG_FILE" 2>&1 &
  pids+=("$!")

  log "Starting Expo web frontend on ${frontend_url}"
  (cd "$FRONTEND_DIR" && EXPO_PUBLIC_BACKEND_URL="$backend_url" npm run web -- --port "$FRONTEND_PORT") >> "$LOG_FILE" 2>&1 &
  pids+=("$!")

  cleanup() {
    for pid in "${pids[@]}"; do
      kill "$pid" >/dev/null 2>&1 || true
    done
  }
  trap cleanup EXIT INT TERM

  if ! wait_url "${backend_url}/api/health" 90; then
    log "Backend did not become healthy. Recent log output:"
    tail -n 100 "$LOG_FILE" || true
    exit 1
  fi
  if ! wait_url "$frontend_url" 90; then
    log "Frontend did not become ready. Recent log output:"
    tail -n 100 "$LOG_FILE" || true
    exit 1
  fi

  log "Ready: ${frontend_url}"
  if [[ "$NO_BROWSER" -eq 0 ]]; then
    open "$frontend_url"
  fi
  wait "${pids[@]}"
}

require_macos
if [[ "$LAUNCH" -eq 1 ]]; then
  launch_app
else
  INSTALL_DEPS=1
  PREPARE_ONLY=1
  prepare_runtime
  create_desktop_launcher
  log "Install complete. Double-click '${DESKTOP_COMMAND_NAME}' on the Desktop to start ${APP_NAME}."
fi
