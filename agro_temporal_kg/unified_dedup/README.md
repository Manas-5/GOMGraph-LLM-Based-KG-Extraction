# Unified Edge Name Deduplication Pipeline

Complete automated pipeline for clustering and deduplicating edge names with LLM-assisted representative selection.

## Quick Start

```bash
cd /mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/unified_dedup

python3 unified_dedup_pipeline.py \
    --tsv /path/to/edges.tsv \
    --model "llama3.1:70b" \
    --embed-model "bge-m3:567m" \
    --base-url "http://localhost:11434/v1"
```

This will create an `output/` directory in the current folder with all results.

## Basic Usage

```bash
python3 unified_dedup_pipeline.py --tsv /path/to/data.tsv
```

## Advanced Usage

```bash
python3 unified_dedup_pipeline.py \
    --tsv /path/to/edges.tsv \
    --out-dir ./my_results \
    --model "llama3.1:70b" \
    --embed-model "bge-m3:567m" \
    --base-url "http://localhost:11434/v1" \
    --api-key "your-api-key" \
    --thresholds 0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90 \
    --sim-threshold 0.90 \
    --limit 1000 \
    --distance-mode
```

## Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--tsv` | ✓ | - | Path to TSV/CSV with raw edges or pre-aggregated names |
| `--out-dir` | | `output` | Output directory (relative to current folder) |
| `--model` | | `llama3.1:70b` | LLM model for representative picking |
| `--embed-model` | | `bge-m3:567m` | Embedding model for name representation |
| `--base-url` | | `http://localhost:11434/v1` | LLM API base URL (OpenAI-compatible) |
| `--api-key` | | `abc` | API key if required |
| `--thresholds` | | `0.10-0.90` | Comma-separated similarity thresholds |
| `--sim-threshold` | | `0.90` | Similarity cutoff for near-duplicate detection |
| `--limit` | | - | Limit top-N names (useful for testing) |
| `--distance-mode` | | - | Interpret thresholds as cosine distance instead of similarity |

## Input Format

Two formats supported:

### Raw Edges (with type column)
```csv
name,type
PLANTED_IN,RELATES_TO
has_been_planted,RELATES_TO
...
```
The pipeline groups by name and counts occurrences.

### Pre-aggregated (name + count)
```csv
name,count
PLANTED_IN,45
has_been_planted,12
...
```
Used directly without grouping.

## Output Directory Structure

```
output/
├── logs/
│   └── pipeline_YYYYMMDD_HHMMSS.log
│
├── 01_clustering/
│   ├── collapsed_sim_0.90.csv
│   ├── mapping_sim_0.90.csv
│   ├── collapsed_sim_0.80.csv
│   ├── mapping_sim_0.80.csv
│   └── ...
│
├── 02_embeddings/
│   ├── normalized_names.csv
│   └── all_names_embeddings.npz
│
├── 03_preprocessing/
│   └── artifacts/
│       ├── 00_exact_normalized_groups.csv
│       ├── 00_similarity_candidates.csv
│       ├── thr_0.90_exact_normalized_groups.csv
│       ├── thr_0.90_similarity_candidates.csv
│       └── ...
│
└── 04_llm_reps/
    ├── llm_reps_0.90.csv
    ├── members_llm_0.90.csv
    ├── llm_reps_0.80.csv
    ├── members_llm_0.80.csv
    └── ... (for each threshold)
    
    └── visualizations/
        ├── 01_unique_edge_names_constrained.png
        ├── 02_avg_edges_per_rep_constrained.png
        ├── 03_unique_edge_names_free.png
        └── 04_avg_edges_per_rep_free.png
```

## How It Works

### 9-Step Pipeline

1. **Load names** - Read TSV/CSV, normalize for embedding
2. **Preprocess** - Analyze raw names, find semantic groups
3. **Save normalized** - Create mapping of all normalization versions
4. **Embed** - Generate vector representations via Ollama
5. **Build matrices** - Compute cosine similarity matrices
6. **Cluster** - Group similar names at multiple thresholds
7. **Per-threshold artifacts** - Analyze each threshold's results
8. **LLM rep picking** - Select representatives (2 modes: constrained + free)
9. **Visualize** - Generate comparison plots

### Dual Normalization

The pipeline uses two normalization strategies:

**For Embedding:**
- Lowercase
- Remove underscores → spaces
- Remove special characters
- Remove auxiliary prefixes (is, are, was, has been, etc.)
- Remove stopwords (a, an, the, of)
- Example: `HAS_BEEN_PLANTED_IN_THE_GROUND` → `planted ground`

**For Analysis:**
- Same as above (both use the same aggressive normalization now)

### LLM Representative Selection

Two modes per cluster:

**Constrained Mode:**
- LLM must pick from cluster members ONLY
- Ensures valid representative from original data
- Falls back to most frequent label if LLM fails

**Free-form Mode:**
- LLM can propose new labels
- Allows for more refined/concise representatives
- Sanitized to `UPPERCASE_WITH_UNDERSCORES` format

## Monitoring

Check the log file for detailed execution:

```bash
tail -f output/logs/pipeline_*.log
```

Log includes:
- Start/end times
- Configuration used
- Success/failure indicators (✓/✗)
- Statistics per threshold
- Any warnings or errors with tracebacks

## Example Run

```bash
# Test with 100 names
python3 unified_dedup_pipeline.py \
    --tsv ../data/edges.csv \
    --limit 100 \
    --out-dir test_output

# Full pipeline
python3 unified_dedup_pipeline.py \
    --tsv ../data/edges.csv \
    --thresholds 0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90
```

## Dependencies

- pandas
- numpy
- scikit-learn
- requests
- tqdm
- seaborn
- matplotlib

Install with:
```bash
pip install pandas numpy scikit-learn requests tqdm seaborn matplotlib
```

## Files in This Folder

- `unified_dedup_pipeline.py` - Main pipeline script
- `PIPELINE_STRUCTURE.md` - Detailed output format documentation
- `README.md` - This file

## Notes

- Ollama server must be running at the configured base URL
- Default models expect Ollama-compatible API (e.g., OpenAI-compatible endpoints)
- Embedding is done once and cached in `02_embeddings/all_names_embeddings.npz`
- Log files accumulate in `output/logs/` with timestamps
- All outputs are organized by processing step for easy navigation
