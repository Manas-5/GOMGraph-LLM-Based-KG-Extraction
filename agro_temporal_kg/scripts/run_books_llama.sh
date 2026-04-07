#!/usr/bin/env bash
set -euo pipefail

# Run a set of book configs (llama only) sequentially (MAX_JOBS forced to 1).
# - Saves per-book print-config to logs/<db>/print-config.json
# - Writes runtime logs to logs/<db>/run.log (real-time)
# - Shows a live summary in the terminal with: book, db, chunk progress, elapsed time
# - Starts the next book when the previous finishes

# Configuration
BOOK_START=${1:-1}
BOOK_END=${2:-21}
MAX_JOBS=1              # always run sequentially
GPUS=(0 1)
LLAMA_MODEL_OVERRIDE=${4:-"llama3.1:70b"}
# Template used to start each job. Available placeholders: {GPU}, {FILE_CFG}, {DB_NAME}, {LLM_MODEL}
# You can override by exporting START_CMD_TEMPLATE in the env before running the script.
# Example: export START_CMD_TEMPLATE='CUDA_VISIBLE_DEVICES={GPU} python scripts/run.py create-tkg --override "file={FILE_CFG} file.group_id={DB_NAME} llm.model={LLM_MODEL} falkordb.database={DB_NAME}"'
START_CMD_TEMPLATE=${START_CMD_TEMPLATE:-'CUDA_VISIBLE_DEVICES={GPU} python "scripts/run.py" create-tkg --override "file={FILE_CFG} file.group_id={DB_NAME} llm.model={LLM_MODEL} falkordb.database={DB_NAME}"'}
# Retry config: how many times to retry a failed job
MAX_RETRIES=${MAX_RETRIES:-1}
# Compute total books and handle edge cases
TOTAL_BOOKS=$((BOOK_END - BOOK_START + 1))
if (( TOTAL_BOOKS <= 0 )); then
    echo "No books in range ${BOOK_START}..${BOOK_END}; exiting."
    exit 0
fi
# If set to 1, assign first half of books to GPUS[0] and second half to GPUS[1]
USE_HALF_SPLIT=${USE_HALF_SPLIT:-1}
DEBUG=${DEBUG:-0}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$ROOT_DIR/scripts"
LOGS_DIR="$ROOT_DIR/logs"

mkdir -p "$LOGS_DIR"

declare -A PID_TO_BOOK
declare -A PID_TO_DB
declare -A PID_START_TS
declare -A PID_TO_GPU
declare -A BOOK_RETRIES
declare -a QUEUE

# Ensure associative arrays are initialized (avoid 'unbound variable' with set -u)
PID_TO_BOOK=()
PID_TO_DB=()
PID_START_TS=()
PID_TO_GPU=()
BOOK_RETRIES=()
QUEUE=()

