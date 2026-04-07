#!/usr/bin/env bash
set -euo pipefail

# Export a range of book graphs (created by run_books_llama.sh) to TSV using:
#   uv run python scripts/run.py export-graph <graph_name>
#
# Naming convention used by your pipeline:
#   graph_name = book${N}_ent_1_edge_0_prompt_new
#
# Output:
#   exported_data/<graph_name>/nodes.tsv
#   exported_data/<graph_name>/edges.tsv
#
# Usage:
#   ./scripts/export_books_graphs.sh 2 21
#   ./scripts/export_books_graphs.sh 2 21 exported_data
#
# Optional env vars:
#   FALKOR_HOST   (default: localhost)
#   FALKOR_PORT   (default: 6380)

# Usage

# chmod +x scripts/export_books_graphs.sh
# ./scripts/export_books_graphs.sh 2 21

# FALKOR_HOST=10.0.7.22 FALKOR_PORT=6380 ./scripts/export_books_graphs.sh 2 21



BOOK_START=${1:-1}
BOOK_END=${2:-21}
OUT_ROOT=${3:-"exported_data"}

FALKOR_HOST=${FALKOR_HOST:-"localhost"}
FALKOR_PORT=${FALKOR_PORT:-6380}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TOTAL=$((BOOK_END - BOOK_START + 1))
if (( TOTAL <= 0 )); then
  echo "No books in range ${BOOK_START}..${BOOK_END}; exiting."
  exit 0
fi

mkdir -p "$OUT_ROOT"

echo "[export_books_graphs] Exporting graphs for books ${BOOK_START}..${BOOK_END}"
echo "[export_books_graphs] FalkorDB: ${FALKOR_HOST}:${FALKOR_PORT}"
echo "[export_books_graphs] Output root: ${OUT_ROOT}"
echo

for ((b=BOOK_START; b<=BOOK_END; b++)); do
  graph_name="book${b}_ent_1_edge_0_prompt_new"
  out_dir="${OUT_ROOT}/${graph_name}"
  mkdir -p "$out_dir"

  echo "============================================================"
  echo "[export_books_graphs] Exporting: ${graph_name} -> ${out_dir}"
  echo "============================================================"

  # Export full graph (no group filter); uses uv environment.
  # Note: your CLI command name is export_graph in code, but Typer exposes it as "export-graph".
  uv run python scripts/run.py export-graph "$graph_name" \
    --output-dir "$out_dir" \
    --host "$FALKOR_HOST" \
    --port "$FALKOR_PORT"

  echo
done

echo "[export_books_graphs] Done. Exports under: ${OUT_ROOT}"
