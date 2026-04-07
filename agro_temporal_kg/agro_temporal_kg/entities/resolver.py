"""
Entity and Relation Type Resolver.

This module provides utilities to resolve string-based type selections
into actual Pydantic model dictionaries for use with Graphiti.
"""

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Mapping

from agro_temporal_kg.entities.entity_types import entity_types as all_entity_types
from agro_temporal_kg.entities.relation_types import edge_types as all_edge_types


class TypeResolutionError(Exception):
    """Raised when type resolution fails."""

    pass


def resolve_entity_types(
    type_names: list[str] | None,
    available_types: dict[str, type[BaseModel]] | None = None,
) -> dict[str, type[BaseModel]] | None:
    """
    Resolve a list of entity type names to a dictionary of type models.

    Args:
        type_names: List of entity type names to include. If None or empty, returns None.
        available_types: Dictionary of all available entity types. If None, uses all_entity_types.

    Returns:
        Dictionary mapping type names to their model classes, or None if type_names is None/empty.

    Raises:
        TypeResolutionError: If any requested type name doesn't exist in available_types.

    Examples:
        >>> resolve_entity_types(["Plant", "Pest"])
        {"Plant": Plant, "Pest": Pest}

        >>> resolve_entity_types(None)
        None

        >>> resolve_entity_types([])
        None
    """
    if available_types is None:
        available_types = all_entity_types

    if not type_names:
        return None

    # Validate all requested types exist
    invalid_types = [name for name in type_names if name not in available_types]
    if invalid_types:
        available_names = ", ".join(sorted(available_types.keys()))
        raise TypeResolutionError(
            f"Unknown entity type(s): {', '.join(invalid_types)}. "
            f"Available types: {available_names}"
        )

    # Build filtered dictionary
    resolved = {name: available_types[name] for name in type_names}
    return resolved


def resolve_edge_types(
    type_names: list[str] | None,
    available_types: dict[str, type[BaseModel]] | None = None,
) -> dict[str, type[BaseModel]] | None:
    """
    Resolve a list of edge/relation type names to a dictionary of type models.

    Args:
        type_names: List of edge type names to include. If None or empty, returns None.
        available_types: Dictionary of all available edge types. If None, uses all_edge_types.

    Returns:
        Dictionary mapping type names to their model classes, or None if type_names is None/empty.

    Raises:
        TypeResolutionError: If any requested type name doesn't exist in available_types.

    Examples:
        >>> resolve_edge_types(["PlantedAt", "HarvestedAt"])
        {"PlantedAt": PlantedAt, "HarvestedAt": HarvestedAt}

        >>> resolve_edge_types(None)
        None

        >>> resolve_edge_types([])
        None
    """
    if available_types is None:
        available_types = all_edge_types

    if not type_names:
        return None

    # Validate all requested types exist
    invalid_types = [name for name in type_names if name not in available_types]
    if invalid_types:
        available_names = ", ".join(sorted(available_types.keys()))
        raise TypeResolutionError(
            f"Unknown edge type(s): {', '.join(invalid_types)}. "
            f"Available types: {available_names}"
        )

    # Build filtered dictionary
    resolved = {name: available_types[name] for name in type_names}
    return resolved


def get_available_entity_types() -> list[str]:
    """Get list of all available entity type names."""
    return sorted(all_entity_types.keys())


def get_available_edge_types() -> list[str]:
    """Get list of all available edge type names."""
    return sorted(all_edge_types.keys())

