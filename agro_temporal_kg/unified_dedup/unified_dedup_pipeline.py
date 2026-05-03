"""
Unified edge name deduplication pipeline.

Steps:
1. Load raw edge data (TSV/CSV with names/counts)
2. Normalize names (lowercase, remove underscores, collapse whitespace)
3. Embed normalized names using Ollama
4. Build similarity/distance matrices
5. Cluster at multiple similarity thresholds
6. Create mapping and collapsed files
7. Use LLM to pick canonical representatives (constrained + free)
8. Generate preprocessing artifacts (normalized groups, similarity candidates)
9. Create visualizations
10. Save all outputs in a organized directory structure

Usage:
python3 unified_dedup_pipeline.py \
    --tsv /path/to/edges.tsv \
    --out-dir /path/to/output \
    --model "llama3.1:70b" \
    --embed-model "bge-m3:567m" \
    --base-url "http://localhost:11434/v1" \
    --thresholds 0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90 \
    --sim-threshold 0.90
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import requests
from tqdm import tqdm
import os
import re
import time
import logging
from collections import defaultdict
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize
from sklearn.cluster import AgglomerativeClustering

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.1:70b"
DEFAULT_EMBED_MODEL = "bge-m3:567m"
DEFAULT_SIMILARITY_THRESHOLD = 0.90
OLLAMA_EMBEDDINGS_URL = "http://localhost:11434/api/embeddings"

AUX_PREFIXES = [
    "is ", "are ", "was ", "were ", "be ",
    "can be ", "may be ", "could be ",
    "should be ", "has been ", "have been "
]

STOPWORDS = {"a", "an", "the", "of"}


def setup_logging(log_dir: Path) -> logging.Logger:
    """Setup logging to both file and console."""
    log_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"pipeline_{timestamp}.log"
    
    logger = logging.getLogger("unified_dedup")
    logger.setLevel(logging.DEBUG)
    
    # File handler (verbose)
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    
    # Console handler (less verbose)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    ))
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger


def normalize_relation(text: str) -> str:
    """Normalize relation strings to reduce grammatical noise."""
    t = str(text).lower()
    t = t.replace("_", " ")
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()

    # Remove auxiliary prefixes
    for p in AUX_PREFIXES:
        if t.startswith(p):
            t = t[len(p):].strip()

    # Remove light stopwords
    tokens = [tok for tok in t.split() if tok not in STOPWORDS]
    return " ".join(tokens)


def normalize_name(s: str) -> str:
    """Normalize a relation label for embedding use.
    Removes auxiliary prefixes and stopwords for cleaner semantics."""
    t = str(s).lower()
    t = t.replace("_", " ")
    t = re.sub(r"[^\w\s]", " ", t)  # Remove special characters
    t = re.sub(r"\s+", " ", t).strip()
    
    # Remove auxiliary prefixes
    for p in AUX_PREFIXES:
        if t.startswith(p):
            t = t[len(p):].strip()
    
    # Remove light stopwords
    tokens = [tok for tok in t.split() if tok not in STOPWORDS]
    return " ".join(tokens)


def sanitize_label(text: str, fallback: str) -> str:
    """Convert text to UPPERCASE_WITH_UNDERSCORES format."""
    t = text.strip()
    t = re.sub(r"[^A-Za-z0-9_]+", "_", t).strip("_")
    t = re.sub(r"_+", "_", t).upper()
    return t if t else fallback


def clean_choice(choice: str) -> str:
    """Strip quotes and whitespace."""
    return choice.strip().strip('"').strip("'").strip()


def load_names(path: str, sep=None):
    """
    Load names/counts from raw edges (with type) or pre-aggregated CSV/TSV.
    Returns dataframe with columns: name, count, embed_text (normalized for embedding).
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
        grouped["embed_text"] = grouped["name"].apply(normalize_name)
        return grouped

    # Pre-aggregated name/count
    if {"name", "count"} <= set(df.columns):
        df["count"] = df["count"].astype(int)
        grouped = df.groupby("name")["count"].sum().reset_index()
        grouped["embed_text"] = grouped["name"].apply(normalize_name)
        return grouped

    raise ValueError("Input must have either a 'type' column or both 'name' and 'count'.")


