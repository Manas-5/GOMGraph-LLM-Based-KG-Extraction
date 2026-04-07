import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from graphiti_core.graphiti import Graphiti
from graphiti_core.nodes import EpisodicNode, EntityNode
from graphiti_core.edges import EntityEdge

logger = logging.getLogger(__name__)


class LoggingGraphiti(Graphiti):
    """Thin wrapper around Graphiti that emits explicit dedupe/edge-resolution logs."""

    async def resolve_extracted_nodes(
        self,
        nodes: list[EntityNode],
        episode: EpisodicNode | None = None,
        previous_episodes: list[EpisodicNode] | None = None,
        entity_types: dict[str, type[BaseModel]] | None = None,
        existing_nodes_override: list[EntityNode] | None = None,
        log_dedupe: bool = True,
    ) -> tuple[list[EntityNode], dict[str, str], list[tuple[EntityNode, EntityNode]]]:
        resolved_nodes, uuid_map, duplicates = await super().resolve_extracted_nodes(
            nodes, episode, previous_episodes, entity_types, existing_nodes_override, log_dedupe
        )
        try:
            logger.info(
                "[DEDUP:NODES] extracted=%d resolved=%d remapped=%d duplicates=%d",
                len(nodes),
                len(resolved_nodes),
                len(uuid_map),
                len(duplicates),
            )
        except Exception:
            logger.debug("Failed to log node dedupe metrics", exc_info=True)
        return resolved_nodes, uuid_map, duplicates

    async def _extract_and_resolve_edges(
        self,
        episode: EpisodicNode,
        extracted_nodes: list[EntityNode],
        previous_episodes: list[EpisodicNode],
        edge_type_map: dict[tuple[str, str], list[str]],
        group_id: str,
        edge_types: dict[str, type[BaseModel]] | None,
        nodes: list[EntityNode],
        uuid_map: dict[str, str],
    ) -> tuple[list[EntityEdge], list[EntityEdge]]:
        resolved_edges, invalidated_edges = await super()._extract_and_resolve_edges(
            episode,
            extracted_nodes,
            previous_episodes,
            edge_type_map,
            group_id,
            edge_types,
            nodes,
            uuid_map,
        )
        try:
            edges_with_dates = sum(
                1 for e in resolved_edges if e.valid_at is not None or e.invalid_at is not None
            )
            logger.info(
                "[DEDUP:EDGES] resolved=%d invalidated=%d with_dates=%d",
                len(resolved_edges),
                len(invalidated_edges),
                edges_with_dates,
            )
        except Exception:
            logger.debug("Failed to log edge dedupe metrics", exc_info=True)
        return resolved_edges, invalidated_edges
