"""
Prompt library registry and factory.

This module creates Graphiti prompt libraries from configuration,
loading prompts from YAML templates.
"""

from pathlib import Path
from typing import Any

from graphiti_core.prompts import create_prompt_library
from graphiti_core.prompts.lib import PromptLibrary
from graphiti_core.prompts.models import PromptFunction

from .loader import create_prompt_function_from_yaml
from .snippet_loader import load_snippet, load_snippet_version


def _inject_snippet_wrapper(
    prompt_func: PromptFunction,
    snippet_name: str,
    snippet_value: str,
) -> PromptFunction:
    """
    Wrap a prompt function to inject a snippet into its context.

    Args:
        prompt_func: The original prompt function to wrap
        snippet_name: Name of the snippet to inject (e.g., "summary_instructions")
        snippet_value: The snippet value to inject

    Returns:
        Wrapped prompt function that injects the snippet into context
    """
    def wrapped_func(context: dict[str, Any]) -> list:
        # Create a copy of context to avoid mutating the original
        enhanced_context = dict(context)
        enhanced_context[snippet_name] = snippet_value
        return prompt_func(enhanced_context)

    return wrapped_func


def create_prompt_library_from_config(
    prompt_config: dict[str, Any],
    config_dir: Path | None = None,
) -> PromptLibrary:
    """
    Create a prompt library from configuration.

    This function processes prompt configuration and creates a Graphiti
    PromptLibrary with YAML-loaded prompts and snippets.

    Args:
        prompt_config: Dictionary with prompt type configurations.
            Example structure:
            {
                "extract_text": {
                    "system_version": "v0",
                    "user_version": "v1"
                },
                "summary_instructions_version": "v0"
            }
        config_dir: Base config directory for loading YAML templates

    Returns:
        PromptLibrary with YAML-loaded prompts applied as overrides

    Example:
        >>> config = {
        ...     "extract_text": {"system_version": "v0", "user_version": "v1"},
        ...     "summary_instructions_version": "v0"
        ... }
        >>> library = create_prompt_library_from_config(config)
        >>> # Library now has custom extract_text prompt and summary_instructions loaded from YAML
    """
    overrides: dict[str, dict[str, Any]] = {}

    def _load_default_versions(prompt_type: str) -> tuple[str, str] | None:
        if config_dir is None:
            base_dir = Path(__file__).parent.parent.parent / "configs"
        else:
            base_dir = config_dir
        default_path = base_dir / "prompts" / prompt_type / "default.yaml"
        if not default_path.exists():
            return None
        cfg = default_path.read_text(encoding="utf-8")
        default_cfg = {}
        try:
            import yaml

            default_cfg = yaml.safe_load(cfg) or {}
        except Exception:
            return None
        system_version = default_cfg.get("system_version")
        user_version = default_cfg.get("user_version")
        if not system_version or not user_version:
            return None
        return system_version, user_version

    # Load summary_instructions snippet if configured
    summary_instructions_value: str | None = None
    if "summary_instructions_version" in prompt_config:
        version = prompt_config["summary_instructions_version"]
        summary_instructions_value = load_snippet("summary_instructions", version, config_dir)
    elif config_dir is not None:
        # Try to load default version from default.yaml
        try:
            default_version = load_snippet_version("summary_instructions", config_dir)
            summary_instructions_value = load_snippet("summary_instructions", default_version, config_dir)
        except FileNotFoundError:
            # If no snippet files exist, use default from graphiti
            pass

    # Process extract_text prompt
    if "extract_text" in prompt_config:
        extract_text_config = prompt_config["extract_text"]
        system_version = extract_text_config.get("system_version", "v0")
        user_version = extract_text_config.get("user_version", "v0")

        prompt_func = create_prompt_function_from_yaml(
            "extract_text", system_version, user_version, config_dir
        )

        if "extract_nodes" not in overrides:
            overrides["extract_nodes"] = {}
        overrides["extract_nodes"]["extract_text"] = prompt_func

    # Process extract_edges prompt
    if "extract_edges" in prompt_config:
        extract_edges_config = prompt_config["extract_edges"]
        system_version = extract_edges_config.get("system_version", "v0")
        user_version = extract_edges_config.get("user_version", "v0")

        prompt_func = create_prompt_function_from_yaml(
            "extract_edges", system_version, user_version, config_dir
        )

        if "extract_edges" not in overrides:
            overrides["extract_edges"] = {}
        overrides["extract_edges"]["edge"] = prompt_func

    # Auto-load default versions for additional prompt families if defaults exist
    default_families = {
        "dedupe_nodes": ("dedupe_nodes", "nodes"),
        "dedupe_edges": ("dedupe_edges", "resolve_edge"),
        "invalidate_edges": ("invalidate_edges", "v2"),
        "extract_edge_dates": ("extract_edge_dates", "v1"),
    }
    for prompt_dir, (library_key, version_name) in default_families.items():
        if library_key in overrides and version_name in overrides[library_key]:
            continue
        versions = _load_default_versions(prompt_dir)
        if not versions:
            continue
        system_version, user_version = versions
        prompt_func = create_prompt_function_from_yaml(
            prompt_dir, system_version, user_version, config_dir
        )
        overrides.setdefault(library_key, {})[version_name] = prompt_func

    # Inject snippets into prompt functions that use them
    if summary_instructions_value:
        # Wrap extract_summary and summarize_context functions
        from graphiti_core.prompts.extract_nodes import extract_summary
        from graphiti_core.prompts.summarize_nodes import summarize_context

        if "extract_nodes" not in overrides:
            overrides["extract_nodes"] = {}
        overrides["extract_nodes"]["extract_summary"] = _inject_snippet_wrapper(
            extract_summary, "summary_instructions", summary_instructions_value
        )

        if "summarize_nodes" not in overrides:
            overrides["summarize_nodes"] = {}
        overrides["summarize_nodes"]["summarize_context"] = _inject_snippet_wrapper(
            summarize_context, "summary_instructions", summary_instructions_value
        )

    # Future: Add support for other prompt types
    # if "extract_message" in prompt_config:
    #     ...
    # if "extract_json" in prompt_config:
    #     ...

    # Create library with overrides (empty dict means use defaults)
    return create_prompt_library(overrides if overrides else None)
