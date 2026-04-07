#!/usr/bin/env python3
"""
Analysis script: Compare clustering results before and after back-mapping.

Usage:
    python3 analyze_backmapping.py \
        --input-dir output \
        --threshold 0.90
"""

import argparse
import pandas as pd
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_clustering_file(filepath: Path) -> pd.DataFrame:
    """Load clustering file."""
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    return pd.read_csv(filepath)


def analyze_threshold(clustering_dir: Path, threshold: float):
    """Analyze clustering results for a threshold."""
    
    mapping_path = clustering_dir / f"mapping_sim_{threshold:.2f}.csv"
    collapsed_path = clustering_dir / f"collapsed_sim_{threshold:.2f}.csv"
    
    if not mapping_path.exists():
        logger.error(f"✗ Mapping file not found: {mapping_path}")
        return None
    
    mapping_df = load_clustering_file(mapping_path)
    collapsed_df = load_clustering_file(collapsed_path)
    
    # Analysis
    total_names = len(mapping_df)
    total_clusters = len(collapsed_df)
    total_edges = mapping_df["count"].sum()
    avg_edges_per_cluster = total_edges / total_clusters if total_clusters > 0 else 0
    avg_names_per_cluster = total_names / total_clusters if total_clusters > 0 else 0
    
    # Find largest clusters
    largest = collapsed_df.nlargest(5, "total_count")
    
    return {
        "threshold": threshold,
        "total_names": total_names,
        "total_clusters": total_clusters,
        "total_edges": total_edges,
        "avg_edges_per_cluster": avg_edges_per_cluster,
        "avg_names_per_cluster": avg_names_per_cluster,
        "largest_clusters": largest
    }


def compare_versions(version1_dir: Path, version2_dir: Path, threshold: float):
    """Compare clustering results between two versions."""
    
    logger.info(f"\n{'='*80}")
    logger.info(f"COMPARISON: Threshold {threshold:.2f}")
    logger.info(f"{'='*80}")
    
    clustering_dir1 = version1_dir / "01_clustering"
    clustering_dir2 = version2_dir / "01_clustering"
    
    # Load data
    try:
        results1 = analyze_threshold(clustering_dir1, threshold)
        results2 = analyze_threshold(clustering_dir2, threshold)
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        return
    
    if not results1 or not results2:
        return
    
    # Display comparison
    logger.info(f"\nBefore back-mapping:")
    logger.info(f"  Total names:          {results1['total_names']:>6}")
    logger.info(f"  Total clusters:       {results1['total_clusters']:>6}")
    logger.info(f"  Total edges:          {results1['total_edges']:>6}")
    logger.info(f"  Avg edges/cluster:    {results1['avg_edges_per_cluster']:>6.2f}")
    
    logger.info(f"\nAfter back-mapping:")
    logger.info(f"  Total names:          {results2['total_names']:>6}")
    logger.info(f"  Total clusters:       {results2['total_clusters']:>6}")
    logger.info(f"  Total edges:          {results2['total_edges']:>6}")
    logger.info(f"  Avg edges/cluster:    {results2['avg_edges_per_cluster']:>6.2f}")
    
    # Calculate differences
    names_diff = results2["total_names"] - results1["total_names"]
    clusters_diff = results2["total_clusters"] - results1["total_clusters"]
    cluster_reduction_pct = (clusters_diff / results1["total_clusters"] * 100) if results1["total_clusters"] > 0 else 0
    
    logger.info(f"\nDifferences:")
    logger.info(f"  Names change:         {names_diff:>+6}")
    logger.info(f"  Clusters change:      {clusters_diff:>+6} ({cluster_reduction_pct:>+.1f}%)")
    
    if clusters_diff < 0:
        logger.info(f"\n✓ SUCCESS: Cluster count REDUCED by {abs(clusters_diff)} ({abs(cluster_reduction_pct):.1f}%)")
    else:
        logger.info(f"\n⚠ WARNING: Cluster count did not reduce as expected")


def show_details(clustering_dir: Path, threshold: float):
    """Show detailed statistics for a threshold."""
    
    logger.info(f"\n{'='*80}")
    logger.info(f"DETAILED ANALYSIS: Threshold {threshold:.2f}")
    logger.info(f"{'='*80}")
    
    results = analyze_threshold(clustering_dir, threshold)
    if not results:
        return
    
    logger.info(f"\nBasic Statistics:")
    logger.info(f"  Total names:          {results['total_names']}")
    logger.info(f"  Total clusters:       {results['total_clusters']}")
    logger.info(f"  Total edges:          {results['total_edges']}")
    logger.info(f"  Avg edges/cluster:    {results['avg_edges_per_cluster']:.2f}")
    logger.info(f"  Avg names/cluster:    {results['avg_names_per_cluster']:.2f}")
    
    logger.info(f"\nTop 5 Largest Clusters:")
    for i, (_, row) in enumerate(results['largest_clusters'].iterrows(), 1):
        logger.info(f"  {i}. Cluster {int(row['cluster_id']):>4d}: "
                   f"{int(row['total_count']):>5} edges, "
                   f"{int(row['members']):>3} names, "
                   f"rep: {row['representative']}")


def main():
    ap = argparse.ArgumentParser(
        description="Analyze and compare clustering results before/after back-mapping"
    )
    ap.add_argument("--input-dir", help="Single input directory to analyze")
    ap.add_argument("--before", help="Directory with original clustering (before back-mapping)")
    ap.add_argument("--after", help="Directory with back-mapped clustering (after back-mapping)")
    ap.add_argument("--threshold", type=float, default=0.90, help="Threshold to analyze (default: 0.90)")
    ap.add_argument("--all-thresholds", action="store_true", help="Analyze all thresholds")
    ap.add_argument("--detail", action="store_true", help="Show detailed statistics")
    
    args = ap.parse_args()
    
    thresholds = None
    if args.all_thresholds:
        thresholds = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00]
    else:
        thresholds = [args.threshold]
    
    # Mode 1: Single directory analysis
    if args.input_dir:
        input_dir = Path(args.input_dir)
        clustering_dir = input_dir / "01_clustering"
        
        logger.info("SINGLE DIRECTORY ANALYSIS")
        
        for thr in thresholds:
            if args.detail:
                show_details(clustering_dir, thr)
            else:
                results = analyze_threshold(clustering_dir, thr)
                if results:
                    logger.info(f"Threshold {thr:.2f}: "
                               f"{results['total_names']} names → "
                               f"{results['total_clusters']} clusters "
                               f"({results['total_edges']} edges)")
    
    # Mode 2: Comparison between two versions
    elif args.before and args.after:
        before_dir = Path(args.before)
        after_dir = Path(args.after)
        
        logger.info("COMPARING TWO VERSIONS")
        
        for thr in thresholds:
            compare_versions(before_dir, after_dir, thr)
    
    else:
        logger.error("Provide either --input-dir or both --before and --after")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
