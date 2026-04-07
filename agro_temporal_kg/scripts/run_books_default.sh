#!/usr/bin/env bash
set -euo pipefail

# Run the books pipeline over a range (default 1..21) with default chunk settings.
# Uses the same runner as other modes; progress/logs land under logs/<db_name>/.
#
# Usage:
#   bash scripts/run_books_default.sh            # runs 1..21
#   bash scripts/run_books_default.sh 5 10       # runs 5..10
#
# Env you can override:
#   EXPORT_GRAPH=1          # default 1 (keep TSV export behaviour of run.sh)
#   GPU=<id>                # to pin GPU
#   MAX_RETRIES=<n>         # fallback to run.sh default if unset

BOOK_START=${1:-1}
BOOK_END=${2:-21}
MODE=books
CHUNK_SIZE=""
CHUNK_OVERLAP=""
EXPORT_GRAPH=${EXPORT_GRAPH:-1}
export ROR_CACHE_FILE="/mnt/diskGum/manas/GOMgraph-main-clone-3/data/ror/v2.0-2025-12-16-ror-data.json"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SH="$SCRIPT_DIR/run.sh"

echo "Running books default: range=${BOOK_START}..${BOOK_END} (default chunk settings)"

MODE=${MODE} \
CHUNK_SIZE=${CHUNK_SIZE} \
CHUNK_OVERLAP=${CHUNK_OVERLAP} \
EXPORT_GRAPH=${EXPORT_GRAPH} \
"${RUN_SH}" "${BOOK_START}" "${BOOK_END}"