def group_by_normalized(names_df: pd.DataFrame) -> tuple:
    """
    Group raw names by their normalized embedding form.
    Returns:
    - grouped_df: deduplicated by normalized form with aggregated counts
    - mapping_raw_to_norm: dict mapping raw names to their normalized form
    - mapping_norm_to_raws: dict mapping normalized form to list of raw names
    """
    # Normalize each name
    names_df = names_df.copy()
    
    # Group by normalized form, aggregating counts and collecting raw names
    grouped = (
        names_df.groupby("embed_text", as_index=False)
        .agg({
            "count": "sum",
            "name": lambda x: list(x)  # Keep list of all raw names that normalize to this form
        })
        .rename(columns={"name": "raw_names"})
    )
    
    # Choose a representative raw name from each group (longest name in group)
    def choose_representative(raw_names_list):
        """Choose the longest raw name as representative."""
        return max(raw_names_list, key=len)
    
    grouped["representative_raw_name"] = grouped["raw_names"].apply(choose_representative)
    
    # Build mappings
    mapping_raw_to_norm = {}
    mapping_norm_to_raws = {}
    
    for _, row in grouped.iterrows():
        norm_form = row["embed_text"]
        raw_names_list = row["raw_names"]
        mapping_norm_to_raws[norm_form] = raw_names_list
        for raw_name in raw_names_list:
            mapping_raw_to_norm[raw_name] = norm_form
    
    return grouped, mapping_raw_to_norm, mapping_norm_to_raws


def consolidate_clusters_by_normalized_form(mapping_df: pd.DataFrame, 
                                            mapping_raw_to_norm: dict, 
                                            logger: logging.Logger) -> pd.DataFrame:
    """
    Consolidate clusters that have members with identical normalized forms.
    
    If multiple clusters have names that normalize to the same form,
    merge them into a single cluster using the representative from the largest cluster.
    """
    # Group mapping by normalized form
    norm_to_clusters = defaultdict(set)
    for _, row in mapping_df.iterrows():
        name = row["name"]
        cluster_id = row["cluster_id"]
        if name in mapping_raw_to_norm:
            norm_form = mapping_raw_to_norm[name]
            norm_to_clusters[norm_form].add(cluster_id)
    
    # Find normalized forms that span multiple clusters
    merges_needed = {norm: clusters for norm, clusters in norm_to_clusters.items() 
                     if len(clusters) > 1}
    
    if not merges_needed:
        logger.debug("  No cluster merges needed (all identical normalized forms already in same cluster)")
        return mapping_df
    
    logger.debug(f"  Found {len(merges_needed)} normalized forms spanning multiple clusters")
    
    # Build merge mapping: old_cluster_id → representative_cluster_id
    cluster_merge_map = {}
    for norm_form, cluster_ids in merges_needed.items():
        # Choose representative cluster: the one with most edges
        cluster_edges = {cid: mapping_df[mapping_df["cluster_id"] == cid]["count"].sum() 
                        for cid in cluster_ids}
        rep_cluster = max(cluster_edges, key=cluster_edges.get)
        
        # Map all other clusters to representative
        for cid in cluster_ids:
            if cid != rep_cluster:
                cluster_merge_map[cid] = rep_cluster
    
    if not cluster_merge_map:
        return mapping_df
    
    # Apply merges to mapping dataframe
    result = mapping_df.copy()
    result["cluster_id"] = result["cluster_id"].map(
        lambda cid: cluster_merge_map.get(cid, cid)
    )
    
    logger.debug(f"  Merged {len(cluster_merge_map)} clusters")
    return result


def embed_texts(model: str, texts, base_url: str, api_key: str, batch_size=64):
    """Return list of embeddings for the given texts using /v1/embeddings."""
    url = base_url.rstrip("/") + "/embeddings"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    embs = []
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
        embs.extend([item["embedding"] for item in data["data"]])
    return embs


def cluster_with_distance(dist_matrix, distance_threshold):
    """Cluster using agglomerative clustering with distance threshold."""
    model = AgglomerativeClustering(
        metric="precomputed",
        linkage="average",
        distance_threshold=distance_threshold,
        n_clusters=None,
    )
    return model.fit_predict(dist_matrix)


def choose_rep(names, counts):
    """Choose representative: longest name with highest count."""
    lengths = [len(n) for n in names]
    best_idx = np.lexsort((lengths, -counts))[0]
    return names[best_idx]


def call_ollama(model: str, prompt: str, base_url: str, api_key: str, retries=3, temperature=0.0):
    """Call LLM to pick a representative label."""
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


