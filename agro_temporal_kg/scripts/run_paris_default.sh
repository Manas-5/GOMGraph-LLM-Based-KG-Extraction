#!/usr/bin/env bash
set -euo pipefail

# Run paris ingestion once (or a small range) with default chunk size/overlap
# from the config file. Allows overriding DB name via DB_NAME env.
#
# Usage:
#   ./scripts/run_paris_default.sh 1 1
#   DB_NAME=paris_dedup_exp ./scripts/run_paris_default.sh 1 1
#
# Notes:
# - MODE is pinned to "paris" to pick configs/file/paris.yaml
# - CHUNK_SIZE/CHUNK_OVERLAP are left unset so the YAML defaults apply
# - If DB_NAME is set, we override both file.group_id and falkordb.database

BOOK_START=${1:-1}
BOOK_END=${2:-1}
MODE=paris
CHUNK_SIZE=""
CHUNK_OVERLAP=""
EXPORT_GRAPH=${EXPORT_GRAPH:-1}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SH="$SCRIPT_DIR/run.sh"

# Optional DB override
if [[ -n "${DB_NAME:-}" ]]; then
  EXTRA_OVERRIDES="file.group_id=${DB_NAME} falkordb.database=${DB_NAME}"
else
  EXTRA_OVERRIDES=""
fi

echo "Running paris default: range=${BOOK_START}..${BOOK_END} DB=${DB_NAME:-<from file.path stem>} (default chunk settings)"

EXTRA_OVERRIDES="${EXTRA_OVERRIDES}" \
MODE=${MODE} \
CHUNK_SIZE=${CHUNK_SIZE} \
CHUNK_OVERLAP=${CHUNK_OVERLAP} \
EXPORT_GRAPH=${EXPORT_GRAPH} \
"${RUN_SH}" "${BOOK_START}" "${BOOK_END}"
