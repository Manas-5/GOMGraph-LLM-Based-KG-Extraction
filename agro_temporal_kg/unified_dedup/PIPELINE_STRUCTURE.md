# Unified Edge Name Deduplication Pipeline

## Overview
Complete pipeline for clustering and deduplicating edge names with LLM-assisted representative selection.

## Directory Structure

```
unified_dedup_output/
├── logs/
│   └── pipeline_YYYYMMDD_HHMMSS.log    ← Detailed pipeline execution log
│
├── 01_clustering/
│   ├── collapsed_sim_0.90.csv           ← Cluster-level results (one row per cluster)
│   ├── mapping_sim_0.90.csv             ← Member-level results (one row per name)
│   ├── collapsed_sim_0.80.csv
│   ├── mapping_sim_0.80.csv
│   └── ... (for each threshold)
│
├── 02_embeddings/
│   ├── normalized_names.csv             ← Reference: raw name + 2 normalization versions
│   └── all_names_embeddings.npz         ← Embeddings array (embeddings, names, normalized_names)
│
├── 03_preprocessing/
│   └── artifacts/
│       ├── 00_exact_normalized_groups.csv          ← Raw data analysis
│       ├── 00_similarity_candidates.csv            ← Raw data near-duplicates
│       ├── thr_0.90_exact_normalized_groups.csv    ← Per-threshold analysis
│       ├── thr_0.90_similarity_candidates.csv
│       ├── thr_0.80_exact_normalized_groups.csv
│       ├── thr_0.80_similarity_candidates.csv
│       └── ... (for each threshold)
│
└── 04_llm_reps/
    ├── llm_reps_0.90.csv                ← LLM rep selection results (cluster-level)
    ├── members_llm_0.90.csv             ← LLM rep selection results (member-level)
    ├── llm_reps_0.80.csv
    ├── members_llm_0.80.csv
    └── ... (for each threshold)
    
    └── visualizations/
        ├── 01_unique_edge_names_constrained.png     ← Unique names vs threshold (constrained)
        ├── 02_avg_edges_per_rep_constrained.png     ← Avg edges vs threshold (constrained)
        ├── 03_unique_edge_names_free.png            ← Unique names vs threshold (free-form)
        └── 04_avg_edges_per_rep_free.png            ← Avg edges vs threshold (free-form)
```

## Files Explained

### Logging
- **pipeline_YYYYMMDD_HHMMSS.log**: Timestamped log file with DEBUG-level detail
  - All operations logged
  - Success indicators: ✓
  - Error indicators: ✗
  - Statistics for each threshold

### Clustering (01_clustering/)

#### collapsed_sim_X.XX.csv
Cluster-level summary (one row per cluster):
```
cluster_id | representative | total_count | members
0          | PLANTED        | 65          | 3
1          | YIELD          | 34          | 2
```

#### mapping_sim_X.XX.csv
Member-level mapping (one row per name):
```
cluster_id | name            | count | representative
0          | IS_PLANTED_IN  | 45    | PLANTED
0          | has_PLANTED    | 12    | PLANTED
1          | has_yield      | 20    | YIELD
```

### Embeddings (02_embeddings/)

#### normalized_names.csv
Comparison of normalization approaches:
```
raw_name          | normalized_for_embedding | normalized_for_analysis | count
IS_PLANTED_IN    | planted                 | planted                 | 45
has_been_PLANTED | planted                 | planted                 | 12
```

#### all_names_embeddings.npz
NumPy archive containing:
- `names`: Original raw names (shape: 861)
- `normalized_names`: Texts used for embedding (shape: 861)
- `embeddings`: Vector representations (shape: 861 × embedding_dim)

### Preprocessing Artifacts (03_preprocessing/artifacts/)

#### 00_exact_normalized_groups.csv (Raw Data Analysis)
Groups of raw names that normalize to the same term:
```
normalized | total_count | examples
planted    | 65          | "IS_PLANTED_IN, has_PLANTED, gets_planted"
yield      | 34          | "has_yield, produces_yield"
```

#### 00_similarity_candidates.csv (Raw Data Near-Duplicates)
Similar normalized terms found via TF-IDF:
```
term_a  | term_b   | similarity
planted | planting | 0.95
yield   | yields   | 0.93
```

#### thr_X.XX_exact_normalized_groups.csv & thr_X.XX_similarity_candidates.csv
Same analysis as `00_*` files, but for each threshold's clustering results.

### LLM Reps (04_llm_reps/)

#### llm_reps_X.XX.csv
LLM-selected representatives (cluster-level):
```
cluster_id | representative_llm  | representative_llm_free | representative | total_count | members
0          | IS_PLANTED_IN      | PLANTED                | PLANTED        | 65          | 3
1          | PRODUCES_YIELD     | YIELD_PRODUCTION       | YIELD          | 34          | 2
```

#### members_llm_X.XX.csv
LLM-selected representatives (member-level):
```
cluster_id | name            | count | representative_llm  | representative_llm_free
0          | IS_PLANTED_IN  | 45    | IS_PLANTED_IN      | PLANTED
0          | has_PLANTED    | 12    | IS_PLANTED_IN      | PLANTED
```

### Visualizations (04_llm_reps/visualizations/)

Four plots comparing constrained vs free-form LLM selections:

1. **01_unique_edge_names_constrained.png**: Number of unique representatives (constrained mode)
2. **02_avg_edges_per_rep_constrained.png**: Average edges per representative (constrained mode)
3. **03_unique_edge_names_free.png**: Number of unique representatives (free-form mode)
4. **04_avg_edges_per_rep_free.png**: Average edges per representative (free-form mode)

## Usage Example

```bash
python3 unified_dedup_pipeline.py \
    --tsv /path/to/edges.tsv \
    --out-dir /path/to/output \
    --model "llama3.1:70b" \
    --embed-model "bge-m3:567m" \
    --base-url "http://localhost:11434/v1" \
    --thresholds 0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90 \
    --sim-threshold 0.90
```

## 9-Step Pipeline

1. **Load names** - Read TSV/CSV, apply embedding normalization
2. **Preprocess** - Analyze raw data with complex normalization, find similarity candidates
3. **Save normalized** - Create reference mapping of all normalization versions
4. **Embed** - Get vector representations from Ollama
5. **Build matrices** - Compute cosine similarity and distance matrices
6. **Cluster** - For each threshold, group similar names
7. **Per-threshold artifacts** - Analyze each threshold's results
8. **LLM rep picking** - Select representatives (constrained + free-form)
9. **Visualize** - Create comparison plots

## Key Features

✅ **Comprehensive logging** - All operations logged with timestamps and statistics
✅ **Organized structure** - Numbered directories for clear flow
✅ **Dual normalization** - Shows both aggressive and simple normalization
✅ **Multiple thresholds** - Compare results across similarity levels
✅ **LLM flexibility** - Constrained (pick from cluster) + free-form (invent new) modes
✅ **Data quality insights** - Preprocessing artifacts for manual review

## Log File

The pipeline log includes:
- Start/end timestamps
- Configuration used
- Success/failure indicators for each step
- Statistics per threshold (number of clusters, edges, members)
- File locations for all outputs
- Any warnings or errors with full tracebacks
