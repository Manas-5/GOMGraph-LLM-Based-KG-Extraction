#!/usr/bin/env python3
"""
Post-process LLM repick outputs to plot multiple diagnostics.

Reads llm_reps_*.csv files emitted by llm_repick_reps.py and produces:

1) edges_per_name_vs_n_names.png
   X: avg edges per new edge name (constrained rep)   Y: number of edge names

2) threshold_vs_n_names.png
   X: threshold   Y: number of edge names

3) threshold_vs_edges_per_name.png
   X: threshold   Y: avg edges per new edge name

4) threshold_vs_n_names_free.png
   X: threshold   Y: number of unique free-form representative names

5) threshold_vs_edges_per_name_free.png
   X: threshold   Y: avg edges per free-form representative name

Optional: --logx applies log scale to plot (1) X axis (helps with L-shaped curves).
"""

import argparse
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


def load_stats(llm_reps_dir: Path) -> pd.DataFrame:
    files = sorted(llm_reps_dir.glob("llm_reps_*.csv"))
    if not files:
        raise FileNotFoundError(f"No llm_reps_*.csv found in {llm_reps_dir}")

    rows = []
    for f in files:
        df = pd.read_csv(f)
        if "total_count" not in df.columns:
            raise ValueError(f"{f} missing total_count column")

        total_edges = df["total_count"].sum()

        n_names = len(df)
        avg_edges = total_edges / n_names if n_names else 0

        if "representative_llm_free" not in df.columns:
            raise ValueError(f"{f} missing representative_llm_free column")

        n_names_free = df["representative_llm_free"].nunique()
        avg_edges_free = total_edges / n_names_free if n_names_free else 0

        try:
            thr = float(f.stem.split("_")[-1])
        except Exception:
            thr = None

        rows.append(
            {
                "file": f.name,
                "threshold": thr,
                "total_edges": float(total_edges),
                "n_names": int(n_names),
                "avg_edges": float(avg_edges),
                "n_names_free": int(n_names_free),
                "avg_edges_free": float(avg_edges_free),
            }
        )

    out = pd.DataFrame(rows)

    # If thresholds are available for all, sort by threshold for consistent plots
    if out["threshold"].notnull().all():
        out = out.sort_values("threshold").reset_index(drop=True)

    return out


def _setup_fonts():
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


def _annotate_thresholds(ax, x, y, thr, fmt="thr {t:.2f}", fontsize=8):
    """
    Light-touch annotation near each point (no arrows, no guidelines).
    Uses small alternating offsets to reduce overlap a bit.
    """
    xoffs = [6, -8, 10, -12, 8, -10]
    yoffs = [8, 10, -8, -10, 12, -12]
    for i, (xi, yi, ti) in enumerate(zip(x, y, thr)):
        if pd.isna(ti):
            continue
        ax.annotate(
            fmt.format(t=ti),
            (xi, yi),
            textcoords="offset points",
            xytext=(xoffs[i % len(xoffs)], yoffs[i % len(yoffs)]),
            fontsize=fontsize,
        )


def plot_edges_per_name_vs_n_names(df: pd.DataFrame, out_path: Path, logx: bool):
    fig, ax = plt.subplots(figsize=(7, 5))
    line_color = "#e34234"

    ax.plot(df["avg_edges"], df["n_names"], marker="o", color=line_color, linewidth=2.2)

    if logx:
        # Avoid log(0)
        ax.set_xscale("log")

    _annotate_thresholds(ax, df["avg_edges"], df["n_names"], df["threshold"])

    ax.set_xlabel("Number of Edges per New Edge Name (avg)")
    ax.set_ylabel("Number of Edge Names")
    ax.set_title("Edge Names vs Edges per New Edge Name")
    ax.grid(True, alpha=0.25)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=190)
    print(f"Wrote {out_path}")


def plot_threshold_vs_metric(df: pd.DataFrame, ycol: str, title: str, ylabel: str, out_path: Path):
    # If no usable thresholds, skip
    if not df["threshold"].notnull().all():
        print(f"Skipping {out_path.name}: thresholds missing in some filenames")
        return

    fig, ax = plt.subplots(figsize=(7, 4.5))
    line_color = "#e34234"

    ax.plot(df["threshold"], df[ycol], marker="o", color=line_color, linewidth=2.2)

    ax.set_xlabel("Threshold")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.25)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=190)
    print(f"Wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description="Plot diagnostics from llm_reps_*.csv outputs.")
    ap.add_argument(
        "--llm-reps-dir",
        default="/mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/scripts/llm_reps",
        help="Directory containing llm_reps_*.csv files.",
    )
    ap.add_argument(
        "--out-dir",
        default="/mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/scripts/distrubution_out",
        help="Directory to write plot PNGs.",
    )
    ap.add_argument("--logx", action="store_true", help="Use log scale on X for edges/name vs names plot.")
    args = ap.parse_args()

    llm_dir = Path(args.llm_reps_dir)
    out_dir = Path(args.out_dir)

    _setup_fonts()
    df = load_stats(llm_dir)

    # 1) Existing plot (improved with optional log-x and light annotations)
    plot_edges_per_name_vs_n_names(
        df,
        out_dir / "edges_per_name_vs_n_names.png",
        logx=args.logx,
    )

    # 2) Threshold vs #names
    plot_threshold_vs_metric(
        df,
        ycol="n_names",
        title="Threshold vs Number of Edge Names",
        ylabel="Number of Edge Names",
        out_path=out_dir / "threshold_vs_n_names.png",
    )

    # 3) Threshold vs avg edges/name (constrained)
    plot_threshold_vs_metric(
        df,
        ycol="avg_edges",
        title="Threshold vs Avg Edges per New Edge Name",
        ylabel="Avg Edges per New Edge Name",
        out_path=out_dir / "threshold_vs_edges_per_name.png",
    )

    # 4) Threshold vs #free rep names
    plot_threshold_vs_metric(
        df,
        ycol="n_names_free",
        title="Threshold vs Number of Free-form Representative Names",
        ylabel="Number of Free-form Rep Names",
        out_path=out_dir / "threshold_vs_n_names_free.png",
    )

    # 5) Threshold vs avg edges per free rep name
    plot_threshold_vs_metric(
        df,
        ycol="avg_edges_free",
        title="Threshold vs Avg Edges per Free-form Representative Name",
        ylabel="Avg Edges per Free-form Rep Name",
        out_path=out_dir / "threshold_vs_edges_per_name_free.png",
    )


if __name__ == "__main__":
    main()
