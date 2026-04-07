"""
Snippet loader from YAML files.

This module provides utilities to load prompt snippets (like summary_instructions)
from YAML configuration files.
"""

from pathlib import Path

from omegaconf import OmegaConf


def load_snippet(
    snippet_name: str,
    version: str,
    config_dir: Path | None = None,
) -> str:
    """
    Load a snippet template from YAML file.

    Args:
        snippet_name: Name of the snippet (e.g., "summary_instructions")
        version: Version identifier (e.g., "v0")
        config_dir: Base config directory (defaults to package configs)

    Returns:
        Snippet string content

    Raises:
        FileNotFoundError: If snippet file doesn't exist
    """
    if config_dir is None:
        # Default to configs directory relative to package root
        config_dir = Path(__file__).parent.parent.parent / "configs"

    snippet_path = config_dir / "prompts" / "snippets" / f"{snippet_name}_{version}.yaml"

    if not snippet_path.exists():
        raise FileNotFoundError(
            f"Snippet template not found: {snippet_path}. "
            f"Expected path: {snippet_path.resolve()}"
        )

    # Load YAML (it's just a string, so read directly)
    snippet = snippet_path.read_text(encoding="utf-8").strip()
    return snippet


def load_snippet_version(
    snippet_name: str,
    config_dir: Path | None = None,
) -> str:
    """
    Load the default version for a snippet from default.yaml.

    Args:
        snippet_name: Name of the snippet (e.g., "summary_instructions")
        config_dir: Base config directory (defaults to package configs)

    Returns:
        Version string (e.g., "v0")

    Raises:
        FileNotFoundError: If default.yaml doesn't exist
        KeyError: If snippet_name not found in default.yaml
    """
    if config_dir is None:
        config_dir = Path(__file__).parent.parent.parent / "configs"

    default_path = config_dir / "prompts" / "snippets" / "default.yaml"

    if not default_path.exists():
        # If no default.yaml, return "v0" as default
        return "v0"

    # Load and parse YAML using OmegaConf
    try:
        default_config = OmegaConf.load(default_path)
        snippet_config = default_config.get(snippet_name, {})
        if isinstance(snippet_config, dict):
            return snippet_config.get("version", "v0")
        return "v0"
    except Exception:
        # If loading fails, return "v0" as fallback
        return "v0"

