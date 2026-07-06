#!/bin/bash
# Install (or remove) a recurring schedule that runs refresh-token.sh, keeping the
# Trackman token fresh without manual logins. Portable across machines/users:
# paths are derived at install time, not hardcoded.
#
#   scripts/install-refresh-schedule.sh            # install
#   scripts/install-refresh-schedule.sh uninstall  # remove
#   scripts/install-refresh-schedule.sh dry-run    # show what would be installed
#
# Schedule: twice a week (Mon & Thu, 09:00) — comfortable margin on the ~7-day
# token. macOS uses a launchd LaunchAgent; Linux uses the user crontab.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REFRESH="$SCRIPT_DIR/refresh-token.sh"
LABEL="com.golf-coach.refresh"
ACTION="${1:-install}"
OS="$(uname -s)"
LOG_DIR="${GOLF_COACH_CACHE_DIR:-$HOME/.golf-coach}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

chmod +x "$REFRESH" 2>/dev/null || true

plist_body() {
  cat <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$REFRESH</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>StandardOutPath</key><string>$LOG_DIR/refresh.launchd.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/refresh.launchd.log</string>
</dict>
</plist>
PLIST
}

install_macos() {
  mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
  plist_body > "$PLIST"
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load -w "$PLIST"
  echo "✓ launchd agent installed: $PLIST (Mon & Thu 09:00)"
}

cron_entry() { echo "0 9 * * 1,4 \"$REFRESH\" >> \"$LOG_DIR/refresh.cron.log\" 2>&1"; }

dry_run() {
  echo "DRY RUN — nothing installed. OS: $OS"
  echo "Refresh script: $REFRESH"
  if [ "$OS" = "Darwin" ]; then
    local tmp; tmp="$(mktemp)"
    plist_body > "$tmp"
    echo "--- launchd plist that would be written to $PLIST ---"
    cat "$tmp"
    if command -v plutil >/dev/null 2>&1; then plutil -lint "$tmp"; fi
    rm -f "$tmp"
  else
    echo "--- crontab line that would be added ---"
    cron_entry
  fi
}

uninstall_macos() {
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "✓ launchd agent removed"
}

install_cron() {
  command -v crontab >/dev/null || { echo "crontab not found — install cron, or schedule $REFRESH via systemd."; exit 1; }
  mkdir -p "$LOG_DIR"
  # Idempotent: drop any existing line for this script, then add the new one.
  ( crontab -l 2>/dev/null | grep -vF "$REFRESH" || true; cron_entry ) | crontab -
  echo "✓ cron entry installed (Mon & Thu 09:00)"
}

uninstall_cron() {
  command -v crontab >/dev/null || return 0
  ( crontab -l 2>/dev/null | grep -vF "$REFRESH" || true ) | crontab -
  echo "✓ cron entry removed"
}

if [ "$ACTION" = "dry-run" ]; then
  dry_run
  exit 0
fi

case "$OS" in
  Darwin) [ "$ACTION" = uninstall ] && uninstall_macos || install_macos ;;
  Linux)  [ "$ACTION" = uninstall ] && uninstall_cron || install_cron ;;
  *) echo "Unsupported OS: $OS. Schedule '$REFRESH' yourself (e.g. Windows Task Scheduler)."; exit 1 ;;
esac

if [ "$ACTION" != uninstall ]; then
  echo ""
  command -v uv >/dev/null 2>&1 || echo "⚠ 'uv' not on PATH here; refresh-token.sh probes common locations — verify it can find uv."
  if [ ! -f "$LOG_DIR/token.json" ]; then
    echo "⚠ No token yet. Run a HEADED login once to establish the browser session:"
    echo "    golf-coach login"
    echo "  After that, the schedule refreshes it silently."
  fi
  echo "Logs: $LOG_DIR/refresh.log"
fi
