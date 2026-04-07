"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
#v2
import json
import logging
import typing
from datetime import datetime

import numpy as np
from pydantic import BaseModel, Field
from typing_extensions import Any

from graphiti_core.driver.driver import (
    GraphDriver,
    GraphDriverSession,
    GraphProvider,
)
from graphiti_core.edges import Edge, EntityEdge, EpisodicEdge, create_entity_edge_embeddings
from graphiti_core.embedder import EmbedderClient
from graphiti_core.graphiti_types import GraphitiClients
from graphiti_core.helpers import normalize_l2, semaphore_gather
from graphiti_core.models.edges.edge_db_queries import (
    get_entity_edge_save_bulk_query,
    get_episodic_edge_save_bulk_query,
)
from graphiti_core.models.nodes.node_db_queries import (
    get_entity_node_save_bulk_query,
    get_episode_node_save_bulk_query,
)
from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode
from graphiti_core.utils.datetime_utils import convert_datetimes_to_strings
from graphiti_core.utils.maintenance.dedup_helpers import (
    DedupResolutionState,
    _build_candidate_indexes,
    _normalize_string_exact,
    _resolve_with_similarity,
)
from graphiti_core.utils.maintenance.edge_operations import (
    extract_edges,
    resolve_extracted_edge,
)
from graphiti_core.utils.maintenance.graph_data_operations import (
    EPISODE_WINDOW_LEN,
    retrieve_episodes,
)
from graphiti_core.utils.maintenance.node_operations import (
    extract_nodes,
    resolve_extracted_nodes,
)

logger = logging.getLogger(__name__)

CHUNK_SIZE = 10


def _build_directed_uuid_map(pairs: list[tuple[str, str]]) -> dict[str, str]:
    """Collapse alias -> canonical chains while preserving direction.

    The incoming pairs represent directed mappings discovered during node dedupe. We use a simple
    union-find with iterative path compression to ensure every source UUID resolves to its ultimate
    canonical target, even if aliases appear lexicographically smaller than the canonical UUID.
    """

    parent: dict[str, str] = {}

    def find(uuid: str) -> str:
        """Directed union-find lookup using iterative path compression."""
        parent.setdefault(uuid, uuid)
        root = uuid
        while parent[root] != root:
            root = parent[root]

        while parent[uuid] != root:
            next_uuid = parent[uuid]
            parent[uuid] = root
            uuid = next_uuid

        return root

    for source_uuid, target_uuid in pairs:
        parent.setdefault(source_uuid, source_uuid)
        parent.setdefault(target_uuid, target_uuid)
        parent[find(source_uuid)] = find(target_uuid)

    return {uuid: find(uuid) for uuid in parent}


class RawEpisode(BaseModel):
    name: str
    uuid: str | None = Field(default=None)
    content: str
    source_description: str
    source: EpisodeType
    reference_time: datetime


async def retrieve_previous_episodes_bulk(
    driver: GraphDriver, episodes: list[EpisodicNode]
) -> list[tuple[EpisodicNode, list[EpisodicNode]]]:
    previous_episodes_list = await semaphore_gather(
        *[
            retrieve_episodes(
                driver, episode.valid_at, last_n=EPISODE_WINDOW_LEN, group_ids=[episode.group_id]
            )
            for episode in episodes
        ]
    )
    episode_tuples: list[tuple[EpisodicNode, list[EpisodicNode]]] = [
        (episode, previous_episodes_list[i]) for i, episode in enumerate(episodes)
    ]

    return episode_tuples


async def add_nodes_and_edges_bulk(
    driver: GraphDriver,
    episodic_nodes: list[EpisodicNode],
    episodic_edges: list[EpisodicEdge],
    entity_nodes: list[EntityNode],
    entity_edges: list[EntityEdge],
    embedder: EmbedderClient,
):
    session = driver.session()
    try:
        await session.execute_write(
            add_nodes_and_edges_bulk_tx,
            episodic_nodes,
            episodic_edges,
            entity_nodes,
            entity_edges,
            embedder,
            driver=driver,
        )
    finally:
        await session.close()


async def add_nodes_and_edges_bulk_tx(
    tx: GraphDriverSession,
    episodic_nodes: list[EpisodicNode],
    episodic_edges: list[EpisodicEdge],
    entity_nodes: list[EntityNode],
    entity_edges: list[EntityEdge],
    embedder: EmbedderClient,
    driver: GraphDriver,
):
    episodes = [dict(episode) for episode in episodic_nodes]
    for episode in episodes:
        episode['source'] = str(episode['source'].value)
        episode.pop('labels', None)

    nodes = []

    for node in entity_nodes:
        if node.name_embedding is None:
            await node.generate_name_embedding(embedder)

        entity_data: dict[str, Any] = {
            'uuid': node.uuid,
            'name': node.name,
            'group_id': node.group_id,
            'summary': node.summary,
            'created_at': node.created_at,
            'name_embedding': node.name_embedding,
            'labels': list(set(node.labels + ['Entity'])),
        }

        if driver.provider == GraphProvider.KUZU:
            attributes = convert_datetimes_to_strings(node.attributes) if node.attributes else {}
            entity_data['attributes'] = json.dumps(attributes)
        else:
            entity_data.update(node.attributes or {})

        nodes.append(entity_data)

    edges = []
    for edge in entity_edges:
        if edge.fact_embedding is None:
            await edge.generate_embedding(embedder)
        edge_data: dict[str, Any] = {
            'uuid': edge.uuid,
            'source_node_uuid': edge.source_node_uuid,
            'target_node_uuid': edge.target_node_uuid,
            'name': edge.name,
            'fact': edge.fact,
            'group_id': edge.group_id,
            'episodes': edge.episodes,
            'created_at': edge.created_at,
            'expired_at': edge.expired_at,
            'valid_at': edge.valid_at,
            'invalid_at': edge.invalid_at,
            'fact_embedding': edge.fact_embedding,
        }

        if driver.provider == GraphProvider.KUZU:
            attributes = convert_datetimes_to_strings(edge.attributes) if edge.attributes else {}
            edge_data['attributes'] = json.dumps(attributes)
        else:
            edge_data.update(edge.attributes or {})

        edges.append(edge_data)

    if driver.graph_operations_interface:
        await driver.graph_operations_interface.episodic_node_save_bulk(None, driver, tx, episodes)
        await driver.graph_operations_interface.node_save_bulk(None, driver, tx, nodes)
        await driver.graph_operations_interface.episodic_edge_save_bulk(
            None, driver, tx, [edge.model_dump() for edge in episodic_edges]
        )
        await driver.graph_operations_interface.edge_save_bulk(None, driver, tx, edges)

    elif driver.provider == GraphProvider.KUZU:
        # FIXME: Kuzu's UNWIND does not currently support STRUCT[] type properly, so we insert the data one by one instead for now.
        episode_query = get_episode_node_save_bulk_query(driver.provider)
        for episode in episodes:
            await tx.run(episode_query, **episode)
        entity_node_query = get_entity_node_save_bulk_query(driver.provider, nodes)
        for node in nodes:
            await tx.run(entity_node_query, **node)
        entity_edge_query = get_entity_edge_save_bulk_query(driver.provider)
        for edge in edges:
            await tx.run(entity_edge_query, **edge)
        episodic_edge_query = get_episodic_edge_save_bulk_query(driver.provider)
        for edge in episodic_edges:
            await tx.run(episodic_edge_query, **edge.model_dump())
    else:
        await tx.run(get_episode_node_save_bulk_query(driver.provider), episodes=episodes)
        await tx.run(
            get_entity_node_save_bulk_query(driver.provider, nodes),
            nodes=nodes,
        )
        await tx.run(
            get_episodic_edge_save_bulk_query(driver.provider),
            episodic_edges=[edge.model_dump() for edge in episodic_edges],
        )
        await tx.run(
            get_entity_edge_save_bulk_query(driver.provider),
            entity_edges=edges,
        )


