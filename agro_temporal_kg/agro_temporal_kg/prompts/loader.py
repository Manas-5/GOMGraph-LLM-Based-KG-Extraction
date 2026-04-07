"""
Prompt template loader from YAML files.

This module provides utilities to load prompt templates from YAML configuration files
and convert them into Graphiti-compatible prompt functions.
"""

from pathlib import Path
from typing import Any

from graphiti_core.prompts.models import Message, PromptFunction
from graphiti_core.prompts.prompt_helpers import to_prompt_json


def load_prompt_template(
    prompt_type: str,
    version: str,
    role: str,
    config_dir: Path | None = None,
) -> str:
    """
    Load a prompt template from YAML file.

    Args:
        prompt_type: Type of prompt (e.g., "extract_text")
        version: Version identifier (e.g., "v0")
        role: Prompt role ("system" or "user")
        config_dir: Base config directory (defaults to package configs)

    Returns:
        Template string with placeholders

    Raises:
        FileNotFoundError: If template file doesn't exist
    """
    if config_dir is None:
        # Default to configs directory relative to package root
        config_dir = Path(__file__).parent.parent.parent / "configs"

    template_path = config_dir / "prompts" / prompt_type / f"{role}_{version}.yaml"

    if not template_path.exists():
        raise FileNotFoundError(
            f"Prompt template not found: {template_path}. "
            f"Expected path: {template_path.resolve()}"
        )

    # Load YAML (it's just a string, so read directly)
    template = template_path.read_text(encoding="utf-8").strip()
    return template


def create_prompt_function_from_yaml(
    prompt_type: str,
    system_version: str,
    user_version: str,
    config_dir: Path | None = None,
) -> PromptFunction:
    """
    Create a PromptFunction from YAML templates.

    This function loads system and user prompt templates from YAML files
    and creates a function that formats them with context variables.

    Args:
        prompt_type: Type of prompt (e.g., "extract_text")
        system_version: Version identifier for system prompt (e.g., "v0")
        user_version: Version identifier for user prompt (e.g., "v1")
        config_dir: Base config directory

    Returns:
        PromptFunction that formats templates with context

    Raises:
        FileNotFoundError: If template files don't exist
        ValueError: If required context variables are missing
    """
    system_template = load_prompt_template(prompt_type, system_version, "system", config_dir)
    user_template = load_prompt_template(prompt_type, user_version, "user", config_dir)

    def prompt_func(context: dict[str, Any]) -> list[Message]:
        """
        Format templates with context variables.

        Args:
            context: Dictionary with context variables like:
                - entity_types: List of entity type definitions
                - episode_content: Text content to extract from
                - custom_prompt: Additional instructions
                - previous_episodes: List of previous episode contents
                - episode_timestamp: ISO timestamp string
                - source_description: Description of the source

        Returns:
            List of Message objects (system and user prompts)

        Raises:
            ValueError: If required context variables are missing
        """
        try:
            # Prepare context for formatting
            format_context = dict(context)

            # Normalize common collections to JSON for prompt readability
            def _normalize_episodes(key: str) -> None:
                if key not in format_context:
                    return
                val = format_context[key]
                if val and hasattr(val[0], "content"):
                    format_context[key] = to_prompt_json([ep.content for ep in val])
                else:
                    format_context[key] = to_prompt_json(val)

            if prompt_type in {"extract_edges", "dedupe_edges", "invalidate_edges", "extract_edge_dates", "dedupe_nodes"}:
                _normalize_episodes("previous_episodes")
            if prompt_type in {"extract_edges", "dedupe_edges"} and "edge_types" in format_context:
                format_context["edge_types"] = to_prompt_json(format_context["edge_types"])
            if prompt_type in {"extract_edges"} and "nodes" in format_context:
                format_context["nodes"] = to_prompt_json(format_context["nodes"])
            if prompt_type in {"dedupe_edges"} and "existing_edges" in format_context:
                format_context["existing_edges"] = to_prompt_json(format_context["existing_edges"])
            if prompt_type in {"dedupe_edges"} and "edge_invalidation_candidates" in format_context:
                format_context["edge_invalidation_candidates"] = to_prompt_json(
                    format_context["edge_invalidation_candidates"]
                )
            if prompt_type in {"invalidate_edges"} and "existing_edges" in format_context:
                format_context["existing_edges"] = to_prompt_json(format_context["existing_edges"])
            if prompt_type in {"dedupe_nodes"}:
                if "extracted_nodes" in format_context:
                    format_context["extracted_nodes"] = to_prompt_json(format_context["extracted_nodes"])
                if "existing_nodes" in format_context:
                    format_context["existing_nodes"] = to_prompt_json(format_context["existing_nodes"])

            # Ensure custom_prompt defaults to empty string when used
            if "custom_prompt" not in format_context:
                format_context["custom_prompt"] = ""

            # Format system prompt
            system_content = system_template.format(**format_context)

            # Format user prompt
            user_content = user_template.format(**format_context)
        except KeyError as e:
            available_keys = list(context.keys())
            raise ValueError(
                f"Missing context variable '{e.args[0]}' in prompt template. "
                f"Available context keys: {available_keys}. "
                f"Template may require: entity_types, episode_content, custom_prompt, "
                f"previous_episodes, episode_timestamp, source_description"
            ) from e

        return [
            Message(role="system", content=system_content),
            Message(role="user", content=user_content),
        ]

    return prompt_func
