#!/usr/bin/env python3
"""
Back-mapping script: Expand clustering results from representatives to all raw names.

This script takes the clustering output (which has only representatives)
and expands it to include all 1147 raw names, mapping each to their group's
representative's cluster assignment.

Usage:
    python3 apply_backmapping.py \
        --input-dir output \
        --mapping raw_to_normalized_mapping.csv \
        --grouped-info normalized_names.csv
"""

import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def load_mapping_file(mapping_path: Path) -> dict:
    """Load raw_to_normalized_mapping.csv into dict."""
    df = pd.read_csv(mapping_path)
    mapping = {}
    for _, row in df.iterrows():
        raw_name = row["raw_name"]
        norm_form = row["normalized_form"]
        mapping[raw_name] = norm_form
    logger.info(f"✓ Loaded mapping: {len(mapping)} raw names")
    return mapping


def load_normalized_names(normalized_path: Path) -> dict:
    """Load normalized_names.csv to find representative for each normalized form."""
    df = pd.read_csv(normalized_path)
    norm_to_rep = {}
    for _, row in df.iterrows():
        norm_form = row["normalized_for_embedding"]
        raw_name = row["raw_name"]
        count = row["count"]
        
        # Use the first occurrence as representative
        if norm_form not in norm_to_rep:
            norm_to_rep[norm_form] = {
                "representative": raw_name,
                "count": count
            }
    
    logger.info(f"✓ Loaded normalized names: {len(norm_to_rep)} unique forms")
    return norm_to_rep


def load_clustering_results(clustering_dir: Path, threshold: float) -> pd.DataFrame:
    """Load clustering mapping for a specific threshold."""
    mapping_path = clustering_dir / f"mapping_sim_{threshold:.2f}.csv"
    if not mapping_path.exists():
        raise FileNotFoundError(f"Clustering file not found: {mapping_path}")
    
    df = pd.read_csv(mapping_path)
    logger.info(f"✓ Loaded clustering results: {len(df)} entries")
    return df


def apply_backmapping(
    clustering_df: pd.DataFrame,
    mapping_raw_to_norm: dict,
    norm_to_rep: dict,
    original_counts: dict = None
) -> pd.DataFrame:
    """
    Expand clustering results to include all raw names.
    
    Args:
        clustering_df: Current clustering mapping (representatives only)
        mapping_raw_to_norm: Dict of raw_name → normalized_form
        norm_to_rep: Dict of normalized_form → {representative, count}
        original_counts: Dict of raw_name → count (if available)
    
    Returns:
        Expanded dataframe with all raw names
    """
    
    # Build representative to cluster mapping
    rep_to_cluster = {}
    for _, row in clustering_df.iterrows():
        rep = row["representative"]
        cluster_id = row["cluster_id"]
        if rep not in rep_to_cluster:
            rep_to_cluster[rep] = cluster_id
    
    logger.info(f"✓ Built representative-to-cluster mapping: {len(rep_to_cluster)} reps")
    
    # Expand to all raw names
    expanded_rows = []
    unmapped_count = 0
    
    for raw_name, norm_form in mapping_raw_to_norm.items():
        # Find representative for this normalized form
        if norm_form not in norm_to_rep:
            logger.warning(f"  Normalized form '{norm_form}' not found for raw name '{raw_name}'")
            unmapped_count += 1
            continue
        
        rep_info = norm_to_rep[norm_form]
        rep_name = rep_info["representative"]
        
        # Get cluster ID for this representative
        if rep_name not in rep_to_cluster:
            logger.warning(f"  Representative '{rep_name}' not in cluster mapping for '{raw_name}'")
            unmapped_count += 1
            continue
        
        cluster_id = rep_to_cluster[rep_name]
        
        # Get count (from original_counts if provided, otherwise use rep's count)
        if original_counts and raw_name in original_counts:
            count = original_counts[raw_name]
        else:
            count = rep_info["count"]
        
        expanded_rows.append({
            "cluster_id": cluster_id,
            "name": raw_name,
            "count": count,
            "representative": rep_name
        })
    
    if unmapped_count > 0:
        logger.warning(f"✗ Could not map {unmapped_count} raw names")
    
    expanded_df = pd.DataFrame(expanded_rows)
    expanded_df = expanded_df.sort_values(["cluster_id", "count"], ascending=[True, False])
    
    logger.info(f"✓ Created expanded mapping: {len(expanded_df)} raw names")
    return expanded_df


def rebuild_collapsed(mapping_df: pd.DataFrame) -> pd.DataFrame:
    """Rebuild collapsed dataframe from expanded mapping."""
    collapsed = (
        mapping_df.groupby("cluster_id", as_index=False)
        .agg({
            "representative": "first",
            "count": "sum",
            "name": "count"
        })
        .rename(columns={"count": "total_count", "name": "members"})
        .sort_values("total_count", ascending=False)
    )
    
    logger.info(f"✓ Rebuilt collapsed: {len(collapsed)} clusters")
    return collapsed


def process_threshold(
    input_dir: Path,
    threshold: float,
    mapping_raw_to_norm: dict,
    norm_to_rep: dict,
    original_counts: dict = None
) -> tuple:
    """Process a single threshold."""
    clustering_dir = input_dir / "01_clustering"
    
    # Load current clustering results
    clustering_df = load_clustering_results(clustering_dir, threshold)
    
    # Apply back-mapping
    expanded_df = apply_backmapping(clustering_df, mapping_raw_to_norm, norm_to_rep, original_counts)
    
    # Rebuild collapsed
    collapsed_df = rebuild_collapsed(expanded_df)
    
    return expanded_df, collapsed_df


