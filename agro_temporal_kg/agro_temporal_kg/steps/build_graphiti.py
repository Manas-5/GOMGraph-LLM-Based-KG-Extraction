"""
Step: Build Graphiti instance.

This step initializes all Graphiti components (driver, LLM client, embedder, reranker)
and returns a configured Graphiti instance ready for episode ingestion.
"""

from pathlib import Path
from typing import Any

try:
    from agro_temporal_kg.logging_graphiti import LoggingGraphiti
except ImportError:
    LoggingGraphiti = None  # Fallback handled below

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig as GraphitiLLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.tracer import create_tracer
from loguru import logger

from agro_temporal_kg.configs import CreateTemporalKGConfig
from agro_temporal_kg.prompts.registry import create_prompt_library_from_config
from agro_temporal_kg.patches.edge_patches import apply_edge_patches
from agro_temporal_kg.ollama_graphiti_client import OllamaGraphitiClient


def _maybe_get_otel_tracer(span_prefix: str = "agro_temporal_kg"):
    """
    Create an OpenTelemetry tracer if the SDK is installed; otherwise return None.

    Passing the tracer into Graphiti enables span emission while preserving no-op behavior
    when OTEL isn't available.
    """
    try:
        from opentelemetry import trace  # type: ignore

        return create_tracer(trace.get_tracer(span_prefix), span_prefix=span_prefix)
    except Exception:
        logger.info("OpenTelemetry not available; tracing disabled")
        return create_tracer()


def build_graphiti(config: CreateTemporalKGConfig) -> LoggingGraphiti:
    """
    Build and configure a Graphiti instance from pipeline configuration.

    Args:
        config: Pipeline configuration containing all component settings.

    Returns:
        Configured Graphiti instance ready for use.

    Raises:
        ValueError: If required configuration values are missing.
    """
    # Initialize FalkorDB driver
    logger.info(
        f"Initializing FalkorDB driver: {config.falkor_db.host}:{config.falkor_db.port}"
    )
    driver = FalkorDriver(
        host=config.falkor_db.host,
        port=config.falkor_db.port,
        database=config.falkor_db.database,
    )

    # Initialize LLM client
    llm_api_key = config.llm.api_key
    if not llm_api_key:
        raise ValueError(
            "LLM API key is required. Set it via config or OPENROUTER_API_KEY env var."
        )

    logger.info(f"Initializing LLM client: {config.llm.model}")
    llm_config = GraphitiLLMConfig(
        api_key=llm_api_key,
        model=config.llm.model,
        base_url=config.llm.base_url,
    )
    llm_client = OllamaGraphitiClient(config=llm_config)

    # Initialize embedder
    embedder_api_key = config.embedder.api_key.get_secret_value()
    if not embedder_api_key:
        raise ValueError(
            "Embedder API key is required. Set it via config or OPENAI_API_KEY env var."
        )

    logger.info(f"Initializing embedder: {config.embedder.embedding_model}")
    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key=embedder_api_key,
            base_url=config.embedder.base_url,
            embedding_model=config.embedder.embedding_model,
            embedding_dim=config.embedder.embedding_dim,
        )
    )

    # Initialize cross-encoder (reranker)
    logger.info("Initializing cross-encoder reranker")
    cross_encoder = OpenAIRerankerClient(config=llm_config, client=llm_client)

    # Load prompts from config if specified
    prompt_library = None
    prompts_dict: dict[str, Any] = {}
    config_dir = Path(__file__).parent.parent.parent / "configs"

    if config.prompts.extract_text:
        extract_text_config = config.prompts.extract_text
        logger.info(
            f"Loading custom prompts: extract_text "
            f"(system: v{extract_text_config.system_version}, "
            f"user: v{extract_text_config.user_version})"
        )
        prompts_dict["extract_text"] = {
            "system_version": extract_text_config.system_version,
            "user_version": extract_text_config.user_version,
        }

    if config.prompts.extract_edges:
        extract_edges_config = config.prompts.extract_edges
        logger.info(
            f"Loading custom prompts: extract_edges "
            f"(system: v{extract_edges_config.system_version}, "
            f"user: v{extract_edges_config.user_version})"
        )
        prompts_dict["extract_edges"] = {
            "system_version": extract_edges_config.system_version,
            "user_version": extract_edges_config.user_version,
        }

    if config.prompts.summary_instructions_version:
        logger.info(
            f"Loading custom summary_instructions snippet: "
            f"v{config.prompts.summary_instructions_version}"
        )
        prompts_dict["summary_instructions_version"] = (
            config.prompts.summary_instructions_version
        )

    if prompts_dict:
        prompt_library = create_prompt_library_from_config(
            prompts_dict, config_dir=config_dir
        )
        logger.info("Custom prompts and snippets loaded successfully")
    else:
        logger.info("Using default graphiti prompts")

    # Apply runtime patches to edge handling (date enrichment + explicit invalidations)
    apply_edge_patches()

    # Initialize tracer (OpenTelemetry if installed; otherwise no-op)
    tracer = _maybe_get_otel_tracer(span_prefix="agro_temporal_kg")

    # Build Graphiti instance
    graphiti_cls = LoggingGraphiti if LoggingGraphiti is not None else Graphiti
    graphiti = graphiti_cls(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=cross_encoder,
        prompt_library=prompt_library,
        tracer=tracer,
        trace_span_prefix="agro_temporal_kg",
    )

    logger.info(
        f"Graphiti initialized successfully (database: {config.falkor_db.database})"
    )
    return graphiti
