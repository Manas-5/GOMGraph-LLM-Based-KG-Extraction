#!/usr/bin/env python3
"""
Build a histogram of edge counts per edge name from llm_reps_*.csv files.
Assumes each llm_reps_*.csv has a column 'total_count'.
"""

import argparse
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt


def load_counts(llm_reps_dir: Path):
    files = sorted(llm_reps_dir.glob("llm_reps_*.csv"))
    if not files:
        raise FileNotFoundError(f"No llm_reps_*.csv found in {llm_reps_dir}")
    counts = []
    for f in files:
        df = pd.read_csv(f)
        if "total_count" not in df.columns:
            raise ValueError(f"{f} missing total_count column")
        counts.extend(df["total_count"].tolist())
    return counts


def make_hist(counts, out_path: Path, bins: int):
    plt.rcParams.update({
        "font.family": "monospace",
        "font.monospace": ["Menlo", "Monaco", "SFMono-Regular", "Consolas", "Liberation Mono", "Courier New"],
    })
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.hist(counts, bins=bins, color="#e34234", edgecolor="#0f172a", alpha=0.85)
    ax.set_xlabel("Edges per Edge Name (total_count)")
    ax.set_ylabel("Frequency")
    ax.set_title("Histogram of Edge Counts per Edge Name")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=190)
    print(f"Wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description="Histogram of edge counts per edge name from llm_reps_*.csv.")
    ap.add_argument(
        "--llm-reps-dir",
        default="/mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/scripts/llm_reps",
        help="Directory containing llm_reps_*.csv files.",
    )
    ap.add_argument(
        "--out-dir",
        default="/mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/scripts/distrubution_out",
        help="Directory to write histogram PNG.",
    )
    ap.add_argument("--out-name", default="edge_count_hist.png", help="Filename for the histogram PNG.")
    ap.add_argument("--bins", type=int, default=20, help="Number of bins for histogram.")
    args = ap.parse_args()

    llm_dir = Path(args.llm_reps_dir)
    out_dir = Path(args.out_dir)
    counts = load_counts(llm_dir)
    out_path = out_dir / args.out_name
    make_hist(counts, out_path, bins=args.bins)


if __name__ == "__main__":
    main()
