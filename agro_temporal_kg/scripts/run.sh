#!/usr/bin/env bash
set -euo pipefail

# Sequential runner (quiet terminal):
# - Runs one item at a time
# - Writes full stdout/stderr to logs/<db>/out.log and logs/<db>/run.log
# - Terminal shows only: item/db + live progress line (chunk X/Y) + DONE + VERIFIED
#
# IMPORTANT: Hydra file configs are selected by "file=<config_name>" (NOT file.path).
# Example: file=tomato_1 or file=book7-llama70b
#
# Usage:
#   MODE=tomato ./scripts/run.sh 1 10
#   MODE=books  ./scripts/run.sh 1 21
#
# Optional env:
#   LLAMA_MODEL_OVERRIDE=llama3.1:70b
#   LLM_BASE_URL_OVERRIDE=http://localhost:11434/v1
#   EMBEDDER_BASE_URL_OVERRIDE=http://localhost:11434/v1
#   DB_SUFFIX=gpu0  (appended to db name to avoid conflicts in parallel runs)
#   MAX_RETRIES=1
#   VERIFY_GRAPH=1
#   FALKOR_HOST=localhost
#   FALKOR_PORT=6380
#   GPU=0   (optional pin; if unset, don't set CUDA_VISIBLE_DEVICES)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$ROOT_DIR/scripts"
LOGS_DIR="$ROOT_DIR/logs"
BOOK_START=${1:-1}
BOOK_END=${2:-21}

MODE=${MODE:-books}
LLAMA_MODEL_OVERRIDE=${LLAMA_MODEL_OVERRIDE:-"llama3.1:70b"}
LLM_BASE_URL_OVERRIDE=${LLM_BASE_URL_OVERRIDE:-""}
EMBEDDER_BASE_URL_OVERRIDE=${EMBEDDER_BASE_URL_OVERRIDE:-""}
DB_SUFFIX=${DB_SUFFIX:-""}
MAX_RETRIES=${MAX_RETRIES:-1}

FALKOR_HOST="localhost"
FALKOR_PORT="6380"
VERIFY_GRAPH=${VERIFY_GRAPH:-1}
EXPORT_GRAPH=${EXPORT_GRAPH:-0}
EXPORT_DIR=${EXPORT_DIR:-"$ROOT_DIR/exported_data"}
CHUNK_SIZE=${CHUNK_SIZE:-""}
CHUNK_OVERLAP=${CHUNK_OVERLAP:-""}

GPU=${GPU:-""}
any_failed=0

mkdir -p "$LOGS_DIR"
if [[ "$EXPORT_GRAPH" == "1" ]]; then
  mkdir -p "$EXPORT_DIR"
fi

TOTAL=$((BOOK_END - BOOK_START + 1))
if (( TOTAL <= 0 )); then
  echo "No items in range ${BOOK_START}..${BOOK_END}; exiting."
  exit 0
fi

ACTIVE_PID=""
ACTIVE_DB=""
ACTIVE_RUNNER_PID_FILE="$LOGS_DIR/active_runner.pid"
ACTIVE_JOB_PID_FILE="$LOGS_DIR/active_job.pid"
ACTIVE_DB_FILE="$LOGS_DIR/active_db.txt"
SCRIPT_START_TS=$(date +%s)

# -------------------------------------------------------------------
# helpers
# -------------------------------------------------------------------
format_secs() {
  local T=$1
  local H=$((T/3600))
  local M=$(((T%3600)/60))
  local S=$((T%60))
  printf "%02d:%02d:%02d" $H $M $S
}

file_cfg_for() {
  local n="$1"
  # Allow a caller to force a specific file config via env FILE_CFG.
  if [[ -n "${FILE_CFG:-}" ]]; then
    echo "${FILE_CFG}"
    return
  fi
  case "$MODE" in
    tomato) echo "tomato_${n}" ;;
    paris) echo "paris" ;;
    *) echo "book${n}-llama70b" ;;
  esac
}

