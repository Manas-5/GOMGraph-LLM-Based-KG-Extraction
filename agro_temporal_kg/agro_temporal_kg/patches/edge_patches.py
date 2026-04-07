"""
Runtime patches for edge handling to keep vendor code untouched.

Adds:
- Edge date enrichment via extract_edge_dates prompt.
- Explicit contradiction invalidation via invalidate_edges prompt.
"""

from __future__ import annotations

from typing import Any

from graphiti_core.helpers import semaphore_gather
from graphiti_core.prompts.lib import prompt_library as default_prompt_library
from graphiti_core.utils.maintenance.temporal_operations import (
    extract_edge_dates,
    get_edge_contradictions,
)

# Import after helpers to grab module logger/functions
from graphiti_core.utils.maintenance import edge_operations as edge_ops  # noqa: E402

_orig_extract_edges = edge_ops.extract_edges
_orig_resolve_extracted_edge = edge_ops.resolve_extracted_edge
logger = edge_ops.logger


async def _extract_edges_with_dates(
    clients: Any,
    episode: Any,
    nodes: list[Any],
    previous_episodes: list[Any],
    edge_type_map: dict[tuple[str, str], list[str]],
    group_id: str = '',
    edge_types: dict[str, Any] | None = None,
):
    edges = await _orig_extract_edges(
        clients, episode, nodes, previous_episodes, edge_type_map, group_id, edge_types
    )
    if not edges:
        return edges

    # Enrich edges with temporal bounds when missing
    date_results = await semaphore_gather(
        *[
            extract_edge_dates(clients.llm_client, edge, episode, previous_episodes, clients.prompt_library)
            for edge in edges
        ]
    )
    for edge, (valid_at, invalid_at) in zip(edges, date_results, strict=True):
        if edge.valid_at is None and valid_at is not None:
            edge.valid_at = valid_at
        if edge.invalid_at is None and invalid_at is not None:
            edge.invalid_at = invalid_at

    return edges


async def _resolve_extracted_edge_with_invalidation(
    llm_client: Any,
    extracted_edge: Any,
    related_edges: list[Any],
    existing_edges: list[Any],
    episode: Any,
    edge_type_candidates: dict[str, Any] | None = None,
    custom_edge_type_names: set[str] | None = None,
    prompt_library: Any | None = None,
):
    resolved_edge, invalidated_edges, duplicate_edges = await _orig_resolve_extracted_edge(
        llm_client,
        extracted_edge,
        related_edges,
        existing_edges,
        episode,
        edge_type_candidates,
        custom_edge_type_names,
        prompt_library,
    )

    # Add explicit contradiction check via invalidate_edges prompt
    if prompt_library is None:
        prompt_library = default_prompt_library
    try:
        extra_invalidations = await get_edge_contradictions(
            llm_client, resolved_edge, existing_edges, prompt_library
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning('LLM contradiction check failed: %s', exc)
        extra_invalidations = []

    # Merge invalidations by UUID, preserving order
    if extra_invalidations:
        seen = {getattr(edge, 'uuid', None) for edge in invalidated_edges}
        for edge in extra_invalidations:
            uuid = getattr(edge, 'uuid', None)
            if uuid in seen:
                continue
            seen.add(uuid)
            invalidated_edges.append(edge)

    return resolved_edge, invalidated_edges, duplicate_edges


def apply_edge_patches() -> None:
    """Monkey-patch edge operations to add date enrichment and explicit invalidation."""
    edge_ops.extract_edges = _extract_edges_with_dates  # type: ignore[assignment]
    edge_ops.resolve_extracted_edge = _resolve_extracted_edge_with_invalidation  # type: ignore[assignment]

