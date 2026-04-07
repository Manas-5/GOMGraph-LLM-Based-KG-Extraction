#!/usr/bin/env python3
import argparse
import os
import sys
import time
from collections import defaultdict

import numpy as np
import pandas as pd
import requests
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize
from tqdm import tqdm
import matplotlib.pyplot as plt

OLLAMA_URL = "http://localhost:11434/api/embeddings"


def normalize_name(s: str) -> str:
    """Lowercase, replace underscores with space, collapse extra whitespace (for embedding text only)."""
    return " ".join(str(s).lower().replace("_", " ").split())


def embed(text, model="bge-m3:567m", session=None, retries=3, backoff=1.5):
    """Get an embedding from Ollama with simple retries."""
    s = session or requests.Session()
    for attempt in range(retries):
        try:
            r = s.post(OLLAMA_URL, json={"model": model, "prompt": text})
            r.raise_for_status()
            return r.json()["embedding"]
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(backoff ** attempt)


def load_names(path, sep):
    """
    Load names/counts from raw edges (with type) or pre-aggregated CSV/TSV.
    Returns dataframe with columns: name, count, embed_text (normalized version used only for embedding).
    """
    if sep is None:
        sep = "\t" if path.lower().endswith(".tsv") else ","
    df = pd.read_csv(path, sep=sep, dtype=str)
    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])

    # Raw edges: keep raw name for identity; group on raw name only.
    if "type" in df.columns:
        df = df[df["type"] == "RELATES_TO"]
        grouped = df.groupby("name").size().reset_index(name="count")
        grouped["embed_text"] = grouped["name"].map(normalize_name)
        return grouped

    # Pre-aggregated name/count
    if {"name", "count"} <= set(df.columns):
        df["count"] = df["count"].astype(int)
        grouped = df.groupby("name")["count"].sum().reset_index()
        grouped["embed_text"] = grouped["name"].map(normalize_name)
        return grouped

    raise ValueError("Input must have either a 'type' column or both 'name' and 'count'.")


def cluster_with_distance(dist_matrix, distance_threshold):
    model = AgglomerativeClustering(
        metric="precomputed",
        linkage="average",
        distance_threshold=distance_threshold,
        n_clusters=None,
    )
    return model.fit_predict(dist_matrix)


def choose_rep(names, counts):
    lengths = [len(n) for n in names]
    best_idx = np.lexsort((lengths, -counts))[0]
    return names[best_idx]


def parse_thresholds(thr_str):
    if thr_str:
        return [float(x) for x in thr_str.split(",")]
    return [round(x, 2) for x in np.arange(0.10, 1.001, 0.10)]  # 0.10..1.00


