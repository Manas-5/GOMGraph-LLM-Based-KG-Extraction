"""
Step: Ingest text chunks as episodes into the knowledge graph.

This step iterates over text chunks and adds them as episodes to the
Graphiti temporal knowledge graph.
"""

import os
import time
from datetime import datetime
from pathlib import Path

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from loguru import logger

from agro_temporal_kg.configs import CreateTemporalKGConfig
from agro_temporal_kg.entities.resolver import resolve_edge_types, resolve_entity_types
from agro_temporal_kg.falkordb_client import FalkorDBClient


def _reset_dedupe_logs(group_id: str) -> None:
    """Ensure logs directory exists; do not delete chunk logs (avoid losing partial runs)."""
    logs_dir = Path.cwd() / "logs" / group_id
    logs_dir.mkdir(parents=True, exist_ok=True)


async def ingest_episodes(
    graphiti: Graphiti,
    chunks: list[str],
    config: CreateTemporalKGConfig,
) -> None:
    """
    Ingest text chunks as episodes into the knowledge graph.

    Args:
        graphiti: Configured Graphiti instance.
        chunks: List of text chunks to ingest.
        config: Pipeline configuration containing file metadata.

    Note:
        This is an async function that must be awaited or run with asyncio.run().
    """
    file_config = config.file

    # Derive episode name base from file path
    if file_config.path:
        basename = Path(file_config.path).stem
    else:
        basename = "document"

    # Create reference time from config
    reference_time = datetime(file_config.reference_year, 1, 1)

    total_chunks = len(chunks)
    logger.info(f"Starting ingestion of {total_chunks} chunks into knowledge graph")
    logger.info(f"  Group ID: {file_config.group_id}")
    logger.info(f"  Source: {file_config.source_description}")
    logger.info(f"  Reference year: {file_config.reference_year}")

    # Resolve entity and edge types from string lists to model dictionaries
    resolved_entity_types = resolve_entity_types(config.entity_types)
    resolved_edge_types = resolve_edge_types(config.edge_types)
    edge_type_map = config.edge_type_map or None

    if resolved_entity_types:
        logger.info(
            f"  Using {len(resolved_entity_types)} entity types: {', '.join(sorted(resolved_entity_types.keys()))}"
        )
    else:
        logger.info("  Using default Graphiti entity types")

    if resolved_edge_types:
        logger.info(
            f"  Using {len(resolved_edge_types)} edge types: {', '.join(sorted(resolved_edge_types.keys()))}"
        )
    else:
        logger.info("  Using default Graphiti edge types")

    if edge_type_map:
        logger.info(
            f"  Using edge_type_map with {len(edge_type_map)} signature(s): "
            f"{', '.join(f'({a},{b})' for a, b in sorted(edge_type_map.keys()))}"
        )
    else:
        logger.info("  No edge_type_map provided; Graphiti will use default mapping")

    # Log availability of optional offline resources
    try:
        import pycountry  # type: ignore
        logger.info("pycountry: available")
    except Exception:
        logger.info("pycountry: not available (using fallback geo hints)")

    ror_cache = os.getenv("ROR_CACHE_FILE")
    if ror_cache and Path(ror_cache).exists():
        logger.info(f"ROR cache: using {ror_cache}")
    elif ror_cache:
        logger.warning(f"ROR cache: path set but missing ({ror_cache})")
    else:
        logger.info("ROR cache: not configured (set ROR_CACHE_FILE to enable)")

    # Clear previous dedupe logs for this group_id so this run is fresh
    if file_config.group_id:
        _reset_dedupe_logs(file_config.group_id)

    for idx, chunk in enumerate(chunks, 1):
        logger.info(f"Processing chunk {idx}/{total_chunks} ({len(chunk)} chars)...")

        # Update a lightweight status file for monitoring (written to logs/<group_id>/status.txt)
        try:
            group_id = file_config.group_id or "default"
            status_dir = Path.cwd() / "logs" / group_id
            status_dir.mkdir(parents=True, exist_ok=True)
            status_file = status_dir / "status.txt"
            if not status_file.exists():
                with open(status_file, "w", encoding="utf-8") as sf:
                    sf.write(f"started_at: {time.time()}\n")
            with open(status_file, "r+", encoding="utf-8") as sf:
                contents = sf.read()
                start_ts = None
                for line in contents.splitlines():
                    if line.startswith("started_at:"):
                        try:
                            start_ts = float(line.split(":", 1)[1].strip())
                        except Exception:
                            start_ts = time.time()
                        break
                if start_ts is None:
                    start_ts = time.time()
                    sf.write(f"started_at: {start_ts}\n")
                elapsed = int(time.time() - start_ts)
                lines = contents.splitlines()
                rest = lines[1:] if len(lines) >= 1 and lines[0].startswith("started_at:") else lines
                status_line = f"chunk: {idx}/{total_chunks} elapsed_s: {elapsed}"
                sf.seek(0)
                sf.truncate(0)
                sf.write(f"started_at: {start_ts}\n")
                sf.write(status_line + "\n")
        except Exception:
            logger.debug("Warning: failed to write status file for monitoring")

        try:
            results = await graphiti.add_episode(
                name=f"{basename}-part_{idx}",
                source_description=file_config.source_description,
                episode_body=chunk,
                group_id=file_config.group_id,
                reference_time=reference_time,
                entity_types=resolved_entity_types,
                edge_types=resolved_edge_types,
                edge_type_map=edge_type_map,
                source=EpisodeType.text,
            )

            invalidated = sum(1 for e in results.edges if e.invalid_at is not None)
            logger.info(
                f"✅ Chunk {idx}/{total_chunks} processed | "
                f"nodes={len(results.nodes)} edges={len(results.edges)} "
                f"episodic_edges={len(results.episodic_edges)} "
                f"communities={len(results.community_edges)} "
                f"invalidated_edges={invalidated}"
            )

            # Per-chunk export for intra-chunk analysis
            try:
                db_name = config.falkor_db.database
                export_root = Path.cwd() / "exported_data" / "checkpoints" / db_name
                chunk_dir = export_root / f"chunk_{idx}"
                # Clear old snapshot for this chunk to avoid stale files
                if chunk_dir.exists():
                    for path in chunk_dir.glob("*"):
                        path.unlink(missing_ok=True)
                client = FalkorDBClient(
                    host=config.falkor_db.host,
                    port=config.falkor_db.port,
                )
                client.export_graph_to_tsv(
                    graph_name=db_name,
                    output_dir=chunk_dir,
                    group_id=None,
                )
                logger.info(f"[EXPORT] Checkpoint written to {chunk_dir}")
            except Exception as export_err:
                logger.warning(f"[EXPORT] Failed to export checkpoint for chunk {idx}: {export_err}")

        except Exception as e:
            logger.error(f"❌ Error processing chunk {idx}: {e}")
            raise

    logger.info(f"✅ All {total_chunks} chunks ingested successfully!")

