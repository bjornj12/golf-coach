#!/bin/bash
# Headless refresh of the Trackman token using the persisted browser session.
# Run on a schedule (launchd/cron). If the saved portal session has expired, this
# fails and you must run a headed `golf-coach login` once to re-establish it.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="${GOLF_COACH_CACHE_DIR:-$HOME/.golf-coach}"
LOG="$LOG_DIR/refresh.log"

# launchd/cron run with a minimal PATH; make sure uv (and tools) are found across
# common install locations (Homebrew arm/intel, ~/.local/bin, ~/.cargo/bin).
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
echo "[$(ts)] refresh start (project: $PROJECT_DIR)" >> "$LOG"

cd "$PROJECT_DIR" || { echo "[$(ts)] FAILED: cannot cd to $PROJECT_DIR" >> "$LOG"; exit 1; }

if uv run golf-coach login --headless >> "$LOG" 2>&1; then
  echo "[$(ts)] refresh OK" >> "$LOG"
  exit 0
else
  echo "[$(ts)] refresh FAILED — run a headed 'golf-coach login' to re-establish the session" >> "$LOG"
  exit 1
fi