graph_exists() {
  local db="$1"
  python - "$FALKOR_HOST" "$FALKOR_PORT" "$db" <<'PY'
import sys
from agro_temporal_kg.falkordb_client import FalkorDBClient

host = sys.argv[1]
port = int(sys.argv[2])
db_name = sys.argv[3]

try:
    client = FalkorDBClient(host=host, port=port)
    graphs = client.list_graphs()
    sys.exit(0 if db_name in graphs else 1)
except Exception as exc:
    print(f"[graph_exists] error: {exc}", file=sys.stderr)
    sys.exit(2)
PY
}

verify_graph_quiet() {
  local db="$1"
  if [[ "$VERIFY_GRAPH" != "1" ]]; then
    echo "VERIFY: skipped"
    return 0
  fi
  if graph_exists "$db"; then
    echo "VERIFY: ✅ exists"
  else
    echo "VERIFY: ⚠️ not found"
  fi
}

# Extract "chunk x/y" from run.log (your ingest_episodes logs this)
progress_from_runlog() {
  local runlog="$1"
  local line
  line=$(grep -E "Processing chunk [0-9]+/[0-9]+" "$runlog" 2>/dev/null | tail -n1 || true)
  if [[ -n "$line" ]]; then
    echo "$line" | sed -E 's/.*Processing chunk ([0-9]+)\/([0-9]+).*/\1\/\2/'
    return
  fi
  line=$(grep -E "Starting ingestion of [0-9]+ chunks" "$runlog" 2>/dev/null | tail -n1 || true)
  if [[ -n "$line" ]]; then
    echo "0/$(echo "$line" | sed -E 's/.*Starting ingestion of ([0-9]+) chunks.*/\1/')"
    return
  fi
  echo "0/0"
}

# -------------------------------------------------------------------
# kill handling: kill current python job if you Ctrl+C this runner
# -------------------------------------------------------------------
cleanup_on_exit() {
  if [[ -n "${ACTIVE_PID}" ]]; then
    if kill -0 "${ACTIVE_PID}" 2>/dev/null; then
      echo
      echo "[RUNNER] terminating active job PID=${ACTIVE_PID} DB=${ACTIVE_DB} ..."
      kill "${ACTIVE_PID}" 2>/dev/null || true
    fi
  fi
  rm -f "$ACTIVE_RUNNER_PID_FILE" "$ACTIVE_JOB_PID_FILE" "$ACTIVE_DB_FILE" 2>/dev/null || true
}
trap cleanup_on_exit EXIT INT TERM

echo $$ > "$ACTIVE_RUNNER_PID_FILE"

echo "========================================"
echo "RUNNER START"
echo "  MODE=${MODE}"
echo "  RANGE=${BOOK_START}..${BOOK_END} total=${TOTAL}"
echo "  MODEL=${LLAMA_MODEL_OVERRIDE}"
echo "  LLM_BASE_URL=${LLM_BASE_URL_OVERRIDE:-<default from config>}"
echo "  EMBEDDER_BASE_URL=${EMBEDDER_BASE_URL_OVERRIDE:-<default from config>}"
echo "  DB_SUFFIX=${DB_SUFFIX:-<none>}"
echo "  FalkorDB=${FALKOR_HOST}:${FALKOR_PORT} VERIFY_GRAPH=${VERIFY_GRAPH} (host/port locked; edit script to change)"
echo "  GPU pin: ${GPU:-<none>}"
echo "  Logs: ${LOGS_DIR}/<db>/{out.log,run.log}"
echo "Kill: ./scripts/kill_tkg.sh"
echo "========================================"

