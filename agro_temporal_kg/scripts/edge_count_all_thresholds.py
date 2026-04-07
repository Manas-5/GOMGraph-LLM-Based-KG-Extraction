#!/usr/bin/env python3
"""
Overlay histograms of total_count across all llm_reps_*.csv thresholds.
- Single panel
- Solid (non-translucent) filled histograms
- Log-scaled x-axis
- Log-spaced bins to reduce clustering in the tail
- Explicit overflow tick label (e.g., "50+")
- Distinct, high-contrast categorical colors
- Keep legend
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def load_all(llm_reps_dir: Path):
    files = sorted(llm_reps_dir.glob("llm_reps_*.csv"))
    if not files:
        raise FileNotFoundError(f"No llm_reps_*.csv found in {llm_reps_dir}")
    datasets = []
    for f in files:
        df = pd.read_csv(f)
        if "total_count" not in df.columns:
            raise ValueError(f"{f} missing total_count column")
        counts = df["total_count"].dropna().to_numpy()
        try:
            thr = float(f.stem.split("_")[-1])
        except Exception:
            thr = None
        datasets.append((f.name, thr, counts))
    return datasets


def prepare_counts(counts, cutoff: int):
    arr = np.asarray(counts, dtype=float)
    arr[arr <= 0] = 1.0  # avoid log(0) and non-positive
    clipped = arr.copy()
    clipped[clipped > cutoff] = cutoff + 1  # overflow bucket
    return clipped


def build_log_bins(cutoff: int, n_bins: int = 28):
    """
    Log-spaced bin edges from 1..cutoff, plus an overflow bin at cutoff+1.
    Uses integer edges and ensures uniqueness/monotonicity.
    """
    if cutoff < 2:
        return [1, cutoff + 1.1]

    edges = np.logspace(np.log10(1), np.log10(cutoff), n_bins)
    edges = np.unique(np.round(edges).astype(int))
    edges = edges[edges >= 1]

    edges = np.unique(np.concatenate(([1], edges)))
    edges = edges[edges <= cutoff]

    if edges[-1] != cutoff:
        edges = np.concatenate((edges, [cutoff]))

    edges = list(edges.astype(float))
    edges.append(cutoff + 1.1)
    return edges


def distinct_colors(n: int):
    """
    Solid, distinct categorical colors.
    Uses tab10 (up to 10). If more than 10, uses tab20 (up to 20).
    If more than 20, cycles through tab20 (still distinct-ish, but repeats).
    """
    if n <= 10:
        cmap = plt.colormaps.get_cmap("tab10")
        return [cmap(i) for i in range(n)]
    cmap = plt.colormaps.get_cmap("tab20")
    base = [cmap(i) for i in range(min(20, n))]
    if n <= 20:
        return base
    # repeat if needed (kept simple, per your request)
    out = []
    for i in range(n):
        out.append(base[i % len(base)])
    return out


def plot_all(datasets, out_path: Path, cutoff: int, n_log_bins: int):
    plt.rcParams.update(
        {
            "font.family": "monospace",
            "font.monospace": [
                "Menlo",
                "Monaco",
                "SFMono-Regular",
                "Consolas",
                "Liberation Mono",
                "Courier New",
            ],
        }
    )

    # Sort by threshold so legend order is meaningful/stable
    datasets = sorted(datasets, key=lambda x: x[1] if x[1] is not None else float("inf"))

    colors = distinct_colors(len(datasets))
    bin_edges = build_log_bins(cutoff, n_bins=n_log_bins)

    fig, ax = plt.subplots(figsize=(8.5, 5.2))

    for idx, (name, thr, counts) in enumerate(datasets):
        clipped = prepare_counts(counts, cutoff)
        label = f"thr {thr:.2f}" if thr is not None else name

        ax.hist(
            clipped,
            bins=bin_edges,
            color=colors[idx],
            alpha=1.0,          # ✅ solid fill (no translucency)
            edgecolor="black",  # ✅ helps separate overlaps
            linewidth=0.6,
            label=label,
        )

    ax.set_xscale("log")

    tick_vals = [1, 2, 5, 10, 20, 50]
    tick_vals = [t for t in tick_vals if t <= cutoff]
    tick_vals.append(cutoff + 1)
    ax.set_xticks(tick_vals)
    ax.set_xticklabels([str(t) for t in tick_vals[:-1]] + [f"{cutoff}+"])

    ax.set_xlabel("Number of Edges per New Edge Name(Representative) {log scale}")
    ax.set_ylabel("Frequency")
    ax.set_title("Histogram of Edge Counts per New Edge Names (Rep) (all thresholds)")
    ax.grid(True, alpha=0.3)

    ax.legend(
        title="Threshold",
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        fontsize=8,
        frameon=False,
    )

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=190, bbox_inches="tight")
    print(f"Wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description="Overlay histograms of total_count across thresholds.")
    ap.add_argument(
        "--llm-reps-dir",
        default="/mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/scripts/llm_reps",
        help="Directory containing llm_reps_*.csv files.",
    )
    ap.add_argument(
        "--out-dir",
        default="/mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/scripts/distrubution_out",
        help="Directory to write plot.",
    )
    ap.add_argument("--out-name", default="edge_count_all_thresholds.png", help="Filename for the plot.")
    ap.add_argument("--cutoff", type=int, default=50, help="Values above go to overflow bin labeled cutoff+.")
    ap.add_argument("--n-log-bins", type=int, default=28, help="Number of log-spaced bins up to cutoff.")
    args = ap.parse_args()

    datasets = load_all(Path(args.llm_reps_dir))
    out_path = Path(args.out_dir) / args.out_name
    plot_all(datasets, out_path, cutoff=args.cutoff, n_log_bins=args.n_log_bins)


if __name__ == "__main__":
    main()
