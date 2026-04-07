#!/usr/bin/env python3
"""
LLM-assisted representative picker for clustered edge names.
- For each threshold file (merged/collapsed), call LLaMA via Ollama to choose a canonical rep per cluster.
- The LLM must pick ONLY from provided member labels (no inventing new labels).
- Outputs LLM-repicked merged file per threshold and a Seaborn plot of avg edges per new edge name vs threshold.


Usage example:
python3 llm_repick_reps.py \
    --cluster-dir "/mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/scripts/cluster_runs" \
    --out-dir "/mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/scripts/llm_reps" \
    --distance-mode \
    --model "llama3.1:70b" \
    --embed-model "bge-m3:567m" \
    --save-embeddings \
    --base-url "http://localhost:11434/v1" \
    --api-key "abc" \
    --thresholds 0.00,0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import requests
from tqdm import tqdm
import os

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.1:70b"  # adjust if your tag differs
DEFAULT_EMBED_MODEL = "bge-m3:567m"

def normalize_name(s: str) -> str:
    """Lowercase, replace underscores with space, collapse extra whitespace."""
    return " ".join(str(s).lower().replace("_", " ").split())

def clean_choice(choice: str) -> str:
    # strip quotes/whitespace; keep original casing of inner content
    return choice.strip().strip('"').strip("'").strip()

def extract_label(raw: str, allowed=None, fallback: str = "") -> str:
    """
    Normalize an LLM reply into a single label.
    - Trim to first line / sentence / comma segment.
    - Drop bullets/quotes.
    - If `allowed` is provided, enforce membership (case-insensitive) and
      fall back to the most frequent label provided by caller.
    """
    text = raw or ""
    # take the first sensible chunk
    for sep in ["\n", ".", ";", ","]:
        if sep in text:
            text = text.split(sep, 1)[0]
            break
    text = text.lstrip("-*• ").strip()
    text = clean_choice(text)

    if allowed:
        allowed_set = set(allowed)
        if text in allowed_set:
            return text
        lower_map = {a.lower(): a for a in allowed_set}
        if text.lower() in lower_map:
            return lower_map[text.lower()]
        return fallback or next(iter(allowed_set))

    # free-form: sanitize for consistency (PLANTED_IN style)
    return sanitize_label(text, fallback=fallback or "UNKNOWN")

def sanitize_label(text: str, fallback: str) -> str:
    import re
    t = text.strip()
    # replace non-alnum with underscore, uppercase, collapse underscores
    t = re.sub(r"[^A-Za-z0-9_]+", "_", t).strip("_")
    t = re.sub(r"_+", "_", t).upper()
    return t if t else fallback

PROMPT_TEMPLATE = """
You are choosing a canonical relation label for one cluster of edge names.
Rules:
- Pick exactly ONE label FROM THE LIST PROVIDED.
- Do NOT invent new labels.
- Prefer the label that is clearest, concise, correctly spelled, and best matches the majority meaning.
Return only the chosen label string.

Cluster members (name -> count):
{items}
"""

PROMPT_TEMPLATE_FREE = """
You are choosing a clear, canonical relation label for a cluster of edge names.
You may propose any concise label that best summarizes the cluster meaning.
Prefer the style and casing of the provided labels (underscores and uppercase are fine).
Return only the chosen label string.