async def extract_nodes_and_edges_bulk(
    clients: GraphitiClients,
    episode_tuples: list[tuple[EpisodicNode, list[EpisodicNode]]],
    edge_type_map: dict[tuple[str, str], list[str]],
    entity_types: dict[str, type[BaseModel]] | None = None,
    excluded_entity_types: list[str] | None = None,
    edge_types: dict[str, type[BaseModel]] | None = None,
) -> tuple[list[list[EntityNode]], list[list[EntityEdge]]]:
    extracted_nodes_bulk: list[list[EntityNode]] = await semaphore_gather(
        *[
            extract_nodes(clients, episode, previous_episodes, entity_types, excluded_entity_types)
            for episode, previous_episodes in episode_tuples
        ]
    )

    extracted_edges_bulk: list[list[EntityEdge]] = await semaphore_gather(
        *[
            extract_edges(
                clients,
                episode,
                extracted_nodes_bulk[i],
                previous_episodes,
                edge_type_map=edge_type_map,
                group_id=episode.group_id,
                edge_types=edge_types,
            )
            for i, (episode, previous_episodes) in enumerate(episode_tuples)
        ]
    )

    return extracted_nodes_bulk, extracted_edges_bulk


async def dedupe_nodes_bulk(
    clients: GraphitiClients,
    extracted_nodes: list[list[EntityNode]],
    episode_tuples: list[tuple[EpisodicNode, list[EpisodicNode]]],
    entity_types: dict[str, type[BaseModel]] | None = None,
) -> tuple[dict[str, list[EntityNode]], dict[str, str]]:
    """Resolve entity duplicates across an in-memory batch using a two-pass strategy.

    1. Run :func:`resolve_extracted_nodes` for every episode in parallel so each batch item is
       reconciled against the live graph just like the non-batch flow.
    2. Re-run the deterministic similarity heuristics across the union of resolved nodes to catch
       duplicates that only co-occur inside this batch, emitting a canonical UUID map that callers
       can apply to edges and persistence.
    """

    first_pass_results = await semaphore_gather(
        *[
            resolve_extracted_nodes(
                clients,
                nodes,
                episode_tuples[i][0],
                episode_tuples[i][1],
                entity_types,
            )
            for i, nodes in enumerate(extracted_nodes)
        ]
    )

    episode_resolutions: list[tuple[str, list[EntityNode]]] = []
    per_episode_uuid_maps: list[dict[str, str]] = []
    duplicate_pairs: list[tuple[str, str]] = []

    for (resolved_nodes, uuid_map, duplicates), (episode, _) in zip(
        first_pass_results, episode_tuples, strict=True
    ):
        episode_resolutions.append((episode.uuid, resolved_nodes))
        per_episode_uuid_maps.append(uuid_map)
        duplicate_pairs.extend((source.uuid, target.uuid) for source, target in duplicates)

    canonical_nodes: dict[str, EntityNode] = {}

    # Build an incremental candidate index to avoid O(n^2) rebuilds.
    incremental_candidates: list[EntityNode] = []
    incremental_index = _build_candidate_indexes(incremental_candidates)

    def _insert_into_index(new_node: EntityNode) -> None:
        normalized = _normalize_string_exact(new_node.name)
        incremental_index.normalized_existing[normalized].append(new_node)
        deplural = normalized[:-1] if normalized.endswith('s') else normalized[:-2] if normalized.endswith('es') else None
        if deplural and deplural != normalized:
            incremental_index.normalized_existing[deplural].append(new_node)
        shingles = incremental_index.shingles_by_candidate.setdefault(
            new_node.uuid, _cached_shingles(_normalize_name_for_fuzzy(new_node.name))
        )
        signature = _minhash_signature(shingles)
        for band_index, band in enumerate(_lsh_bands(signature)):
            incremental_index.lsh_buckets[(band_index, band)].append(new_node.uuid)
        incremental_index.nodes_by_uuid[new_node.uuid] = new_node
        incremental_candidates.append(new_node)

    for _, resolved_nodes in episode_resolutions:
        for node in resolved_nodes:
            if not canonical_nodes:
                canonical_nodes[node.uuid] = node
                _insert_into_index(node)
                continue

            normalized = _normalize_string_exact(node.name)
            exact_candidates = list(incremental_index.normalized_existing.get(normalized, []))
            deplural = normalized[:-1] if normalized.endswith('s') else normalized[:-2] if normalized.endswith('es') else None
            if deplural and deplural != normalized:
                exact_candidates.extend(incremental_index.normalized_existing.get(deplural, []))

            chosen: EntityNode | None = None
            if exact_candidates:
                for cand in sorted(exact_candidates, key=lambda c: c.uuid):
                    merge_ok, _stage = (True, 'exact')
                    if merge_ok:
                        chosen = cand
                        break

            if chosen is None:
                state = DedupResolutionState(resolved_nodes=[None], uuid_map={}, unresolved_indices=[])
                _resolve_with_similarity([node], incremental_index, state)
                chosen = state.resolved_nodes[0]

            if chosen is None:
                canonical_nodes[node.uuid] = node
                _insert_into_index(node)
                continue

            canonical_uuid = chosen.uuid
            canonical_nodes.setdefault(canonical_uuid, chosen)
            if canonical_uuid != node.uuid:
                duplicate_pairs.append((node.uuid, canonical_uuid))
            _insert_into_index(canonical_nodes[canonical_uuid])

    union_pairs: list[tuple[str, str]] = []
    for uuid_map in per_episode_uuid_maps:
        union_pairs.extend(uuid_map.items())
    union_pairs.extend(duplicate_pairs)

    compressed_map: dict[str, str] = _build_directed_uuid_map(union_pairs)

    nodes_by_episode: dict[str, list[EntityNode]] = {}
    for episode_uuid, resolved_nodes in episode_resolutions:
        deduped_nodes: list[EntityNode] = []
        seen: set[str] = set()
        for node in resolved_nodes:
            canonical_uuid = compressed_map.get(node.uuid, node.uuid)
            if canonical_uuid in seen:
                continue
            seen.add(canonical_uuid)
            canonical_node = canonical_nodes.get(canonical_uuid)
            if canonical_node is None:
                logger.error(
                    'Canonical node %s missing during batch dedupe; falling back to %s',
                    canonical_uuid,
                    node.uuid,
                )
                canonical_node = node
            deduped_nodes.append(canonical_node)

        nodes_by_episode[episode_uuid] = deduped_nodes

    return nodes_by_episode, compressed_map


