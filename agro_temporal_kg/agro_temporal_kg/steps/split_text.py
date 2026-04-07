"""
Step: Split text into chunks.

This step uses LangChain's RecursiveCharacterTextSplitter to chunk text
for processing by the knowledge graph pipeline.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from agro_temporal_kg.configs import CreateTemporalKGConfig


def split_text(text: str, config: CreateTemporalKGConfig) -> list[str]:
    """
    Split text into overlapping chunks for KG ingestion.

    Args:
        text: The full text content to split.
        config: Pipeline configuration containing text_splitter settings.

    Returns:
        List of text chunks.

    Raises:
        ValueError: If text is empty.
    """
    if not text.strip():
        raise ValueError("Cannot split empty text")

    splitter_config = config.text_splitter

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=splitter_config.chunk_size,
        chunk_overlap=splitter_config.chunk_overlap,
        length_function=len,
        separators=splitter_config.separators,
    )

    chunks = text_splitter.split_text(text)

    logger.info(
        f"Split text into {len(chunks)} chunks "
        f"(chunk_size={splitter_config.chunk_size}, overlap={splitter_config.chunk_overlap})"
    )

    return chunks