def main():
    ap = argparse.ArgumentParser(
        description="Apply back-mapping to expand clustering results from representatives to all raw names"
    )
    ap.add_argument("--input-dir", required=True, help="Input directory with clustering results (e.g., output)")
    ap.add_argument("--mapping", default="raw_to_normalized_mapping.csv", 
                    help="Path to raw_to_normalized_mapping.csv (relative to input-dir)")
    ap.add_argument("--normalized", default="normalized_names.csv",
                    help="Path to normalized_names.csv (relative to input-dir)")
    ap.add_argument("--threshold", type=float, default=None,
                    help="Apply only to this threshold (e.g., 0.90). If None, apply to all.")
    ap.add_argument("--thresholds", default="0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90,1.00",
                    help="Comma-separated thresholds to process")
    ap.add_argument("--backup", action="store_true", default=True,
                    help="Backup original files before overwriting (default: True)")
    ap.add_argument("--no-backup", dest="backup", action="store_false",
                    help="Don't backup original files")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be done without modifying files")
    
    args = ap.parse_args()
    
    input_dir = Path(args.input_dir)
    embeddings_dir = input_dir / "02_embeddings"
    clustering_dir = input_dir / "01_clustering"
    
    # Validate directories
    if not input_dir.exists():
        logger.error(f"✗ Input directory not found: {input_dir}")
        return 1
    
    if not clustering_dir.exists():
        logger.error(f"✗ Clustering directory not found: {clustering_dir}")
        return 1
    
    # Load mappings
    mapping_path = embeddings_dir / args.mapping
    if not mapping_path.exists():
        logger.error(f"✗ Mapping file not found: {mapping_path}")
        return 1
    
    normalized_path = embeddings_dir / args.normalized
    if not normalized_path.exists():
        logger.error(f"✗ Normalized file not found: {normalized_path}")
        return 1
    
    logger.info("="*80)
    logger.info("BACK-MAPPING APPLICATION")
    logger.info("="*80)
    logger.info(f"Input directory: {input_dir}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Backup originals: {args.backup}")
    logger.info("="*80)
    
    # Load mappings
    mapping_raw_to_norm = load_mapping_file(mapping_path)
    norm_to_rep = load_normalized_names(normalized_path)
    
    # Parse thresholds to process
    if args.threshold:
        thresholds = [args.threshold]
    else:
        thresholds = [float(x) for x in args.thresholds.split(",")]
    
    logger.info(f"Processing {len(thresholds)} thresholds: {thresholds}")
    
    # Process each threshold
    results_summary = []
    
    for thr in thresholds:
        try:
            logger.info(f"\nProcessing threshold {thr:.2f}...")
            
            expanded_df, collapsed_df = process_threshold(
                input_dir, thr, mapping_raw_to_norm, norm_to_rep
            )
            
            # Save results
            mapping_out = clustering_dir / f"mapping_sim_{thr:.2f}.csv"
            collapsed_out = clustering_dir / f"collapsed_sim_{thr:.2f}.csv"
            
            if not args.dry_run:
                # Backup originals if requested
                if args.backup:
                    mapping_backup = clustering_dir / f"mapping_sim_{thr:.2f}.csv.bak"
                    collapsed_backup = clustering_dir / f"collapsed_sim_{thr:.2f}.csv.bak"
                    if mapping_out.exists():
                        import shutil
                        shutil.copy2(mapping_out, mapping_backup)
                        logger.info(f"  Backed up: {mapping_backup.name}")
                    if collapsed_out.exists():
                        import shutil
                        shutil.copy2(collapsed_out, collapsed_backup)
                        logger.info(f"  Backed up: {collapsed_backup.name}")
                
                # Write new files
                expanded_df.to_csv(mapping_out, index=False)
                collapsed_df.to_csv(collapsed_out, index=False)
                logger.info(f"✓ Saved: {mapping_out.name}")
                logger.info(f"✓ Saved: {collapsed_out.name}")
            else:
                logger.info(f"[DRY RUN] Would save: {mapping_out.name}")
                logger.info(f"[DRY RUN] Would save: {collapsed_out.name}")
            
            results_summary.append({
                "threshold": thr,
                "total_names": len(expanded_df),
                "total_clusters": len(collapsed_df),
                "status": "OK"
            })
            
        except Exception as e:
            logger.error(f"✗ Error processing threshold {thr:.2f}: {e}", exc_info=True)
            results_summary.append({
                "threshold": thr,
                "status": "ERROR",
                "error": str(e)
            })
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info("RESULTS SUMMARY")
    logger.info("="*80)
    
    for result in results_summary:
        if result["status"] == "OK":
            logger.info(f"✓ Threshold {result['threshold']:.2f}: "
                       f"{result['total_names']} names → {result['total_clusters']} clusters")
        else:
            logger.info(f"✗ Threshold {result['threshold']:.2f}: {result.get('error', 'Unknown error')}")
    
    logger.info("="*80)
    logger.info(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)
    
    return 0


if __name__ == "__main__":
    exit(main())
