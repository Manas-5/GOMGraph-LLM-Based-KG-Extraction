#!/usr/bin/env python3
"""
Post-process LLM repick outputs to plot:

Y-axis: Number of edge names
X-axis: Number of edges per new edge name

Adds:
- Log-X version of the main plot
- Cluster entropy plots (constrained + free), vs threshold

Entropy is computed over cluster sizes (sum(total_count) per representative name):
  H = -Σ p_i log2 p_i
  H_norm = H / log2(k)   (k = number of clusters), in [0, 1]
"""

import argparse
import math
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
from adjustText import adjust_text


def shannon_entropy_from_counts(counts) -> tuple[float, float]:
    """
    counts: iterable of positive numbers
    returns: (H_bits, H_norm)
    """
    counts = [float(c) for c in counts if c and float(c) > 0]
    if not counts:
        return 0.0, 0.0
    total = sum(counts)
    ps = [c / total for c in counts]
    H = -sum(p * math.log(p, 2) for p in ps if p > 0)

    k = len(ps)
    if k <= 1:
        return H, 0.0
    H_norm = H / math.log(k, 2)
    return H, H_norm


def infer_rep_cols(df: pd.DataFrame) -> tuple[str | None, str | None]:
    """
    Try to infer constrained and free rep columns.
    - Free rep: representative_llm_free (as in your code)
    - Constrained rep: try common names (representative_llm, representative, rep, etc.)
    """
    free_col = "representative_llm_free" if "representative_llm_free" in df.columns else None

    # Try a few likely constrained rep column names (adjust if your CSV uses a different one)
    constrained_candidates = [
        "representative_llm",
        "representative",
        "representative_constrained",
        "rep_llm",
        "rep",
        "representative_name",
    ]
    constrained_col = None
    for c in constrained_candidates:
        if c in df.columns:
            constrained_col = c
            break

    return constrained_col, free_col


def load_stats(llm_reps_dir: Path) -> pd.DataFrame:
    files = sorted(llm_reps_dir.glob("llm_reps_*.csv"))
    if not files:
        raise FileNotFoundError(f"No llm_reps_*.csv found in {llm_reps_dir}")

    rows = []
    for f in files:
        df = pd.read_csv(f)

        if "total_count" not in df.columns:
            raise ValueError(f"{f} missing total_count column")

        constrained_col, free_col = infer_rep_cols(df)

        total_edges = float(df["total_count"].sum())

        n_names = int(len(df))
        avg_edges = total_edges / n_names if n_names else 0.0

        # free stats
        if free_col is None:
            raise ValueError(f"{f} missing representative_llm_free column")
        n_names_free = int(df[free_col].nunique())
        avg_edges_free = total_edges / n_names_free if n_names_free else 0.0

        # entropy (free)
        free_cluster_sizes = df.groupby(free_col)["total_count"].sum().values
        H_free, Hn_free = shannon_entropy_from_counts(free_cluster_sizes)

        # entropy (constrained) if available
        H_con, Hn_con = None, None
        n_names_con = None
        avg_edges_con = None
        if constrained_col is not None:
            n_names_con = int(df[constrained_col].nunique())
            avg_edges_con = total_edges / n_names_con if n_names_con else 0.0
            con_cluster_sizes = df.groupby(constrained_col)["total_count"].sum().values
            H_con, Hn_con = shannon_entropy_from_counts(con_cluster_sizes)

        try:
            thr = float(f.stem.split("_")[-1])
        except Exception:
            thr = None

        rows.append(
            {
                "file": f.name,
                "threshold": thr,
                "total_edges": total_edges,

                # your original metrics
                "n_names": n_names,
                "avg_edges": avg_edges,
                "n_names_free": n_names_free,
                "avg_edges_free": avg_edges_free,

                # constrained rep metrics (if present)
                "n_names_constrained": n_names_con,
                "avg_edges_constrained": avg_edges_con,

                # entropies
                "entropy_bits_free": H_free,
                "entropy_norm_free": Hn_free,
                "entropy_bits_constrained": H_con,
                "entropy_norm_constrained": Hn_con,

                "constrained_rep_col": constrained_col,
                "free_rep_col": free_col,
            }
        )

    out = pd.DataFrame(rows)

    if out["threshold"].notnull().all():
        out = out.sort_values("threshold").reset_index(drop=True)

    return out