Cluster members (name -> count):
{items}
"""


def find_cluster_file(cluster_dir: Path, sim: float):
    fmt_vals = [f"{sim:.2f}", f"{sim:.1f}", f"{sim:.0f}"]
    for v in fmt_vals:
        for prefix in ("merged_sim_", "collapsed_sim_"):
            cand = cluster_dir / f"{prefix}{v}.csv"
            if cand.exists():
                return cand
    raise FileNotFoundError(f"Missing cluster file for similarity {sim:.2f}")

def find_mapping_file(cluster_dir: Path, sim: float):
    fmt_vals = [f"{sim:.2f}", f"{sim:.1f}", f"{sim:.0f}"]
    for v in fmt_vals:
        cand = cluster_dir / f"mapping_sim_{v}.csv"
        if cand.exists():
            return cand
    raise FileNotFoundError(f"Missing mapping file for similarity {sim:.2f}")


def call_ollama(model: str, prompt: str, base_url: str, api_key: str, retries=3, temperature=0.0):
    for attempt in range(retries):
        try:
            url = base_url.rstrip("/") + "/chat/completions"
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            resp = requests.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You choose labels; respond with a single label only."},
                        {"role": "user", "content": prompt},
                    ],
                "temperature": temperature,
                "stream": False,
                "max_tokens": 32,
                # "stop": ["\n"],
            },
            timeout=120,
        )
            resp.raise_for_status()
            data = resp.json()
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"].strip()
        except Exception:
            if attempt == retries - 1:
                raise
    raise RuntimeError("LLM call failed")


def embed_texts(model: str, texts, base_url: str, api_key: str, batch_size=64):
    """Return list of embeddings for the given texts using /v1/embeddings."""
    url = base_url.rstrip("/") + "/embeddings"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    embs = []
    import math
    for i in tqdm(range(0, len(texts), batch_size), desc="Embedding names", unit="batch"):
        chunk = texts[i : i + batch_size]
        resp = requests.post(
            url,
            headers=headers,
            json={"model": model, "input": chunk},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        # expect data['data'] list of {embedding: [...]}
        embs.extend([item["embedding"] for item in data["data"]])
    return embs


def repick_for_file(fpath: Path, mapping_path: Path, model: str, base_url: str, api_key: str):
    df = pd.read_csv(fpath)
    for col in ("cluster_id", "representative", "total_count", "members"):
        if col not in df.columns:
            raise ValueError(f"File {fpath} missing column {col}")

    map_df = pd.read_csv(mapping_path)
    for col in ("cluster_id", "name", "count"):
        if col not in map_df.columns:
            raise ValueError(f"Mapping file {mapping_path} missing column {col}")

    new_reps = {}
    free_reps = {}
    for cid, group in tqdm(map_df.groupby("cluster_id"), desc="LLM picking reps", unit="cluster"):
        items = "\n".join([f"- {n} ({c})" for n, c in zip(group["name"], group["count"])]);
        prompt = PROMPT_TEMPLATE.format(items=items)
        choice = call_ollama(model, prompt, base_url, api_key)
        majority = group.sort_values("count", ascending=False).iloc[0]["name"]
        choice = extract_label(choice, allowed=set(group["name"]), fallback=majority)
        new_reps[cid] = choice

        prompt_free = PROMPT_TEMPLATE_FREE.format(items=items)
        free_choice = call_ollama(model, prompt_free, base_url, api_key)
        free_choice = extract_label(free_choice, allowed=None, fallback=majority)
        free_reps[cid] = free_choice

    out_df = df.copy()
    out_df["representative_llm"] = out_df["cluster_id"].map(new_reps)
    out_df["representative_llm_free"] = out_df["cluster_id"].map(free_reps)
    return out_df


def plot_seaborn(rows, out_base: Path, distance_mode: bool):
    import seaborn as sns
    import matplotlib.pyplot as plt
    import matplotlib as mpl

    sns.set_theme(style="whitegrid", rc={
        "axes.facecolor": "#0b0f16",
        "figure.facecolor": "#0b0f16",
        "grid.color": "#1f2735",
        "axes.edgecolor": "#324155",
        "text.color": "#f1f5f9",
        "axes.labelcolor": "#e2e8f0",
        "xtick.color": "#cbd5e1",
        "ytick.color": "#cbd5e1",
        "font.family": "DejaVu Sans Mono",
        "font.sans-serif": ["DejaVu Sans Mono", "SFMono-Regular", "Menlo", "Consolas", "Liberation Mono", "Courier New", "Arial"],
    })
    mpl.rcParams.update({
        "font.family": "DejaVu Sans Mono",
        "font.sans-serif": ["DejaVu Sans Mono", "SFMono-Regular", "Menlo", "Consolas", "Liberation Mono", "Courier New", "Arial"],
        "axes.titleweight": "bold",
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
    })

    dfp = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    accent = "#f97316"
    line = "#fb923c"
    sns.lineplot(data=dfp, x="threshold", y="avg_edges_per_new_edge_name",
                 marker="o", linewidth=2.9, color=line, ax=ax,
                 markerfacecolor=accent, markeredgecolor="#0b0f16", markeredgewidth=0.8)
    for x, y in zip(dfp["threshold"], dfp["avg_edges_per_new_edge_name"]):
        ax.text(x, y, f"{y:.2f}", ha="center", va="bottom", fontsize=9, color="#f8fafc",
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", fc="#111827", ec="#fb923c", alpha=0.8))
    ax.set_xlabel(f"Cosine {'distance' if distance_mode else 'similarity'} threshold")
    ax.set_ylabel("Avg edges per new edge name (LLM rep)")
    ax.set_title("Avg number of edges per new edge name (LLM-chosen reps)", color="#e2e8f0", fontsize=13, fontweight="bold")
    fig.tight_layout()
    seaborn_path = out_base.with_name(out_base.stem + "_seaborn.png")
    fig.savefig(seaborn_path, bbox_inches="tight", dpi=190)
    print(f"Wrote {seaborn_path}")

def plot_seaborn_dual(rows, out_dir: Path, distance_mode: bool):
    import seaborn as sns
    import matplotlib.pyplot as plt
    sns.set_theme(style="whitegrid")

    def annotate(ax, xs, ys, fmt):
        for x, y in zip(xs, ys):
            ax.text(x, y, fmt.format(y), ha="center", va="bottom", fontsize=9, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#cbd5e1", alpha=0.9))

    dfp = pd.DataFrame(rows)

    # Unique reps (constrained)
    fig, ax = plt.subplots(figsize=(7, 4))
    sns.lineplot(data=dfp, x="threshold", y="representatives", marker="o", ax=ax, color="#2563eb")
    annotate(ax, dfp["threshold"], dfp["representatives"], "{:.0f}")
    ax.set_xlabel("Cosine distance threshold" if distance_mode else "Cosine similarity threshold")
    ax.set_ylabel("Unique edge names (LLM constrained)")
    ax.set_title("Unique edge names vs threshold (constrained)")
    fig.tight_layout()
    uniq_path = out_dir / "unique_edge_names_vs_threshold_constrained.png"
    fig.savefig(uniq_path, bbox_inches="tight", dpi=170)
    print(f"Wrote {uniq_path}")

    # Avg edges per rep (constrained)
    fig, ax = plt.subplots(figsize=(7, 4))
    sns.lineplot(data=dfp, x="threshold", y="avg_edges_per_new_edge_name", marker="o", ax=ax, color="#fb923c")
    annotate(ax, dfp["threshold"], dfp["avg_edges_per_new_edge_name"], "{:.2f}")
    ax.set_xlabel("Cosine distance threshold" if distance_mode else "Cosine similarity threshold")
    ax.set_ylabel("Avg edges per new edge name (LLM constrained)")
    ax.set_title("Avg edges per new edge name vs threshold (constrained)")
    fig.tight_layout()
    avg_path = out_dir / "avg_edges_per_rep_llm_constrained.png"
    fig.savefig(avg_path, bbox_inches="tight", dpi=170)
    print(f"Wrote {avg_path}")

    # Unique reps (free)
    fig, ax = plt.subplots(figsize=(7, 4))
    sns.lineplot(data=dfp, x="threshold", y="representatives_free", marker="o", ax=ax, color="#0ea5e9")
    annotate(ax, dfp["threshold"], dfp["representatives_free"], "{:.0f}")
    ax.set_xlabel("Cosine distance threshold" if distance_mode else "Cosine similarity threshold")
    ax.set_ylabel("Unique edge names (LLM free)")
    ax.set_title("Unique edge names vs threshold (free)")
    fig.tight_layout()
    uniq_free_path = out_dir / "unique_edge_names_vs_threshold_free.png"
    fig.savefig(uniq_free_path, bbox_inches="tight", dpi=170)
    print(f"Wrote {uniq_free_path}")

    # Avg edges per rep (free)
    fig, ax = plt.subplots(figsize=(7, 4))
    sns.lineplot(data=dfp, x="threshold", y="avg_edges_per_new_edge_name_free", marker="o", ax=ax, color="#22c55e")
    annotate(ax, dfp["threshold"], dfp["avg_edges_per_new_edge_name_free"], "{:.2f}")
    ax.set_xlabel("Cosine distance threshold" if distance_mode else "Cosine similarity threshold")
    ax.set_ylabel("Avg edges per new edge name (LLM free)")
    ax.set_title("Avg edges per new edge name vs threshold (free)")
    fig.tight_layout()
    avg_free_path = out_dir / "avg_edges_per_rep_llm_free.png"
    fig.savefig(avg_free_path, bbox_inches="tight", dpi=170)
    print(f"Wrote {avg_free_path}")


def main():
    ap = argparse.ArgumentParser(description="LLM repicker for cluster reps + visualization")
    ap.add_argument("--cluster-dir", required=True, help="Dir with merged_sim_*.csv or collapsed_sim_*.csv")
    ap.add_argument("--thresholds", default=None, help="Comma list of distance thresholds; default 0.10..1.00 step 0.10")
    ap.add_argument("--distance-mode", action="store_true", help="Interpret thresholds as cosine distance (default)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model name, e.g., llama3:70b")
    ap.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL, help="Embedding model for edge names (e.g., bge-m3:567m)")
    ap.add_argument("--save-embeddings", action="store_true", help="Persist embeddings for each threshold mapping file")
    ap.add_argument("--out-dir", default="llm_reps", help="Output directory")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help="LLM base URL (OpenAI-compatible), default http://localhost:11434/v1")
    ap.add_argument("--api-key", default="abc", help='API key if required (default "abc"; or set OPENROUTER_API_KEY)')
    args = ap.parse_args()

    default_dist_list = [round(x, 2) for x in np.arange(0.00, 1.001, 0.10)]
    thresholds = [float(x) for x in args.thresholds.split(",")] if args.thresholds else default_dist_list

    cluster_dir = Path(args.cluster_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Using LLM model: {args.model}")
    print(f"Using embedding model: {args.embed_model}")

    rows_for_plot = []

    # Precompute embeddings once for the union of names across all thresholds (if requested)
    if args.save_embeddings:
        emb_path = out_dir / "all_names_embeddings.npz"
        if emb_path.exists():
            loaded = np.load(emb_path)
            emb_shape = loaded["embeddings"].shape
            print(f"Embeddings already present: {emb_path} (skipping recompute) | model={args.embed_model} | shape={emb_shape}")
        else:
            print("Building union of names across mapping files for all thresholds...")
            all_raw_names = set()
            for thr in thresholds:
                sim = 1.0 - thr if (args.distance_mode or args.thresholds is None) else thr
                mapping_file = find_mapping_file(cluster_dir, sim)
                if mapping_file is None:
                    print(f"  [warn] Missing mapping file for sim={sim:.2f}; skipping in embedding union.")
                    continue
                map_df = pd.read_csv(mapping_file)
                all_raw_names.update(map_df["name"].dropna().tolist())
            raw_names_list = sorted(all_raw_names)
            norm_texts = [normalize_name(n) for n in raw_names_list]
            print(f"Embedding {len(raw_names_list)} unique names once with {args.embed_model} (normalized text) ...")
            embs = embed_texts(args.embed_model, norm_texts, args.base_url, args.api_key or os.environ.get("OPENROUTER_API_KEY", ""))
            embs = np.asarray(embs, dtype=np.float32)
            np.savez(emb_path, names=np.array(raw_names_list), embeddings=embs)
            print(f"Saved embeddings to {emb_path}")

    for thr in tqdm(thresholds, desc="Processing thresholds", unit="thr"):
        sim = 1.0 - thr if (args.distance_mode or args.thresholds is None) else thr
        in_file = find_cluster_file(cluster_dir, sim)
        mapping_file = find_mapping_file(cluster_dir, sim)
        if mapping_file is None:
            print(f"[warn] Missing mapping file for sim={sim:.2f}; skipping this threshold.")
            continue
        out_file = out_dir / f"llm_reps_{thr:.2f}.csv"
        print(f"Processing threshold {thr:.2f} (sim {sim:.2f}) -> {in_file}")
        repicked = repick_for_file(in_file, mapping_file, args.model, args.base_url, args.api_key or os.environ.get("OPENROUTER_API_KEY", ""))
        repicked_out = repicked[["cluster_id", "representative_llm", "representative_llm_free", "representative", "total_count", "members"]]
        repicked_out.to_csv(out_file, index=False)

        # Emit member-level view with LLM rep
        map_df = pd.read_csv(mapping_file)
        map_df["representative_llm"] = map_df["cluster_id"].map(dict(zip(repicked["cluster_id"], repicked["representative_llm"])))
        map_df["representative_llm_free"] = map_df["cluster_id"].map(dict(zip(repicked["cluster_id"], repicked["representative_llm_free"])))
        members_out = out_dir / f"members_llm_{thr:.2f}.csv"
        map_df.to_csv(members_out, index=False)
        print(f"  Saved members with LLM reps -> {members_out}")

        total_edges = repicked["total_count"].sum()
        avg_edges = total_edges / len(repicked) if len(repicked) else 0
        unique_free = repicked["representative_llm_free"].nunique()
        avg_edges_free = total_edges / unique_free if unique_free else 0
        rows_for_plot.append({
            "threshold": thr,
            "avg_edges_per_new_edge_name": avg_edges,
            "representatives": len(repicked),
            "representatives_free": unique_free,
            "avg_edges_per_new_edge_name_free": avg_edges_free,
        })
        print(f"  avg_edges_per_new_edge_name={avg_edges:.2f} reps={len(repicked)} -> {out_file}")

    # plots (constrained and free)
    plot_seaborn(rows_for_plot, out_dir / "avg_edges_per_rep_llm.csv", args.distance_mode)
    plot_seaborn_dual(rows_for_plot, out_dir, args.distance_mode)


if __name__ == "__main__":
    main()
