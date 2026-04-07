#!/usr/bin/env python3
import argparse
import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def parse_thresholds(thr_str, default_list):
    """Parse comma list or fallback to provided default list."""
    if thr_str:
        return [float(x) for x in thr_str.split(",")]
    return default_list


def load_original_unique(path):
    df = pd.read_csv(path, dtype=str)
    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])
    if "name" not in df.columns:
        raise ValueError("collapse file must have a 'name' column")
    return df["name"].nunique()


def load_cluster_unique(cluster_file):
    df = pd.read_csv(cluster_file, dtype=str)
    return len(df)


def find_cluster_file(cluster_dir: Path, sim: float):
    """Return path to merged/collapsed file for given similarity, trying common names."""
    fmt_vals = [f"{sim:.2f}", f"{sim:.1f}", f"{sim:.0f}"]
    candidates = []
    for v in fmt_vals:
        candidates.append(cluster_dir / f"merged_sim_{v}.csv")
        candidates.append(cluster_dir / f"collapsed_sim_{v}.csv")
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(f"Missing cluster file for similarity {sim:.2f} (checked: {', '.join(str(c) for c in candidates)})")


def make_plots(thresholds, uniques, ratios, out_dir, x_label="Cosine similarity threshold"):
    plt.style.use("seaborn-v0_8-whitegrid")

    # Ratio plot
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.plot(thresholds, ratios, marker="o", markersize=7, linewidth=2.4,
            color="#2563eb", markerfacecolor="#60a5fa", markeredgecolor="#1d4ed8")
    for x, y in zip(thresholds, ratios):
        ax.text(x, y, f"{y:.3f}", ha="center", va="bottom", fontsize=9, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#cbd5e1", alpha=0.9))
    ax.set_xlabel(x_label, fontsize=11)
    ax.set_ylabel("Retention ratio (unique_after / unique_original)", fontsize=11)
    ax.set_title("Edge-name retention vs threshold", fontsize=13, fontweight="bold")
    ax.set_ylim(0, 1.05)
    ax.tick_params(labelsize=10)
    ratio_png = Path(out_dir) / "ratio_vs_threshold.png"
    fig.tight_layout()
    fig.savefig(ratio_png, bbox_inches="tight", dpi=180)

    # Unique counts plot
    fig2, ax2 = plt.subplots(figsize=(7.2, 4.6))
    ax2.plot(thresholds, uniques, marker="o", markersize=7, linewidth=2.4,
             color="#ea580c", markerfacecolor="#fdba74", markeredgecolor="#c2410c")
    for x, y in zip(thresholds, uniques):
        ax2.text(x, y, f"{int(y)}", ha="center", va="bottom", fontsize=9, fontweight="bold",
                 bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#fed7aa", alpha=0.9))
    ax2.set_xlabel(x_label, fontsize=11)
    ax2.set_ylabel("Unique edge names after collapsing", fontsize=11)
    ax2.set_title("Unique edge names vs threshold", fontsize=13, fontweight="bold")
    ax2.tick_params(labelsize=10)
    uniq_png = Path(out_dir) / "unique_vs_threshold.png"
    fig2.tight_layout()
    fig2.savefig(uniq_png, bbox_inches="tight", dpi=180)

    return ratio_png, uniq_png


def main():
    parser = argparse.ArgumentParser(description="Compute retention ratios across thresholds")
    parser.add_argument("--cluster-dir", required=True, help="Directory with merged_sim_*.csv files")
    parser.add_argument("--collapse", required=True, help="collapse_names.csv (name,count)")
    parser.add_argument("--thresholds", default=None, help="Comma list, e.g., 0.4,0.5,0.6")
    parser.add_argument("--distance-mode", action="store_true",
                        help="Interpret thresholds as cosine distance; files are looked up using similarity = 1 - distance")
    parser.add_argument("--out-dir", default=None, help="Where to write outputs (default: cluster-dir)")
    args = parser.parse_args()

    default_sim_list = [round(x, 2) for x in np.arange(0.40, 0.81, 0.10)]  # 0.40..0.80
    default_dist_list = [0.60, 0.50, 0.40, 0.30, 0.20, 0.10]               # 0.60..0.10

    thresholds = parse_thresholds(args.thresholds, default_dist_list if args.distance_mode else default_sim_list)
    cluster_dir = Path(args.cluster_dir)
    out_dir = Path(args.out_dir) if args.out_dir else cluster_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    original_unique = load_original_unique(args.collapse)

    rows = []
    uniques = []
    ratios = []

    for thr in thresholds:
        if args.distance_mode:
            sim = 1.0 - thr
            fname = find_cluster_file(cluster_dir, sim)
            x_val = thr  # distance on x-axis
        else:
            sim = thr
            fname = find_cluster_file(cluster_dir, sim)
            x_val = thr
        uniq = load_cluster_unique(fname)
        ratio = uniq / original_unique
        rows.append({
            "threshold_input": thr,
            "similarity_used": (1.0 - thr) if args.distance_mode else thr,
            "unique_after": uniq,
            "original_unique": original_unique,
            "ratio": ratio
        })
        uniques.append(uniq)
        ratios.append(ratio)

    ratios_df = pd.DataFrame(rows)
    ratios_csv = out_dir / "ratios.csv"
    ratios_df.to_csv(ratios_csv, index=False)

    x_label = "Cosine distance threshold" if args.distance_mode else "Cosine similarity threshold"
    ratio_png, uniq_png = make_plots(thresholds, uniques, ratios, out_dir, x_label=x_label)

    print(f"Original unique edge names: {original_unique}")
    print("Saved:")
    print(f"  {ratios_csv}")
    print(f"  {ratio_png}")
    print(f"  {uniq_png}")


if __name__ == "__main__":
    main()
