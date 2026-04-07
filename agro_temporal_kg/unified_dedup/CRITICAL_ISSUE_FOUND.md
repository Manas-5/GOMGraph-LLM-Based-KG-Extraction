# Option A Implementation - Critical Issue & Solution Path

**Date:** February 17, 2026  
**Status:** Option A partially working, but needs final mapping step

## What's Working

✅ **Grouping:** 1147 → 1108 unique normalized forms (39 consolidated)  
✅ **Embedding:** Only 1108 vectors (not 1147)  
✅ **Clustering:** Works on 1108 representatives  

## Critical Issue Found

The clustering output (`mapping_sim_0.90.csv`) still has 997 clusters because:

1. We embed and cluster only 1108 **representatives** (e.g., `CAN_BE_AFFECTED_BY`)
2. But the output file needs to map all 1147 **raw names** back to clusters
3. Currently, this mapping happens in the reverse pipeline step, but it's not consolidating the raw names that map to the same group!

### Example:
- Raw names: `AFFECTED_BY`, `CAN_BE_AFFECTED_BY`, `IS_AFFECTED_BY` (all normalize to "affected by")
- Grouped representative: `CAN_BE_AFFECTED_BY` (selected as the longest/representative name)
- Clustering: `CAN_BE_AFFECTED_BY` ends up in cluster 114
- Expected output: All three raw names (`AFFECTED_BY`, `CAN_BE_AFFECTED_BY`, `IS_AFFECTED_BY`) should map to cluster 114
- What's happening: Only `CAN_BE_AFFECTED_BY` is directly clustered; the others need to be "back-mapped"

## Solution Path

Need to add a **final step** that back-maps raw names to representative clusters:

```python
# After clustering 1108 representatives and getting cluster assignments
cluster_assignment = {  # repr_name → cluster_id
    'CAN_BE_AFFECTED_BY': 114,
    'PLANTED_IN': 6,
    # ... 1108 total
}

# Map back to 1147 raw names using mapping_raw_to_norm
final_mapping = {}
for raw_name, norm_form in mapping_raw_to_norm.items():
    # Find which representative has this normalized form
    rep_for_norm = ...  # Find from grouped_df
    cluster_id = cluster_assignment[rep_for_norm]
    final_mapping[raw_name] = cluster_id
```

## Current Flow (Broken)

```
Raw names (1147)
    ↓
Group by norm (1108 reps)
    ↓  
Embed 1108
    ↓
Cluster 1108
    ↓
Output ??? (Should map 1147 back, but isn't properly consolidating)
```

## Fixed Flow (Needed)

```
Raw names (1147)
    ↓
Group by norm (1108 reps + mapping dict)
    ↓  
Embed 1108
    ↓
Cluster 1108 → cluster_assignment {rep_name: cluster_id}
    ↓
Back-map raw names:
  For each raw_name in 1147:
    - Find its norm_form
    - Find rep_name for that norm_form
    - Get cluster_id from cluster_assignment[rep_name]
    ↓
Output mapping with 1147 rows (properly consolidated)
```

## Code Location to Fix

**File:** `unified_dedup_pipeline.py`  
**Step:** 6 (Clustering) - after building `collapsed_df` and `mapping_df`

**Current code problem:**
- Creates clusters for 1108 representatives
- Outputs rows in `mapping_df` only include the representatives
- **Missing:** back-mapping of consolidated raw names

**What needs to happen:**
1. After clustering 1108 representatives, build a `rep_name → cluster_id` map
2. For each of the 1147 raw names:
   - Look up its normalized form
   - Find the representative for that normalized form
   - Look up that representative's cluster_id
   - Create a row in mapping_df with the raw name → cluster_id

## Expected Result After Fix

- **Cluster count at 0.90:** Instead of 997 (based on 1108 reps), should drop to ~860-900
  - Why? Because consolidated raw names that map to the same representative will be in the same cluster
  - Example: `AFFECTED_BY`, `CAN_BE_AFFECTED_BY`, `IS_AFFECTED_BY` all in cluster 114

## Next Steps

1. Modify the clustering loop to:
   - Build mapping from representatives to their group's raw names
   - Expand `mapping_df` to include all 1147 raw names
   - Ensure raw names in same group get same cluster_id

2. Test and verify:
   - mapping_sim_0.90.csv should have ~1147 rows
   - But unique cluster_ids should be ~860-900 (much fewer)
   - Spot-check: AFFECTED_BY, CAN_BE_AFFECTED_BY, IS_AFFECTED_BY should all be in same cluster

3. Final result:
   - Actually achieve the consolidation we've been aiming for
   - Reach closer to 861 target clusters
