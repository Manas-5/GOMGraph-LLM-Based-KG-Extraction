#!/usr/bin/env python3
"""
Utilities for single-model KG experiments (Graphiti + FalkorDB).

This module exposes:
- sanitize_model_name()
- OllamaChunkLogTracker
- async process_model(...)

process_model does:
- create / reset a FalkorDB graph per iteration,
- run Graphiti.add_episode() over all chunks,
- track per-chunk warnings/errors from Ollama logs,
- capture Graphiti core logs to a file,
- generate:
    * per-chunk log files (warnings + errors),
    * a bar chart of nodes & edges per chunk,
    * metrics_document.txt with chunkwise aggregated info.
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.openai import OpenAIEmbedder
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EpisodeType

from agro_temporal_kg.ollama_graphiti_client import OllamaGraphitiClient


# -------------------------------------------------------------------
# ERROR TYPE BUCKETS
# -------------------------------------------------------------------

ERROR_TYPES = [
    "Pydantic validation",
    "Fallback empty structure",
    "JSON parsing error",
    "Unexpected type",
    "Graphiti core exception",
    "Other",
]

logger = logging.getLogger(__name__)


def sanitize_model_name(model_name: str) -> str:
    """
    Sanitize model name so it can be safely used in folder / filenames.

    Example:
        "llama3.1:70b" -> "llama3-1-70b"
    """
    sanitized = model_name.lower()
    sanitized = sanitized.replace(":", "-")
    sanitized = sanitized.replace(".", "-")
    sanitized = sanitized.replace(" ", "-")
    return sanitized


class OllamaChunkLogTracker(logging.Handler):
    """
    Logging handler that listens to OllamaGraphitiClient logs and:
    - increments per-chunk error/warning counters
    - stores the actual messages per chunk
    - increments error-type buckets for a histogram
    """

    def __init__(
        self,
        get_current_chunk_idx,
        errors_by_chunk_idx,
        warnings_by_chunk_idx,
        error_msgs,
        warning_msgs,
        error_type_counts,
    ):
        super().__init__()
        self.get_current_chunk_idx = get_current_chunk_idx
        self.errors_by_chunk_idx = errors_by_chunk_idx
        self.warnings_by_chunk_idx = warnings_by_chunk_idx
        self.error_msgs = error_msgs        # dict[int, list[str]]
        self.warning_msgs = warning_msgs    # dict[int, list[str]]
        self.error_type_counts = error_type_counts  # dict[str, int]

    def _classify_message(self, msg: str) -> str:
        if "Pydantic validation" in msg:
            return "Pydantic validation"
        if "Using empty fallback structure instead" in msg:
            return "Fallback empty structure"
        if "JSON parsing error from Ollama" in msg or "JSONDecodeError from Ollama" in msg:
            return "JSON parsing error"
        if "Unexpected response type from Ollama" in msg:
            return "Unexpected type"
        if "Graphiti core exception" in msg:
            return "Graphiti core exception"
        return "Other"

    def emit(self, record: logging.LogRecord) -> None:
        idx = self.get_current_chunk_idx()
        if idx is None:
            return

        array_index = idx - 1
        if array_index < 0 or array_index >= len(self.errors_by_chunk_idx):
            return

        msg_text = record.getMessage()
        category = self._classify_message(msg_text)
        self.error_type_counts[category] = self.error_type_counts.get(category, 0) + 1

        if record.levelno >= logging.ERROR:
            self.errors_by_chunk_idx[array_index] += 1
            self.error_msgs[idx].append(msg_text)
        elif record.levelno == logging.WARNING:
            self.warnings_by_chunk_idx[array_index] += 1
            self.warning_msgs[idx].append(msg_text)


# -------------------------------------------------------------------
# PER-MODEL PROCESSING
# -------------------------------------------------------------------
async def process_model(
    model_name: str,
    chunks: List[str],
    basename: str,
    text_file_path: str,
    embedder: OpenAIEmbedder,
    per_model_root: Path,
    num_iterations: int,
    graph_name_base: str,
) -> dict:
    """
    Run the KG + basic visualization pipeline for a single model and a single text file.

    Parameters
    ----------
    model_name: str
        Ollama model name (e.g. "llama3.1:70b").
    chunks: list[str]
        Text chunks to feed to Graphiti.
    basename: str
        Base name used in episode names (e.g. file stem).
    text_file_path: str
        Original source text file path (for logging).
    embedder: OpenAIEmbedder
        Shared embedder instance.
    per_model_root: Path
        Root dir for all outputs: model_outputs/<...>.
    num_iterations: int
        Number of runs (usually 1 for your use case).
    graph_name_base: str
        Desired graph name base. If num_iterations == 1,
        the Falkor graph name is EXACTLY this string.
        If num_iterations > 1, we append "-iter-<k>".

    Returns
    -------
    dict
        Summary with basic totals for this text file.
    """

    print("\n" + "=" * 80)
    print(f" Starting processing for model: {model_name}")
    print(f"📄 Source file: {text_file_path}")
    print("=" * 80)

    # Per-model-and-text folder: model_outputs/<sanitized_model_name>/<graph_name_base>/
    sanitized_model_name = sanitize_model_name(model_name)
    model_root_dir = per_model_root / sanitized_model_name / graph_name_base
    model_root_dir.mkdir(parents=True, exist_ok=True)

    # Containers for totals per iteration
    iter_total_nodes: list[int] = []
    iter_total_edges: list[int] = []
    iter_total_warnings: list[int] = []
    iter_total_errors: list[int] = []
    iter_total_times: list[float] = []
    iter_graph_names: list[str] = []

    # LLM client & cross encoder reused across iterations
    llm_config = LLMConfig(
        api_key="abc",  # dummy, Ollama doesn't need this
        model=model_name,
        base_url="http://localhost:11434/v1",
        temperature=0.0,
    )
    llm_client = OllamaGraphitiClient(config=llm_config)
    cross_encoder = OpenAIRerankerClient(config=llm_config, client=llm_client)

    total_chunks = len(chunks)
    chunk_lengths = [len(c) for c in chunks]

    for iteration in range(1, num_iterations + 1):
        print("\n" + "-" * 80)
        print(f"Model {model_name} — Iteration {iteration}/{num_iterations}")
        print("-" * 80)

        # Graph name logic:
        # - if just one iteration, graph_name = graph_name_base   (== file stem)
        # - otherwise, append -iter-<n>
        if num_iterations == 1:
            graph_name = graph_name_base
        else:
            graph_name = f"{graph_name_base}-iter-{iteration}"
        iter_graph_names.append(graph_name)

        # Per-iteration folder: model_outputs/<model>/<graph_name_base>/iter_<n>/
        output_dir = model_root_dir / f"iter_{iteration}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # FalkorDB driver for this iteration
        driver = FalkorDriver(
            host="localhost",
            port=6380,
            database=graph_name,
        )

        # Try to delete any existing graph with this iteration name
        try:
            print(f"Attempting to delete graph '{driver._database}'...")
            graph_obj = driver._get_graph(driver._database)  # sync getter
            await graph_obj.delete()
            print(f"Graph '{driver._database}' deleted successfully.")
        except Exception as e:
            print(f"Could not delete graph (this is OK if it's the first run): {e}")

        graphiti = Graphiti(
            graph_driver=driver,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=cross_encoder,
        )

        processed_chunk_indices: list[int] = []
        nodes_by_chunk_idx: list[int] = [0] * total_chunks
        edges_by_chunk_idx: list[int] = [0] * total_chunks
        processing_time_by_chunk_idx: list[float] = [0.0] * total_chunks

        errors_by_chunk_idx: list[int] = [0] * total_chunks
        warnings_by_chunk_idx: list[int] = [0] * total_chunks

        error_msgs: dict[int, list[str]] = {i: [] for i in range(1, total_chunks + 1)}
        warning_msgs: dict[int, list[str]] = {i: [] for i in range(1, total_chunks + 1)}

        error_type_counts: dict[str, int] = {t: 0 for t in ERROR_TYPES}

        # --- SETUP LOG TRACKING FOR THIS ITERATION (Ollama logs) ---
        current_chunk = {"idx": None}

        def get_current_chunk_idx():
            return current_chunk["idx"]

        ollama_logger_name = "agro_temporal_kg.ollama_graphiti_client"
        ollama_logger = logging.getLogger(ollama_logger_name)
        ollama_logger.setLevel(logging.DEBUG)

        tracker_handler = OllamaChunkLogTracker(
            get_current_chunk_idx=get_current_chunk_idx,
            errors_by_chunk_idx=errors_by_chunk_idx,
            warnings_by_chunk_idx=warnings_by_chunk_idx,
            error_msgs=error_msgs,
            warning_msgs=warning_msgs,
            error_type_counts=error_type_counts,
        )
        tracker_handler.setLevel(logging.WARNING)  # WARNING & ERROR
        ollama_logger.addHandler(tracker_handler)

        # --- SETUP GRAPHITI CORE LOG FILE FOR THIS ITERATION ---
        graphiti_logger_name = "graphiti_core"  # root logger for Graphiti internals
        graphiti_logger = logging.getLogger(graphiti_logger_name)
        graphiti_logger.setLevel(logging.INFO)

        graphiti_log_path = output_dir / f"{graph_name}_graphiti_core_logs.txt"
        graphiti_file_handler = logging.FileHandler(graphiti_log_path, encoding="utf-8")
        graphiti_file_handler.setLevel(logging.INFO)
        graphiti_file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
            )
        )
        graphiti_logger.addHandler(graphiti_file_handler)

        print(f"📄 Graphiti core logs for this iteration → {graphiti_log_path}")

        start_time = time.perf_counter()
        print("\nCreating temporal knowledge graph for this iteration...")

        try:
            for idx, chunk in enumerate(chunks, 1):
                print(
                    f"\n[{model_name} / iter {iteration}] Processing chunk "
                    f"{idx}/{len(chunks)} (length: {chunk_lengths[idx-1]} chars)..."
                )

                processed_chunk_indices.append(idx)
                current_chunk["idx"] = idx

                t0 = time.perf_counter()
                try:
                    result = await graphiti.add_episode(
                        name=f"{basename}-part_{idx}",
                        source_description=(
                            "French gardening manual containing "
                            "comprehensive vegetable gardening calendar, "
                            "weather predictions, soil amendments, and agricultural "
                            "techniques"
                        ),
                        episode_body=chunk,
                        group_id="the_french_gardener",
                        reference_time=datetime(1880, 1, 1),
                        source=EpisodeType.text,
                    )
                    duration = time.perf_counter() - t0
                    processing_time_by_chunk_idx[idx - 1] = duration

                    this_nodes = getattr(result, "nodes", [])
                    this_edges = getattr(result, "edges", [])

                    num_nodes = len(this_nodes)
                    num_edges = len(this_edges)

                    nodes_by_chunk_idx[idx - 1] = num_nodes
                    edges_by_chunk_idx[idx - 1] = num_edges

                    print(
                        f"✅ [{model_name} / iter {iteration}] Chunk {idx} OK "
                        f"(Nodes: {num_nodes}, Edges: {num_edges}, "
                        f"Warnings: {warnings_by_chunk_idx[idx - 1]}, "
                        f"Errors: {errors_by_chunk_idx[idx - 1]}, "
                        f"Time: {duration:.3f}s)"
                    )

                except Exception as e:
                    duration = time.perf_counter() - t0
                    processing_time_by_chunk_idx[idx - 1] = duration

                    errors_by_chunk_idx[idx - 1] += 1
                    msg = f"Graphiti core exception: {repr(e)}"
                    error_msgs[idx].append(msg)
                    error_type_counts["Graphiti core exception"] = (
                        error_type_counts.get("Graphiti core exception", 0) + 1
                    )

                    print(
                        f"❌ [{model_name} / iter {iteration}] Error processing chunk {idx}: {e} "
                        f"(Time: {duration:.3f}s)"
                    )

            end_time = time.perf_counter()
            total_processing_time_sec = end_time - start_time

        finally:
            current_chunk["idx"] = None
            ollama_logger.removeHandler(tracker_handler)

            graphiti_logger.removeHandler(graphiti_file_handler)
            graphiti_file_handler.close()

        print(
            f"\n✅ [{model_name} / iter {iteration}] All chunks processed for graph '{graph_name}'"
        )

        # ---------- ITERATION-LEVEL METRICS ----------
        total_processed_chunks = len(processed_chunk_indices)
        total_chars_all_chunks = sum(chunk_lengths)
        total_chars_processed_chunks = sum(
            chunk_lengths[i - 1] for i in processed_chunk_indices
        )

        total_nodes = sum(nodes_by_chunk_idx)
        total_edges = sum(edges_by_chunk_idx)
        total_errors = sum(errors_by_chunk_idx)
        total_warnings = sum(warnings_by_chunk_idx)

        iter_total_nodes.append(total_nodes)
        iter_total_edges.append(total_edges)
        iter_total_warnings.append(total_warnings)
        iter_total_errors.append(total_errors)
        iter_total_times.append(total_processing_time_sec)

        successful_indices = [
            i for i in range(1, total_chunks + 1)
            if errors_by_chunk_idx[i - 1] == 0 and warnings_by_chunk_idx[i - 1] == 0
        ]

        # ---------- WRITE PER-CHUNK LOG FILES ----------
        chunk_indices = list(range(1, total_chunks + 1))
        for idx in chunk_indices:
            log_path = output_dir / f"chunk_{idx}_logs.txt"
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write(f"Logs for model '{model_name}', iteration {iteration}, chunk {idx}\n")
                lf.write("=" * 80 + "\n\n")
                for msg in warning_msgs[idx]:
                    lf.write("[WARNING] " + msg + "\n")
                for msg in error_msgs[idx]:
                    lf.write("[ERROR] " + msg + "\n")

        # ---------- METRICS DOCUMENT (PER ITERATION) ----------
        metrics_path = output_dir / "metrics_document.txt"
        lines: list[str] = []
        lines.append(f"Graph name: {graph_name}")
        lines.append(f"Model name: {model_name}")
        lines.append(f"Iteration: {iteration}")
        lines.append(f"Source file: {text_file_path}")
        lines.append("")
        lines.append(f"Total chunks (after splitting): {total_chunks}")
        lines.append(f"Total processed chunks: {total_processed_chunks}")
        lines.append(f"Total characters (all chunks): {total_chars_all_chunks}")
        lines.append(
            f"Total characters (processed chunks): {total_chars_processed_chunks}"
        )
        lines.append("")
        lines.append(f"Total processing time (seconds): {total_processing_time_sec:.3f}")
        lines.append(f"Total nodes (approx): {total_nodes}")
        lines.append(f"Total edges (approx): {total_edges}")
        lines.append(f"Total warnings (Ollama + Graphiti): {total_warnings}")
        lines.append(f"Total errors (Ollama + Graphiti): {total_errors}")
        lines.append("")
        lines.append("Error type histogram (this model, this iteration):")
        for k in ERROR_TYPES:
            lines.append(f"  {k}: {error_type_counts.get(k, 0)}")
        lines.append("")
        lines.append(
            "Successful chunks with no errors/warnings: "
            + (", ".join(map(str, successful_indices)) if successful_indices else "NONE")
        )
        lines.append("")
        lines.append("=" * 80)
        lines.append("DETAILED CHUNK INFORMATION")
        lines.append("=" * 80)

        for idx, length in enumerate(chunk_lengths, 1):
            processed_flag = "PROCESSED" if idx in chunk_indices else "SKIPPED"
            nodes_here = nodes_by_chunk_idx[idx - 1]
            edges_here = edges_by_chunk_idx[idx - 1]
            time_here = processing_time_by_chunk_idx[idx - 1]
            errs_here = errors_by_chunk_idx[idx - 1]
            warns_here = warnings_by_chunk_idx[idx - 1]

            lines.append("")
            lines.append(f"--- CHUNK {idx} ---")
            lines.append(f"Status: {processed_flag}")
            lines.append(f"Length: {length} characters")
            lines.append(f"Nodes created (approx): {nodes_here}")
            lines.append(f"Edges created (approx): {edges_here}")
            lines.append(f"Ollama warnings: {warns_here}")
            if warning_msgs[idx]:
                lines.append("Warning messages:")
                for msg in warning_msgs[idx]:
                    lines.append(f"  - {msg}")
            lines.append(f"Ollama/Graphiti errors: {errs_here}")
            if error_msgs[idx]:
                lines.append("Error messages:")
                for msg in error_msgs[idx]:
                    lines.append(f"  - {msg}")
            lines.append(f"Processing time: {time_here:.3f} seconds")
            lines.append("")
            lines.append("Chunk Text:")
            lines.append(chunks[idx - 1])
            lines.append("-" * 80)

        with open(metrics_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"\n📄 [{model_name} / iter {iteration}] Metrics document written to: {metrics_path}")



                # ---------- PER-ITERATION VISUAL: TOTAL NODES VS TOTAL EDGES ----------
        plt.figure(figsize=(6, 6))
        labels = ["Total nodes", "Total edges"]
        values = [total_nodes, total_edges]

        plt.bar(labels, values)
        plt.ylabel("Count")
        plt.title(
            f"[{model_name} / iter {iteration}] Total nodes vs edges for '{graph_name}'"
        )
        plt.grid(True, linestyle="--", axis="y", alpha=0.4)
        total_ne_png = output_dir / f"{graph_name}_total_nodes_vs_edges.png"
        plt.tight_layout()
        plt.savefig(total_ne_png, dpi=150)
        plt.close()

        print(
            f"📊 [{model_name} / iter {iteration}] Total nodes vs edges plot → {total_ne_png}"
        )


        # # ---------- PER-ITERATION VISUAL: NODES & EDGES PER CHUNK ----------
        # plt.figure(figsize=(12, 6))
        # x_axis = list(range(1, total_chunks + 1))
        # width = 0.4
        # plt.bar(
        #     [x - width / 2 for x in x_axis],
        #     nodes_by_chunk_idx,
        #     width,
        #     label="Nodes",
        # )
        # plt.bar(
        #     [x + width / 2 for x in x_axis],
        #     edges_by_chunk_idx,
        #     width,
        #     label="Edges",
        # )
        # plt.xlabel("Chunk index")
        # plt.ylabel("Count")
        # plt.title(
        #     f"[{model_name} / iter {iteration}] Nodes & edges per chunk index for '{graph_name}'"
        # )
        # plt.xticks(ticks=x_axis, labels=x_axis)
        # plt.legend()
        # plt.grid(True, linestyle="--", alpha=0.4)
        # ne_png = output_dir / f"{graph_name}_nodes_edges_per_chunk.png"
        # plt.tight_layout()
        # plt.savefig(ne_png, dpi=150)
        # plt.close()

        # print(f"📊 [{model_name} / iter {iteration}] Nodes & edges per chunk plot → {ne_png}")

        # problem_chunks = [
        #     i for i in range(1, total_chunks + 1)
        #     if errors_by_chunk_idx[i - 1] > 0 or warnings_by_chunk_idx[i - 1] > 0
        # ]
        # if problem_chunks:
        #     print(f"[{model_name} / iter {iteration}] Chunks with warnings/errors: {problem_chunks}")
        # else:
        #     print(f"[{model_name} / iter {iteration}] No warnings/errors recorded at chunk level.")

        # print(f"\n[{model_name} / iter {iteration}] Finished all per-iteration outputs.\n")

    # ----------------------------------------------------------------
    # AFTER ALL ITERATIONS FOR THIS MODEL AND TEXT FILE
    # ----------------------------------------------------------------
    total_nodes_all = sum(iter_total_nodes)
    total_edges_all = sum(iter_total_edges)
    total_time_all = sum(iter_total_times)
    total_warnings_all = sum(iter_total_warnings)
    total_errors_all = sum(iter_total_errors)

    print(
        f"\n📊 [{model_name}] Summary across {num_iterations} iteration(s) for graph '{graph_name_base}':"
        f"\n   Total nodes   : {total_nodes_all}"
        f"\n   Total edges   : {total_edges_all}"
        f"\n   Total time (s): {total_time_all:.3f}"
        f"\n   Total warnings: {total_warnings_all}"
        f"\n   Total errors  : {total_errors_all}"
    )

    # Final summary dict used by the runner
    return {
        "model_name": model_name,
        "graph_names": iter_graph_names,
        "total_nodes": total_nodes_all,
        "total_edges": total_edges_all,
        "total_time_sec": total_time_all,
        "warnings": total_warnings_all,
        "errors": total_errors_all,
    }
