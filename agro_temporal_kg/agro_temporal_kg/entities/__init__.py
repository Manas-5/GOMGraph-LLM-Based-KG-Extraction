"""Entity and relation type definitions and resolvers."""

from agro_temporal_kg.entities.entity_types import entity_types
from agro_temporal_kg.entities.relation_types import edge_types
from agro_temporal_kg.entities.resolver import (
    TypeResolutionError,
    get_available_edge_types,
    get_available_entity_types,
    resolve_edge_types,
    resolve_entity_types,
)

__all__ = [
    "entity_types",
    "edge_types",
    "resolve_entity_types",
    "resolve_edge_types",
    "get_available_entity_types",
    "get_available_edge_types",
    "TypeResolutionError",
]

