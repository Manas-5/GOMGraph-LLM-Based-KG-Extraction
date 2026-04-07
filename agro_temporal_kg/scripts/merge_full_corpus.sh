#!/usr/bin/env bash

# Merge the numbered GOM text files (1_*.txt ... 21_*.txt) into a single corpus,
# inserting strong separators so chunking won't straddle books.
# Output: /mnt/diskGum/manas/graph-dedup-patch/data/full_gom_corpus.txt

set -euo pipefail

DATA_DIR="/mnt/diskGum/manas/graph-dedup-patch/data"
OUT_FILE="${DATA_DIR}/full_gom_corpus.txt"
# Separator between books: a single newline.
SEP=$'\n'

echo "Writing ${OUT_FILE}"
> "${OUT_FILE}"

for i in $(seq 1 21); do
  file=$(ls "${DATA_DIR}/${i}_"*.txt 2>/dev/null | head -n 1 || true)
  if [[ -z "${file}" ]]; then
    echo "Warning: no file found for index ${i}" >&2
    continue
  fi
  echo "Appending ${file}"
  {
    cat "${file}"
    printf "%s" "${SEP}"
  } >> "${OUT_FILE}"
done

echo "Done."
