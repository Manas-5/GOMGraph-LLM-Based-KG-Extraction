#!/usr/bin/env python3
"""
Runner script for single-model KG experiments over MULTIPLE text files.

This version:
- finds all .txt files whose names look like "<N>_<something>.txt"
- sorts them by N (numeric prefix)
- for each file:
    * reads and chunks the text
    * runs process_model(...) ONCE (num_iterations = 1)
    * uses the text file's stem as the graph name

Per-file outputs (logs, metrics, plots) are written under:
    model_outputs/<sanitized_model_name>/<graph_name_base>/iter_1/
"""

import asyncio
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter

from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

from books_kg_eval_utils import process_model

# Load environment variables from .env file
load_dotenv()

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------

# Single model (you can change this if needed)
MODELS = [
    "llama3.1:70b",
]

# Only ONE iteration per text file
NUM_ITERATIONS = 1

# Directory containing your input .txt files
# TEXT_DIR = Path("/mnt/diskGum/manas/agro_temporal_kg/data/multi_texts")
TEXT_DIR = Path("/mnt/diskGum/manas/agro_temporal_kg/data")

# Pattern: "<number>_<anything>.txt"
FILENAME_PATTERN = re.compile(r"^(\d+)_.*\.txt$")


def find_ordered_text_files(text_dir: Path) -> list[Path]:
    """
    Find all .txt files in `text_dir` with names like '1_name.txt', '2_other.txt',
    and return them sorted by the leading number.
    """
    files_with_idx = []

    for p in text_dir.glob("*.txt"):
        m = FILENAME_PATTERN.match(p.name)
        if not m:
            continue
        idx = int(m.group(1))
        files_with_idx.append((idx, p))

    files_with_idx.sort(key=lambda t: t[0])
    return [p for _, p in files_with_idx]


async def main():
    """Process all matching text files in numeric order, for a single model."""

    # Shared embedder (Ollama-compatible OpenAIEmbedder wrapper)
    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key="abc",  # Ollama ignores this
            base_url="http://localhost:11434/v1",
            embedding_model="bge-m3:567m",
            embedding_dim=768,
        )
    )

    # Root folder for per-model outputs
    per_model_root = Path("model_outputs")
    per_model_root.mkdir(parents=True, exist_ok=True)

    # Collect ordered text files
    text_files = find_ordered_text_files(TEXT_DIR)
    if not text_files:
        print(f"No matching text files found in: {TEXT_DIR}")
        return

    print("Found the following files to process (in order):")
    for p in text_files:
        print("  -", p.name)

    # Support multiple models (currently just one)
    for model_name in MODELS:
        print("\n" + "=" * 80)
        print(f"MODEL: {model_name}")
        print("=" * 80)

        for text_file_path in text_files:
            print("\n" + "-" * 80)
            print(f"📄 Processing file: {text_file_path.name}")
            print("-" * 80)

            # Graph name base = file stem, e.g. "1_some_name"
            graph_name_base = text_file_path.stem

            # Read the text
            with open(text_file_path, encoding="utf-8") as f:
                text_content = f.read()
            print(
                f"Text file loaded successfully. "
                f"Length: {len(text_content)} characters"
            )

            # Chunk the text
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1_000,
                chunk_overlap=150,
                length_function=len,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            chunks = text_splitter.split_text(text_content)
            print(f"Split text into {len(chunks)} chunks")

            # Run the model for this one text file
            summary = await process_model(
                model_name=model_name,
                chunks=chunks,
                basename=graph_name_base,          # for episode names
                text_file_path=str(text_file_path),
                embedder=embedder,
                per_model_root=per_model_root,
                num_iterations=NUM_ITERATIONS,     # 1
                graph_name_base=graph_name_base,   # graph name == file stem
            )

            print("\n✅ Finished file:", text_file_path.name)
            print(f"   Graph name    : {summary['graph_names'][0]}")
            print(f"   Total nodes   : {summary['total_nodes']}")
            print(f"   Total edges   : {summary['total_edges']}")
            print(f"   Total time (s): {summary['total_time_sec']:.3f}")
            print(f"   Warnings      : {summary['warnings']}")
            print(f"   Errors        : {summary['errors']}")
            print("-" * 80)

        print("\n" + "=" * 80)
        print(f" Completed all files for model: {model_name}")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
