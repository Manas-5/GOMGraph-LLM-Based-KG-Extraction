"""
Step: Load file content from disk.

This step reads a text file and returns its content as a string.
"""

from pathlib import Path

from loguru import logger


def load_file(file_path: str | Path) -> str:
    """
    Load text content from a file.

    Args:
        file_path: Path to the text file to load.

    Returns:
        The text content of the file.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file path is empty.
    """
    if not file_path:
        raise ValueError("File path cannot be empty")

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    logger.info(f"Loading file: {path}")

    # Try UTF-8 first, fall back to latin-1 for legacy texts
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning(f"UTF-8 decoding failed for {path}, falling back to latin-1")
        content = path.read_text(encoding="latin-1")

    logger.info(f"Loaded {len(content):,} characters from {path.name}")
    return content