def extract_label(raw: str, allowed=None, fallback: str = "") -> str:
    """
    Normalize an LLM reply into a single label.
    If allowed set is provided, enforce membership (case-insensitive).
    """
    text = raw or ""
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

    return sanitize_label(text, fallback=fallback or "UNKNOWN")


def build_preprocessing_artifacts(map_df: pd.DataFrame, out_dir: Path, prefix: str, similarity_threshold: float):
    """
    Create normalized groupings and near-duplicate candidates.
    Writes two CSVs:
    - {prefix}_exact_normalized_groups.csv
    - {prefix}_similarity_candidates.csv
    """
    required = {"name", "count"}
    missing = required - set(map_df.columns)
    if missing:
        raise ValueError(f"Mapping dataframe missing columns: {missing}")

    working = map_df[["name", "count"]].copy()
    working["normalized"] = working["name"].apply(normalize_relation)

    exact_groups = (
        working.groupby("normalized", as_index=False)
        .agg(
            total_count=("count", "sum"),
            examples=("name", lambda x: ", ".join(sorted(set(x))[:5]))
        )
        .sort_values("total_count", ascending=False)
    )
    exact_path = out_dir / f"{prefix}_exact_normalized_groups.csv"
    exact_groups.to_csv(exact_path, index=False)

    unique_terms = exact_groups["normalized"].tolist()
    sim_df = pd.DataFrame(columns=["term_a", "term_b", "similarity"])
    if unique_terms:
        vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 5))
        X = vectorizer.fit_transform(unique_terms)
        sim_matrix = cosine_similarity(X)

        pairs = []
        n = len(unique_terms)
        for i in range(n):
            for j in range(i + 1, n):
                score = sim_matrix[i, j]
                if score >= similarity_threshold:
                    pairs.append({
                        "term_a": unique_terms[i],
                        "term_b": unique_terms[j],
                        "similarity": round(float(score), 3),
                    })
        if pairs:
            sim_df = pd.DataFrame(pairs).sort_values("similarity", ascending=False)

    sim_path = out_dir / f"{prefix}_similarity_candidates.csv"
    sim_df.to_csv(sim_path, index=False)
    return exact_path, sim_path


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
You may propose any concise label that best summarizes the cluster meaning and do NOT return any label that appears in the cluster list.
Prefer the style and casing of the provided labels (underscores and uppercase are fine).
Return only the chosen label string.