async def dedupe_edges_bulk(
    clients: GraphitiClients,
    extracted_edges: list[list[EntityEdge]],
    episode_tuples: list[tuple[EpisodicNode, list[EpisodicNode]]],
    _entities: list[EntityNode],
    edge_types: dict[str, type[BaseModel]],
    _edge_type_map: dict[tuple[str, str], list[str]],
) -> dict[str, list[EntityEdge]]:
    embedder = clients.embedder
    min_score = 0.6

    # generate embeddings
    await semaphore_gather(
        *[create_entity_edge_embeddings(embedder, edges) for edges in extracted_edges]
    )

    # Find similar results
    dedupe_tuples: list[tuple[EpisodicNode, EntityEdge, list[EntityEdge]]] = []
    for i, edges_i in enumerate(extracted_edges):
        existing_edges: list[EntityEdge] = []
        for edges_j in extracted_edges:
            existing_edges += edges_j

        for edge in edges_i:
            candidates: list[EntityEdge] = []
            for existing_edge in existing_edges:
                # Skip self-comparison
                if edge.uuid == existing_edge.uuid:
                    continue
                # Approximate BM25 by checking for word overlaps (this is faster than creating many in-memory indices)
                # This approach will cast a wider net than BM25, which is ideal for this use case
                if (
                    edge.source_node_uuid != existing_edge.source_node_uuid
                    or edge.target_node_uuid != existing_edge.target_node_uuid
                ):
                    continue

                edge_words = set(edge.fact.lower().split())
                existing_edge_words = set(existing_edge.fact.lower().split())
                has_overlap = not edge_words.isdisjoint(existing_edge_words)
                if has_overlap:
                    candidates.append(existing_edge)
                    continue

                # Check for semantic similarity even if there is no overlap
                similarity = np.dot(
                    normalize_l2(edge.fact_embedding or []),
                    normalize_l2(existing_edge.fact_embedding or []),
                )
                if similarity >= min_score:
                    candidates.append(existing_edge)

            dedupe_tuples.append((episode_tuples[i][0], edge, candidates))

    bulk_edge_resolutions: list[
        tuple[EntityEdge, EntityEdge, list[EntityEdge]]
    ] = await semaphore_gather(
        *[
            resolve_extracted_edge(
                clients.llm_client,
                edge,
                candidates,
                candidates,
                episode,
                edge_types,
                set(edge_types),
                clients.prompt_library,
            )
            for episode, edge, candidates in dedupe_tuples
        ]
    )

    # For now we won't track edge invalidation
    duplicate_pairs: list[tuple[str, str]] = []
    duplicate_stage: dict[str, str] = {}
    for i, (_, _, duplicates) in enumerate(bulk_edge_resolutions):
        episode, edge, candidates = dedupe_tuples[i]
        for duplicate in duplicates:
            duplicate_pairs.append((edge.uuid, duplicate.uuid))
            duplicate_stage[edge.uuid] = 'llm'

    # PATCH: fact-embedding similarity dedupe for edges sharing endpoints (only for still-unmerged edges)
    sim_threshold = 0.9
    grouped_edges: dict[tuple[str, str], list[EntityEdge]] = {}
    for edge in edge_uuid_map.values():
        grouped_edges.setdefault((edge.source_node_uuid, edge.target_node_uuid), []).append(edge)

    already = {alias for alias, canon in duplicate_pairs} | {canon for alias, canon in duplicate_pairs}

    for edges_grp in grouped_edges.values():
        n = len(edges_grp)
        for a in range(n):
            e1 = edges_grp[a]
            if e1.uuid in already or not e1.fact_embedding:
                continue
            v1n = normalize_l2(e1.fact_embedding)
            for b in range(a + 1, n):
                e2 = edges_grp[b]
                if e2.uuid in already or not e2.fact_embedding:
                    continue
                v2n = normalize_l2(e2.fact_embedding)
                try:
                    sim = float(np.dot(v1n, v2n))
                except Exception:
                    continue
                if sim >= sim_threshold:
                    duplicate_pairs.append((e1.uuid, e2.uuid))
                    already.add(e1.uuid)
                    already.add(e2.uuid)
                    duplicate_stage[e1.uuid] = 'fact_cosine_0.9'
                    duplicate_stage[e2.uuid] = 'fact_cosine_0.9'

    # Now we compress the duplicate_map, so that 3 -> 2 and 2 -> becomes 3 -> 1 (sorted by uuid)
    compressed_map: dict[str, str] = compress_uuid_map(duplicate_pairs)

    edge_uuid_map: dict[str, EntityEdge] = {
        edge.uuid: edge for edges in extracted_edges for edge in edges
    }

    edges_by_episode: dict[str, list[EntityEdge]] = {}
    for i, edges in enumerate(extracted_edges):
        episode = episode_tuples[i][0]

        edges_by_episode[episode.uuid] = [
            edge_uuid_map[compressed_map.get(edge.uuid, edge.uuid)] for edge in edges
        ]

    # Log edge dedupe (aggregate). Only groups with at least one alias!=canonical are written.
    _log_bulk_edge_dedupe(
        compressed_map,
        episode_tuples,
        edge_uuid_map,
        [e for edges in extracted_edges for e in edges],
        duplicate_stage,
    )

    return edges_by_episode


