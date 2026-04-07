# Agro Temporal Knowledge Graph — Run Guide

This document explains how to run the pipeline using `scripts/run.sh`, which is the main entry point for building temporal knowledge graphs from agricultural text corpora. All commands should be run from the `agro_temporal_kg/` project root unless noted otherwise.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Basic Usage](#basic-usage)
4. [Running a Range of Books](#running-a-range-of-books)
5. [Running All Books (Books 1–21)](#running-all-books-books-121)
6. [Running the Full Merged Corpus Dataset](#running-the-full-merged-corpus-dataset)
7. [Overriding the Model](#overriding-the-model)
8. [Overriding the LLM and Embedder Base URLs](#overriding-the-llm-and-embedder-base-urls)
9. [Overriding the Book / File Config](#overriding-the-book--file-config)
10. [Overriding Chunk Size and Overlap](#overriding-chunk-size-and-overlap)
11. [GPU Pinning](#gpu-pinning)
12. [Database Suffix (Parallel Runs)](#database-suffix-parallel-runs)
13. [Verifying and Exporting Graphs](#verifying-and-exporting-graphs)
14. [Retries and Fault Tolerance](#retries-and-fault-tolerance)
15. [Logs](#logs)
16. [Killing a Running Job](#killing-a-running-job)
17. [run.py CLI Reference](#runpy-cli-reference)
18. [Quick Reference](#quick-reference)

---

## Overview

`scripts/run.sh` is a **sequential runner** that processes one book/file at a time. For each item in the specified range it:

1. Resolves the Hydra file config (e.g. `book3-llama70b`) from the range index and `MODE`.
2. Derives the FalkorDB database name from the input file path stem.
3. Drops any pre-existing graph of that name (fresh start).
4. Runs `python scripts/run.py create-tkg` with the assembled Hydra overrides.
5. Shows a live progress line (`chunk X/Y`) in the terminal while full output goes to log files.
6. On success, optionally verifies the graph exists in FalkorDB and exports it to TSV.
7. On failure, retries up to `MAX_RETRIES` times before giving up and moving to the next item.

`run.sh` calls `run.py`, which provides the actual Typer/Hydra CLI. You can also call `run.py` directly for one-off runs (see [run.py CLI Reference](#runpy-cli-reference)).

---

## Prerequisites

- FalkorDB is running and accessible (default: `localhost:6380`). It runs on the docker instance. docker-compose up -d
- Ollama is running with the desired LLM and embedding models pulled. (ollama serve)
- The Python virtual environment is activated:

```bash
cd agro_temporal_kg
source dedup/bin/activate
```

- Sync UV: uv sync --active


---

## Basic Usage

The signature of `run.sh` is:

```bash
MODE=<mode> [ENV_VARS...] ./scripts/run.sh <BOOK_START> <BOOK_END>
```

- `BOOK_START` — First index in the range (default: `1`).
- `BOOK_END` — Last index in the range (default: `21`).
- `MODE` — Selects the naming scheme for file configs: `books` (default), `tomato`, or `paris`.

The two positional arguments are **integers** serving as a loop counter. They do **not** directly refer to a filename — they are used to look up the correct Hydra config file via the `file_cfg_for()` function inside `run.sh`:

| MODE | Config resolved for index `N` | Example |
|------|-------------------------------|---------|
| `books` (default) | `book{N}-llama70b` → `configs/file/book{N}-llama70b.yaml` | `book3-llama70b` |
| `tomato` | `tomato_{N}` → `configs/file/tomato_{N}.yaml` | `tomato_3` |
| `paris` | `paris` → `configs/file/paris.yaml` | `paris` (same file every iteration) |

---

## Running a Range of Books

Process books 3 through 7 (default `books` mode and default model):

```bash
MODE=books ./scripts/run.sh 3 7
```

Process a single book (book 5 only):

```bash
MODE=books ./scripts/run.sh 5 5
```

Process tomato dataset files 1–10:

```bash
MODE=tomato ./scripts/run.sh 1 10
```

---

## Running All Books (Books 1–21)

The full book corpus spans indices 1 to 21. Each index maps to a config file named `book{N}-llama70b.yaml` under `configs/file/`. There are 21 books total.

```bash
MODE=books ./scripts/run.sh 1 21
```

Since `books` is the default `MODE` and `1 21` are the defaults, this is equivalent to:

```bash
./scripts/run.sh
```

There is also a dedicated convenience wrapper:

```bash
./scripts/run_books_llama.sh
```

---

## Running the Full Merged Corpus Dataset

A **single merged file** exists containing all 21 books concatenated into one text document (`full_gom_corpus.txt`). Its Hydra config is `configs/file/full_gom_corpus.yaml`. Use this when you want to ingest the entire corpus as a single run rather than book by book.

Use the dedicated wrapper:

```bash
./scripts/run_full_gom_corpus.sh
```
# Specifying the model

```bash
LLAMA_MODEL_OVERRIDE=llama3.3:70b ./scripts/run_full_gom_corpus.sh
```
LLAMA_MODEL_OVERRIDE=llama3.3:70b ./scripts/run_full_gom_corpus.sh

Or manually via `run.sh` using the `FILE_CFG` override (which bypasses the index-based config lookup):

```bash
FILE_CFG=full_gom_corpus MODE=books ./scripts/run.sh 1 1
```

`FILE_CFG` forces a specific config name regardless of the loop index. `BOOK_START=1 BOOK_END=1` ensures only one iteration runs.

Export the graph automatically after ingestion:

```bash
EXPORT_GRAPH=1 ./scripts/run_full_gom_corpus.sh
```

Custom chunk size for the full corpus:

```bash
CHUNK_SIZE=1200 CHUNK_OVERLAP=200 ./scripts/run_full_gom_corpus.sh
```

Run with the `test.yaml` file config instead of the full corpus (useful for quick sanity checks):

```bash
./scripts/run_full_gom_corpus.sh test
```

---

## Overriding the Model

The default model is `llama3.1:70b` (set by `LLAMA_MODEL_OVERRIDE`). This overrides the `llm.model` Hydra key at runtime. The model name must match what is available in your Ollama instance or the LLM endpoint you are using.

```bash
# Switch to llama3.3:70b
LLAMA_MODEL_OVERRIDE=llama3.3:70b MODE=books ./scripts/run.sh 1 21

# Use Mixtral 8x22b
LLAMA_MODEL_OVERRIDE=mixtral:8x22b MODE=books ./scripts/run.sh 1 5

# Use Qwen 2.5 72b
LLAMA_MODEL_OVERRIDE=qwen2.5:72b MODE=books ./scripts/run.sh 1 1

# Use a specific Mistral model
LLAMA_MODEL_OVERRIDE=mistral:7b MODE=books ./scripts/run.sh 1 1
```

For cloud providers such as OpenRouter, also set `LLM_BASE_URL_OVERRIDE` and ensure `OPENROUTER_API_KEY` is set in your `.env`:

```bash
LLAMA_MODEL_OVERRIDE=tngtech/deepseek-r1t2-chimera:free \
LLM_BASE_URL_OVERRIDE=https://openrouter.ai/api/v1 \
MODE=books ./scripts/run.sh 1 1
```

---

## Overriding the LLM and Embedder Base URLs

By default both the LLM and the embedder point to `http://localhost:11434/v1` (Ollama's OpenAI-compatible endpoint). Override them independently:

```bash
# Different LLM host (e.g. remote GPU server)
LLM_BASE_URL_OVERRIDE=http://192.168.1.50:11434/v1 \
MODE=books ./scripts/run.sh 1 5
```

```bash
# Different embedder host
EMBEDDER_BASE_URL_OVERRIDE=http://192.168.1.51:11434/v1 \
MODE=books ./scripts/run.sh 1 5
```

```bash
# Both overridden independently
LLM_BASE_URL_OVERRIDE=http://192.168.1.50:11434/v1 \
EMBEDDER_BASE_URL_OVERRIDE=http://192.168.1.51:11434/v1 \
MODE=books ./scripts/run.sh 1 21
```

---

## Overriding the Book / File Config

If you want to force a custom file config that doesn't follow the `book{N}-llama70b` naming convention, set `FILE_CFG`:

```bash
# Use configs/file/L_horticulture.yaml
FILE_CFG=L_horticulture MODE=books ./scripts/run.sh 1 1

# Use configs/file/paris.yaml explicitly
FILE_CFG=paris MODE=books ./scripts/run.sh 1 1

# Use configs/file/test.yaml (e.g. for a quick smoke test)
FILE_CFG=test MODE=books ./scripts/run.sh 1 1
```

`FILE_CFG` completely replaces the auto-generated config name derived from the loop index.

### Providing a file path directly (without a pre-existing config)

Call `run.py` directly with a `file.path` override to bypass the config files entirely:

```bash
python scripts/run.py create-tkg \
  --override "file.path=/data/my_custom_book.txt llm.model=llama3.1:70b"
```

---

## Overriding Chunk Size and Overlap

Text is split into chunks before ingestion. Defaults are `chunk_size=1000` and `chunk_overlap=150` (defined in `configs/text_splitter/default.yaml`). Override them:

```bash
CHUNK_SIZE=1500 CHUNK_OVERLAP=300 MODE=books ./scripts/run.sh 1 21
```

When chunk parameters are overridden, they are appended to the derived database name to prevent collisions with other runs. For example, processing book 3 with `CHUNK_SIZE=1500 CHUNK_OVERLAP=300` produces a database named something like `<book_stem>_cs1500_co300`.

---

## GPU Pinning

To bind execution to a specific GPU (sets `CUDA_VISIBLE_DEVICES` internally):

```bash
GPU=0 MODE=books ./scripts/run.sh 1 21
GPU=1 MODE=books ./scripts/run.sh 1 21
```

If `GPU` is unset (the default), `CUDA_VISIBLE_DEVICES` is left unset and CUDA uses all visible devices.

---

## Database Suffix (Parallel Runs)

When running multiple `run.sh` processes in parallel (e.g. on different GPUs or machines pointing to the same FalkorDB), use `DB_SUFFIX` to prevent database name collisions:

```bash
# Terminal 1 — GPU 0, books 1–10
GPU=0 DB_SUFFIX=gpu0 MODE=books ./scripts/run.sh 1 10

# Terminal 2 — GPU 1, books 11–21
GPU=1 DB_SUFFIX=gpu1 MODE=books ./scripts/run.sh 11 21
```

The suffix is appended to the derived database name: `<book_stem>_gpu0`, `<book_stem>_gpu1`, etc.

---

## Verifying and Exporting Graphs

### Graph Verification

After each successful run, `run.sh` checks that the graph actually appears in FalkorDB. This is on by default (`VERIFY_GRAPH=1`). To skip:

```bash
VERIFY_GRAPH=0 MODE=books ./scripts/run.sh 1 21
```

### Graph Export to TSV

To automatically export each graph to TSV files (`nodes_<name>.tsv` + `edges_<name>.tsv`) immediately after ingestion:

```bash
EXPORT_GRAPH=1 MODE=books ./scripts/run.sh 1 21
```

Exported files are written to `exported_data/<db_name>/` by default. Override the output directory:

```bash
EXPORT_GRAPH=1 EXPORT_DIR=/mnt/storage/exports MODE=books ./scripts/run.sh 1 21
```

---

## Retries and Fault Tolerance

If a run fails (non-zero exit from `run.py`), `run.sh` retries up to `MAX_RETRIES` times (default: `1`) before logging a failure and moving to the next item. Raise this for flaky network connections:

```bash
MAX_RETRIES=3 MODE=books ./scripts/run.sh 1 21
```

Failed runs produce a `logs/<db_name>/status_failed` marker file. The runner exits with a non-zero status if any item failed, making it easy to detect in CI pipelines.

---

## Logs

All stdout and stderr is written to `logs/<db_name>/out.log`. The terminal only displays a compact summary:

- Which item is being processed (`ITEM N/M  file=...  db=...`)
- A live progress line showing the current chunk (`chunk X/Y`) and elapsed time
- A final `DONE ✅` or `FAIL ❌` line with progress and elapsed time
- A `VERIFY` line confirming the graph exists in FalkorDB

Per-run artifacts inside `logs/<db_name>/`:

| File | Contents |
|------|----------|
| `out.log` | Full stdout + stderr from the Python pipeline |
| `print-config.json` | The fully resolved Hydra config used for that run |
| `start.cmd` | The exact shell command used to launch the run |
| `pid` | PID of the Python subprocess while running |
| `finished.txt` | Unix timestamp of successful completion |
| `status_failed` | Created if the run ultimately failed after all retries |
| `export.log` | Output from the TSV export step (if `EXPORT_GRAPH=1`) |

Global files under `logs/`:

| File | Contents |
|------|----------|
| `active_runner.pid` | PID of the current `run.sh` process |
| `active_job.pid` | PID of the currently active Python subprocess |
| `active_db.txt` | Name of the database currently being built |

---

## Killing a Running Job

To gracefully stop a running pipeline (terminates the active Python subprocess cleanly):

```bash
./scripts/kill_tkg.sh
```

You can also press `Ctrl+C` in the terminal running `run.sh` — the trap handler will kill the active Python job before exiting.

---

## run.py CLI Reference

`scripts/run.py` is the Typer-based CLI that `run.sh` calls internally. Invoke it directly for one-off operations or debugging.

### Create a temporal knowledge graph

```bash
python scripts/run.py create-tkg --override "file=book1-llama70b llm.model=llama3.1:70b"
```

Use `--print-config` to inspect the resolved configuration without running:

```bash
python scripts/run.py create-tkg --override "file=book1-llama70b" --print-config
```

### List all graphs in FalkorDB

```bash
python scripts/run.py list-graphs
python scripts/run.py list-graphs --host 192.168.1.100 --port 6380
```

### Drop (permanently delete) a graph

```bash
# With confirmation prompt
python scripts/run.py drop-graph my_graph_name

# Skip confirmation
python scripts/run.py drop-graph my_graph_name --force

# Remote FalkorDB
python scripts/run.py drop-graph my_graph_name --host 192.168.1.100 --port 6380 --force
```

### Export a graph to TSV

```bash
# Export all nodes and edges
python scripts/run.py export-graph my_graph_name --output-dir ./exported_data/my_graph

# Filter by group_id
python scripts/run.py export-graph my_graph_name \
  --output-dir ./out \
  --group-id b1-llama70b

# Remote FalkorDB
python scripts/run.py export-graph my_graph_name \
  --host 192.168.1.100 --port 6380 \
  --output-dir ./out
```

---

## Quick Reference

| Goal | Command |
|------|---------|
| Single book (book 1) | `./scripts/run.sh 1 1` |
| Books 3–7 | `MODE=books ./scripts/run.sh 3 7` |
| All 21 books | `./scripts/run.sh 1 21` |
| All books, different model | `LLAMA_MODEL_OVERRIDE=llama3.3:70b ./scripts/run.sh 1 21` |
| All books, export TSV | `EXPORT_GRAPH=1 ./scripts/run.sh 1 21` |
| All books, 2 retries | `MAX_RETRIES=2 ./scripts/run.sh 1 21` |
| Full merged corpus | `./scripts/run_full_gom_corpus.sh` |
| Full merged corpus + llama3.3:70B + export | ` LLAMA_MODEL_OVERRIDE=llama3.3:70b ./scripts/run_full_gom_corpus.sh `|
<!-- | Full corpus + export | `EXPORT_GRAPH=1 ./scripts/run_full_gom_corpus.sh` | -->
| Tomato dataset 1–10 | `MODE=tomato ./scripts/run.sh 1 10` |
| Custom chunk size | `CHUNK_SIZE=1500 CHUNK_OVERLAP=200 ./scripts/run.sh 1 21` |
| GPU 0 pin | `GPU=0 ./scripts/run.sh 1 21` |
| Parallel run (GPU 0) | `GPU=0 DB_SUFFIX=gpu0 ./scripts/run.sh 1 10` |
| Parallel run (GPU 1) | `GPU=1 DB_SUFFIX=gpu1 ./scripts/run.sh 11 21` |
| Remote LLM server | `LLM_BASE_URL_OVERRIDE=http://192.168.1.50:11434/v1 ./scripts/run.sh 1 21` |
| OpenRouter cloud model | `LLAMA_MODEL_OVERRIDE=tngtech/deepseek-r1t2-chimera:free LLM_BASE_URL_OVERRIDE=https://openrouter.ai/api/v1 ./scripts/run.sh 1 1` |
| Print resolved config | `python scripts/run.py create-tkg --override "file=book1-llama70b" --print-config` |
| List all graphs | `python scripts/run.py list-graphs` |
| Drop a graph | `python scripts/run.py drop-graph <name> --force` |
| Export a graph | `python scripts/run.py export-graph <name> --output-dir ./out` |
| Kill running job | `./scripts/kill_tkg.sh` | or Ctrl + C 
Note: MAX RETRIES = 2 (Cancel twice to stop the ingestion, one cancelation will stop 1st process and restart the ingestion)
