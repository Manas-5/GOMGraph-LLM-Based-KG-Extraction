#!/usr/bin/env python3
"""
Streamlit app: LLM merge-review on clustered edge names.
- Loads collapsed + mapping CSVs and a union embedding file (names + embeddings).
- Computes cluster centroids and finds close pairs by cosine distance.
- For each candidate pair, asks an LLM (OpenAI-compatible / Ollama / OpenRouter) to MERGE or KEEP.
- Shows results in-app and offers a CSV download. No clusters are modified (review only).
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import streamlit as st

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.1:70b"

PROMPT_MERGE = """You are reviewing whether two relation-label clusters should be merged.
Rules:
- Answer with MERGE or KEEP.
- If MERGE, also give one canonical label chosen ONLY from the provided member names.
- Keep the reply concise: "MERGE | <label>" or "KEEP".

Cluster A (name -> count):
{a_items}

Cluster B (name -> count):
{b_items}
"""


@st.cache_data(show_spinner=False)
def load_embeddings(npz_path: str):
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
            dist = 1 - float(np.dot(da, db))  # cosine distance (normed)
            if dist <= max_dist:
                pairs.append((a, b, dist))
    pairs.sort(key=lambda x: x[2])
    return pairs[:max_pairs]


def call_llm(model: str, prompt: str, base_url: str, api_key: str, temperature=0.0):
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    resp = requests.post(
        url,
        headers=headers,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "Decide MERGE or KEEP. If MERGE, choose one provided label."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "stream": False,
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def top_items(group: pd.DataFrame, k: int):
    sub = group.sort_values("count", ascending=False).head(k)
    return "\n".join([f"- {n} ({c})" for n, c in zip(sub["name"], sub["count"])])


def parse_reply(reply: str):
    """Return action, merge_label from reply."""
    txt = reply.strip()
    upper = txt.upper()
    if upper.startswith("MERGE"):
        # try to split on |
        if "|" in txt:
            label = txt.split("|", 1)[1].strip()
        else:
            label = ""
        return "MERGE", label
    return "KEEP", ""


st.title("LLM Merge Review (Experimental)")

st.sidebar.header("Inputs")
collapsed_path = st.sidebar.text_input("collapsed_sim_*.csv (or llm_reps_*.csv)", "")
mapping_path = st.sidebar.text_input("mapping_sim_*.csv", "")
emb_path = st.sidebar.text_input("all_names_embeddings.npz", "")

max_dist = st.sidebar.slider("Max cosine distance for candidate pairs", 0.0, 0.5, 0.15, 0.01)
max_pairs = st.sidebar.number_input("Max pairs to review", 10, 2000, 200, 10)
top_k = st.sidebar.slider("Top-k names per cluster to show", 3, 30, 12)

model = st.sidebar.text_input("LLM model", DEFAULT_MODEL)
base_url = st.sidebar.text_input("Base URL", DEFAULT_BASE_URL)
api_key = st.sidebar.text_input("API key", "abc")

run = st.sidebar.button("Run merge review")

if run:
    try:
        collapsed_df = pd.read_csv(collapsed_path)
        map_df = pd.read_csv(mapping_path)
    except Exception as e:
        st.error(f"Failed to load CSVs: {e}")
        st.stop()

    if not {"cluster_id", "name", "count"}.issubset(map_df.columns):
        st.error("Mapping file must have columns: cluster_id, name, count")
        st.stop()

    st.write("Loading embeddings...")
    try:
        name_to_emb = load_embeddings(emb_path)
    except Exception as e:
        st.error(f"Failed to load embeddings: {e}")
        st.stop()

    st.write("Computing centroids and candidate pairs...")
    cents = cluster_centroids(map_df, name_to_emb)
    pairs = pair_candidates(cents, max_dist, max_pairs)
    st.write(f"Candidate pairs: {len(pairs)}")
    if not pairs:
        st.info("No pairs within the distance threshold.")
        st.stop()

    decisions = []
    progress = st.progress(0)

    rep_map = {}
    for col in ("representative_llm", "representative"):
        if col in collapsed_df.columns:
            rep_map = collapsed_df.set_index("cluster_id")[col].to_dict()
            break
    if not rep_map and "representative" in collapsed_df.columns:
        rep_map = collapsed_df.set_index("cluster_id")["representative"].to_dict()

    for idx, (a, b, dist) in enumerate(pairs, 1):
        ga = map_df[map_df["cluster_id"] == a]
        gb = map_df[map_df["cluster_id"] == b]
        prompt = PROMPT_MERGE.format(a_items=top_items(ga, top_k), b_items=top_items(gb, top_k))
        reply = call_llm(model, prompt, base_url, api_key)
        action, merge_label = parse_reply(reply)
        decisions.append({
            "cluster_id_a": a,
            "cluster_id_b": b,
            "distance": dist,
            "llm_raw": reply,
            "action": action,
            "merge_label": merge_label,
            "size_a": len(ga),
            "size_b": len(gb),
            "rep_a": rep_map.get(a, ""),
            "rep_b": rep_map.get(b, ""),
        })
        progress.progress(idx / len(pairs))

    out_df = pd.DataFrame(decisions)
    st.subheader("LLM Decisions")
    show_cols = ["cluster_id_a", "cluster_id_b", "distance", "action", "merge_label", "rep_a", "rep_b", "size_a", "size_b"]
    st.dataframe(out_df[show_cols].head(200))

    csv_bytes = out_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv_bytes, file_name="llm_merge_review.csv", mime="text/csv")
else:
    st.info("Set paths and click Run to start the merge review.")