# Helpers to safely access associative arrays when running with 'set -u'
function pid_count() {
    if declare -p PID_TO_BOOK >/dev/null 2>&1; then
        echo ${#PID_TO_BOOK[@]}
    else
        echo 0
    fi
}

function pids() {
    if declare -p PID_TO_BOOK >/dev/null 2>&1; then
        # expand keys, safe even if empty
        echo "${!PID_TO_BOOK[@]}"
    else
        echo ""
    fi
}

# Script start time
SCRIPT_START_TS=$(date +%s)

# Initialize queue with all book numbers
for ((i=BOOK_START;i<=BOOK_END;i++)); do
    QUEUE+=("$i")
done

# initialize job index used when launching jobs
current_job_index=0

### function definitions (moved early so initial-fill can call them)
function start_book() {
    local book_num=$1
    local file_cfg="book${book_num}-llama70b"
    local db_name="book${book_num}_ent_1_edge_0_prompt_new"
    local book_log_dir="$LOGS_DIR/${db_name}"
    mkdir -p "$book_log_dir"

    # Remove stale status file so elapsed/time counters reset for a new run
    if [[ -f "$book_log_dir/status.txt" ]]; then
        echo "Removing stale status file $book_log_dir/status.txt"
        rm -f "$book_log_dir/status.txt" || true
    fi

    # Remove stale out/run logs so each run starts fresh
    if [[ -f "$book_log_dir/out.log" ]]; then
        rm -f "$book_log_dir/out.log" || true
    fi
    if [[ -f "$book_log_dir/run.log" ]]; then
        rm -f "$book_log_dir/run.log" || true
    fi

    # Save composed config for debugging (spawn in background so it doesn't block launching other jobs)
    echo "Saving composed config for ${file_cfg} -> ${book_log_dir}/print-config.json"
    python "$SCRIPTS_DIR/run.py" create-tkg --override "file=${file_cfg} file.group_id=${db_name} llm.model=${LLAMA_MODEL_OVERRIDE} falkordb.database=${db_name}" --print-config > "$book_log_dir/print-config.json" 2>&1 &

    # Start the actual run; determine GPU assignment
    local job_index=$2
    local gpu_index=$((job_index % ${#GPUS[@]}))
    local gpu=${GPUS[$gpu_index]}
    # If USE_HALF_SPLIT enabled, assign by book index range (first half -> GPU0, second half -> GPU1)
    if [[ "${USE_HALF_SPLIT}" == "1" ]]; then
        local total_books=$((TOTAL_BOOKS))
        local idx=$((book_num - BOOK_START))
        # ceil half so first GPU receives the extra book when odd
        local half=$(((total_books + 1) / 2))
        if (( idx < half )); then
            gpu=${GPUS[0]}
        else
            gpu=${GPUS[1]:-${GPUS[0]}}
        fi
    fi
    # If a caller provided an override GPU as third argument, use it
    if [[ ${#} -ge 3 && -n "${3:-}" ]]; then
        gpu=${3}
    fi

    echo "Starting book ${book_num} on GPU ${gpu} -> DB=${db_name} (logs: ${book_log_dir}/run.log, ${book_log_dir}/out.log)"

    # Build the actual start command from the template and write it to start.cmd for debugging
    start_cmd=${START_CMD_TEMPLATE//\{GPU\}/$gpu}
    start_cmd=${start_cmd//\{FILE_CFG\}/$file_cfg}
    start_cmd=${start_cmd//\{DB_NAME\}/$db_name}
    start_cmd=${start_cmd//\{LLM_MODEL\}/$LLAMA_MODEL_OVERRIDE}
    echo "# Generated start command" > "$book_log_dir/start.cmd"
    echo "$start_cmd" >> "$book_log_dir/start.cmd"

    # Execute the command in a shell so env assignments like CUDA_VISIBLE_DEVICES are applied.
    # Pipe output to both out.log and run.log via tee and run in background.
    bash -c "$start_cmd" 2>&1 | tee "$book_log_dir/out.log" "$book_log_dir/run.log" > /dev/null &
    local pid=$!
    # write pid into log dir for easy inspection/targeted kills
    echo "$pid" > "$book_log_dir/pid"
    PID_TO_BOOK[$pid]=$book_num
    PID_TO_DB[$pid]=$db_name
    PID_TO_GPU[$pid]=$gpu
    PID_START_TS[$pid]=$(date +%s)
    # Write GPU assignment to a small file for external verification
    echo "$gpu" > "$book_log_dir/gpu.txt" || true
}

# Initial fill: start one book per GPU if possible (helps ensure both GPUs are used quickly)
if [[ "${USE_HALF_SPLIT}" == "1" ]]; then
    total_books=$((TOTAL_BOOKS))
    half=$(((total_books + 1) / 2))
    # deterministic picks: first GPU gets BOOK_START; second GPU gets BOOK_START+half (if in range)
    for idx_g in "${!GPUS[@]}"; do
        g=${GPUS[$idx_g]}
        if [[ $idx_g -eq 0 ]]; then
            pick_book=$BOOK_START
        else
            pick_book=$((BOOK_START + half))
            # if that exceeds BOOK_END, skip
            if (( pick_book > BOOK_END )); then
                continue
            fi
        fi
        # find and remove pick_book from QUEUE
        pick_index=-1
        for i in "${!QUEUE[@]}"; do
            if [[ "${QUEUE[i]}" -eq "$pick_book" ]]; then
                pick_index=$i
                break
            fi
        done
        if [[ $pick_index -ge 0 ]]; then
            if [[ $DEBUG -eq 1 ]]; then
                echo "[DEBUG] initial-fill: starting book $pick_book on GPU $g (queue_index=$pick_index)"
            fi
            if [[ $pick_index -eq 0 ]]; then
                QUEUE=("${QUEUE[@]:1}")
            else
                QUEUE=( "${QUEUE[@]:0:$pick_index}" "${QUEUE[@]:$((pick_index+1))}" )
            fi
            start_book $pick_book $current_job_index
            ((current_job_index++))
        else
            if [[ $DEBUG -eq 1 ]]; then
                echo "[DEBUG] initial-fill: book $pick_book not found in queue"
            fi
        fi
        if [[ $(pid_count) -ge $MAX_JOBS ]]; then
            break
        fi
    done
fi

# Format seconds to HH:MM:SS
function format_secs() {
    local T=$1
    local H=$((T/3600))
    local M=$(( (T%3600)/60 ))
    local S=$((T%60))
    printf "%02d:%02d:%02d" $H $M $S
}

function start_book() {
    local book_num=$1
    local file_cfg="book${book_num}-llama70b"
    local db_name="book${book_num}_ent_1_edge_0_prompt_new"
    local book_log_dir="$LOGS_DIR/${db_name}"
    mkdir -p "$book_log_dir"

    # Remove stale status file so elapsed/time counters reset for a new run
    if [[ -f "$book_log_dir/status.txt" ]]; then
        echo "Removing stale status file $book_log_dir/status.txt"
        rm -f "$book_log_dir/status.txt" || true
    fi

    # Remove stale out/run logs so each run starts fresh
    if [[ -f "$book_log_dir/out.log" ]]; then
        rm -f "$book_log_dir/out.log" || true
    fi
    if [[ -f "$book_log_dir/run.log" ]]; then
        rm -f "$book_log_dir/run.log" || true
    fi

    # Save composed config for debugging (spawn in background so it doesn't block launching other jobs)
    echo "Saving composed config for ${file_cfg} -> ${book_log_dir}/print-config.json"
    python "$SCRIPTS_DIR/run.py" create-tkg --override "file=${file_cfg} file.group_id=${db_name} llm.model=${LLAMA_MODEL_OVERRIDE} falkordb.database=${db_name}" --print-config > "$book_log_dir/print-config.json" 2>&1 &

    # Start the actual run; determine GPU assignment
    local job_index=$2
    local gpu_index=$((job_index % ${#GPUS[@]}))
    local gpu=${GPUS[$gpu_index]}
    # If USE_HALF_SPLIT enabled, assign by book index range (first half -> GPU0, second half -> GPU1)
    if [[ "${USE_HALF_SPLIT}" == "1" ]]; then
        local total_books=$((TOTAL_BOOKS))
        local idx=$((book_num - BOOK_START))
        # ceil half so first GPU receives the extra book when odd
        local half=$(((total_books + 1) / 2))
        if (( idx < half )); then
            gpu=${GPUS[0]}
        else
            gpu=${GPUS[1]:-${GPUS[0]}}
        fi
    fi
    # If a caller provided an override GPU as third argument, use it
    if [[ ${#} -ge 3 && -n "${3:-}" ]]; then
        gpu=${3}
    fi

    echo "Starting book ${book_num} on GPU ${gpu} -> DB=${db_name} (logs: ${book_log_dir}/run.log, ${book_log_dir}/out.log)"

    # Build the actual start command from the template and write it to start.cmd for debugging
    start_cmd=${START_CMD_TEMPLATE//\{GPU\}/$gpu}
    start_cmd=${start_cmd//\{FILE_CFG\}/$file_cfg}
    start_cmd=${start_cmd//\{DB_NAME\}/$db_name}
    start_cmd=${start_cmd//\{LLM_MODEL\}/$LLAMA_MODEL_OVERRIDE}
    echo "# Generated start command" > "$book_log_dir/start.cmd"
    echo "$start_cmd" >> "$book_log_dir/start.cmd"

    # Execute the command in a shell so env assignments like CUDA_VISIBLE_DEVICES are applied.
    # Pipe output to both out.log and run.log via tee and run in background.
    bash -c "$start_cmd" 2>&1 | tee "$book_log_dir/out.log" "$book_log_dir/run.log" > /dev/null &
    local pid=$!
    # write pid into log dir for easy inspection/targeted kills
    echo "$pid" > "$book_log_dir/pid"
    PID_TO_BOOK[$pid]=$book_num
    PID_TO_DB[$pid]=$db_name
    PID_TO_GPU[$pid]=$gpu
    PID_START_TS[$pid]=$(date +%s)
    # Write GPU assignment to a small file for external verification
    echo "$gpu" > "$book_log_dir/gpu.txt" || true
}

function get_progress_from_log() {
    local log_file=$1
    # Look for last "Processing chunk X/Y" line produced by ingest_episodes
    local line
    line=$(grep -E "Processing chunk [0-9]+/[0-9]+" "$log_file" 2>/dev/null | tail -n1 || true)
    if [[ -n "$line" ]]; then
        echo "$line" | sed -E 's/.*Processing chunk ([0-9]+)\/([0-9]+).*/\1\/\2/'
        return
    fi
    # Fallback: check for 'Starting ingestion of' to get total chunks
    line=$(grep -E "Starting ingestion of [0-9]+ chunks" "$log_file" 2>/dev/null | tail -n1 || true)
    if [[ -n "$line" ]]; then
        echo "0/$(echo $line | sed -E 's/.*Starting ingestion of ([0-9]+) chunks.*/\1/')"
        return
    fi
    echo "0/0"
}

function print_status() {
    local now_ts=$(date +%s)
    local total_elapsed=$((now_ts - SCRIPT_START_TS))
    # Count completed books by checking logs dir for 'finished' markers (simple heuristic)
    local total_books=$((BOOK_END - BOOK_START + 1))
    local running_jobs=$(pid_count)
    # Completed = started books - running_jobs - remaining books
    local started_books=$((next_book - BOOK_START))
    local completed_books=$((started_books - running_jobs))

    echo "========================================"
    echo "Overall: started=${started_books}/${total_books}  running=${running_jobs}  completed=${completed_books}/${total_books}  total_elapsed=$(format_secs ${total_elapsed})"
    echo "========================================"
    printf "%-6s %-8s %-6s %-40s %-12s %-10s\n" "PID" "BOOK" "GPU" "DB_NAME" "PROGRESS" "ELAPSED"
    if declare -p PID_TO_BOOK >/dev/null 2>&1; then
        for pid in ${pids}; do
            local book=${PID_TO_BOOK[$pid]}
            local db=${PID_TO_DB[$pid]}
            local gpu=${PID_TO_GPU[$pid]:-}
            local log_file="$LOGS_DIR/${db}/run.log"
            local progress="0/0"
            if [[ -f "$log_file" ]]; then
                progress=$(get_progress_from_log "$log_file")
            fi
            local start_ts=${PID_START_TS[$pid]}
            local elapsed=$((now_ts - start_ts))
            printf "%-6s %-8s %-6s %-40s %-12s %-10s\n" "$pid" "$book" "$gpu" "$db" "$progress" "$(format_secs ${elapsed})"
        done
    fi
    echo
}

# Main loop: maintain up to MAX_JOBS concurrent processes
current_job_index=0

while true; do
    # exit condition: queue empty and no running jobs
    if [[ ${#QUEUE[@]} -eq 0 && $(pid_count) -eq 0 ]]; then
        break
    fi

    # Start new jobs while we have capacity and queue items
    while [[ $(pid_count) -lt $MAX_JOBS && ${#QUEUE[@]} -gt 0 ]]; do
        # When using half-split, try to find any queued book that maps to a currently free GPU
        if [[ "${USE_HALF_SPLIT}" == "1" ]]; then
            # compute half split constants
            total_books=$((TOTAL_BOOKS))
            half=$(((total_books + 1) / 2))

            # find which GPUs are currently free (we allow one job per GPU)
            declare -A GPU_OCCUPIED
            for g in "${GPUS[@]}"; do
                GPU_OCCUPIED[$g]=0
            done
            for pid in $(pids); do
                g=${PID_TO_GPU[$pid]:-}
                if [[ -n "$g" ]]; then
                    GPU_OCCUPIED[$g]=1
                fi
            done

            # collect free GPUs
            free_any=0
            declare -A FREE_GPU_SET
            for g in "${GPUS[@]}"; do
                if [[ ${GPU_OCCUPIED[$g]:-0} -eq 0 ]]; then
                    FREE_GPU_SET[$g]=1
                    free_any=1
                else
                    FREE_GPU_SET[$g]=0
                fi
            done
            if [[ $free_any -eq 0 ]]; then
                # no free GPU right now
                if [[ $DEBUG -eq 1 ]]; then
                    echo "[DEBUG] no free GPU (GPU_OCCUPIED=${GPU_OCCUPIED[*]})"
                    echo "[DEBUG] QUEUE=${QUEUE[*]}"
                fi
                break
            fi
            if [[ $DEBUG -eq 1 ]]; then
                echo "[DEBUG] FREE GPUs:"
                for g in "${GPUS[@]}"; do
                    echo "[DEBUG]   GPU $g free=${FREE_GPU_SET[$g]:-0}"
                done
                echo "[DEBUG] QUEUE=${QUEUE[*]}"
            fi

            # For each free GPU, pick the first queued book that belongs to that GPU's half
            for g in "${GPUS[@]}"; do
                if [[ ${FREE_GPU_SET[$g]:-0} -ne 1 ]]; then
                    continue
                fi
                # find first queued book assigned to this GPU
                pick_index=-1
                pick_book=""
                for i in "${!QUEUE[@]}"; do
                    b=${QUEUE[i]}
                    idx=$((b - BOOK_START))
                    if (( idx < half )); then
                        target_gpu=${GPUS[0]}
                    else
                        target_gpu=${GPUS[1]:-${GPUS[0]}}
                    fi
                    if [[ "$target_gpu" == "$g" ]]; then
                        pick_index=$i
                        pick_book=$b
                        break
                    fi
                done
                if [[ $pick_index -lt 0 ]]; then
                    # no matching book for this GPU
                    if [[ $DEBUG -eq 1 ]]; then
                        echo "[DEBUG] No queued book for GPU $g"
                    fi
                    continue
                fi
                # remove the picked book from the queue
                if [[ $pick_index -eq 0 ]]; then
                    QUEUE=("${QUEUE[@]:1}")
                else
                    QUEUE=( "${QUEUE[@]:0:$pick_index}" "${QUEUE[@]:$((pick_index+1))}" )
                fi
                if [[ $DEBUG -eq 1 ]]; then
                    echo "[DEBUG] Starting pick_book=$pick_book on GPU $g (queue_index=$pick_index)"
                fi
                # start the picked book on its assigned GPU
                start_book $pick_book $current_job_index
                ((current_job_index++))
                sleep 1
                # stop starting more if we reached MAX_JOBS
                if [[ $(pid_count) -ge $MAX_JOBS ]]; then
                    break
                fi
            done
        else
            # find a free GPU (based on GPUs used by our launched jobs)
            free_gpu=""
            for g in "${GPUS[@]}"; do
                occupied=0
                for pid in $(pids); do
                    if [[ "${PID_TO_GPU[$pid]:-}" == "$g" ]]; then
                        occupied=1
                        break
                    fi
                done
                if [[ $occupied -eq 0 ]]; then
                    free_gpu="$g"
                    break
                fi
            done

            if [[ -z "$free_gpu" ]]; then
                # no GPU free now; push book back to front of queue and wait
                QUEUE=("$book" "${QUEUE[@]}")
                break
            fi

            start_book $book $current_job_index "$free_gpu"
            ((current_job_index++))
            sleep 1
        fi
    done

    # Print status summary
    clear
    echo "Running up to $MAX_JOBS jobs (GPUs: ${GPUS[*]})"
    print_status

    # Check running jobs for completion and requeue on failure
    for pid in $(pids); do
        if ! kill -0 "$pid" 2>/dev/null; then
            # process finished
            wait "$pid"
            rc=$?
            book=${PID_TO_BOOK[$pid]}
            db=${PID_TO_DB[$pid]}
            start_ts=${PID_START_TS[$pid]}
            end_ts=$(date +%s)
            elapsed=$((end_ts - start_ts))
            echo "Book ${book} (DB=${db}) finished in ${elapsed}s (rc=${rc})"
            gpu=${PID_TO_GPU[$pid]:-}
            unset PID_TO_BOOK[$pid]
            unset PID_TO_DB[$pid]
            unset PID_START_TS[$pid]
            unset PID_TO_GPU[$pid]

            if [[ $rc -ne 0 ]]; then
                retries=${BOOK_RETRIES[$book]:-0}
                if (( retries < MAX_RETRIES )); then
                    ((BOOK_RETRIES[$book]++))
                    echo "Job for book ${book} failed (rc=${rc}); requeueing (retry ${BOOK_RETRIES[$book]}/${MAX_RETRIES})"
                    QUEUE+=("$book")
                else
                    echo "Job for book ${book} failed after ${retries} retries; giving up. See logs/${db}/run.log"
                    echo "failed" > "$LOGS_DIR/${db}/status_failed" || true
                fi
            else
                # success: write finished marker
                echo "finished_at: $(date +%s)" > "$LOGS_DIR/${db}/finished.txt" || true
            fi
        fi
    done

    sleep 3
done

echo "All books processed. Logs are under $LOGS_DIR"
