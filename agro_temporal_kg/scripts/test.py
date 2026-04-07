import asyncio
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.openai_reranker_client import (
    OpenAIRerankerClient,
)
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.nodes import EpisodeType
from langchain_text_splitters import RecursiveCharacterTextSplitter

from agro_temporal_kg.entities import edge_types, entity_types

load_dotenv()


async def main():
    """Main async function to create temporal knowledge graph from French gardening text."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables")

    print(f"API Key loaded: {api_key[:10]}...")

    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not found in environment variables")

    print(f"API Key loaded: {api_key[:10]}...")

    # Initialize FalkorDB driver
    driver = FalkorDriver(host="localhost", port=6379, database="agro-database")
    await driver._get_graph(None).delete()
    # return

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
    graphiti = Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=cross_encoder,
    )

    # Read the French gardening text file
    root_folder = "/home/pablo.sanchez2/GitHub/GOMgraph"
    text_file_path = os.path.join(
        root_folder,
        "data",
        "The-French-Gardener-Part One-A Comprehensive-Vegetable-Gardener-Calendar-and-Manual.txt",
    )

    basename = Path(os.path.basename(text_file_path)).stem

    print("Reading French gardening text file...")
    with open(text_file_path, encoding="utf-8") as file:
        text_content = file.read()

    print(f"Text file loaded successfully. Length: {len(text_content)} characters")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1_000,  # Characters per chunk (roughly 10k tokens)
        chunk_overlap=150,  # Overlap to maintain context between chunks
        length_function=len,
        separators=[
            "\n\n",
            "\n",
            ". ",
            " ",
            "",
        ],  # Try to split on paragraphs, then sentences
    )

    # Split text into chunks
    chunks = text_splitter.split_text(text_content)

    print(f"Split text into {len(chunks)} chunks")

    # Process each chunk
    print("\nCreating temporal knowledge graph...")

    for idx, chunk in enumerate(chunks, 1):
        print(f"\nProcessing chunk {idx}/{len(chunks)} (length: {len(chunk)} chars)...")

        result = await graphiti.add_episode(
            name=f"{basename}-part_{idx}",
            source_description="French gardening manual containing "
            "comprehensive vegetable gardening calendar, weather predictions, "
            "soil amendments, and agricultural techniques",
            episode_body=chunk,
            group_id="the_french_gardener",
            reference_time=datetime(1880, 1, 1),
            entity_types=entity_types,
            edge_types=edge_types,
            source=EpisodeType.text,
        )

        print(f"✅ Chunk {idx} processed successfully!")

    print("\n✅ All chunks processed! Knowledge graph created successfully!")

    # Query the knowledge graph to verify it was created
    print("\nQuerying the knowledge graph...")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