# -------------------------------------------------------------------
# main loop
# -------------------------------------------------------------------
for ((i=BOOK_START;i<=BOOK_END;i++)); do
  file_cfg="$(file_cfg_for "$i")"
  # Build overrides array
  overrides=(
    "file=${file_cfg}"
    "llm.model=${LLAMA_MODEL_OVERRIDE}"
  )
  if [[ -n "$LLM_BASE_URL_OVERRIDE" ]]; then
    overrides+=("llm.base_url=${LLM_BASE_URL_OVERRIDE}")
  fi
  if [[ -n "$EMBEDDER_BASE_URL_OVERRIDE" ]]; then
    overrides+=("embedder.base_url=${EMBEDDER_BASE_URL_OVERRIDE}")
  fi
  if [[ -n "$CHUNK_SIZE" ]]; then
    overrides+=("text_splitter.chunk_size=${CHUNK_SIZE}")
  fi
  if [[ -n "$CHUNK_OVERLAP" ]]; then
    overrides+=("text_splitter.chunk_overlap=${CHUNK_OVERLAP}")
  fi

  # Resolve database/group_id from file path stem (sanitized)
  base_db_name=$(python - "$FALKOR_HOST" "$FALKOR_PORT" "${overrides[@]}" <<'PY'
import sys
import re
from pathlib import Path
from agro_temporal_kg.configs import compose_config, CreateTemporalKGConfig

overrides = sys.argv[3:]
cfg = compose_config(config_name="create_tkg", overrides=list(overrides))
config = CreateTemporalKGConfig.from_omegaconf(cfg)
path = config.file.path or ""
stem = Path(path).stem or "graph"
clean = re.sub(r'[^A-Za-z0-9_-]+', '_', stem)
print(clean)
PY
)

  # append chunk params for uniqueness
  suffix=""
  if [[ -n "$CHUNK_SIZE" ]]; then
    suffix="${suffix}_cs${CHUNK_SIZE}"
  fi
  if [[ -n "$CHUNK_OVERLAP" ]]; then
    suffix="${suffix}_co${CHUNK_OVERLAP}"
  fi
  if [[ -n "$DB_SUFFIX" ]]; then
    suffix="${suffix}_${DB_SUFFIX}"
  fi
  db_name="${base_db_name}${suffix}"

  overrides+=("file.group_id=${db_name}" "falkordb.database=${db_name}")

  run_dir="$LOGS_DIR/${db_name}"
  mkdir -p "$run_dir"

  out_log="$run_dir/out.log"
  run_log="$run_dir/run.log"

  # reset per-item logs (keep print-config/start.cmd)
  : > "$out_log"
  : > "$run_log"
  rm -f "$run_dir/pid" "$run_dir/finished.txt" "$run_dir/status_failed" 2>/dev/null || true

  echo "$db_name" > "$ACTIVE_DB_FILE"
  ACTIVE_DB="$db_name"

  # Print config to file (doesn't spam terminal)
  override_str=$(printf "%s\n" "${overrides[@]}" | tr '\n' ' ' | sed 's/[[:space:]]*$//')
  python "$SCRIPTS_DIR/run.py" create-tkg \
    --override "$override_str" \
    --print-config > "$run_dir/print-config.json" 2>&1 || true

  # Always attempt to drop an existing graph before starting ingestion (ignore errors if not present)
  echo "🗑️  Dropping graph if exists: $db_name"
  set +e
  python "$SCRIPTS_DIR/run.py" drop-graph "$db_name" --host "$FALKOR_HOST" --port "$FALKOR_PORT" --force >>"$out_log" 2>&1
  set -e

  # Build command
  if [[ -n "$GPU" ]]; then
    start_cmd="CUDA_VISIBLE_DEVICES=${GPU} python \"scripts/run.py\" create-tkg --override \"${override_str}\""
  else
    start_cmd="python \"scripts/run.py\" create-tkg --override \"${override_str}\""
  fi

  echo "# Generated start command" > "$run_dir/start.cmd"
  echo "$start_cmd" >> "$run_dir/start.cmd"

  echo
  echo "▶️  ITEM ${i}/${BOOK_END}  file=${file_cfg}  db=${db_name}"

  retries=0
  item_start_ts=$(date +%s)

  while true; do
    # Start job with output ONLY to files
    set +e
    bash -c "$start_cmd" >>"$out_log" 2>>"$out_log" &
    ACTIVE_PID=$!
    echo "$ACTIVE_PID" > "$ACTIVE_JOB_PID_FILE"
    echo "$ACTIVE_PID" > "$run_dir/pid"

    # Live progress line (tqdm-ish). Reads run.log which is written by loguru.
    # We update once per 2 seconds until job ends.
    last_progress=""
    while kill -0 "$ACTIVE_PID" 2>/dev/null; do
      prog="$(progress_from_runlog "$out_log")"
      # only redraw if changed
      if [[ "$prog" != "$last_progress" ]]; then
        elapsed=$(( $(date +%s) - item_start_ts ))
        printf "\r   progress: %s   elapsed: %s" "$prog" "$(format_secs "$elapsed")"
        last_progress="$prog"
      fi
      sleep 2
    done
    printf "\r"  # reset line

    wait "$ACTIVE_PID"
    rc=$?
    ACTIVE_PID=""
    rm -f "$ACTIVE_JOB_PID_FILE" 2>/dev/null || true
    set -e

    elapsed=$(( $(date +%s) - item_start_ts ))
    prog="$(progress_from_runlog "$out_log")"

    if [[ $rc -eq 0 ]]; then
      echo "✅ DONE  db=${db_name}  progress=${prog}  elapsed=$(format_secs "$elapsed")"
      echo "finished_at: $(date +%s)" > "$run_dir/finished.txt" || true
      echo "$(verify_graph_quiet "$db_name")"

      if [[ "$EXPORT_GRAPH" == "1" ]]; then
        echo "⬇️  Exporting graph to TSV ..."
        python "$SCRIPTS_DIR/run.py" export-graph "$db_name" \
          --output-dir "$EXPORT_DIR/$db_name" \
          --host "$FALKOR_HOST" --port "$FALKOR_PORT" \
          > "$run_dir/export.log" 2>&1 || echo "⚠️  Export failed, see $run_dir/export.log"
      fi
      break
    fi

    ((retries++)) || true
    echo "❌ FAIL  db=${db_name}  rc=${rc}  progress=${prog}  retry=${retries}/${MAX_RETRIES}"

    if (( retries > MAX_RETRIES )); then
      echo "failed" > "$run_dir/status_failed" || true
      any_failed=1
      echo "⛔ GIVE UP  db=${db_name}  see: $run_log"
      break
    fi

    echo "🔁 RETRYING db=${db_name} ..."
  done
