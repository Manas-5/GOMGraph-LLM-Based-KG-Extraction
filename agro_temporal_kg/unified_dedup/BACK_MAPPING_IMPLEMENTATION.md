# Fix for Option A: Back-Mapping Implementation

## The Problem
After clustering 1108 representatives, the clustering output only includes those 1108 representatives. But we need to expand it to map all 1147 raw names. Consolidated raw names should map to their group representative's cluster.

## The Solution: Back-Mapping Step

### Location in Code
**File:** `unified_dedup_pipeline.py`  
**After:** The current clustering loop (around line 790, after rebuilding collapsed_df)  
**Before:** Saving the clustering outputs to disk

### Implementation Strategy

The key is to track:
1. Which representative was chosen for each normalized form
2. The cluster assignment for each representative  
3. The mapping of all 1147 raw names to their representatives

Then expand the mapping_df to include all raw names.

### Required Data Structures

Need to pass to the clustering loop:
- `grouped_df`: Contains mapping of normalized_form → representative_raw_name
- `mapping_raw_to_norm`: Dict of {raw_name → normalized_form}
- Store these as outer scope for the clustering loop

Currently available in main():
```python
grouped_df  # has columns: embed_text, representative_raw_name, raw_names, count
mapping_raw_to_norm  # dict
```

These are already available in the clustering loop context!

### Code Changes Required

**In the clustering loop (around line 750-800):**

After this block:
```python
collapsed_df = pd.DataFrame(collapsed_rows).sort_values("total_count", ascending=False)
mapping_df = pd.DataFrame(mapping_rows).sort_values(["cluster_id", "count"], ascending=[True, False])
```

Add this new block:
```python
# === Back-mapping: expand mapping to include ALL 1147 raw names ===
# Map representatives to their cluster IDs
rep_to_cluster = {}
for _, row in mapping_df.iterrows():
    rep = row["representative"]
    cid = row["cluster_id"]
    if rep not in rep_to_cluster:
        rep_to_cluster[rep] = cid

# Build mapping for all 1147 raw names
all_mapping_rows = []
for raw_name, norm_form in mapping_raw_to_norm.items():
    # Find the representative for this normalized form
    # Look in grouped_df for the row where embed_text == norm_form
    group_rows = grouped_df[grouped_df["embed_text"] == norm_form]
    if len(group_rows) == 0:
        logger.warning(f"  Raw name '{raw_name}' not found in groups (norm_form='{norm_form}')")
        continue
    
    rep_name = group_rows.iloc[0]["representative_raw_name"]
    rep_count = group_rows.iloc[0]["count"]  # Total count for this group
    
    # Get cluster ID for this representative
    if rep_name not in rep_to_cluster:
        logger.warning(f"  Representative '{rep_name}' not in cluster mapping")
        continue
    
    cluster_id = rep_to_cluster[rep_name]
    
    # Find the count for this specific raw name (if available)
    raw_name_count = raw_names_df[raw_names_df["name"] == raw_name]["count"].sum()
    
    all_mapping_rows.append({
        "cluster_id": cluster_id,
        "name": raw_name,
        "count": raw_name_count,
        "representative": rep_name
    })

# Replace mapping_df with expanded version
mapping_df = pd.DataFrame(all_mapping_rows).sort_values(["cluster_id", "count"], ascending=[True, False])

# Update collapsed_df based on new mapping
collapsed_df = (
    mapping_df.groupby("cluster_id", as_index=False)
    .agg({
        "representative": "first",
        "count": "sum",
        "name": "count"
    })
    .rename(columns={"count": "total_count", "name": "members"})
    .sort_values("total_count", ascending=False)
)

n_clusters = len(collapsed_df)  # Update cluster count
```

### Why This Works

1. **`rep_to_cluster`**: Maps each representative name to its assigned cluster ID
2. **Loop through all 1147 raw names**: For each raw name, we know:
   - Its normalized form (via `mapping_raw_to_norm`)
   - Which representative covers that form (via `grouped_df` lookup)
   - That representative's cluster ID (via `rep_to_cluster`)
3. **Expand mapping_df**: Include all 1147 rows, each with correct cluster_id
4. **Rebuild collapsed_df**: Updated based on expanded mapping

### Expected Results

Before (current broken state):
- mapping_sim_0.90.csv: 1108 rows (only representatives)
- collapsed_sim_0.90.csv: ~997 clusters

After (with back-mapping):
- mapping_sim_0.90.csv: 1147 rows (all raw names, properly consolidated)
- collapsed_sim_0.90.csv: ~850-900 clusters (consolidated groups)

### Example Flow

For raw names that normalize to "affected by":
```
AFFECTED_BY → norm form "affected by"
            → representative "CAN_BE_AFFECTED_BY"
            → rep_to_cluster["CAN_BE_AFFECTED_BY"] = 114
            → Add row: cluster_id=114, name="AFFECTED_BY", representative="CAN_BE_AFFECTED_BY"

IS_AFFECTED_BY → same as above → cluster_id=114
CAN_BE_AFFECTED_BY → (already in original mapping) → cluster_id=114

Result: All three in cluster 114 ✅
```

### Testing This Fix

```bash
cd /mnt/diskGum/manas/graph-dedup-patch/agro_temporal_kg/unified_dedup

# Run pipeline with fix
python3 unified_dedup_pipeline.py \
    --tsv /path/to/edges.tsv \
    --out-dir output_v4

# Verify expansion
wc -l output_v4/01_clustering/mapping_sim_0.90.csv  
# Should be ~1148 (1147 raw names + header)

# Check cluster reduction
tail -1 output_v4/01_clustering/collapsed_sim_0.90.csv | cut -d',' -f1
# Should show cluster count (not 997, but something like 850-900)

# Spot-check consolidation
grep "AFFECTED_BY\|CAN_BE_AFFECTED_BY\|IS_AFFECTED_BY" output_v4/01_clustering/mapping_sim_0.90.csv
# All should have same cluster_id
```

## Additional Notes

### Data Availability
All required data is already available at this point:
- ✅ `grouped_df`: Created in STEP 1.5
- ✅ `mapping_raw_to_norm`: Created in STEP 1.5
- ✅ `raw_names_df`: Loaded in STEP 1
- ✅ `counts_list`: Available from STEP 1.5 output

### No External Dependencies Needed
The fix only uses pandas operations already in use, no new imports needed.

### Error Handling
Added warnings for:
- Raw names not found in groups
- Representatives not in cluster mapping
- Count lookup failures

These help debug any issues with the mapping process.