Cluster members (name -> count):
{items}
"""


def repick_for_threshold(map_df: pd.DataFrame, collapsed_df: pd.DataFrame, model: str, base_url: str, api_key: str):
    """Use LLM to repick representatives (constrained and free-form)."""
    new_reps = {}
    free_reps = {}
    
    for cid, group in tqdm(map_df.groupby("cluster_id"), desc="LLM picking reps", unit="cluster"):
        items = "\n".join([f"- {n} ({c})" for n, c in zip(group["name"], group["count"])])
        prompt = PROMPT_TEMPLATE.format(items=items)
        choice = call_ollama(model, prompt, base_url, api_key)
        majority = group.sort_values("count", ascending=False).iloc[0]["name"]
        choice = extract_label(choice, allowed=set(group["name"]), fallback=majority)
        new_reps[cid] = choice

        prompt_free = PROMPT_TEMPLATE_FREE.format(items=items)
        free_choice = call_ollama(model, prompt_free, base_url, api_key)
        free_choice = extract_label(free_choice, allowed=None, fallback=majority)
        free_reps[cid] = free_choice

    out_df = collapsed_df.copy()
    out_df["representative_llm"] = out_df["cluster_id"].map(new_reps)
    out_df["representative_llm_free"] = out_df["cluster_id"].map(free_reps)
    return out_df


def plot_seaborn_dual(rows, out_dir: Path, distance_mode: bool):
    """Generate comparison plots for constrained vs free-form LLM reps."""
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
    uniq_path = out_dir / "01_unique_edge_names_constrained.png"
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
    avg_path = out_dir / "02_avg_edges_per_rep_constrained.png"
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
    uniq_free_path = out_dir / "03_unique_edge_names_free.png"
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
    avg_free_path = out_dir / "04_avg_edges_per_rep_free.png"
    fig.savefig(avg_free_path, bbox_inches="tight", dpi=170)
    print(f"Wrote {avg_free_path}")


def parse_thresholds(thr_str):
    """Parse threshold list or return defaults."""
    if thr_str:
        return [float(x) for x in thr_str.split(",")]
    return [round(x, 2) for x in np.arange(0.10, 1.001, 0.10)]


def main():
    ap = argparse.ArgumentParser(
        description="Unified edge name deduplication: cluster + LLM rep picking"
    )
    ap.add_argument("--tsv", required=True, help="Path to TSV/CSV with raw edges or pre-aggregated names")
    ap.add_argument("--sep", default=None, help="Field separator (auto by extension if omitted)")
    ap.add_argument("--out-dir", default="output", help="Output directory (default: ./output)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="LLM model for rep picking")
    ap.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL, help="Embedding model")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help="LLM base URL")
    ap.add_argument("--api-key", default="abc", help="API key if required")
    ap.add_argument("--thresholds", default=None, help="Comma-separated similarity thresholds (or distance if --distance-mode)")
    ap.add_argument("--sim-threshold", type=float, default=DEFAULT_SIMILARITY_THRESHOLD,
                    help="Cosine similarity cutoff for near-duplicate detection")
    ap.add_argument("--limit", type=int, default=None, help="Limit top-N names for testing")
    ap.add_argument("--distance-mode", action="store_true", help="Interpret --thresholds as cosine distance (not similarity)")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Create organized subdirectories
    logs_dir = out_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    clustering_dir = out_dir / "01_clustering"
    clustering_dir.mkdir(exist_ok=True)
    
    embeddings_dir = out_dir / "02_embeddings"
    embeddings_dir.mkdir(exist_ok=True)
    
    preprocessing_dir = out_dir / "03_preprocessing"
    preprocessing_dir.mkdir(exist_ok=True)
    
    artifacts_dir = preprocessing_dir / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    
    llm_dir = out_dir / "04_llm_reps"
    llm_dir.mkdir(exist_ok=True)
    
    visualizations_dir = llm_dir / "visualizations"
    visualizations_dir.mkdir(exist_ok=True)

    # Setup logging
    logger = setup_logging(logs_dir)
    logger.info("="*80)
    logger.info("UNIFIED EDGE NAME DEDUPLICATION PIPELINE")
    logger.info("="*80)
    logger.info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Input file: {args.tsv}")
    logger.info(f"Output directory: {out_dir}")
    logger.info(f"LLM model: {args.model}")
    logger.info(f"Embedding model: {args.embed_model}")
    logger.info(f"Thresholds: {args.thresholds or 'default (0.10-0.90)'}")
    logger.info(f"Similarity threshold for near-duplicates: {args.sim_threshold}")
    logger.info("="*80)

    thresholds = parse_thresholds(args.thresholds)

    # === STEP 1: Load and normalize names ===
    logger.info("\n" + "="*80)
    logger.info("STEP 1: Loading names...")
    logger.info("="*80)
    try:
        raw_names_df = load_names(args.tsv, args.sep)
        if args.limit:
            raw_names_df = raw_names_df.sort_values("count", ascending=False).head(args.limit).reset_index(drop=True)
        
        logger.info(f"✓ Loaded {len(raw_names_df)} raw unique names")
        logger.info(f"✓ Total edges: {int(raw_names_df['count'].sum())}")
    except Exception as e:
        logger.error(f"✗ Failed to load names: {e}", exc_info=True)
        raise
    
    # === STEP 1.5: Group by normalized form (NEW STEP) ===
    logger.info("\n" + "="*80)
    logger.info("STEP 1.5: Grouping by normalized embedding form...")
    logger.info("="*80)
    try:
        grouped_df, mapping_raw_to_norm, mapping_norm_to_raws = group_by_normalized(raw_names_df)
        
        # Extract deduplicated data for embedding
        # KEY: We embed ONE representative per normalized form, NOT all raw names
        names_list = grouped_df["representative_raw_name"].tolist()  # 1108 raw names (1 per group)
        embed_texts_list = grouped_df["embed_text"].tolist()  # 1108 normalized forms
        counts_list = grouped_df["count"].to_numpy()  # 1108 aggregated counts
        
        logger.info(f"✓ Grouped into {len(grouped_df)} unique normalized forms")
        logger.info(f"✓ Reduction: {len(raw_names_df)} → {len(grouped_df)} ({len(raw_names_df) - len(grouped_df)} consolidated)")
        logger.info(f"✓ Embedding only {len(grouped_df)} representatives (1 per normalized form)")
        logger.info(f"✓ Total edges still: {int(counts_list.sum())}")
    except Exception as e:
        logger.error(f"✗ Failed to group by normalized form: {e}", exc_info=True)
        raise

    # === STEP 2: Preprocess on raw data (normalize + find similarity candidates) ===
    logger.info("\n" + "="*80)
    logger.info("STEP 2: Preprocessing raw data (normalization + similarity analysis)...")
    logger.info("="*80)
    try:
        # Use the original raw names for preprocessing analysis
        raw_df = raw_names_df.copy()
        
        # Normalize relations (complex normalization for analysis)
        raw_df["normalized"] = raw_df["name"].apply(normalize_relation)
        
        # 2a. Exact normalized grouping
        logger.info("Building exact normalized groups...")
        exact_groups = (
            raw_df.groupby("normalized", as_index=False)
            .agg(
                total_count=("count", "sum"),
                examples=("name", lambda x: ", ".join(sorted(set(x))[:5]))
            )
            .sort_values("total_count", ascending=False)
        )
        exact_path = artifacts_dir / "00_exact_normalized_groups.csv"
        exact_groups.to_csv(exact_path, index=False)
        logger.info(f"✓ Saved {exact_path} ({len(exact_groups)} unique normalized terms)")
        
        # 2b. Similarity candidates on normalized terms
        logger.info("Computing similarity candidates on normalized terms...")
        unique_terms = exact_groups["normalized"].tolist()
        
        sim_df = pd.DataFrame(columns=["term_a", "term_b", "similarity"])
        if unique_terms:
            vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 5))
            X = vectorizer.fit_transform(unique_terms)
            sim_matrix = cosine_similarity(X)
            
            pairs = []
            n = len(unique_terms)
            for i in range(n):
                for j in range(i + 1, n):
                    score = sim_matrix[i, j]
                    if score >= args.sim_threshold:
                        pairs.append({
                            "term_a": unique_terms[i],
                            "term_b": unique_terms[j],
                            "similarity": round(float(score), 3)
                        })
            if pairs:
                sim_df = pd.DataFrame(pairs).sort_values("similarity", ascending=False)
        
        sim_path = artifacts_dir / "00_similarity_candidates.csv"
        sim_df.to_csv(sim_path, index=False)
        logger.info(f"✓ Saved {sim_path} ({len(sim_df)} similarity pairs)")
    except Exception as e:
        logger.error(f"✗ Preprocessing failed: {e}", exc_info=True)
        raise
    
    # === STEP 3: Save normalized list and mapping ===
    logger.info("\n" + "="*80)
    logger.info("STEP 3: Saving normalized names and mappings...")
    logger.info("="*80)
    try:
        norm_df = pd.DataFrame({
            "raw_name": names_list,
            "normalized_for_embedding": embed_texts_list,
            "count": counts_list
        })
        normalized_list_path = embeddings_dir / "normalized_names.csv"
        norm_df.to_csv(normalized_list_path, index=False)
        logger.info(f"✓ Saved {normalized_list_path}")
        
        # Save mapping of raw names to normalized forms
        mapping_df = pd.DataFrame([
            {"raw_name": raw, "normalized_form": norm}
            for raw, norm in mapping_raw_to_norm.items()
        ])
        mapping_path = embeddings_dir / "raw_to_normalized_mapping.csv"
        mapping_df.to_csv(mapping_path, index=False)
        logger.info(f"✓ Saved {mapping_path}")
    except Exception as e:
        logger.error(f"✗ Failed to save normalized names: {e}", exc_info=True)
        raise

    # === STEP 4: Embed names ===
    logger.info("\n" + "="*80)
    logger.info("STEP 4: Embedding normalized names...")
    logger.info("="*80)
    try:
        logger.info(f"Embedding {len(embed_texts_list)} names with {args.embed_model}...")
        embeddings = embed_texts(args.embed_model, embed_texts_list, args.base_url, args.api_key or os.environ.get("OPENROUTER_API_KEY", ""))
        embeddings_array = np.asarray(embeddings, dtype=np.float32)
        logger.info(f"✓ Generated embeddings with shape {embeddings_array.shape}")

        # Save embeddings
        emb_path = embeddings_dir / "all_names_embeddings.npz"
        np.savez(emb_path, names=np.array(names_list), normalized_names=np.array(embed_texts_list), embeddings=embeddings_array)
        logger.info(f"✓ Saved embeddings to {emb_path}")
    except Exception as e:
        logger.error(f"✗ Embedding failed: {e}", exc_info=True)
        raise

    # === STEP 5: Build similarity matrices ===
    logger.info("\n" + "="*80)
    logger.info("STEP 5: Building similarity/distance matrices...")
    logger.info("="*80)
    try:
        emb_matrix = normalize(embeddings_array)
        sim_matrix = cosine_similarity(emb_matrix)
        dist_matrix = 1.0 - sim_matrix
        logger.info(f"✓ Computed matrices with shape {sim_matrix.shape}")
    except Exception as e:
        logger.error(f"✗ Matrix computation failed: {e}", exc_info=True)
        raise

    # === STEP 6: Cluster at multiple thresholds ===
    logger.info("\n" + "="*80)
    logger.info("STEP 6: Clustering at multiple thresholds...")
    logger.info("="*80)

    rows_for_plot = []
    all_mapping_dfs = {}  # Store for later use in LLM step
    clustering_stats = {}

    for thr in thresholds:
        try:
            if args.distance_mode:
                dist_thr = thr
                sim_label = 1.0 - thr
                logger.info(f"\nClustering at distance ≤ {dist_thr:.2f} (similarity ≥ {sim_label:.2f})...")
            else:
                dist_thr = 1.0 - thr
                logger.info(f"\nClustering at similarity ≥ {thr:.2f} (distance ≤ {dist_thr:.2f})...")

            labels = cluster_with_distance(dist_matrix, dist_thr)
            n_clusters = len(set(labels))
            logger.debug(f"  Found {n_clusters} clusters")

            clusters = defaultdict(list)
            for name, cnt, lbl in zip(names_list, counts_list, labels):
                clusters[lbl].append((name, cnt))

            collapsed_rows, mapping_rows = [], []
            for lbl, items in clusters.items():
                cl_names = [n for n, _ in items]
                cl_counts = np.array([c for _, c in items])
                rep = choose_rep(cl_names, cl_counts)
                total = int(cl_counts.sum())
                collapsed_rows.append({
                    "cluster_id": lbl,
                    "representative": rep,
                    "total_count": total,
                    "members": len(items)
                })
                for n, c in items:
                    mapping_rows.append({
                        "cluster_id": lbl,
                        "name": n,
                        "count": c,
                        "representative": rep
                    })

            collapsed_df = pd.DataFrame(collapsed_rows).sort_values("total_count", ascending=False)
            mapping_df = pd.DataFrame(mapping_rows).sort_values(["cluster_id", "count"], ascending=[True, False])

            # === Post-clustering consolidation: merge clusters with identical normalized forms ===
            logger.debug(f"Post-processing: consolidating clusters by normalized form...")
            mapping_df = consolidate_clusters_by_normalized_form(mapping_df, mapping_raw_to_norm, logger)
            
            # Rebuild collapsed_df after consolidation
            collapsed_df = (
                mapping_df.groupby("cluster_id", as_index=False)
                .agg({
                    "representative": "first",  # All names in a cluster have same rep after consolidation
                    "count": "sum",
                    "name": "count"
                })
                .rename(columns={"count": "total_count", "name": "members"})
                .sort_values("total_count", ascending=False)
            )
            
            n_clusters = len(collapsed_df)  # Update cluster count after consolidation

            # Save clustering outputs
            c_path = clustering_dir / f"collapsed_sim_{thr:.2f}.csv"
            m_path = clustering_dir / f"mapping_sim_{thr:.2f}.csv"
            collapsed_df.to_csv(c_path, index=False)
            mapping_df.to_csv(m_path, index=False)

            # Also write distance-labeled copies (distance = 1 - similarity) for convenience
            dist_val = 1.0 - thr
            c_path_dist = clustering_dir / f"collapsed_dist_{dist_val:.2f}.csv"
            m_path_dist = clustering_dir / f"mapping_dist_{dist_val:.2f}.csv"
            collapsed_df.to_csv(c_path_dist, index=False)
            mapping_df.to_csv(m_path_dist, index=False)

            all_mapping_dfs[thr] = mapping_df
            clustering_stats[thr] = {
                "n_clusters": n_clusters,
                "total_edges": int(collapsed_df["total_count"].sum()),
                "members": len(mapping_df)
            }
            logger.info(f"✓ Saved clustering outputs: {c_path.name}, {m_path.name}")
            logger.debug(f"  Stats: {n_clusters} clusters, {clustering_stats[thr]['total_edges']} edges, {len(mapping_df)} members")
        except Exception as e:
            logger.error(f"✗ Clustering failed for threshold {thr:.2f}: {e}", exc_info=True)
            raise

    # === STEP 7: Preprocessing artifacts (per threshold) ===
    logger.info("\n" + "="*80)
    logger.info("STEP 7: Building per-threshold preprocessing artifacts...")
    logger.info("="*80)
    try:
        for thr, map_df in all_mapping_dfs.items():
            pre_prefix = f"thr_{thr:.2f}"
            exact_path, sim_path = build_preprocessing_artifacts(map_df, artifacts_dir, pre_prefix, args.sim_threshold)
            logger.info(f"✓ Threshold {thr:.2f}: saved artifacts")
            logger.debug(f"  {exact_path.name}, {sim_path.name}")
    except Exception as e:
        logger.error(f"✗ Preprocessing artifacts generation failed: {e}", exc_info=True)
        raise

    # === STEP 8: LLM rep picking ===
    logger.info("\n" + "="*80)
    logger.info("STEP 8: LLM rep picking (constrained + free)...")
    logger.info("="*80)
    
    for thr in thresholds:
        try:
            map_df = all_mapping_dfs[thr]
            c_path = clustering_dir / f"collapsed_sim_{thr:.2f}.csv"
            collapsed_df = pd.read_csv(c_path)
            
            logger.info(f"\nProcessing LLM reps for threshold {thr:.2f}...")
            repicked = repick_for_threshold(map_df, collapsed_df, args.model, args.base_url, args.api_key or os.environ.get("OPENROUTER_API_KEY", ""))
            
            # Save LLM repicked
            llm_path = llm_dir / f"llm_reps_{thr:.2f}.csv"
            repicked_out = repicked[["cluster_id", "representative_llm", "representative_llm_free", "representative", "total_count", "members"]]
            repicked_out.to_csv(llm_path, index=False)
            logger.info(f"✓ Saved {llm_path.name}")

            # Save member-level view with LLM reps
            map_df["representative_llm"] = map_df["cluster_id"].map(dict(zip(repicked["cluster_id"], repicked["representative_llm"])))
            map_df["representative_llm_free"] = map_df["cluster_id"].map(dict(zip(repicked["cluster_id"], repicked["representative_llm_free"])))
            members_path = llm_dir / f"members_llm_{thr:.2f}.csv"
            map_df.to_csv(members_path, index=False)
            logger.info(f"✓ Saved {members_path.name}")

            # Compute stats
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
            logger.info(f"  Stats - avg_edges={avg_edges:.2f} | reps={len(repicked)} | free_reps={unique_free}")
        except Exception as e:
            logger.error(f"✗ LLM rep picking failed for threshold {thr:.2f}: {e}", exc_info=True)
            raise

    # === STEP 9: Visualization ===
    logger.info("\n" + "="*80)
    logger.info("STEP 9: Generating visualizations...")
    logger.info("="*80)
    try:
        plot_seaborn_dual(rows_for_plot, visualizations_dir, args.distance_mode)
        logger.info("✓ Generated all visualization plots")
    except Exception as e:
        logger.error(f"✗ Visualization generation failed: {e}", exc_info=True)
        raise

    # Final summary
    logger.info("\n" + "="*80)
    logger.info("PIPELINE COMPLETE!")
    logger.info("="*80)
    logger.info(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Output directory: {out_dir}")
    logger.info(f"  ├── logs/ (pipeline logs)")
    logger.info(f"  ├── 01_clustering/ (clustering outputs)")
    logger.info(f"  ├── 02_embeddings/ (embeddings + normalized names)")
    logger.info(f"  ├── 03_preprocessing/")
    logger.info(f"  │   └── artifacts/ (analysis outputs)")
    logger.info(f"  └── 04_llm_reps/ (LLM representative selection)")
    logger.info(f"      └── visualizations/ (comparison plots)")
    logger.info("="*80)


if __name__ == "__main__":
    main()
