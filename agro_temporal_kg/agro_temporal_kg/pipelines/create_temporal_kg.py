"""
Pipeline: Create Temporal Knowledge Graph.

This module provides the main pipeline orchestrator that can be called
programmatically or from the CLI.
"""

import asyncio

from loguru import logger

from agro_temporal_kg.configs import CreateTemporalKGConfig
from agro_temporal_kg.steps import build_graphiti, ingest_episodes, load_file, split_text


def create_temporal_kg(config: CreateTemporalKGConfig) -> int:
    """Run the complete temporal knowledge graph creation pipeline."""
    if not config.file.path:
        raise ValueError("No input file specified in config.file.path")

    logger.info("=" * 60)
    logger.info("Starting Temporal Knowledge Graph Pipeline")
    logger.info("=" * 60)

    logger.info("[Step 1/4] Loading file...")
    text_content = load_file(config.file.path)

    logger.info("[Step 2/4] Splitting text into chunks...")
    chunks = split_text(text_content, config)

    logger.info("[Step 3/4] Initializing Graphiti...")
    graphiti = build_graphiti(config)

    logger.info("[Step 4/4] Ingesting episodes into knowledge graph...")
    asyncio.run(ingest_episodes(graphiti, chunks, config))

    logger.info(
        f"[GRAPH_DONE] graph={config.falkor_db.database} "
        f"host={config.falkor_db.host} port={config.falkor_db.port}"
    )

    # Best-effort verification: confirm the graph name is visible in FalkorDB.
    try:
        from agro_temporal_kg.falkordb_client import FalkorDBClient

        client = FalkorDBClient(host=config.falkor_db.host, port=config.falkor_db.port)
        graphs = client.list_graphs()
        if config.falkor_db.database in graphs:
            logger.info(f"[GRAPH_VERIFIED] graph={config.falkor_db.database}")
        else:
            logger.warning(f"[GRAPH_NOT_FOUND] graph={config.falkor_db.database}")
    except Exception as e:
        logger.warning(f"[GRAPH_VERIFY_FAILED] {e}")

    logger.info("=" * 60)
    logger.info("✅ Pipeline completed successfully!")
    logger.info(f"   Database: {config.falkor_db.database}")
    logger.info(f"   Chunks processed: {len(chunks)}")
    logger.info("=" * 60)

    return len(chunks)

