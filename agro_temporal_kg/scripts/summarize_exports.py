"""
Summarize exported graphs (final + per-chunk checkpoints) into a results table.

Usage:
  python agro_temporal_kg/scripts/summarize_exports.py \
    --export-root exported_data \
    --logs-root logs \
    --output results.csv \
    --target "Target Entity Name"
"""

import argparse
import csv
import json
from pathlib import Path


def read_config_meta(logs_root: Path, db_name: str) -> tuple[int | None, int | None]:
    cfg_path = logs_root / db_name / "print-config.json"
    if not cfg_path.exists():
        return None, None
    try:
        cfg = json.loads(cfg_path.read_text())
        chunk_size = cfg.get("text_splitter", {}).get("chunk_size")
        chunk_overlap = cfg.get("text_splitter", {}).get("chunk_overlap")
        return chunk_size, chunk_overlap
    except Exception:
        return None, None


def count_tsv(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as f:
        return sum(1 for _ in f) - 1  # minus header


def load_nodes(path: Path) -> dict[str, dict]:
    nodes: dict[str, dict] = {}
    if not path.exists():
        return nodes
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            uuid = row.get("uuid")
            if not uuid:
                continue
            nodes[uuid] = row
    return nodes


def load_edges(path: Path) -> dict[str, dict]:
    edges: dict[str, dict] = {}
    if not path.exists():
        return edges
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            uuid = row.get("uuid")
            if not uuid:
                continue
            edges[uuid] = row
    return edges


def merge_checkpoints(chk_root: Path) -> tuple[int, int, dict[str, dict], dict[str, dict]]:
    all_nodes: dict[str, dict] = {}
    all_edges: dict[str, dict] = {}
    for chunk_dir in sorted(chk_root.glob("chunk_*")):
        nodes = load_nodes(chunk_dir / "nodes.tsv")
        edges = load_edges(chunk_dir / "edges.tsv")
        all_nodes.update(nodes)
        all_edges.update(edges)
    return len(all_nodes), len(all_edges), all_nodes, all_edges


def count_target(nodes: dict[str, dict], target: str | None) -> int:
    if not target:
        return 0
    target_lower = target.lower()
    return sum(1 for row in nodes.values() if row.get("name", "").lower() == target_lower)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize graph exports.")
    parser.add_argument("--export-root", type=Path, default=Path("exported_data"))
    parser.add_argument("--logs-root", type=Path, default=Path("logs"))
    parser.add_argument("--output", type=Path, default=Path("results.csv"))
    parser.add_argument("--target", type=str, default=None, help="Target entity name to count")
    args = parser.parse_args()

    rows: list[dict] = []
    run_id = 1

    # Final exports (inter-chunk)
    for db_dir in sorted(args.export_root.iterdir()):
        if not db_dir.is_dir() or db_dir.name == "checkpoints":
            continue
        db_name = db_dir.name
        chunk_size, chunk_overlap = read_config_meta(args.logs_root, db_name)
        nodes = load_nodes(db_dir / "nodes.tsv")
        edges = load_edges(db_dir / "edges.tsv")
        rows.append(
            {
                "Run ID": run_id,
                "Deduplication Scope": "inter-chunk",
                "Chunk Size (tokens)": chunk_size or "",
                "Chunk Overlap (tokens)": chunk_overlap or "",
                "Total # Entities in KG": len(nodes),
                "Total # Edges in KG": len(edges),
                "# Appearances of Target Entity": count_target(nodes, args.target),
                "Notes / Errors / Observations": "",
                "Graph": db_name,
            }
        )
        run_id += 1

    # Checkpoint exports (intra-chunk)
    chk_root = args.export_root / "checkpoints"
    if chk_root.exists():
        for db_dir in sorted(chk_root.iterdir()):
            if not db_dir.is_dir():
                continue
            db_name = db_dir.name
            chunk_size, chunk_overlap = read_config_meta(args.logs_root, db_name)
            ent_count, edge_count, nodes, edges = merge_checkpoints(db_dir)
            rows.append(
                {
                    "Run ID": run_id,
                    "Deduplication Scope": "intra-chunk",
                    "Chunk Size (tokens)": chunk_size or "",
                    "Chunk Overlap (tokens)": chunk_overlap or "",
                    "Total # Entities in KG": ent_count,
                    "Total # Edges in KG": edge_count,
                    "# Appearances of Target Entity": count_target(nodes, args.target),
                    "Notes / Errors / Observations": "",
                    "Graph": db_name,
                }
            )
            run_id += 1

    fieldnames = [
        "Run ID",
        "Deduplication Scope",
        "Chunk Size (tokens)",
        "Chunk Overlap (tokens)",
        "Total # Entities in KG",
        "Total # Edges in KG",
        "# Appearances of Target Entity",
        "Notes / Errors / Observations",
        "Graph",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Wrote summary to {args.output}")


if __name__ == "__main__":
    main()
