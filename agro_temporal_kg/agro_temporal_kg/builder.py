import os

from dotenv import load_dotenv
from loguru import logger
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.openai_reranker_client import (
    OpenAIRerankerClient,
)
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient

load_dotenv()


def get_graphiti(graph_name: str = "agro-database") -> Graphiti:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables")

    logger.info(f"API Key loaded: {api_key[:10]}...")

    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not found in environment variables")

    logger.info(f"API Key loaded: {api_key[:10]}...")

    # Initialize FalkorDB driver
    driver = FalkorDriver(host="localhost", port=6379, database=graph_name)

    llm_config = LLMConfig(
        api_key=openrouter_api_key,
        model=os.getenv("OPENROUTER_MODEL_NAME"),
        base_url="https://openrouter.ai/api/v1",
    )

    llm_client = OpenAIClient(config=llm_config)

    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key=api_key,
            embedding_model="text-embedding-3-small",
        )
    )

    # Configure cross encoder (reranker)
    cross_encoder = OpenAIRerankerClient(config=llm_config, client=llm_client)

    # Initialize Graphiti with all components
    return Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=cross_encoder,
    )
