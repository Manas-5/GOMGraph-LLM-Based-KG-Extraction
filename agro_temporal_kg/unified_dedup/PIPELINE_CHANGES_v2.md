# Pipeline Changes - Option A Implementation (Group Then Embed)

**Date:** February 17, 2026  
**Version:** 2.0  
**Issue Addressed:** Normalize before embedding to reduce unique relations count

## Problem Statement

The original pipeline was:
1. Load 1147 unique raw names
2. Normalize each for embedding purposes
3. **Embed all 1147 names separately** (even though some normalize to the same form)
4. Cluster the 1147 embeddings → still get up to 1147 clusters

Result: At highest similarity threshold (0.90), still getting 996 clusters instead of expected ~861 or fewer.

**Root Cause:** Names that normalize to the same embedding form were being embedded as separate vectors, so they never clustered together.

## Solution: Group Before Embedding (Option A)

### New Pipeline Flow

1. **Load raw names** - Read TSV/CSV
2. **GROUP by normalized form** - Consolidate raw names with identical normalized embeddings (NEW)
3. **Save mapping** - Document which raw names map to each normalized form (NEW)
4. Preprocess & analyze
5. Embed normalized forms (now ~1109 instead of 1147)
6. Cluster the ~1109 embeddings
7. LLM representative selection
8. Visualize

### Expected Outcome

- Input: 1147 unique raw names
- After grouping: ~1109 unique normalized forms (38 consolidated)
- Embeddings: ~1109 vectors instead of 1147
- Clustering: Now can merge identical normalized forms at step 6
- Final result: Should get significantly fewer clusters (approaching 861 target)

## Code Changes

### 1. New Function: `group_by_normalized()`

**Location:** After `load_names()` function

```python
def group_by_normalized(names_df: pd.DataFrame) -> tuple:
    """
    Group raw names by their normalized embedding form.
    
    Returns:
    - grouped_df: deduplicated by normalized form with aggregated counts
    - mapping_raw_to_norm: dict mapping raw names to normalized form
    - mapping_norm_to_raws: dict mapping normalized form to list of raw names
    """
```

**What it does:**
- Takes raw names dataframe
- Groups by `embed_text` (normalized form)
- Aggregates counts (sums edges from all raw names in group)
- Keeps list of all raw names that map to each normalized form
- Selects longest raw name as representative for identity purposes

**Returns:**
- `grouped_df`: 1109 rows (one per unique normalized form)
- `mapping_raw_to_norm`: {raw_name → normalized_form}
- `mapping_norm_to_raws`: {normalized_form → [list of raw names]}

### 2. Pipeline Step Changes

#### STEP 1: Load names (unchanged in logic, renamed variables)
```
Before: Load 1147 unique names
After:  Load 1147 unique names (still raw)
```

#### STEP 1.5: NEW - Group by normalized form
```python
logger.info("STEP 1.5: Grouping by normalized embedding form...")

grouped_df, mapping_raw_to_norm, mapping_norm_to_raws = group_by_normalized(raw_names_df)

# Extract deduplicated data for embedding
names_list = grouped_df["representative_raw_name"].tolist()      # ~1109 (raw names)
embed_texts_list = grouped_df["embed_text"].tolist()             # ~1109 (normalized)
counts_list = grouped_df["count"].to_numpy()                     # ~1109 (aggregated)

logger.info(f"✓ Grouped into {len(grouped_df)} unique normalized forms")
logger.info(f"✓ Reduction: 1147 → {len(grouped_df)} ({1147-len(grouped_df)} consolidated)")
```

#### STEP 2: Preprocess (uses original raw data for analysis)
- Now explicitly uses `raw_names_df` (the 1147 original names)
- This is important: preprocessing analyzes semantic relationships in original data
- But clustering will be on deduplicated normalized forms

#### STEP 3: Save normalized list and mapping (enhanced)
Now saves TWO files instead of one:
1. `normalized_names.csv` - Standard output with all three normalization levels
2. `raw_to_normalized_mapping.csv` - NEW: Maps which raw names consolidate to each normalized form

Example mapping file:
```csv
raw_name,normalized_form
HAS_BEEN_PLANTED,planted
has_been_planted,planted
planted,planted
```

#### STEP 4: Embed (fewer vectors now)
```
Before: Embed 1147 vectors → 1147 × 1024
After:  Embed ~1109 vectors → 1109 × 1024

Time saved: ~3% fewer vectors
```