done

overall_elapsed=$(( $(date +%s) - SCRIPT_START_TS ))
echo
echo "========================================"
if [[ "$any_failed" -eq 1 ]]; then
  echo "ALL PROCESSES DONE (with failures)  total_elapsed=$(format_secs "$overall_elapsed")"
  echo "Some runs failed; see ${LOGS_DIR}/*/status_failed"
else
  echo "ALL PROCESSES DONE ✅  total_elapsed=$(format_secs "$overall_elapsed")"
fi
echo "Logs are under: $LOGS_DIR"
echo "========================================"
exit "$any_failed"





# #!/usr/bin/env bash
# set -euo pipefail

# # Sequential runner (quiet terminal):
# # - Runs one item at a time
# # - Writes full stdout/stderr to logs/<db>/out.log and logs/<db>/run.log
# # - Terminal shows only: item/db + live progress line (chunk X/Y) + DONE + VERIFIED
# #
# # IMPORTANT: Hydra file configs are selected by "file=<config_name>" (NOT file.path).
# # Example: file=tomato_1 or file=book7-llama70b
# #
# # Usage:
# #   MODE=tomato ./scripts/run.sh 1 10
# #   MODE=books  ./scripts/run.sh 1 21
# #
# # Optional env:
# #   LLAMA_MODEL_OVERRIDE=llama3.1:70b
# #   MAX_RETRIES=1
# #   VERIFY_GRAPH=1
# #   FALKOR_HOST=localhost
# #   FALKOR_PORT=6380
# #   GPU=0   (optional pin; if unset, don't set CUDA_VISIBLE_DEVICES)

# ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# SCRIPTS_DIR="$ROOT_DIR/scripts"
# LOGS_DIR="$ROOT_DIR/logs"
# BOOK_START=${1:-1}
# BOOK_END=${2:-21}

# MODE=${MODE:-books}
# LLAMA_MODEL_OVERRIDE=${LLAMA_MODEL_OVERRIDE:-"llama3.1:70b"}
# MAX_RETRIES=${MAX_RETRIES:-1}