def make_main_plot(df: pd.DataFrame, out_path: Path, logx: bool = False):
    plt.rcParams.update({
        "font.family": "monospace",
        "font.monospace": [
            "Menlo", "Monaco", "SFMono-Regular",
            "Consolas", "Liberation Mono", "Courier New"
        ],
    })

    fig, ax = plt.subplots(figsize=(8, 5))
    line_color = "#e34234"

    plot_df = df.copy()
    if logx:
        plot_df = plot_df[plot_df["avg_edges"] > 0]

    ax.plot(
        plot_df["avg_edges"],
        plot_df["n_names"],
        marker="o",
        color=line_color,
        linewidth=2.2,
    )

    if logx:
        ax.set_xscale("log")

    texts = []
    for row in plot_df.itertuples():
        label = f"thr {row.threshold:.2f}" if row.threshold is not None else row.file
        texts.append(ax.text(row.avg_edges, row.n_names, label, fontsize=8))

    adjust_text(
        texts,
        ax=ax,
        expand_points=(1.2, 1.4),
        expand_text=(1.2, 1.4),
        verbose=False,
    )

    ax.set_xlabel("Number of Edges per New Edge Name(Representative)")
    ax.set_ylabel("Number of Edge Names")
    ax.set_title("Edge Names vs Edges per New Edge Name (Representative)" + (" (log X-axis)" if logx else ""))
    ax.grid(True, alpha=0.25)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=190)
    print(f"Wrote {out_path}")


def plot_entropy_vs_threshold(df: pd.DataFrame, out_path: Path, which: str = "free", normalized: bool = True):
    """
    which: "free" or "constrained"
    normalized: plot normalized entropy (0..1) if True, else bits
    """
    if not df["threshold"].notnull().all():
        print(f"Skipping entropy plot (no thresholds parsed): {out_path}")
        return

    if which == "free":
        ycol = "entropy_norm_free" if normalized else "entropy_bits_free"
        title = f"Threshold vs Cluster Entropy ({'normalized' if normalized else 'bits'}, free reps)"
    else:
        ycol = "entropy_norm_constrained" if normalized else "entropy_bits_constrained"
        title = f"Threshold vs Cluster Entropy ({'normalized' if normalized else 'bits'}, constrained reps)"

    # If constrained not available, skip
    if df[ycol].isnull().all():
        print(f"Skipping {out_path.name}: constrained representative column not found in CSVs.")
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    line_color = "#e34234"

    ax.plot(df["threshold"], df[ycol], marker="o", color=line_color, linewidth=2.2)
    ax.set_xlabel("Threshold")
    ax.set_ylabel("Entropy (normalized 0–1)" if normalized else "Entropy (bits)")
    ax.set_title(title)
    ax.grid(True, alpha=0.25)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=190)
    print(f"Wrote {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--llm-reps-dir",
        default="/mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/scripts/llm_reps",
    )
    ap.add_argument(
        "--out-dir",
        default="/mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/scripts/distrubution_out",
    )
    ap.add_argument(
        "--out-name",
        default="edge_names_vs_edges_per_name.png",
    )
    args = ap.parse_args()

    df = load_stats(Path(args.llm_reps_dir))
    out_dir = Path(args.out_dir)

    # Main plots: linear + logx
    out_linear = out_dir / args.out_name
    make_main_plot(df, out_linear, logx=False)

    out_log = out_dir / args.out_name.replace(".png", "_logx.png")
    make_main_plot(df, out_log, logx=True)

    # Entropy plots (normalized by default; easiest to compare across runs)
    plot_entropy_vs_threshold(df, out_dir / "threshold_vs_entropy_norm_free.png", which="free", normalized=True)
    plot_entropy_vs_threshold(df, out_dir / "threshold_vs_entropy_bits_free.png", which="free", normalized=False)

    plot_entropy_vs_threshold(df, out_dir / "threshold_vs_entropy_norm_constrained.png", which="constrained", normalized=True)
    plot_entropy_vs_threshold(df, out_dir / "threshold_vs_entropy_bits_constrained.png", which="constrained", normalized=False)


if __name__ == "__main__":
    main()
