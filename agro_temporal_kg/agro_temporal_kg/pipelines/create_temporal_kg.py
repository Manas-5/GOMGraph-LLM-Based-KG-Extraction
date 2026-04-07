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
    """
    Run the complete temporal knowledge graph creation pipeline.
    """
    if not config.file.path:
        raise ValueError("No input file specified in config.file.path")

    logger.info("=" * 60)
    logger.info("Starting Temporal Knowledge Graph Pipeline")
    logger.info("=" * 60)

    # Step 1: Load file
    logger.info("[Step 1/4] Loading file...")
    text_content = load_file(config.file.path)

    # Step 2: Split text into chunks
    logger.info("[Step 2/4] Splitting text into chunks...")
    chunks = split_text(text_content, config)

    # Step 3: Build Graphiti instance
    logger.info("[Step 3/4] Initializing Graphiti...")
    graphiti = build_graphiti(config)

    # Step 4: Ingest episodes (async)
    logger.info("[Step 4/4] Ingesting episodes into knowledge graph...")
    asyncio.run(ingest_episodes(graphiti, chunks, config))

    # --- Tiny patch: explicit, machine-checkable completion markers ---
    logger.info(
        f"[GRAPH_DONE] graph={config.falkor_db.database} "
        f"host={config.falkor_db.host} port={config.falkor_db.port}"
    )

    # Best-effort verification: confirm the graph name is visible in FalkorDB
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
    # ---------------------------------------------------------------

    logger.info("=" * 60)
    logger.info("✅ Pipeline completed successfully!")
    logger.info(f"   Database: {config.falkor_db.database}")
    logger.info(f"   Chunks processed: {len(chunks)}")
    logger.info("=" * 60)

    return len(chunks)





# """
# Pipeline: Create Temporal Knowledge Graph.

# This module provides the main pipeline orchestrator that can be called
# programmatically or from the CLI.
# """

# import asyncio

# from loguru import logger

# from agro_temporal_kg.configs import CreateTemporalKGConfig
# from agro_temporal_kg.steps import build_graphiti, ingest_episodes, load_file, split_text


# def create_temporal_kg(config: CreateTemporalKGConfig) -> int:
#     """
#     Run the complete temporal knowledge graph creation pipeline.

#     This function orchestrates all pipeline steps:
#     1. Load text file
#     2. Split into chunks
#     3. Build Graphiti instance
#     4. Ingest episodes into the graph

#     Args:
#         config: Fully configured CreateTemporalKGConfig instance.

#     Returns:
#         Number of chunks processed.

#     Raises:
#         ValueError: If file path is not specified in config.
#         FileNotFoundError: If the input file does not exist.
#     """
#     if not config.file.path:
#         raise ValueError("No input file specified in config.file.path")

#     logger.info("=" * 60)
#     logger.info("Starting Temporal Knowledge Graph Pipeline")
#     logger.info("=" * 60)

#     # Step 1: Load file
#     logger.info("[Step 1/4] Loading file...")
#     text_content = load_file(config.file.path)

#     # Step 2: Split text into chunks
#     logger.info("[Step 2/4] Splitting text into chunks...")
#     chunks = split_text(text_content, config)

#     # Step 3: Build Graphiti instance
#     logger.info("[Step 3/4] Initializing Graphiti...")
#     graphiti = build_graphiti(config)

#     # Step 4: Ingest episodes (async)
#     logger.info("[Step 4/4] Ingesting episodes into knowledge graph...")
#     asyncio.run(ingest_episodes(graphiti, chunks, config))

#     logger.info("=" * 60)
#     logger.info("✅ Pipeline completed successfully!")
#     logger.info(f"   Database: {config.falkor_db.database}")
#     logger.info(f"   Chunks processed: {len(chunks)}")
#     logger.info("=" * 60)

#     # return len(chunks)