# FALKOR_HOST="localhost"
# FALKOR_PORT="6380"
# VERIFY_GRAPH=${VERIFY_GRAPH:-1}
# EXPORT_GRAPH=${EXPORT_GRAPH:-0}
# EXPORT_DIR=${EXPORT_DIR:-"$ROOT_DIR/exported_data"}
# CHUNK_SIZE=${CHUNK_SIZE:-""}
# CHUNK_OVERLAP=${CHUNK_OVERLAP:-""}

# GPU=${GPU:-""}
# any_failed=0

# mkdir -p "$LOGS_DIR"
# if [[ "$EXPORT_GRAPH" == "1" ]]; then
#   mkdir -p "$EXPORT_DIR"
# fi

# TOTAL=$((BOOK_END - BOOK_START + 1))
# if (( TOTAL <= 0 )); then
#   echo "No items in range ${BOOK_START}..${BOOK_END}; exiting."
#   exit 0
# fi

# ACTIVE_PID=""
# ACTIVE_DB=""
# ACTIVE_RUNNER_PID_FILE="$LOGS_DIR/active_runner.pid"
# ACTIVE_JOB_PID_FILE="$LOGS_DIR/active_job.pid"
# ACTIVE_DB_FILE="$LOGS_DIR/active_db.txt"
# SCRIPT_START_TS=$(date +%s)

# # -------------------------------------------------------------------
# # helpers
# # -------------------------------------------------------------------
# format_secs() {
#   local T=$1
#   local H=$((T/3600))
#   local M=$(((T%3600)/60))
#   local S=$((T%60))
#   printf "%02d:%02d:%02d" $H $M $S
# }

# file_cfg_for() {
#   local n="$1"
#   case "$MODE" in
#     tomato) echo "tomato_${n}" ;;
#     paris) echo "paris" ;;
#     *) echo "book${n}-llama70b" ;;
#   esac
# }

# graph_exists() {
#   local db="$1"
#   python - "$FALKOR_HOST" "$FALKOR_PORT" "$db" <<'PY'
# import sys
# from agro_temporal_kg.falkordb_client import FalkorDBClient

# host = sys.argv[1]
# port = int(sys.argv[2])
# db_name = sys.argv[3]

# try:
#     client = FalkorDBClient(host=host, port=port)
#     graphs = client.list_graphs()
#     sys.exit(0 if db_name in graphs else 1)
# except Exception as exc:
#     print(f"[graph_exists] error: {exc}", file=sys.stderr)
#     sys.exit(2)
# PY
# }

# verify_graph_quiet() {
#   local db="$1"
#   if [[ "$VERIFY_GRAPH" != "1" ]]; then
#     echo "VERIFY: skipped"
#     return 0
#   fi
#   if graph_exists "$db"; then
#     echo "VERIFY: ✅ exists"
#   else
#     echo "VERIFY: ⚠️ not found"
#   fi
# }

# # Extract "chunk x/y" from run.log (your ingest_episodes logs this)
# progress_from_runlog() {
#   local runlog="$1"
#   local line
#   line=$(grep -E "Processing chunk [0-9]+/[0-9]+" "$runlog" 2>/dev/null | tail -n1 || true)
#   if [[ -n "$line" ]]; then
#     echo "$line" | sed -E 's/.*Processing chunk ([0-9]+)\/([0-9]+).*/\1\/\2/'
#     return
#   fi
#   line=$(grep -E "Starting ingestion of [0-9]+ chunks" "$runlog" 2>/dev/null | tail -n1 || true)
#   if [[ -n "$line" ]]; then
#     echo "0/$(echo "$line" | sed -E 's/.*Starting ingestion of ([0-9]+) chunks.*/\1/')"
#     return
#   fi
#   echo "0/0"
# }

# # -------------------------------------------------------------------
# # kill handling: kill current python job if you Ctrl+C this runner
# # -------------------------------------------------------------------
# cleanup_on_exit() {
#   if [[ -n "${ACTIVE_PID}" ]]; then
#     if kill -0 "${ACTIVE_PID}" 2>/dev/null; then
#       echo
#       echo "[RUNNER] terminating active job PID=${ACTIVE_PID} DB=${ACTIVE_DB} ..."
#       kill "${ACTIVE_PID}" 2>/dev/null || true
#     fi
#   fi
#   rm -f "$ACTIVE_RUNNER_PID_FILE" "$ACTIVE_JOB_PID_FILE" "$ACTIVE_DB_FILE" 2>/dev/null || true
# }
# trap cleanup_on_exit EXIT INT TERM