class UnionFind:
    def __init__(self, elements):
        # start each element in its own set
        self.parent = {e: e for e in elements}

    def find(self, x):
        # path‐compression
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        # attach the lexicographically larger root under the smaller
        if ra < rb:
            self.parent[rb] = ra
        else:
            self.parent[ra] = rb


def compress_uuid_map(duplicate_pairs: list[tuple[str, str]]) -> dict[str, str]:
    """
    all_ids: iterable of all entity IDs (strings)
    duplicate_pairs: iterable of (id1, id2) pairs
    returns: dict mapping each id -> lexicographically smallest id in its duplicate set
    """
    all_uuids = set()
    for pair in duplicate_pairs:
        all_uuids.add(pair[0])
        all_uuids.add(pair[1])

    uf = UnionFind(all_uuids)
    for a, b in duplicate_pairs:
        uf.union(a, b)
    # ensure full path‐compression before mapping
    return {uuid: uf.find(uuid) for uuid in all_uuids}


def _log_bulk_edge_dedupe(
    compressed_map: dict[str, str],
    episode_tuples: list[tuple[EpisodicNode, list[EpisodicNode]]],
    edge_uuid_map: dict[str, EntityEdge],
    entities: list[EntityNode],
    stage_map: dict[str, str] | None = None,
) -> None:
    """Persist deduped edge pairs to logs/<group_id>/dedupe_edges.csv.

    Only writes when alias != canonical. Uses the first episode's group_id to choose the folder.
    """

    if not compressed_map:
        return

    pairs = [(alias, canon) for alias, canon in compressed_map.items() if alias != canon]
    if not pairs:
        return

    group_id = episode_tuples[0][0].group_id if episode_tuples else None
    if not group_id:
        return

    log_dir = Path.cwd() / 'logs' / group_id
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return

    csv_path = log_dir / 'dedupe_edges.csv'
    is_new = not csv_path.exists()

    node_map: dict[str, EntityNode] = {n.uuid: n for n in entities}
    episode_map: dict[str, EpisodicNode] = {ep.uuid: ep for ep, _ in episode_tuples}

    headers = [
        'timestamp_utc',
        'dedupe_stage',
        'canonical_edge_uuid',
        'canonical_fact',
        'canonical_source_uuid',
        'canonical_source_name',
        'canonical_target_uuid',
        'canonical_target_name',
        'alias_edge_uuid',
        'alias_fact',
        'alias_source_uuid',
        'alias_source_name',
        'alias_target_uuid',
        'alias_target_name',
        'alias_episode_uuid',
        'alias_episode_excerpt',
    ]

    def _row(alias_id: str, canon_id: str) -> list[str]:
        now = datetime.now(timezone.utc).isoformat()
        alias_edge = edge_uuid_map.get(alias_id)
        canon_edge = edge_uuid_map.get(canon_id)
        if alias_edge is None or canon_edge is None:
            return []
        alias_ep_uuid = alias_edge.episodes[0] if alias_edge.episodes else ''
        alias_ep = episode_map.get(alias_ep_uuid)
        excerpt = (alias_ep.content or '')[:200].replace('\n', ' ') if alias_ep else ''
        canon_src = node_map.get(canon_edge.source_node_uuid)
        canon_tgt = node_map.get(canon_edge.target_node_uuid)
        alias_src = node_map.get(alias_edge.source_node_uuid)
        alias_tgt = node_map.get(alias_edge.target_node_uuid)
        return [
            now,
            (stage_map or {}).get(alias_id, ''),
            canon_id,
            canon_edge.fact,
            canon_edge.source_node_uuid,
            canon_src.name if canon_src else '',
            canon_edge.target_node_uuid,
            canon_tgt.name if canon_tgt else '',
            alias_id,
            alias_edge.fact,
            alias_edge.source_node_uuid,
            alias_src.name if alias_src else '',
            alias_edge.target_node_uuid,
            alias_tgt.name if alias_tgt else '',
            alias_ep_uuid,
            excerpt,
        ]

    try:
        mode = 'w' if is_new else 'a'
        with csv_path.open(mode, newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(headers)
            for alias_id, canon_id in pairs:
                row = _row(alias_id, canon_id)
                if row:
                    writer.writerow(row)
    except Exception:
        logger.debug('Failed to write dedupe_edges.csv at %s', csv_path)


E = typing.TypeVar('E', bound=Edge)


def resolve_edge_pointers(edges: list[E], uuid_map: dict[str, str]):
    for edge in edges:
        source_uuid = edge.source_node_uuid
        target_uuid = edge.target_node_uuid
        edge.source_node_uuid = uuid_map.get(source_uuid, source_uuid)
        edge.target_node_uuid = uuid_map.get(target_uuid, target_uuid)

    return edges


#v1
# """
# Copyright 2024, Zep Software, Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# """

# import json
# import logging
# import typing
# from datetime import datetime

# import numpy as np
# from pydantic import BaseModel, Field
# from typing_extensions import Any

# from graphiti_core.driver.driver import (
#     GraphDriver,
#     GraphDriverSession,
#     GraphProvider,
# )
# from graphiti_core.edges import Edge, EntityEdge, EpisodicEdge, create_entity_edge_embeddings
# from graphiti_core.embedder import EmbedderClient
# from graphiti_core.graphiti_types import GraphitiClients
# from graphiti_core.helpers import normalize_l2, semaphore_gather
# from graphiti_core.models.edges.edge_db_queries import (
#     get_entity_edge_save_bulk_query,
#     get_episodic_edge_save_bulk_query,
# )
# from graphiti_core.models.nodes.node_db_queries import (
#     get_entity_node_save_bulk_query,
#     get_episode_node_save_bulk_query,
# )
# from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode
# from graphiti_core.utils.datetime_utils import convert_datetimes_to_strings
# from graphiti_core.utils.maintenance.dedup_helpers import (
#     DedupResolutionState,
#     _build_candidate_indexes,
#     _normalize_string_exact,
#     _resolve_with_similarity,
# )
# from graphiti_core.utils.maintenance.edge_operations import (
#     extract_edges,
#     resolve_extracted_edge,
# )
# from graphiti_core.utils.maintenance.graph_data_operations import (
#     EPISODE_WINDOW_LEN,
#     retrieve_episodes,
# )
# from graphiti_core.utils.maintenance.node_operations import (
#     extract_nodes,
#     resolve_extracted_nodes,
# )

# logger = logging.getLogger(__name__)

# CHUNK_SIZE = 10


# def _build_directed_uuid_map(pairs: list[tuple[str, str]]) -> dict[str, str]:
#     """Collapse alias -> canonical chains while preserving direction.

#     The incoming pairs represent directed mappings discovered during node dedupe. We use a simple
#     union-find with iterative path compression to ensure every source UUID resolves to its ultimate
#     canonical target, even if aliases appear lexicographically smaller than the canonical UUID.
#     """

#     parent: dict[str, str] = {}

#     def find(uuid: str) -> str:
#         """Directed union-find lookup using iterative path compression."""
#         parent.setdefault(uuid, uuid)
#         root = uuid
#         while parent[root] != root:
#             root = parent[root]

#         while parent[uuid] != root:
#             next_uuid = parent[uuid]
#             parent[uuid] = root
#             uuid = next_uuid

#         return root

#     for source_uuid, target_uuid in pairs:
#         parent.setdefault(source_uuid, source_uuid)
#         parent.setdefault(target_uuid, target_uuid)
#         parent[find(source_uuid)] = find(target_uuid)

#     return {uuid: find(uuid) for uuid in parent}


# class RawEpisode(BaseModel):
#     name: str
#     uuid: str | None = Field(default=None)
#     content: str
#     source_description: str
#     source: EpisodeType
#     reference_time: datetime


# async def retrieve_previous_episodes_bulk(
#     driver: GraphDriver, episodes: list[EpisodicNode]
# ) -> list[tuple[EpisodicNode, list[EpisodicNode]]]:
#     previous_episodes_list = await semaphore_gather(
#         *[
#             retrieve_episodes(
#                 driver, episode.valid_at, last_n=EPISODE_WINDOW_LEN, group_ids=[episode.group_id]
#             )
#             for episode in episodes
#         ]
#     )
#     episode_tuples: list[tuple[EpisodicNode, list[EpisodicNode]]] = [
#         (episode, previous_episodes_list[i]) for i, episode in enumerate(episodes)
#     ]

#     return episode_tuples


# async def add_nodes_and_edges_bulk(
#     driver: GraphDriver,
#     episodic_nodes: list[EpisodicNode],
#     episodic_edges: list[EpisodicEdge],
#     entity_nodes: list[EntityNode],
#     entity_edges: list[EntityEdge],
#     embedder: EmbedderClient,
# ):
#     session = driver.session()
#     try:
#         await session.execute_write(
#             add_nodes_and_edges_bulk_tx,
#             episodic_nodes,
#             episodic_edges,
#             entity_nodes,
#             entity_edges,
#             embedder,
#             driver=driver,
#         )
#     finally:
#         await session.close()


# async def add_nodes_and_edges_bulk_tx(
#     tx: GraphDriverSession,
#     episodic_nodes: list[EpisodicNode],
#     episodic_edges: list[EpisodicEdge],
#     entity_nodes: list[EntityNode],
#     entity_edges: list[EntityEdge],
#     embedder: EmbedderClient,
#     driver: GraphDriver,
# ):
#     episodes = [dict(episode) for episode in episodic_nodes]
#     for episode in episodes:
#         episode['source'] = str(episode['source'].value)
#         episode.pop('labels', None)

#     nodes = []

#     for node in entity_nodes:
#         if node.name_embedding is None:
#             await node.generate_name_embedding(embedder)

#         entity_data: dict[str, Any] = {
#             'uuid': node.uuid,
#             'name': node.name,
#             'group_id': node.group_id,
#             'summary': node.summary,
#             'created_at': node.created_at,
#             'name_embedding': node.name_embedding,
#             'labels': list(set(node.labels + ['Entity'])),
#         }

#         if driver.provider == GraphProvider.KUZU:
#             attributes = convert_datetimes_to_strings(node.attributes) if node.attributes else {}
#             entity_data['attributes'] = json.dumps(attributes)
#         else:
#             entity_data.update(node.attributes or {})

#         nodes.append(entity_data)

#     edges = []
#     for edge in entity_edges:
#         if edge.fact_embedding is None:
#             await edge.generate_embedding(embedder)
#         edge_data: dict[str, Any] = {
#             'uuid': edge.uuid,
#             'source_node_uuid': edge.source_node_uuid,
#             'target_node_uuid': edge.target_node_uuid,
#             'name': edge.name,
#             'fact': edge.fact,
#             'group_id': edge.group_id,
#             'episodes': edge.episodes,
#             'created_at': edge.created_at,
#             'expired_at': edge.expired_at,
#             'valid_at': edge.valid_at,
#             'invalid_at': edge.invalid_at,
#             'fact_embedding': edge.fact_embedding,
#         }

#         if driver.provider == GraphProvider.KUZU:
#             attributes = convert_datetimes_to_strings(edge.attributes) if edge.attributes else {}
#             edge_data['attributes'] = json.dumps(attributes)
#         else:
#             edge_data.update(edge.attributes or {})

#         edges.append(edge_data)

#     if driver.graph_operations_interface:
#         await driver.graph_operations_interface.episodic_node_save_bulk(None, driver, tx, episodes)
#         await driver.graph_operations_interface.node_save_bulk(None, driver, tx, nodes)
#         await driver.graph_operations_interface.episodic_edge_save_bulk(
#             None, driver, tx, [edge.model_dump() for edge in episodic_edges]
#         )
#         await driver.graph_operations_interface.edge_save_bulk(None, driver, tx, edges)

#     elif driver.provider == GraphProvider.KUZU:
#         # FIXME: Kuzu's UNWIND does not currently support STRUCT[] type properly, so we insert the data one by one instead for now.
#         episode_query = get_episode_node_save_bulk_query(driver.provider)
#         for episode in episodes:
#             await tx.run(episode_query, **episode)
#         entity_node_query = get_entity_node_save_bulk_query(driver.provider, nodes)
#         for node in nodes:
#             await tx.run(entity_node_query, **node)
#         entity_edge_query = get_entity_edge_save_bulk_query(driver.provider)
#         for edge in edges:
#             await tx.run(entity_edge_query, **edge)
#         episodic_edge_query = get_episodic_edge_save_bulk_query(driver.provider)
#         for edge in episodic_edges:
#             await tx.run(episodic_edge_query, **edge.model_dump())
#     else:
#         await tx.run(get_episode_node_save_bulk_query(driver.provider), episodes=episodes)
#         await tx.run(
#             get_entity_node_save_bulk_query(driver.provider, nodes),
#             nodes=nodes,
#         )
#         await tx.run(
#             get_episodic_edge_save_bulk_query(driver.provider),
#             episodic_edges=[edge.model_dump() for edge in episodic_edges],
#         )
#         await tx.run(
#             get_entity_edge_save_bulk_query(driver.provider),
#             entity_edges=edges,
#         )


# async def extract_nodes_and_edges_bulk(
#     clients: GraphitiClients,
#     episode_tuples: list[tuple[EpisodicNode, list[EpisodicNode]]],
#     edge_type_map: dict[tuple[str, str], list[str]],
#     entity_types: dict[str, type[BaseModel]] | None = None,
#     excluded_entity_types: list[str] | None = None,
#     edge_types: dict[str, type[BaseModel]] | None = None,
# ) -> tuple[list[list[EntityNode]], list[list[EntityEdge]]]:
#     extracted_nodes_bulk: list[list[EntityNode]] = await semaphore_gather(
#         *[
#             extract_nodes(clients, episode, previous_episodes, entity_types, excluded_entity_types)
#             for episode, previous_episodes in episode_tuples
#         ]
#     )

#     extracted_edges_bulk: list[list[EntityEdge]] = await semaphore_gather(
#         *[
#             extract_edges(
#                 clients,
#                 episode,
#                 extracted_nodes_bulk[i],
#                 previous_episodes,
#                 edge_type_map=edge_type_map,
#                 group_id=episode.group_id,
#                 edge_types=edge_types,
#             )
#             for i, (episode, previous_episodes) in enumerate(episode_tuples)
#         ]
#     )

#     return extracted_nodes_bulk, extracted_edges_bulk


# async def dedupe_nodes_bulk(
#     clients: GraphitiClients,
#     extracted_nodes: list[list[EntityNode]],
#     episode_tuples: list[tuple[EpisodicNode, list[EpisodicNode]]],
#     entity_types: dict[str, type[BaseModel]] | None = None,
# ) -> tuple[dict[str, list[EntityNode]], dict[str, str]]:
#     """Resolve entity duplicates across an in-memory batch using a two-pass strategy.

#     1. Run :func:`resolve_extracted_nodes` for every episode in parallel so each batch item is
#        reconciled against the live graph just like the non-batch flow.
#     2. Re-run the deterministic similarity heuristics across the union of resolved nodes to catch
#        duplicates that only co-occur inside this batch, emitting a canonical UUID map that callers
#        can apply to edges and persistence.
#     """

#     first_pass_results = await semaphore_gather(
#         *[
#             resolve_extracted_nodes(
#                 clients,
#                 nodes,
#                 episode_tuples[i][0],
#                 episode_tuples[i][1],
#                 entity_types,
#             )
#             for i, nodes in enumerate(extracted_nodes)
#         ]
#     )

#     episode_resolutions: list[tuple[str, list[EntityNode]]] = []
#     per_episode_uuid_maps: list[dict[str, str]] = []
#     duplicate_pairs: list[tuple[str, str]] = []

#     for (resolved_nodes, uuid_map, duplicates), (episode, _) in zip(
#         first_pass_results, episode_tuples, strict=True
#     ):
#         episode_resolutions.append((episode.uuid, resolved_nodes))
#         per_episode_uuid_maps.append(uuid_map)
#         duplicate_pairs.extend((source.uuid, target.uuid) for source, target in duplicates)

#     canonical_nodes: dict[str, EntityNode] = {}

#     # Build an incremental candidate index to avoid O(n^2) rebuilds.
#     incremental_candidates: list[EntityNode] = []
#     incremental_index = _build_candidate_indexes(incremental_candidates)

#     def _insert_into_index(new_node: EntityNode) -> None:
#         normalized = _normalize_string_exact(new_node.name)
#         incremental_index.normalized_existing[normalized].append(new_node)
#         deplural = normalized[:-1] if normalized.endswith('s') else normalized[:-2] if normalized.endswith('es') else None
#         if deplural and deplural != normalized:
#             incremental_index.normalized_existing[deplural].append(new_node)
#         shingles = incremental_index.shingles_by_candidate.setdefault(
#             new_node.uuid, _cached_shingles(_normalize_name_for_fuzzy(new_node.name))
#         )
#         signature = _minhash_signature(shingles)
#         for band_index, band in enumerate(_lsh_bands(signature)):
#             incremental_index.lsh_buckets[(band_index, band)].append(new_node.uuid)
#         incremental_index.nodes_by_uuid[new_node.uuid] = new_node
#         incremental_candidates.append(new_node)

#     for _, resolved_nodes in episode_resolutions:
#         for node in resolved_nodes:
#             if not canonical_nodes:
#                 canonical_nodes[node.uuid] = node
#                 _insert_into_index(node)
#                 continue

#             normalized = _normalize_string_exact(node.name)
#             exact_candidates = list(incremental_index.normalized_existing.get(normalized, []))
#             deplural = normalized[:-1] if normalized.endswith('s') else normalized[:-2] if normalized.endswith('es') else None
#             if deplural and deplural != normalized:
#                 exact_candidates.extend(incremental_index.normalized_existing.get(deplural, []))

#             chosen: EntityNode | None = None
#             if exact_candidates:
#                 for cand in sorted(exact_candidates, key=lambda c: c.uuid):
#                     merge_ok, _stage = (True, 'exact')
#                     if merge_ok:
#                         chosen = cand
#                         break

#             if chosen is None:
#                 state = DedupResolutionState(resolved_nodes=[None], uuid_map={}, unresolved_indices=[])
#                 _resolve_with_similarity([node], incremental_index, state)
#                 chosen = state.resolved_nodes[0]

#             if chosen is None:
#                 canonical_nodes[node.uuid] = node
#                 _insert_into_index(node)
#                 continue

#             canonical_uuid = chosen.uuid
#             canonical_nodes.setdefault(canonical_uuid, chosen)
#             if canonical_uuid != node.uuid:
#                 duplicate_pairs.append((node.uuid, canonical_uuid))
#             _insert_into_index(canonical_nodes[canonical_uuid])

#     union_pairs: list[tuple[str, str]] = []
#     for uuid_map in per_episode_uuid_maps:
#         union_pairs.extend(uuid_map.items())
#     union_pairs.extend(duplicate_pairs)

#     compressed_map: dict[str, str] = _build_directed_uuid_map(union_pairs)

#     nodes_by_episode: dict[str, list[EntityNode]] = {}
#     for episode_uuid, resolved_nodes in episode_resolutions:
#         deduped_nodes: list[EntityNode] = []
#         seen: set[str] = set()
#         for node in resolved_nodes:
#             canonical_uuid = compressed_map.get(node.uuid, node.uuid)
#             if canonical_uuid in seen:
#                 continue
#             seen.add(canonical_uuid)
#             canonical_node = canonical_nodes.get(canonical_uuid)
#             if canonical_node is None:
#                 logger.error(
#                     'Canonical node %s missing during batch dedupe; falling back to %s',
#                     canonical_uuid,
#                     node.uuid,
#                 )
#                 canonical_node = node
#             deduped_nodes.append(canonical_node)

#         nodes_by_episode[episode_uuid] = deduped_nodes

#     return nodes_by_episode, compressed_map


# async def dedupe_edges_bulk(
#     clients: GraphitiClients,
#     extracted_edges: list[list[EntityEdge]],
#     episode_tuples: list[tuple[EpisodicNode, list[EpisodicNode]]],
#     _entities: list[EntityNode],
#     edge_types: dict[str, type[BaseModel]],
#     _edge_type_map: dict[tuple[str, str], list[str]],
# ) -> dict[str, list[EntityEdge]]:
#     embedder = clients.embedder
#     min_score = 0.6

#     # generate embeddings
#     await semaphore_gather(
#         *[create_entity_edge_embeddings(embedder, edges) for edges in extracted_edges]
#     )

#     # Find similar results
#     dedupe_tuples: list[tuple[EpisodicNode, EntityEdge, list[EntityEdge]]] = []
#     for i, edges_i in enumerate(extracted_edges):
#         existing_edges: list[EntityEdge] = []
#         for edges_j in extracted_edges:
#             existing_edges += edges_j

#         for edge in edges_i:
#             candidates: list[EntityEdge] = []
#             for existing_edge in existing_edges:
#                 # Skip self-comparison
#                 if edge.uuid == existing_edge.uuid:
#                     continue
#                 # Approximate BM25 by checking for word overlaps (this is faster than creating many in-memory indices)
#                 # This approach will cast a wider net than BM25, which is ideal for this use case
#                 if (
#                     edge.source_node_uuid != existing_edge.source_node_uuid
#                     or edge.target_node_uuid != existing_edge.target_node_uuid
#                 ):
#                     continue

#                 edge_words = set(edge.fact.lower().split())
#                 existing_edge_words = set(existing_edge.fact.lower().split())
#                 has_overlap = not edge_words.isdisjoint(existing_edge_words)
#                 if has_overlap:
#                     candidates.append(existing_edge)
#                     continue

#                 # Check for semantic similarity even if there is no overlap
#                 similarity = np.dot(
#                     normalize_l2(edge.fact_embedding or []),
#                     normalize_l2(existing_edge.fact_embedding or []),
#                 )
#                 if similarity >= min_score:
#                     candidates.append(existing_edge)

#             dedupe_tuples.append((episode_tuples[i][0], edge, candidates))

#     bulk_edge_resolutions: list[
#         tuple[EntityEdge, EntityEdge, list[EntityEdge]]
#     ] = await semaphore_gather(
#         *[
#             resolve_extracted_edge(
#                 clients.llm_client,
#                 edge,
#                 candidates,
#                 candidates,
#                 episode,
#                 edge_types,
#                 set(edge_types),
#                 clients.prompt_library,
#             )
#             for episode, edge, candidates in dedupe_tuples
#         ]
#     )

#     # For now we won't track edge invalidation
#     duplicate_pairs: list[tuple[str, str]] = []
#     for i, (_, _, duplicates) in enumerate(bulk_edge_resolutions):
#         episode, edge, candidates = dedupe_tuples[i]
#         for duplicate in duplicates:
#             duplicate_pairs.append((edge.uuid, duplicate.uuid))

#     # Now we compress the duplicate_map, so that 3 -> 2 and 2 -> becomes 3 -> 1 (sorted by uuid)
#     compressed_map: dict[str, str] = compress_uuid_map(duplicate_pairs)

#     edge_uuid_map: dict[str, EntityEdge] = {
#         edge.uuid: edge for edges in extracted_edges for edge in edges
#     }

#     edges_by_episode: dict[str, list[EntityEdge]] = {}
#     for i, edges in enumerate(extracted_edges):
#         episode = episode_tuples[i][0]

#         edges_by_episode[episode.uuid] = [
#             edge_uuid_map[compressed_map.get(edge.uuid, edge.uuid)] for edge in edges
#         ]

#     # Log edge dedupe (aggregate). Only groups with at least one alias!=canonical are written.
#     _log_bulk_edge_dedupe(
#         compressed_map,
#         episode_tuples,
#         edge_uuid_map,
#         [e for edges in extracted_edges for e in edges],
#     )

#     return edges_by_episode


# class UnionFind:
#     def __init__(self, elements):
#         # start each element in its own set
#         self.parent = {e: e for e in elements}

#     def find(self, x):
#         # path‐compression
#         if self.parent[x] != x:
#             self.parent[x] = self.find(self.parent[x])
#         return self.parent[x]

#     def union(self, a, b):
#         ra, rb = self.find(a), self.find(b)
#         if ra == rb:
#             return
#         # attach the lexicographically larger root under the smaller
#         if ra < rb:
#             self.parent[rb] = ra
#         else:
#             self.parent[ra] = rb


# def compress_uuid_map(duplicate_pairs: list[tuple[str, str]]) -> dict[str, str]:
#     """
#     all_ids: iterable of all entity IDs (strings)
#     duplicate_pairs: iterable of (id1, id2) pairs
#     returns: dict mapping each id -> lexicographically smallest id in its duplicate set
#     """
#     all_uuids = set()
#     for pair in duplicate_pairs:
#         all_uuids.add(pair[0])
#         all_uuids.add(pair[1])

#     uf = UnionFind(all_uuids)
#     for a, b in duplicate_pairs:
#         uf.union(a, b)
#     # ensure full path‐compression before mapping
#     return {uuid: uf.find(uuid) for uuid in all_uuids}


# def _log_bulk_edge_dedupe(
#     compressed_map: dict[str, str],
#     episode_tuples: list[tuple[EpisodicNode, list[EpisodicNode]]],
#     edge_uuid_map: dict[str, EntityEdge],
#     entities: list[EntityNode],
# ) -> None:
#     """Persist deduped edge pairs to logs/<group_id>/dedupe_edges.csv.

#     Only writes when alias != canonical. Uses the first episode's group_id to choose the folder.
#     """

#     if not compressed_map:
#         return

#     pairs = [(alias, canon) for alias, canon in compressed_map.items() if alias != canon]
#     if not pairs:
#         return

#     group_id = episode_tuples[0][0].group_id if episode_tuples else None
#     if not group_id:
#         return

#     log_dir = Path.cwd() / 'logs' / group_id
#     try:
#         log_dir.mkdir(parents=True, exist_ok=True)
#     except Exception:
#         return

#     csv_path = log_dir / 'dedupe_edges.csv'
#     is_new = not csv_path.exists()

#     node_map: dict[str, EntityNode] = {n.uuid: n for n in entities}
#     episode_map: dict[str, EpisodicNode] = {ep.uuid: ep for ep, _ in episode_tuples}

#     headers = [
#         'timestamp_utc',
#         'canonical_edge_uuid',
#         'canonical_fact',
#         'canonical_source_uuid',
#         'canonical_source_name',
#         'canonical_target_uuid',
#         'canonical_target_name',
#         'alias_edge_uuid',
#         'alias_fact',
#         'alias_source_uuid',
#         'alias_source_name',
#         'alias_target_uuid',
#         'alias_target_name',
#         'alias_episode_uuid',
#         'alias_episode_excerpt',
#     ]

#     def _row(alias_id: str, canon_id: str) -> list[str]:
#         now = datetime.now(timezone.utc).isoformat()
#         alias_edge = edge_uuid_map.get(alias_id)
#         canon_edge = edge_uuid_map.get(canon_id)
#         if alias_edge is None or canon_edge is None:
#             return []
#         alias_ep_uuid = alias_edge.episodes[0] if alias_edge.episodes else ''
#         alias_ep = episode_map.get(alias_ep_uuid)
#         excerpt = (alias_ep.content or '')[:200].replace('\n', ' ') if alias_ep else ''
#         canon_src = node_map.get(canon_edge.source_node_uuid)
#         canon_tgt = node_map.get(canon_edge.target_node_uuid)
#         alias_src = node_map.get(alias_edge.source_node_uuid)
#         alias_tgt = node_map.get(alias_edge.target_node_uuid)
#         return [
#             now,
#             canon_id,
#             canon_edge.fact,
#             canon_edge.source_node_uuid,
#             canon_src.name if canon_src else '',
#             canon_edge.target_node_uuid,
#             canon_tgt.name if canon_tgt else '',
#             alias_id,
#             alias_edge.fact,
#             alias_edge.source_node_uuid,
#             alias_src.name if alias_src else '',
#             alias_edge.target_node_uuid,
#             alias_tgt.name if alias_tgt else '',
#             alias_ep_uuid,
#             excerpt,
#         ]

#     try:
#         mode = 'w' if is_new else 'a'
#         with csv_path.open(mode, newline='', encoding='utf-8') as f:
#             writer = csv.writer(f)
#             if is_new:
#                 writer.writerow(headers)
#             for alias_id, canon_id in pairs:
#                 row = _row(alias_id, canon_id)
#                 if row:
#                     writer.writerow(row)
#     except Exception:
#         logger.debug('Failed to write dedupe_edges.csv at %s', csv_path)


# E = typing.TypeVar('E', bound=Edge)


# def resolve_edge_pointers(edges: list[E], uuid_map: dict[str, str]):
#     for edge in edges:
#         source_uuid = edge.source_node_uuid
#         target_uuid = edge.target_node_uuid
#         edge.source_node_uuid = uuid_map.get(source_uuid, source_uuid)
#         edge.target_node_uuid = uuid_map.get(target_uuid, target_uuid)

#     return edges
