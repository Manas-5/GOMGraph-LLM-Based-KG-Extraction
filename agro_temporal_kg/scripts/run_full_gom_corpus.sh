#!/usr/bin/env bash
set -euo pipefail

# Thin wrapper around run.sh, mirroring run_books_default style, but targeting
# a single file config: default full_gom_corpus, optional test.
#
# Usage:
#   ./scripts/run_full_gom_corpus.sh          # runs full_gom_corpus
#   ./scripts/run_full_gom_corpus.sh test     # runs test.yaml
#   GPU=1 ./scripts/run_full_gom_corpus.sh    # pin GPU
#   EXPORT_GRAPH=1 ./scripts/run_full_gom_corpus.sh
#   CHUNK_SIZE=1200 CHUNK_OVERLAP=200 ./scripts/run_full_gom_corpus.sh

CONFIG_ARG=${1:-full}
case "$CONFIG_ARG" in
  full|full_gom_corpus) FILE_CFG="full_gom_corpus" ;;
  test|test.yaml) FILE_CFG="test" ;;
  *) echo "Unknown mode '$CONFIG_ARG'. Use 'full' (default) or 'test'." >&2; exit 1 ;;
esac

# Match run_books_default defaults
BOOK_START=1
BOOK_END=1
MODE=books
CHUNK_SIZE=${CHUNK_SIZE:-""}
CHUNK_OVERLAP=${CHUNK_OVERLAP:-""}
EXPORT_GRAPH=${EXPORT_GRAPH:-1}
MAX_RETRIES=${MAX_RETRIES:-1}
GPU=${GPU:-""}
LLAMA_MODEL_OVERRIDE=${LLAMA_MODEL_OVERRIDE:-"llama3.1:70b"}
VERIFY_GRAPH=${VERIFY_GRAPH:-1}
export ROR_CACHE_FILE="/mnt/diskGum/manas/GOMgraph-main-clone-3/data/ror/v2.0-2025-12-16-ror-data.json"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SH="$SCRIPT_DIR/run.sh"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Ensure Hydra finds configs/ regardless of caller cwd (mirrors typical usage of run_books_default)
cd "$ROOT_DIR"

echo "Running ${FILE_CFG} via run.sh (books runner style)"

export FILE_CFG
FILE_CFG="${FILE_CFG}" \
MODE=${MODE} \
CHUNK_SIZE=${CHUNK_SIZE} \
CHUNK_OVERLAP=${CHUNK_OVERLAP} \
EXPORT_GRAPH=${EXPORT_GRAPH} \
MAX_RETRIES=${MAX_RETRIES} \
GPU=${GPU} \
LLAMA_MODEL_OVERRIDE="${LLAMA_MODEL_OVERRIDE}" \
VERIFY_GRAPH=${VERIFY_GRAPH} \
"${RUN_SH}" "${BOOK_START}" "${BOOK_END}"
