#!/usr/bin/env python3
"""
For each llm_reps_*.csv, plot:
  1) Histogram of total_count (edges per edge name)
  2) Cumulative distribution (ECDF) of total_count
Outputs one PNG per threshold file.
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def load_per_file(llm_reps_dir: Path):
    files = sorted(llm_reps_dir.glob("llm_reps_*.csv"))
    if not files:
        raise FileNotFoundError(f"No llm_reps_*.csv found in {llm_reps_dir}")
    data = []
    for f in files:
        df = pd.read_csv(f)
        if "total_count" not in df.columns:
            raise ValueError(f"{f} missing total_count column")
        counts = df["total_count"].dropna().to_numpy()
        # Extract threshold from filename if present
        try:
            thr = float(f.stem.split("_")[-1])
        except Exception:
            thr = None
        data.append((f.name, thr, counts))
    return data


def plot_hist_and_cdf(name: str, thr, counts, out_path: Path, bin_step: int, cutoff: int):
    plt.rcParams.update({
        "font.family": "monospace",
        "font.monospace": ["Menlo", "Monaco", "SFMono-Regular", "Consolas", "Liberation Mono", "Courier New"],
    })

    counts_arr = np.asarray(counts, dtype=float)
    # Avoid log(0): bump zeros to 1
    zero_mask = counts_arr == 0
    if zero_mask.any():
        counts_arr[zero_mask] = 1.0

    # Clip to create an overflow bin > cutoff
    clipped = counts_arr.copy()
    clipped[clipped > cutoff] = cutoff + 1

    # Bin edges: small bins up to cutoff, then overflow bin edge
    bin_edges = list(range(0, cutoff + 1, bin_step))
    if bin_edges[-1] < cutoff:
        bin_edges.append(cutoff)
    bin_edges.append(cutoff + 1.1)  # overflow bin upper edge

    fig, (ax_hist, ax_cdf) = plt.subplots(2, 1, figsize=(7, 7), sharex=False)
    title = f"Threshold {thr:.2f}" if thr is not None else name

    # Histogram
    ax_hist.hist(clipped, bins=bin_edges, color="#e34234", edgecolor="#0f172a", alpha=0.85)
    ax_hist.set_xscale("log")
    ax_hist.set_ylabel("Frequency")
    ax_hist.set_title(f"Histogram of Edge Counts per Edge Name ({title})")
    ax_hist.grid(True, alpha=0.3)
    ax_hist.set_xticks([1, 2, 5, 10, 20, 50, cutoff, cutoff + 1])
    ax_hist.get_xaxis().set_major_formatter(plt.ScalarFormatter())
    ax_hist.ticklabel_format(style="plain", axis="x")

    # CDF
    sorted_counts = np.sort(counts_arr)
    y = np.arange(1, len(sorted_counts) + 1) / len(sorted_counts)
    ax_cdf.plot(sorted_counts, y, color="#0f172a", linewidth=2.2)
    ax_cdf.set_xscale("log")
    ax_cdf.set_xlabel("Edges per Edge Name (total_count)")
    ax_cdf.set_ylabel("Cumulative fraction")
    ax_cdf.set_title("Cumulative Distribution")
    ax_cdf.grid(True, alpha=0.3)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=190)
    print(f"Wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description="Per-threshold histogram and cumulative curve of total_count.")
    ap.add_argument(
        "--llm-reps-dir",
        default="/mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/scripts/llm_reps",
        help="Directory containing llm_reps_*.csv files.",
    )
    ap.add_argument(
        "--out-dir",
        default="/mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/scripts/distrubution_out",
        help="Directory to write plots.",
    )
    ap.add_argument("--bin-step", type=int, default=1, help="Bin width up to cutoff (default 1).")
    ap.add_argument("--cutoff", type=int, default=50, help="Max value for fine bins; values above go to overflow bin.")
    args = ap.parse_args()

    llm_dir = Path(args.llm_reps_dir)
    out_dir = Path(args.out_dir)
    data = load_per_file(llm_dir)

    for name, thr, counts in data:
        label = f"{thr:.2f}" if thr is not None else name
        out_path = out_dir / f"edge_count_hist_cdf_thr_{label}.png"
        plot_hist_and_cdf(name, thr, counts, out_path, bin_step=args.bin_step, cutoff=args.cutoff)


if __name__ == "__main__":
    main()