# echo $$ > "$ACTIVE_RUNNER_PID_FILE"

# echo "========================================"
# echo "RUNNER START"
# echo "  MODE=${MODE}"
# echo "  RANGE=${BOOK_START}..${BOOK_END} total=${TOTAL}"
# echo "  MODEL=${LLAMA_MODEL_OVERRIDE}"
# echo "  FalkorDB=${FALKOR_HOST}:${FALKOR_PORT} VERIFY_GRAPH=${VERIFY_GRAPH} (host/port locked; edit script to change)"
# echo "  GPU pin: ${GPU:-<none>}"
# echo "  Logs: ${LOGS_DIR}/<db>/{out.log,run.log}"
# echo "Kill: ./scripts/kill_tkg.sh"
# echo "========================================"

# # -------------------------------------------------------------------
# # main loop
# # -------------------------------------------------------------------
# for ((i=BOOK_START;i<=BOOK_END;i++)); do
#   file_cfg="$(file_cfg_for "$i")"
#   # Build overrides array
#   overrides=(
#     "file=${file_cfg}"
#     "llm.model=${LLAMA_MODEL_OVERRIDE}"
#   )
#   if [[ -n "$CHUNK_SIZE" ]]; then
#     overrides+=("text_splitter.chunk_size=${CHUNK_SIZE}")
#   fi
#   if [[ -n "$CHUNK_OVERLAP" ]]; then
#     overrides+=("text_splitter.chunk_overlap=${CHUNK_OVERLAP}")
#   fi

#   # Resolve database/group_id from file path stem (sanitized)
#   base_db_name=$(python - "$FALKOR_HOST" "$FALKOR_PORT" "${overrides[@]}" <<'PY'
# import sys
# import re
# from pathlib import Path
# from agro_temporal_kg.configs import compose_config, CreateTemporalKGConfig

# overrides = sys.argv[3:]
# cfg = compose_config(config_name="create_tkg", overrides=list(overrides))
# config = CreateTemporalKGConfig.from_omegaconf(cfg)
# path = config.file.path or ""
# stem = Path(path).stem or "graph"
# clean = re.sub(r'[^A-Za-z0-9_-]+', '_', stem)
# print(clean)
# PY
# )

#   # append chunk params for uniqueness
#   suffix=""
#   if [[ -n "$CHUNK_SIZE" ]]; then
#     suffix="${suffix}_cs${CHUNK_SIZE}"
#   fi
#   if [[ -n "$CHUNK_OVERLAP" ]]; then
#     suffix="${suffix}_co${CHUNK_OVERLAP}"
#   fi
#   db_name="${base_db_name}${suffix}"

#   overrides+=("file.group_id=${db_name}" "falkordb.database=${db_name}")

#   run_dir="$LOGS_DIR/${db_name}"
#   mkdir -p "$run_dir"

#   out_log="$run_dir/out.log"
#   run_log="$run_dir/run.log"

#   # reset per-item logs (keep print-config/start.cmd)
#   : > "$out_log"
#   : > "$run_log"
#   rm -f "$run_dir/pid" "$run_dir/finished.txt" "$run_dir/status_failed" 2>/dev/null || true

#   echo "$db_name" > "$ACTIVE_DB_FILE"
#   ACTIVE_DB="$db_name"

#   # Print config to file (doesn't spam terminal)
#   override_str=$(printf "%s\n" "${overrides[@]}" | tr '\n' ' ' | sed 's/[[:space:]]*$//')
#   python "$SCRIPTS_DIR/run.py" create-tkg \
#     --override "$override_str" \
#     --print-config > "$run_dir/print-config.json" 2>&1 || true

#   # Always attempt to drop an existing graph before starting ingestion (ignore errors if not present)
#   echo "🗑️  Dropping graph if exists: $db_name"
#   set +e
#   python "$SCRIPTS_DIR/run.py" drop-graph "$db_name" --host "$FALKOR_HOST" --port "$FALKOR_PORT" --force >>"$out_log" 2>&1
#   set -e