def main():
    ap = argparse.ArgumentParser(
        description="Collapse similar RELATES_TO names using cosine similarity"
    )
    ap.add_argument("--tsv", required=True, help="Path to TSV/CSV (raw edges or pre-aggregated)")
    ap.add_argument("--sep", default=None, help="Field separator (auto by extension if omitted)")
    ap.add_argument("--model", default="bge-m3:567m", help="Ollama embedding model")
    ap.add_argument("--thresholds", default=None, help="Comma list of similarity cutoffs (e.g., 0.15,0.25)")
    ap.add_argument("--limit", type=int, default=None, help="Limit top-N names by count for quick tests")
    ap.add_argument("--out-dir", default="cluster_runs", help="Output folder")
    args = ap.parse_args()

    thresholds = parse_thresholds(args.thresholds)
    os.makedirs(args.out_dir, exist_ok=True)

    counts = load_names(args.tsv, args.sep)
    if args.limit:
        counts = counts.sort_values("count", ascending=False).head(args.limit).reset_index(drop=True)

    names = counts["name"].tolist()
    embed_texts = counts["embed_text"].tolist()
    name_counts = counts["count"].to_numpy()

    print(f"Embedding {len(names)} names (normalized text for embedding) with {args.model} …")
    sess = requests.Session()
    embeddings = [embed(txt, model=args.model, session=sess) for txt in tqdm(embed_texts)]

    # Build similarity/distance matrices once
    emb_matrix = normalize(np.asarray(embeddings, dtype=np.float32))
    sim_matrix = cosine_similarity(emb_matrix)
    dist_matrix = 1.0 - sim_matrix

    cluster_counts = []
    dist_thresholds = []

    for thr in thresholds:
        dist_thr = 1.0 - thr
        dist_thresholds.append(dist_thr)
        print(f"\nClustering at similarity ≥ {thr:.2f} (distance ≤ {dist_thr:.2f}) …")
        labels = cluster_with_distance(dist_matrix, dist_thr)
        cluster_counts.append(len(set(labels)))

        clusters = defaultdict(list)
        for name, cnt, lbl in zip(names, name_counts, labels):
            clusters[lbl].append((name, cnt))

        collapsed_rows, mapping_rows = [], []
        for lbl, items in clusters.items():
            cl_names = [n for n, _ in items]
            cl_counts = np.array([c for _, c in items])
            rep = choose_rep(cl_names, cl_counts)
            total = int(cl_counts.sum())
            collapsed_rows.append(
                {"cluster_id": lbl, "representative": rep, "total_count": total, "members": len(items)}
            )
            for n, c in items:
                mapping_rows.append({"cluster_id": lbl, "name": n, "count": c, "representative": rep})

        collapsed_df = pd.DataFrame(collapsed_rows).sort_values("total_count", ascending=False)
        mapping_df = pd.DataFrame(mapping_rows).sort_values(["cluster_id", "count"], ascending=[True, False])

        c_path = os.path.join(args.out_dir, f"collapsed_sim_{thr:.2f}.csv")
        m_path = os.path.join(args.out_dir, f"mapping_sim_{thr:.2f}.csv")
        collapsed_df.to_csv(c_path, index=False)
        mapping_df.to_csv(m_path, index=False)
        print(f"Saved {c_path} and {m_path}")

    # Plots
    # Pretty plots with point labels
    plt.style.use("seaborn-v0_8-whitegrid")

    def annotate_points(xs, ys, ax):
        for x, y in zip(xs, ys):
            ax.text(x, y, f"{int(y)}", fontsize=9, fontweight="bold",
                    ha="center", va="bottom", color="#0f172a",
                    bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#cbd5e1", alpha=0.9))

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(thresholds, cluster_counts, marker="o", markersize=7,
            linewidth=2.4, color="#2563eb", markerfacecolor="#60a5fa", markeredgecolor="#1d4ed8")
    annotate_points(thresholds, cluster_counts, ax)
    ax.set_xlabel("Cosine similarity threshold", fontsize=11)
    ax.set_ylabel("Number of Unique edge names after merging", fontsize=11)
    ax.set_title("Unique Edge Names vs Cosine Similarity", fontsize=13, fontweight="bold")
    ax.set_xlim(min(thresholds) - 0.02, max(thresholds) + 0.02)
    ax.tick_params(labelsize=10)
    sim_plot = os.path.join(args.out_dir, "clusters_vs_similarity.png")
    fig.tight_layout()
    fig.savefig(sim_plot, bbox_inches="tight", dpi=180)

    fig2, ax2 = plt.subplots(figsize=(7, 4.5))
    ax2.plot(dist_thresholds, cluster_counts, marker="o", markersize=7,
             linewidth=2.4, color="#ea580c", markerfacecolor="#fdba74", markeredgecolor="#c2410c")
    annotate_points(dist_thresholds, cluster_counts, ax2)
    ax2.set_xlabel("Cosine distance threshold", fontsize=11)
    ax2.set_ylabel("Number of Unique edge names after merging", fontsize=11)
    ax2.set_title("Unique Edge Names vs Cosine Distance", fontsize=13, fontweight="bold")
    ax2.set_xlim(min(dist_thresholds) - 0.02, max(dist_thresholds) + 0.02)
    ax2.tick_params(labelsize=10)
    dist_plot = os.path.join(args.out_dir, "clusters_vs_distance.png")
    fig2.tight_layout()
    fig2.savefig(dist_plot, bbox_inches="tight", dpi=180)

    print("Saved plots:")
    print(f"  {sim_plot}")
    print(f"  {dist_plot}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
