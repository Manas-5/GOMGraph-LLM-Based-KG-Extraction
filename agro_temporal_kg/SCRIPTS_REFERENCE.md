# Scripts & Modules Reference

Detailed description of every key script and module in the `agro_temporal_kg` project.

---

## Table of Contents

1. [scripts/run.sh](#1-scriptsrunsh)
2. [scripts/run.py](#2-scriptsrunpy)
3. [Config Files — `configs/`](#3-config-files--configs)
4. [scripts/unified_dedup_pipeline.py](#4-scriptsunified_dedup_pipelinepy)
5. [unified_dedup/unified_dedup_pipeline.py](#5-unified_dedupunified_dedup_pipelinepy)
6. [scripts/llm_repick_reps.py](#6-scriptsllm_repick_repspy)
7. [scripts/llm_repick_reps_v2.py](#7-scriptsllm_repick_reps_v2py)
8. [agro_temporal_kg/falkordb_client.py](#8-agro_temporal_kgfalkordb_clientpy)
9. [agro_temporal_kg/logging_graphiti.py](#9-agro_temporal_kglogging_graphitipy)
10. [agro_temporal_kg/ollama_graphiti_client.py](#10-agro_temporal_kgollama_graphiti_clientpy)

---

## 1. `scripts/run.sh`

**Role:** Main orchestration shell script. The single entry point for batch-processing one or more books/datasets through the full temporal KG pipeline.

### What it does

`run.sh` is a sequential runner that loops over a numeric range (e.g. books 1–21) and, for each index, runs the full Python ingestion pipeline (`run.py create-tkg`) once. It is designed to be quiet in the terminal — only a compact summary is printed per item while all verbose output is redirected to log files.

The script handles:

- **Config resolution** — translates the loop index into a Hydra file config name (e.g. index `3` + `MODE=books` → `book3-llama70b`). The `FILE_CFG` environment variable can override this entirely.
- **DB name derivation** — calls a small inline Python snippet to compose the Hydra config and read the resulting `file.path`, then uses the filename stem (sanitized) as the FalkorDB database name. Chunk size/overlap and `DB_SUFFIX` are appended when set.
- **Pre-drop** — deletes the FalkorDB graph of that name before ingestion starts, so each run is always a fresh build (idempotent).
- **Job management** — launches `run.py` as a background subprocess, writes its PID to `logs/active_job.pid`, and polls `out.log` every 2 seconds to extract and display the current chunk progress (`chunk X/Y`).
- **Retry logic** — on non-zero exit codes, retries up to `MAX_RETRIES` times before marking a run as permanently failed.
- **Post-run steps** — optionally verifies the graph exists in FalkorDB (`VERIFY_GRAPH=1`) and optionally exports it to TSV (`EXPORT_GRAPH=1`).
- **Signal handling** — `trap` on `EXIT/INT/TERM` ensures the active Python subprocess is killed cleanly when `Ctrl+C` is pressed or when `kill_tkg.sh` terminates the script.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODE` | `books` | Selects file config naming: `books`, `tomato`, or `paris` |
| `LLAMA_MODEL_OVERRIDE` | `llama3.1:70b` | LLM model name passed to Hydra as `llm.model` |
| `LLM_BASE_URL_OVERRIDE` | _(empty)_ | Override `llm.base_url` if set |
| `EMBEDDER_BASE_URL_OVERRIDE` | _(empty)_ | Override `embedder.base_url` if set |
| `DB_SUFFIX` | _(empty)_ | Appended to FalkorDB database name (for parallel runs) |
| `MAX_RETRIES` | `1` | Number of retry attempts on failure |
| `VERIFY_GRAPH` | `1` | `1` = check graph exists in FalkorDB after completion |
| `EXPORT_GRAPH` | `0` | `1` = export graph to TSV after completion |
| `EXPORT_DIR` | `$ROOT/exported_data` | Directory for TSV export output |
| `CHUNK_SIZE` | _(empty)_ | Override `text_splitter.chunk_size` |
| `CHUNK_OVERLAP` | _(empty)_ | Override `text_splitter.chunk_overlap` |
| `GPU` | _(empty)_ | If set, prefixes command with `CUDA_VISIBLE_DEVICES=<GPU>` |
| `FILE_CFG` | _(empty)_ | Force a specific file config name (bypasses index-based lookup) |

### Positional arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `$1` (`BOOK_START`) | `1` | First loop index |
| `$2` (`BOOK_END`) | `21` | Last loop index (inclusive) |

### Key helper functions

- **`file_cfg_for(n)`** — returns the Hydra file config name for index `n` based on `MODE`. Respects `FILE_CFG` override.
- **`graph_exists(db)`** — inline Python snippet that connects to FalkorDB and returns exit code 0 if the graph exists.
- **`progress_from_runlog(runlog)`** — greps `out.log` for the most recent `Processing chunk X/Y` line and returns the fraction `X/Y` for live display.
- **`format_secs(T)`** — formats elapsed seconds as `HH:MM:SS`.

---

## 2. `scripts/run.py`

**Role:** The Python CLI that `run.sh` invokes for each item. Built with [Typer](https://typer.tiangolo.com/) and [Hydra](https://hydra.cc/). Also usable directly for one-off operations.

### Commands

#### `create-tkg`

Runs the full temporal knowledge graph pipeline for a single file.

```
python scripts/run.py create-tkg [--override "key=value ..."] [--print-config]
```

Internally it:
1. Calls `compose_config("create_tkg", overrides=...)` to assemble the Hydra config from `configs/create_tkg.yaml` and any override strings.
2. Parses the result into a `CreateTemporalKGConfig` Pydantic model.
3. If `--print-config` is set, dumps the resolved JSON config and exits.
4. Otherwise, drops any pre-existing graph of the same name from FalkorDB.
5. Calls `create_temporal_kg(config)` — the main pipeline function from `agro_temporal_kg/pipelines/`.

The `--override` string is space-separated `key=value` pairs using Hydra override syntax (e.g. `"file=book3-llama70b llm.model=llama3.1:70b"`).

#### `list-graphs`

Lists all graphs currently stored in FalkorDB, with node counts and relation type statistics for each.

```
python scripts/run.py list-graphs [--host HOST] [--port PORT]
```

Default: `localhost:6380`.

#### `drop-graph`

Permanently deletes a graph from FalkorDB.

```
python scripts/run.py drop-graph <GRAPH_NAME> [--host HOST] [--port PORT] [--force]
```

Without `--force`, prompts for confirmation before deletion.

#### `export-graph`

Exports a graph to two TSV files: `nodes_<name>.tsv` and `edges_<name>.tsv`.

```
python scripts/run.py export-graph <GRAPH_NAME> \
  --output-dir ./exported_data \
  [--group-id GROUP_ID] \
  [--host HOST] [--port PORT]
```

The export includes all Entity, Episodic, and Community nodes, and all RELATES_TO, MENTIONS, and HAS_MEMBER edges. Use `--group-id` to filter the export to a specific group.

---

## 3. Config Files — `configs/`

The project uses [Hydra](https://hydra.cc/) for configuration composition. The top-level config is `configs/create_tkg.yaml`, which sets defaults and references sub-configs via Hydra config groups.

### `configs/create_tkg.yaml`

The root config file. Declares the default config group selections:

```yaml
defaults:
  - text_splitter: default
  - llm: ollama
  - embedder: ollama
  - falkordb: default
  - file: book1
  - prompts/extract_text: default
  - prompts/extract_edges: default
  - entity_types: all
  - edge_types: all
  - edge_type_map: etm
```

Each item maps to a subdirectory under `configs/` containing YAML files that can be swapped via overrides.

### Config Group Directories

#### `configs/llm/`

Configures the language model used for knowledge extraction.

| File | Description |
|------|-------------|
| `ollama.yaml` | Local Ollama endpoint (`http://localhost:11434/v1`). Sets `model`, `temperature`, `api_key`, `base_url`. |
| `openrouter.yaml` | Cloud LLM via OpenRouter. Reads `OPENROUTER_API_KEY` from the environment. |
| `mixtral_8_22.yaml` | Mixtral 8×22B model configuration. |

Key fields: `model` (model name/tag), `temperature` (default `0.0` for determinism), `api_key`, `base_url`.

#### `configs/embedder/`

Configures the embedding model for vector representations used in Graphiti's entity resolution.

| File | Description |
|------|-------------|
| `ollama.yaml` | Local Ollama embedder. Default model: `bge-m3:567m`, dim: 768. |
| `openai.yaml` | OpenAI-compatible embedding endpoint. |

Key fields: `embedding_model`, `embedding_dim`, `base_url`, `api_key`.

#### `configs/file/`

One YAML file per input document. Tells the pipeline what to ingest and provides metadata.

Key fields per file config:

| Field | Description |
|-------|-------------|
| `path` | Absolute path to the input `.txt` file |
| `group_id` | FalkorDB graph identifier / Graphiti group ID |
| `source_description` | Human-readable description of the source document |
| `reference_year` | Publication/reference year used for temporal anchoring |

Notable configs:

| Config | Description |
|--------|-------------|
| `book1-llama70b.yaml` through `book21-llama70b.yaml` | Individual books from the GOM corpus (21 books total) |
| `full_gom_corpus.yaml` | All 21 books merged into a single file (`full_gom_corpus.txt`) |
| `tomato_1.yaml` through `tomato_10.yaml` | Tomato cultivation dataset, split into 10 parts |
| `paris.yaml` | Paris horticulture dataset |
| `L_horticulture.yaml` | Another standalone horticulture text |
| `test.yaml` | Small test file for smoke-testing the pipeline |

#### `configs/falkordb/`

FalkorDB connection settings.

| File | Description |
|------|-------------|
| `default.yaml` | Default: `host=localhost`, `port=6380`, `database=agro-database` |

#### `configs/text_splitter/`

Controls how input text is chunked before ingestion.

| File | Description |
|------|-------------|
| `default.yaml` | `chunk_size=1000`, `chunk_overlap=150`, default separator hierarchy |

#### `configs/entity_types/`

Defines which entity types Graphiti should extract and track.

| File | Description |
|------|-------------|
| `all.yaml` | All domain-specific agricultural entity types |
| `minimal.yaml` | Reduced set of core types |
| `plants.yaml` | Plant-focused entity types only |
| `pests_diseases.yaml` | Pest and disease entity types only |
| `none.yaml` | No custom entity types (Graphiti defaults) |

#### `configs/edge_types/` and `configs/relation_types/`

Defines which relationship types can be extracted between entities.

| File | Description |
|------|-------------|
| `all.yaml` | All relation types (temporal, causal, spatial) |
| `temporal.yaml` | Temporal relationships only |
| `causal.yaml` | Causal relationships only |
| `spatial.yaml` | Spatial relationships only |
| `none.yaml` | No custom edge types (Graphiti defaults) |

#### `configs/edge_type_map/`

Maps `(source_entity_label, target_entity_label)` pairs to the subset of allowed edge types between them. Constrains which relationships can exist between specific entity type combinations.

| File | Description |
|------|-------------|
| `etm.yaml` | The production edge type map used by default |
| `all.yaml` | All combinations allowed |

#### `configs/prompts/`

Version-controlled prompt files for each Graphiti step. Organized into sub-groups:

| Subdirectory | Controls |
|--------------|----------|
| `prompts/extract_text/` | Prompt for extracting entities and text from episodes |
| `prompts/extract_edges/` | Prompt for extracting relationships between entities |
| `prompts/dedupe_nodes/` | Prompt for deduplicating entity nodes |
| `prompts/dedupe_edges/` | Prompt for deduplicating edges |
| `prompts/extract_edge_dates/` | Prompt for extracting temporal dates from edges |
| `prompts/invalidate_edges/` | Prompt for invalidating outdated edges |
| `prompts/snippets/` | Reusable prompt snippets (e.g. `summary_instructions`) |

Each subdirectory contains a `default.yaml` (pointing to the active version) plus versioned files (`system_v0.yaml`, `user_v0.yaml`, `user_v1.yaml`, etc.) allowing prompt A/B testing without code changes.

### Pydantic Config Classes (`agro_temporal_kg/configs/`)

The Python side of configuration lives in `agro_temporal_kg/configs/`:

- **`compose_config.py`** — `compose_config()` helper that initialises Hydra, composes the config from the `configs/` directory, resolves all interpolations, and returns an `OmegaConf DictConfig`.
- **`create_temporal_kg.py`** — Pydantic models that mirror the YAML structure:
  - `CreateTemporalKGConfig` — top-level config class with fields for `embedder`, `falkor_db`, `text_splitter`, `llm`, `file`, `prompts`, `entity_types`, `edge_types`, `edge_type_map`.
  - `LLMConfig` — `model`, `temperature`, `api_key`, `base_url`.
  - `EmbedderConfig` — `embedding_model`, `embedding_dim`, `base_url`, `api_key` (reads `EMBEDDER_*` env vars).
  - `FalkorDBConfig` — `host`, `port`, `database`.
  - `FileConfig` — `path`, `group_id`, `source_description`, `reference_year`.
  - `TextSplitterConfig` — `chunk_size`, `chunk_overlap`, `separators`.
  - `PromptConfig` / `PromptTypeConfig` — version selectors for prompt files.

`from_omegaconf()` on `CreateTemporalKGConfig` handles all necessary key renaming (e.g. `falkordb` → `falkor_db`) and nested structure flattening needed to bridge Hydra config groups with Pydantic.

---

## 4. `scripts/unified_dedup_pipeline.py`

**Role:** The **canonical, production** edge name deduplication pipeline. This is the active version used for post-processing knowledge graphs. It is a single self-contained script that takes raw or pre-aggregated edge data and produces clustered, LLM-canonicalized edge name mappings.

### Purpose

After the KG ingestion pipeline runs, the knowledge graph contains many semantically equivalent but syntactically different edge names (e.g. `planted_in`, `is planted in`, `were planted`, `plant in`). This script normalizes, embeds, clusters, and uses an LLM to select a single canonical representative name per cluster, producing a clean edge name vocabulary.

### Pipeline Steps

The script runs 9 sequential steps:

1. **Load** — reads raw `edges.tsv` (with a `type` column) or a pre-aggregated `name/count` CSV/TSV. Filters to `RELATES_TO` edges only. Normalizes names for embedding (removes aux prefixes, stopwords, punctuation).

2. **Preprocessing** — on the raw data, computes exact normalized groups (grouping syntactically similar names) and near-duplicate similarity candidates using TF-IDF character n-gram cosine similarity. Saves to `03_preprocessing/artifacts/00_exact_normalized_groups.csv` and `00_similarity_candidates.csv`.

3. **Save normalized list** — writes a CSV mapping each raw name to its embedding-ready normalized form.

4. **Embed** — sends normalized names to an Ollama-compatible `/v1/embeddings` endpoint in batches of 64. Saves embeddings as a compressed `.npz` file.

5. **Build similarity/distance matrices** — computes a pairwise cosine similarity matrix and a distance matrix (`1 - similarity`) from the embeddings.

6. **Cluster** — runs agglomerative clustering with `average` linkage at each threshold in the `--thresholds` list. For each threshold, produces a `collapsed_sim_{thr}.csv` (one row per cluster with a heuristic representative) and a `mapping_sim_{thr}.csv` (one row per original name, mapping it to its cluster).

7. **Per-threshold preprocessing artifacts** — for each clustering threshold, saves a normalized group analysis and similarity candidates for the clustered data.

8. **LLM rep picking** — for each threshold, calls an LLM (via the OpenAI-compatible chat completions API) for every cluster. The LLM is called twice:
   - **Constrained** — must pick exactly one label from the provided cluster members.
   - **Free-form** — can propose any concise canonical label (not restricted to the members list).
   Results are saved as `llm_reps_{thr}.csv` and `members_llm_{thr}.csv`.

9. **Visualization** — generates 4 Seaborn line plots showing unique edge name count and average edges per edge name vs. threshold, for both constrained and free-form LLM selections.

### Usage

```bash
python3 scripts/unified_dedup_pipeline.py \
    --tsv /path/to/edges.tsv \
    --out-dir /path/to/output \
    --model "llama3.1:70b" \
    --embed-model "bge-m3:567m" \
    --base-url "http://localhost:11434/v1" \
    --thresholds 0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90 \
    --sim-threshold 0.90
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--tsv` | _(required)_ | Path to raw edges TSV/CSV or pre-aggregated name/count file |
| `--sep` | auto | Field separator (auto-detected from extension) |
| `--out-dir` | `unified_dedup_output` | Root output directory |
| `--model` | `llama3.1:70b` | LLM for representative picking |
| `--embed-model` | `bge-m3:567m` | Embedding model |
| `--base-url` | `http://localhost:11434/v1` | OpenAI-compatible API base URL |
| `--api-key` | `abc` | API key (or set via env variable) |
| `--thresholds` | `0.10–0.90` step 0.10 | Comma-separated cosine similarity thresholds |
| `--sim-threshold` | `0.90` | Cosine similarity cutoff for near-duplicate detection in preprocessing |
| `--limit` | _(none)_ | Limit to top-N most frequent names (for testing) |
| `--distance-mode` | `false` | Treat thresholds as cosine distance instead of similarity |

### Output Structure

```
out-dir/
├── logs/                        # Timestamped log file
├── 01_clustering/               # Per-threshold clustering outputs
│   ├── collapsed_sim_0.10.csv   # Cluster representatives + counts
│   ├── mapping_sim_0.10.csv     # Name → cluster mapping
│   └── ...
├── 02_embeddings/               # Embeddings and normalized names
│   ├── normalized_names.csv
│   └── all_names_embeddings.npz
├── 03_preprocessing/
│   └── artifacts/
│       ├── 00_exact_normalized_groups.csv
│       ├── 00_similarity_candidates.csv
│       ├── thr_0.10_exact_normalized_groups.csv
│       ├── thr_0.10_similarity_candidates.csv
│       └── ...
└── 04_llm_reps/
    ├── llm_reps_0.10.csv        # LLM-chosen reps (constrained + free) per cluster
    ├── members_llm_0.10.csv     # Member-level view with LLM reps attached
    ├── ...
    └── visualizations/
        ├── 01_unique_edge_names_constrained.png
        ├── 02_avg_edges_per_rep_constrained.png
        ├── 03_unique_edge_names_free.png
        └── 04_avg_edges_per_rep_free.png
```

---

## 5. `unified_dedup/unified_dedup_pipeline.py`

**Role:** Exploratory variant of the dedup pipeline. Differs from the canonical `scripts/` version by adding two extra steps:

- `group_by_normalized()` — pre-groups raw edge names by their normalized embedding form before clustering, so labels like `"is a type of"` and `"is_a_type_of"` are merged with summed counts before embedding.
- `consolidate_clusters_by_normalized_form()` — post-clustering merge of clusters whose members share identical normalized forms.

The final thesis numbers (688 → 115 canonical relations, 100% node-duplicate elimination across 1,533 nodes) were produced with the `scripts/` version. Treat this file as the alternative implementation kept for reference; new work should use `scripts/unified_dedup_pipeline.py` unless the extra normalization-grouping behavior is specifically wanted.

---

## 6. `scripts/llm_repick_reps.py`

**Role:** The **first version** of the LLM-assisted representative picker. Operates on pre-existing clustering output from a separate clustering step, rather than running the full pipeline end-to-end like `unified_dedup_pipeline.py`.

### Purpose

This script takes already-computed cluster files (from a separate clustering run) and uses an LLM to select the best canonical representative label for each cluster. The LLM is constrained to pick from the provided member labels only (no label invention).

It also generates embedding-based visualizations (avg edges per new edge name vs. threshold) using Seaborn.

### Key Differences vs `unified_dedup_pipeline.py`

- Takes a `--cluster-dir` of pre-computed clustering results as input rather than raw edges.
- Runs only the LLM rep-picking + visualization steps (no embedding, no clustering).
- LLM output is constrained only — no free-form LLM picking.
- Simpler normalization: just lowercasing + underscore replacement (no auxiliary prefix or stopword removal).
- No preprocessing artifacts (no exact normalized groups, no similarity candidates).
- Does not have the structured 9-step pipeline with organized subdirectory outputs.

This script was used in early experiments and has been superseded by `unified_dedup_pipeline.py`, which runs the complete end-to-end workflow.

### Usage

```bash
python3 scripts/llm_repick_reps.py \
    --cluster-dir /path/to/cluster_runs \
    --out-dir /path/to/llm_reps \
    --distance-mode \
    --model "llama3.1:70b" \
    --embed-model "bge-m3:567m" \
    --save-embeddings \
    --base-url "http://localhost:11434/v1" \
    --api-key "abc" \
    --thresholds 0.00,0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--cluster-dir` | _(required)_ | Directory containing pre-computed cluster files |
| `--out-dir` | _(required)_ | Output directory for LLM rep results |
| `--model` | `llama3.1:70b` | LLM model |
| `--embed-model` | `bge-m3:567m` | Embedding model (for optional embedding step) |
| `--base-url` | `http://localhost:11434/v1` | API base URL |
| `--api-key` | _(empty)_ | API key |
| `--thresholds` | `0.00–0.90` | Comma-separated thresholds to process |
| `--distance-mode` | `false` | Interpret thresholds as distance values |
| `--save-embeddings` | `false` | Save embeddings to disk |

---

## 7. `scripts/llm_repick_reps_v2.py`

**Role:** The **second version** of the LLM representative picker, adding per-threshold preprocessing artifacts and near-duplicate detection on top of the v1 functionality. It sits between `llm_repick_reps.py` and `unified_dedup_pipeline.py` in terms of capability.

### Key Additions vs v1

- **Improved normalization** — uses the full `normalize_relation()` function that removes auxiliary verb prefixes (`is`, `are`, `was`, `were`, `can be`, etc.) and light stopwords (`a`, `an`, `the`, `of`) in addition to lowercasing and punctuation stripping.
- **Per-threshold preprocessing artifacts** — for each clustering threshold, generates exact normalized groupings and TF-IDF character n-gram similarity candidates (near-duplicate pairs above a configurable cosine threshold).
- **`--sim-threshold` argument** — controls the cosine similarity cutoff for near-duplicate detection.
- No free-form LLM picking (still constrained only, like v1).
- No end-to-end pipeline (still takes pre-computed clustering directories as input).

This version added the preprocessing analysis capability that was later fully integrated into `unified_dedup_pipeline.py`. For new work, prefer `unified_dedup_pipeline.py` which combines all steps.

### Usage

```bash
python3 scripts/llm_repick_reps_v2.py \
    --cluster-dir /path/to/cluster_runs \
    --out-dir /path/to/llm_reps_v2 \
    --distance-mode \
    --model "llama3.1:70b" \
    --embed-model "bge-m3:567m" \
    --save-embeddings \
    --base-url "http://localhost:11434/v1" \
    --api-key "abc" \
    --thresholds 0.00,0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90 \
    --sim-threshold 0.90
```

The arguments are identical to v1 plus `--sim-threshold`.

---

## 8. `agro_temporal_kg/falkordb_client.py`

**Role:** High-level Python client for all FalkorDB operations used throughout the project. Abstracts the raw Redis/FalkorDB protocol behind clean, typed methods.

### Classes

#### `FalkorDBConnection`

A context manager that creates and tests a Redis connection to FalkorDB. Used internally by `FalkorDBClient`. Handles connection errors with informative messages and clean exits.

```python
with FalkorDBConnection(host="localhost", port=6380) as r:
    result = r.execute_command("GRAPH.LIST")
```

#### `FalkorDBClient`

The main client class. Instantiate with a host, port, and optionally a config directory (to load connection settings from a Hydra config file).

```python
client = FalkorDBClient(host="localhost", port=6380)
```

### Methods

**`list_graphs() → list[str]`**
Returns the names of all graphs currently stored in FalkorDB, by issuing a `GRAPH.LIST` Redis command.

**`get_graph_statistics(graph_name) → dict`**
Queries node count, total edge count, and per-relation-type counts for a named graph. Returns:
```python
{
    "node_count": int,
    "total_relations": int,
    "rel_type_counts": {"RELATES_TO": int, "MENTIONS": int, ...}
}
```

**`delete_graph(graph_name) → bool`**
Issues a `GRAPH.DELETE` Redis command. Returns `True` if the graph was deleted, `False` if it didn't exist.

**`export_graph_to_tsv(graph_name, output_dir, group_id=None) → tuple[Path, Path]`**
Exports a full graph to two TSV files. Queries FalkorDB via Cypher for all node types (Entity, Episodic, Community) and all edge types (RELATES_TO, MENTIONS, HAS_MEMBER). Embedding fields are automatically stripped from attributes to keep files manageable.

Returns `(nodes_file, edges_file)` paths.

The output filenames are `nodes_<sanitized_graph_name>.tsv` and `edges_<sanitized_graph_name>.tsv`.

**TSV schema — nodes file:**

| Column | Description |
|--------|-------------|
| `uuid` | Node UUID |
| `type` | `Entity`, `Episodic`, or `Community` |
| `name` | Node name |
| `group_id` | Group identifier |
| `labels` | JSON array of labels |
| `created_at` | Creation timestamp |
| `summary` | Entity/Community summary |
| `attributes` | JSON dict of extra properties (embeddings excluded) |
| `source` | Episodic only: source identifier |
| `source_description` | Episodic only |
| `content` | Episodic only: raw text content |
| `valid_at` | Episodic only: temporal anchor |
| `entity_edges` | Episodic only: linked edge UUIDs |

**TSV schema — edges file:**

| Column | Description |
|--------|-------------|
| `uuid` | Edge UUID |
| `type` | `RELATES_TO`, `MENTIONS`, or `HAS_MEMBER` |
| `source_node_uuid` | UUID of the source node |
| `target_node_uuid` | UUID of the target node |
| `group_id` | Group identifier |
| `created_at` | Creation timestamp |
| `name` | Edge label / relation name (RELATES_TO only) |
| `fact` | Fact string (RELATES_TO only) |
| `episodes` | JSON list of episode UUIDs (RELATES_TO only) |
| `expired_at` | Expiry timestamp (RELATES_TO only) |
| `valid_at` | Validity start (RELATES_TO only) |
| `invalid_at` | Invalidity timestamp (RELATES_TO only) |
| `attributes` | JSON dict of extra properties (RELATES_TO only) |

### Static Helpers

- **`_escape_tsv_value(value)`** — Escapes a Python value for safe TSV inclusion: handles `None`, lists/dicts (JSON-encoded), datetimes, and string escaping of `\t`, `\n`, `\r`.
- **`_filter_embeddings_from_attributes(attributes)`** — Strips any attribute key containing the word `embedding` before writing to TSV.
- **`_format_labels(labels)`** — Formats a list of label strings as a JSON array.

---

## 9. `agro_temporal_kg/logging_graphiti.py`

**Role:** A thin instrumented subclass of `Graphiti` (from `graphiti_core`) that adds structured logging for deduplication events at the node and edge level.

### Class: `LoggingGraphiti`

Extends `graphiti_core.graphiti.Graphiti`. It overrides two methods to inject logging calls:

#### `resolve_extracted_nodes(...)`

After calling the parent `resolve_extracted_nodes()`, logs a structured summary line at `INFO` level:

```
[DEDUP:NODES] extracted=N resolved=M remapped=K duplicates=D
```

Where:
- `extracted` — number of entity nodes that came out of the LLM extraction step.
- `resolved` — number of nodes after deduplication against the existing graph.
- `remapped` — number of UUID remappings applied (nodes merged into existing ones).
- `duplicates` — number of `(extracted, existing)` duplicate pairs found.

#### `_extract_and_resolve_edges(...)`

After calling the parent implementation, logs:

```
[DEDUP:EDGES] resolved=N invalidated=M with_dates=K
```

Where:
- `resolved` — number of entity edges that survived deduplication.
- `invalidated` — number of edges that were marked invalid by the contradiction detection step.
- `with_dates` — number of resolved edges that have a non-null `valid_at` or `invalid_at` timestamp.

### Why it exists

The base `Graphiti` class from `graphiti_core` does not emit structured logs for deduplication statistics. `LoggingGraphiti` makes it possible to track deduplication quality over time by examining `out.log` files, without modifying the upstream library.

---

## 10. `agro_temporal_kg/ollama_graphiti_client.py`

**Role:** A custom LLM client for Graphiti that is optimized for use with locally-hosted Ollama models (and any OpenAI-compatible endpoint). Extends `OpenAIGenericClient` from `graphiti_core`.

### Problem It Solves

Graphiti's built-in clients rely on OpenAI-style structured outputs (function calling / JSON mode). Local models served by Ollama do not reliably support these features in the same way. The `OllamaGraphitiClient` bridges this gap by:

1. **Simplifying Pydantic schemas** — strips `$defs`, resolves `$ref` references, and keeps only essential keys (`type`, `properties`, `items`, `required`, `description`, `title`) before sending to the model.
2. **Prompt injection** — injects a simplified schema and a concrete example into the last user message, telling the model exactly what JSON format to return and showing it an example of the expected output.
3. **Robust JSON parsing** — handles model responses that wrap JSON in markdown code blocks (` ```json ... ``` ` or ` ``` ... ``` `), plain JSON, or JSON embedded in surrounding text.
4. **Auto-repair** — if the model emits unquoted `SCREAMING_SNAKE_CASE` values for `relation_type` fields, the client repairs the JSON by quoting them before retrying the parse.
5. **Graceful fallback** — if parsing or Pydantic validation still fails, returns an empty-but-valid structure derived from the schema, so Graphiti does not crash on a single malformed response.
6. **Deterministic sampling** — calls the model with `temperature=0`, `top_p=1`, `seed=0`, `top_k=0`, `repeat_penalty=1.0` to maximize reproducibility across runs.
7. **Response canonicalization** — sorts dict keys recursively before returning, for additional determinism.

### Class: `OllamaGraphitiClient`

Inherits from `OpenAIGenericClient`. The key override is `generate_response()`.

#### `generate_response(messages, response_model=None, **kwargs)`

The main entry point called by Graphiti for every LLM interaction.

- If `response_model` is `None`: calls the model and returns the raw text response.
- If `response_model` is provided (a Pydantic class): simplifies its schema, injects schema + example into the prompt, calls the model, parses the JSON response, validates with Pydantic, and returns the validated dict. Falls back to an empty structure on errors.

#### Helper Methods

| Method | Description |
|--------|-------------|
| `_simplify_schema(schema)` | Recursively resolves `$ref` references and strips non-essential schema keys |
| `_create_example_from_schema(schema)` | Builds a concrete example instance from a schema (for prompt injection) |
| `_create_empty_from_schema(schema)` | Builds an empty-but-valid fallback structure from a schema |
| `_extract_json_from_response(text)` | Extracts JSON from a raw model response, handling markdown blocks |
| `_quote_relation_types(raw)` | Regex-repairs unquoted `SCREAMING_SNAKE_CASE` values in JSON strings |
| `_canonicalize_for_determinism(obj)` | Recursively sorts dict keys in the response for reproducibility |

### Supported Models

Any model that can be served via an OpenAI-compatible endpoint works with this client. This includes all models available through Ollama: LLaMA, Mistral, Mixtral, Qwen, DeepSeek, etc. It is also compatible with OpenRouter and similar cloud proxies.
