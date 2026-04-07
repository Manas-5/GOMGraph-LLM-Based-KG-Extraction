#!/usr/bin/env python3
"""
LLM merge-review experiment on top of embedding-based clusters.
- Loads collapsed + mapping CSVs and a union embedding file (names + embeddings).
- Computes cluster centroids from member embeddings.
- Flags cluster pairs whose centroid cosine distance is below a threshold.
- For each candidate pair, asks an LLM (OpenAI-compatible chat) whether to MERGE or KEEP them separate,
  constrained to choose a canonical label only from the provided member names.
- Writes a decision CSV; does NOT actually merge clusters (review-only).
"""
import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from tqdm import tqdm
from sklearn.preprocessing import normalize

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.1:70b"

PROMPT_MERGE = """
You are reviewing whether two relation-label clusters should be merged.
Rules:
- Answer with MERGE or KEEP.
- If MERGE, also give one canonical label chosen ONLY from the provided member names.
- Keep your reply concise: "MERGE | <label>" or "KEEP".

Cluster A (name -> count):
{a_items}

Cluster B (name -> count):
{b_items}
"""


def load_embeddings(npz_path: Path):
    data = np.load(npz_path, allow_pickle=False)
    names = data["names"]
    embs = data["embeddings"]
    name_to_emb = {n: emb for n, emb in zip(names, embs)}
    return name_to_emb


def cluster_centroids(map_df: pd.DataFrame, name_to_emb: dict):
    centroids = {}
    for cid, g in map_df.groupby("cluster_id"):
        vecs = []
        for n in g["name"].dropna():
            if n in name_to_emb:
                vecs.append(name_to_emb[n])
        if not vecs:
            continue
        mat = np.stack(vecs, axis=0)
        centroid = mat.mean(axis=0)
        centroid = centroid / (np.linalg.norm(centroid) + 1e-9)
        centroids[cid] = centroid
    return centroids


def pair_candidates(centroids: dict, max_dist: float, max_pairs: int):
    cids = list(centroids.keys())
    C = len(cids)
    pairs = []
    for i in range(C):
        for j in range(i + 1, C):
            a, b = cids[i], cids[j]
            da = centroids[a]
            db = centroids[b]
            dist = 1 - float(np.dot(da, db))  # cosine distance since vectors normalized
            if dist <= max_dist:
                pairs.append((a, b, dist))
    pairs.sort(key=lambda x: x[2])
    return pairs[:max_pairs]


def call_llm(model: str, prompt: str, base_url: str, api_key: str, temperature=0.0):
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    resp = requests.post(url, headers=headers, json={
        "model": model,
        "messages": [
            {"role": "system", "content": "Decide MERGE or KEEP. If MERGE, choose one provided label."},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "stream": False,
    }, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def top_items(group: pd.DataFrame, k: int):
    sub = group.sort_values("count", ascending=False).head(k)
    return "\n".join([f"- {n} ({c})" for n, c in zip(sub["name"], sub["count"])])


def main():
    ap = argparse.ArgumentParser(description="LLM merge review over clustered edges")
    ap.add_argument("--collapsed", required=True, help="collapsed_sim_*.csv (or llm_reps_*.csv) with cluster_id")
    ap.add_argument("--mapping", required=True, help="mapping_sim_*.csv with cluster_id,name,count")
    ap.add_argument("--embeddings", required=True, help="all_names_embeddings.npz (names, embeddings)")
    ap.add_argument("--max-dist", type=float, default=0.15, help="Cosine distance threshold for candidate pairs")
    ap.add_argument("--max-pairs", type=int, default=200, help="Max candidate pairs to review")
    ap.add_argument("--top-k", type=int, default=12, help="Top-k names per cluster to show in prompt")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="LLM model")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI-compatible base URL")
    ap.add_argument("--api-key", default="abc", help="API key (default 'abc')")
    ap.add_argument("--out", default="llm_merge_review.csv", help="Output CSV")
    args = ap.parse_args()

    map_df = pd.read_csv(args.mapping)
    if not {"cluster_id", "name", "count"}.issubset(map_df.columns):
        raise ValueError("mapping file missing required columns")

    name_to_emb = load_embeddings(Path(args.embeddings))
    cents = cluster_centroids(map_df, name_to_emb)
    pairs = pair_candidates(cents, args.max_dist, args.max_pairs)
    print(f"Reviewing {len(pairs)} candidate pairs within dist <= {args.max_dist}")

    decisions = []
    for a, b, dist in tqdm(pairs, desc="LLM reviewing", unit="pair"):
        ga = map_df[map_df["cluster_id"] == a]
        gb = map_df[map_df["cluster_id"] == b]
        prompt = PROMPT_MERGE.format(a_items=top_items(ga, args.top_k), b_items=top_items(gb, args.top_k))
        reply = call_llm(args.model, prompt, args.base_url, args.api_key)
        decisions.append({
            "cluster_id_a": a,
            "cluster_id_b": b,
            "distance": dist,
            "llm_decision": reply,
            "size_a": len(ga),
            "size_b": len(gb),
        })

    out_df = pd.DataFrame(decisions)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.out, index=False)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
