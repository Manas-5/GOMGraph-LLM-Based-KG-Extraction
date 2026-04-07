#!/usr/bin/env bash
set -euo pipefail

# kill_tkg.sh
#
# Goal: STOP THE ENTIRE TKG RUN (runner + children) so the next graph DOES NOT start.
# This script:
#   1) Finds any running scripts/run.sh runner processes
#   2) Kills their PROCESS GROUPS (kills run.sh + all child python create-tkg jobs)
#   3) Also kills any remaining "run.py create-tkg" processes as a safety net
#
# No sudo required.

DRY_RUN=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [--dry-run] [--help]

Options:
  --dry-run   Print what would be killed, but do nothing
  --help      Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1"
      usage
      exit 1
      ;;
  esac
done

echo "[kill_tkg] Starting (dry-run=${DRY_RUN})"

# ----------------------------
# 1) Kill process groups for run.sh
# ----------------------------
echo "[kill_tkg] Searching for runner processes: scripts/run.sh"

# pgrep -af prints: "<pid> <full cmdline>"
RUNNERS="$(pgrep -af "scripts/run.sh" || true)"

if [[ -z "${RUNNERS}" ]]; then
  echo "[kill_tkg] No scripts/run.sh runner found."
else
  echo "[kill_tkg] Found runner(s):"
  echo "${RUNNERS}"

  # Collect runner PIDs
  RUNNER_PIDS="$(echo "${RUNNERS}" | awk '{print $1}' | tr '\n' ' ')"

  for pid in $RUNNER_PIDS; do
    # PGID is "process group id" for the pid
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ' || true)"
    if [[ -z "$pgid" ]]; then
      echo "[kill_tkg] Could not determine PGID for runner pid=$pid; will kill PID only."
      if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "[kill_tkg] dry-run: kill -TERM $pid"
      else
        kill -TERM "$pid" 2>/dev/null || true
      fi
      continue
    fi

    echo "[kill_tkg] Runner pid=$pid has pgid=$pgid"
    echo "[kill_tkg] Killing entire process group: -$pgid  (runner + all children)"

    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "[kill_tkg] dry-run: kill -TERM -$pgid"
    else
      kill -TERM "-$pgid" 2>/dev/null || true
    fi
  done
fi

# Give processes a moment to exit
if [[ "$DRY_RUN" -eq 0 ]]; then
  sleep 1
fi

# ----------------------------
# 2) Safety net: kill any remaining create-tkg jobs
# ----------------------------
echo "[kill_tkg] Searching for remaining create-tkg jobs: run.py create-tkg"
CREATE_PIDS="$(pgrep -f "run.py create-tkg" || true)"

if [[ -z "${CREATE_PIDS}" ]]; then
  echo "[kill_tkg] No remaining create-tkg jobs found."
else
  echo "[kill_tkg] Remaining create-tkg PID(s): ${CREATE_PIDS}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[kill_tkg] dry-run: kill -TERM ${CREATE_PIDS}"
  else
    kill -TERM ${CREATE_PIDS} 2>/dev/null || true
  fi
fi

# ----------------------------
# 3) Report what is still alive
# ----------------------------
echo "[kill_tkg] Post-kill check:"
if pgrep -af "scripts/run.sh" >/dev/null 2>&1; then
  echo "[kill_tkg] ⚠️ Still running runner(s):"
  pgrep -af "scripts/run.sh" || true
else
  echo "[kill_tkg] ✅ No runner(s) remaining."
fi

if pgrep -af "run.py create-tkg" >/dev/null 2>&1; then
  echo "[kill_tkg] ⚠️ Still running create-tkg job(s):"
  pgrep -af "run.py create-tkg" || true
else
  echo "[kill_tkg] ✅ No create-tkg jobs remaining."
fi

echo "[kill_tkg] Done."
