#!/usr/bin/env bash
set -euo pipefail

# Sweep chunk sizes/overlaps sequentially using run.sh.
# Defaults: MODE=paris, ranges 1..1, chunk sizes 100/500, overlaps 0/50.

MODE=${MODE:-paris}
BOOK_START=${1:-1}
BOOK_END=${2:-1}
CHUNK_SIZES=${CHUNK_SIZES:-"100 500"}
CHUNK_OVERLAPS=${CHUNK_OVERLAPS:-"0 50"}
EXPORT_GRAPH=${EXPORT_GRAPH:-1}
FAILURES=()

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SH="$SCRIPT_DIR/run.sh"

echo "Sweep start: MODE=${MODE} range=${BOOK_START}..${BOOK_END} chunk_sizes=${CHUNK_SIZES} overlaps=${CHUNK_OVERLAPS}"

for cs in ${CHUNK_SIZES}; do
  for co in ${CHUNK_OVERLAPS}; do
    echo "------------------------------------------------------------------"
    echo "Running CHUNK_SIZE=${cs} CHUNK_OVERLAP=${co}"
    if ! CHUNK_SIZE=${cs} CHUNK_OVERLAP=${co} MODE=${MODE} EXPORT_GRAPH=${EXPORT_GRAPH} "${RUN_SH}" "${BOOK_START}" "${BOOK_END}"; then
      FAILURES+=("${cs}/${co}")
      echo "Run failed for CHUNK_SIZE=${cs} CHUNK_OVERLAP=${co}; continuing sweep."
    fi
  done
done

if ((${#FAILURES[@]})); then
  echo "Sweep complete with failures for: ${FAILURES[*]}"
  exit 1
fi

echo "Sweep complete (all runs succeeded)."