#### STEP 5-9: Clustering onwards
Same logic, but now working with consolidated vectors, so:
- Similarity matrices: 1109 × 1109 instead of 1147 × 1147
- Clusters can form from identical normalized groups
- Expected final reps at 0.90 threshold: ~700-900 instead of 996

## Data Flow Diagram

```
Input TSV (1147 raw names)
         ↓
   STEP 1: Load
   (1147 names)
         ↓
   STEP 1.5: Group by normalized ← NEW
   (1147 → 1109 unique normalized forms)
         ↓
   Extract for embedding:
   names_list = representative raw names (1109)
   embed_texts_list = normalized forms (1109)
   counts_list = aggregated counts (1109)
         ↓
   STEP 2: Preprocess (using original 1147 raw data)
   - Analyze semantic structure
   - Find similarity candidates
         ↓
   STEP 3: Save mappings
   - normalized_names.csv (1109 deduplicated)
   - raw_to_normalized_mapping.csv (1147→1109 mapping)
         ↓
   STEP 4: Embed (1109 vectors)
         ↓
   STEP 5: Build matrices (1109×1109)
         ↓
   STEP 6-9: Cluster & LLM (fewer clusters expected)
```

## Impact Analysis

### Pros
✅ Reduces redundant embeddings (1147 → 1109)  
✅ Eliminates "multiple embeddings for same meaning" problem  
✅ Clusters naturally merge identical normalized forms  
✅ Moves closer to 861 target  
✅ More efficient (fewer vectors to process)  
✅ More interpretable (raw names grouped by meaning)  

### Cons
⚠️ Slightly more complex pipeline (one additional step)  
⚠️ Must maintain mapping for downstream use  
⚠️ Preprocessing now works on 1147 names but clustering on 1109  

### Expected Improvements

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| Unique raw names | 1147 | 1147 | - |
| Unique normalized forms | 1147 | 1109 | - |
| Embedding vectors | 1147 | 1109 | - |
| Clusters @ 0.90 threshold | 996 | ~700-850 | <861 |
| Similarity matrix size | 1147² | 1109² | - |
| Processing time | 100% | ~95% | - |

## Testing the Changes

```bash
cd /mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/unified_dedup

# Run with the new grouping logic
python3 unified_dedup_pipeline.py \
    --tsv /mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/exported_data/1_Manuel_pratique_de_la_culture_maraichere_de_Paris__par_Moreau_et_Daverne__1845/edges_*.tsv \
    --out-dir output_v2

# Check the reduction
echo "=== Checking grouping efficiency ==="
wc -l output_v2/02_embeddings/normalized_names.csv
wc -l output_v2/02_embeddings/raw_to_normalized_mapping.csv

# Compare cluster counts
echo "=== Comparing cluster counts ==="
head -5 output_v2/01_clustering/mapping_sim_0.90.csv
wc -l output_v2/01_clustering/mapping_sim_0.90.csv
```

## Files Modified

- `unified_dedup_pipeline.py`
  - Added `group_by_normalized()` function (NEW)
  - Modified STEP 1 to load raw names first
  - Added STEP 1.5 for grouping (NEW)
  - Updated STEP 2 to use raw_names_df explicitly
  - Enhanced STEP 3 to save mapping file
  - Rest of pipeline unchanged

## Backward Compatibility

⚠️ **Breaking change:** Output structure slightly different
- New file: `02_embeddings/raw_to_normalized_mapping.csv`
- Other files have same format as before

## Next Steps

1. **Run the pipeline** with new code:
   ```bash
   python3 unified_dedup_pipeline.py --tsv /path/to/data.tsv
   ```

2. **Compare outputs** between old and new:
   - Check `01_clustering/mapping_sim_0.90.csv` line count
   - Should be 700-900 instead of 996

3. **Verify mapping correctness**:
   - Open `02_embeddings/raw_to_normalized_mapping.csv`
   - Spot-check that consolidations make sense

4. **Monitor efficiency**:
   - Embedding should be ~5% faster
   - Check `logs/pipeline_*.log` for timing

## Summary

**Option A** restructures the pipeline to group raw names by their normalized embedding form **before** embedding and clustering. This eliminates redundant vectors and allows the clustering step to naturally consolidate names that normalize to the same form, moving closer to the 861-relation target.

The key insight: **Normalize first, then embed** (not embed first, then try to cluster).