#   # Build command
#   if [[ -n "$GPU" ]]; then
#     start_cmd="CUDA_VISIBLE_DEVICES=${GPU} python \"scripts/run.py\" create-tkg --override \"${override_str}\""
#   else
#     start_cmd="python \"scripts/run.py\" create-tkg --override \"${override_str}\""
#   fi

#   echo "# Generated start command" > "$run_dir/start.cmd"
#   echo "$start_cmd" >> "$run_dir/start.cmd"

#   echo
#   echo "▶️  ITEM ${i}/${BOOK_END}  file=${file_cfg}  db=${db_name}"

#   retries=0
#   item_start_ts=$(date +%s)

#   while true; do
#     # Start job with output ONLY to files
#     set +e
#     bash -c "$start_cmd" >>"$out_log" 2>>"$out_log" &
#     ACTIVE_PID=$!
#     echo "$ACTIVE_PID" > "$ACTIVE_JOB_PID_FILE"
#     echo "$ACTIVE_PID" > "$run_dir/pid"

#     # Live progress line (tqdm-ish). Reads run.log which is written by loguru.
#     # We update once per 2 seconds until job ends.
#     last_progress=""
#     while kill -0 "$ACTIVE_PID" 2>/dev/null; do
#       prog="$(progress_from_runlog "$out_log")"
#       # only redraw if changed
#       if [[ "$prog" != "$last_progress" ]]; then
#         elapsed=$(( $(date +%s) - item_start_ts ))
#         printf "\r   progress: %s   elapsed: %s" "$prog" "$(format_secs "$elapsed")"
#         last_progress="$prog"
#       fi
#       sleep 2
#     done
#     printf "\r"  # reset line

#     wait "$ACTIVE_PID"
#     rc=$?
#     ACTIVE_PID=""
#     rm -f "$ACTIVE_JOB_PID_FILE" 2>/dev/null || true
#     set -e

#     elapsed=$(( $(date +%s) - item_start_ts ))
#     prog="$(progress_from_runlog "$out_log")"

#     if [[ $rc -eq 0 ]]; then
#       echo "✅ DONE  db=${db_name}  progress=${prog}  elapsed=$(format_secs "$elapsed")"
#       echo "finished_at: $(date +%s)" > "$run_dir/finished.txt" || true
#       echo "$(verify_graph_quiet "$db_name")"

#       if [[ "$EXPORT_GRAPH" == "1" ]]; then
#         echo "⬇️  Exporting graph to TSV ..."
#         python "$SCRIPTS_DIR/run.py" export-graph "$db_name" \
#           --output-dir "$EXPORT_DIR/$db_name" \
#           --host "$FALKOR_HOST" --port "$FALKOR_PORT" \
#           > "$run_dir/export.log" 2>&1 || echo "⚠️  Export failed, see $run_dir/export.log"
#       fi
#       break
#     fi

#     ((retries++)) || true
#     echo "❌ FAIL  db=${db_name}  rc=${rc}  progress=${prog}  retry=${retries}/${MAX_RETRIES}"

#     if (( retries > MAX_RETRIES )); then
#       echo "failed" > "$run_dir/status_failed" || true
#       any_failed=1
#       echo "⛔ GIVE UP  db=${db_name}  see: $run_log"
#       break
#     fi

#     echo "🔁 RETRYING db=${db_name} ..."
#   done
# done

# overall_elapsed=$(( $(date +%s) - SCRIPT_START_TS ))
# echo
# echo "========================================"
# if [[ "$any_failed" -eq 1 ]]; then
#   echo "ALL PROCESSES DONE (with failures)  total_elapsed=$(format_secs "$overall_elapsed")"
#   echo "Some runs failed; see ${LOGS_DIR}/*/status_failed"
# else
#   echo "ALL PROCESSES DONE ✅  total_elapsed=$(format_secs "$overall_elapsed")"
# fi
# echo "Logs are under: $LOGS_DIR"
# echo "========================================"
# exit "$any_failed"
