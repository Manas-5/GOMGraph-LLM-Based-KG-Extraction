#!/usr/bin/env bash
set -euo pipefail

# Helper script: run the same input file through multiple models.
# Approach: override file.path, file.group_id and falkordb.database per run
# - Sequential by default (safe)
# - Writes per-model logs to logs/book1-<sanitized>/out.log
# - Easy to add new models: edit the MODELS and SANITIZED arrays below
#
# Usage:
#   chmod +x scripts/run_models_for_file.sh
#   ./scripts/run_models_for_file.sh
#
# Optional environment variables:
#   FILE  - path to the input file (defaults to the project example path)
#   PRINT_CONFIG - if set to "true" will run --print-config before each job

# ---------------------- Edit these arrays to add/remove models -----------------
MODELS=(
  "llama3.1:70b"
  "mistral:7b-instruct"
  "mixtral:latest"
  "qwen3:32b"
)

SANITIZED=(
  "llama3-1-70b"
  "mistral-7b-instruct"
  "mixtral-latest"
  "qwen3-32b"
)
# -----------------------------------------------------------------------------

# Default input file (override by setting FILE env var)
: ${FILE:="/mnt/diskGum/manas/GOMgraph-main/data/1_Manuel_pratique_de_la_culture_maraichere_de_Paris__par_Moreau_et_Daverne__1845.txt"}

PRINT_CONFIG=${PRINT_CONFIG:-false}

mkdir -p logs

for i in "${!MODELS[@]}"; do
  MODEL="${MODELS[$i]}"
  SUF="${SANITIZED[$i]}"
  DB="book1-${SUF}"
  LOGDIR="logs/${DB}"
  mkdir -p "$LOGDIR"

  echo "=== [$((i+1))/${#MODELS[@]}] Running model $MODEL -> FalkorDB DB: $DB, group_id: $DB ==="

  if [ "$PRINT_CONFIG" = "true" ]; then
    echo "   Running --print-config for verification (output -> $LOGDIR/print-config.json)"
    python scripts/run.py create-tkg --override "file.path=${FILE} file.group_id=${DB} llm.model=${MODEL} falkordb.database=${DB}" --print-config >"$LOGDIR/print-config.json" 2>&1 || true
  fi

  # Run the pipeline; capture stdout/stderr to per-model log
  if python scripts/run.py create-tkg --override "file.path=${FILE} file.group_id=${DB} llm.model=${MODEL} falkordb.database=${DB}" >"$LOGDIR/out.log" 2>&1; then
    echo "=== Model $MODEL finished successfully (logs: $LOGDIR/out.log) ==="
  else
    echo "=== Model $MODEL FAILED (see $LOGDIR/out.log). Continuing with next model ==="
  fi

  # quick cooldown between runs
  sleep 2
done

echo "All models processed. Logs are in the logs/ directory."
