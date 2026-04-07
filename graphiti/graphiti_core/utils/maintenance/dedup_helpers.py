"""
  1. Build exact keys for the extracted entity:
      - normalized_exact (lowercase, collapse spaces)
      - normalized_deplural (simple s/es stripping)
      - Lookup all candidates with either key.
  2. Exact stage (with safeguards):
      - If any candidates, try them (sorted by UUID) through _should_merge_exact:
          - Location: geo hints overlap → merge (exact_geo); if only one side has hints → merge (exact_geo_hint_partial); if none → merge (exact_geo).
          - People: if both have person_name, require equality; if only one or none, still merge (exact_people).
          - Institution: ROR overlap → merge (exact_ror); if only one has ROR → merge (exact_ror_partial); else if both have institution_name, require equality; if only one → merge (exact_institution_partial); else merge (exact).
          - Others: merge (exact).
      - If a candidate passes, merge and stop.
      - If no candidate passes safeguards, fall back to LLM (see step 4).
  3. Fuzzy stage (only if no exact merge):
      - If the name has sufficient entropy/length (_has_high_entropy), run MinHash/LSH and Jaccard ≥ 0.90 to find a best candidate; if found, merge (fuzzy).
      - If low-entropy and not Location/Entity/Practice, skip fuzzy.
  4. LLM stage (only unresolved items):
      - Anything not merged in steps 2–3 is sent to the LLM dedupe prompt; if the LLM picks a match, merge (llm); otherwise keep as new.
  5. Output resolved nodes and uuid_map; dedupe CSVs are written when log_dedupe=True (default).

  So: exact (with de-plural + safeguards) → fuzzy (if allowed) → LLM. Locations still use pycountry for geo hints in the exact safeguard. Low-entropy names that aren’t Location/Entity/Practice go straight to LLM if exact didn’t
  merge.

• MinHash/LSH (locality-sensitive hashing) is a fast way to find likely similar strings without comparing every pair directly:

  - We turn a normalized name into character 3‑grams (“marketgardener” → “mar”, “ark”, “rke”, …).
  - MinHash compresses that shingle set into a fixed-length signature that preserves Jaccard similarity: sets with higher Jaccard have more matching signature values.
  - LSH groups signatures into “bands” so strings with high Jaccard fall into the same buckets; this gives us a small candidate set instead of scanning all nodes.
  - For each extracted name, we:
      1. Compute its signature and LSH buckets.
      2. Collect candidate IDs from matching buckets.
      3. Compute the real Jaccard similarity of the shingle sets for those candidates.
      4. If the best Jaccard ≥ 0.90, we merge (stage=fuzzy).

  So MinHash/LSH narrows the search; Jaccard is the final similarity check.

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
#v3 updated version with depluralization in exact matching

from __future__ import annotations

import functools
import json
import logging
import math
import os
import re
import zipfile
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import blake2b
from pathlib import Path
from typing import TYPE_CHECKING, Iterable as TypingIterable

if TYPE_CHECKING:
    from graphiti_core.nodes import EntityNode

_NAME_ENTROPY_THRESHOLD = 1.5
_MIN_NAME_LENGTH = 6
_MIN_TOKEN_COUNT = 2
_FUZZY_JACCARD_THRESHOLD = 0.9
_MINHASH_PERMUTATIONS = 32
_MINHASH_BAND_SIZE = 4

logger = logging.getLogger(__name__)
try:
    import pycountry  # type: ignore
except Exception:
    pycountry = None


def _normalize_string_exact(name: str) -> str:
    """Lowercase text and collapse whitespace so equal names map to the same key."""
    normalized = re.sub(r'[\s]+', ' ', name.lower())
    return normalized.strip()


def _strip_plural(normalized: str) -> str:
    """Best-effort singularization for exact matching (simple s/es stripping)."""
    if not normalized:
        return normalized
    tokens = normalized.split()
    stripped: list[str] = []
    for tok in tokens:
        # Avoid mangling words that end with double consonants like "glass"
        if len(tok) > 3 and tok.endswith('es') and not tok.endswith('sses') and not tok.endswith('ss'):
            stripped.append(tok[:-2])
        elif len(tok) > 2 and tok.endswith('s') and not tok.endswith('ss'):
            stripped.append(tok[:-1])
        else:
            stripped.append(tok)
    return ' '.join(stripped).strip()


def _normalize_name_for_fuzzy(name: str) -> str:
    """Produce a fuzzier form that keeps alphanumerics and apostrophes for n-gram shingles."""
    normalized = re.sub(r"[^a-z0-9' ]", ' ', _normalize_string_exact(name))
    normalized = normalized.strip()
    return re.sub(r'[\s]+', ' ', normalized)


def _name_entropy(normalized_name: str) -> float:
    """Approximate text specificity using Shannon entropy over characters.

    We strip spaces, count how often each character appears, and sum
    probability * -log2(probability). Short or repetitive names yield low
    entropy, which signals we should defer resolution to the LLM instead of
    trusting fuzzy similarity.
    """
    if not normalized_name:
        return 0.0

    counts: dict[str, int] = {}
    for char in normalized_name.replace(' ', ''):
        counts[char] = counts.get(char, 0) + 1

    total = sum(counts.values())
    if total == 0:
        return 0.0

    entropy = 0.0
    for count in counts.values():
        probability = count / total
        entropy -= probability * math.log2(probability)

    return entropy


def _has_high_entropy(normalized_name: str) -> bool:
    """Filter out very short or low-entropy names that are unreliable for fuzzy matching."""
    token_count = len(normalized_name.split())
    if len(normalized_name) < _MIN_NAME_LENGTH and token_count < _MIN_TOKEN_COUNT:
        return False

    return _name_entropy(normalized_name) >= _NAME_ENTROPY_THRESHOLD


def _shingles(normalized_name: str) -> set[str]:
    """Create 3-gram shingles from the normalized name for MinHash calculations."""
    cleaned = normalized_name.replace(' ', '')
    if len(cleaned) < 2:
        return {cleaned} if cleaned else set()

    return {cleaned[i : i + 3] for i in range(len(cleaned) - 2)}


def _hash_shingle(shingle: str, seed: int) -> int:
    """Generate a deterministic 64-bit hash for a shingle given the permutation seed."""
    digest = blake2b(f'{seed}:{shingle}'.encode(), digest_size=8)
    return int.from_bytes(digest.digest(), 'big')


def _minhash_signature(shingles: Iterable[str]) -> tuple[int, ...]:
    """Compute the MinHash signature for the shingle set across predefined permutations."""
    if not shingles:
        return tuple()

    seeds = range(_MINHASH_PERMUTATIONS)
    signature: list[int] = []
    for seed in seeds:
        min_hash = min(_hash_shingle(shingle, seed) for shingle in shingles)
        signature.append(min_hash)

    return tuple(signature)


def _lsh_bands(signature: Iterable[int]) -> list[tuple[int, ...]]:
    """Split the MinHash signature into fixed-size bands for locality-sensitive hashing."""
    signature_list = list(signature)
    if not signature_list:
        return []

    bands: list[tuple[int, ...]] = []
    for start in range(0, len(signature_list), _MINHASH_BAND_SIZE):
        band = tuple(signature_list[start : start + _MINHASH_BAND_SIZE])
        if len(band) == _MINHASH_BAND_SIZE:
            bands.append(band)
    return bands


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Return the Jaccard similarity between two shingle sets, handling empty edge cases."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    intersection = len(a.intersection(b))
    union = len(a.union(b))
    return intersection / union if union else 0.0


@lru_cache(maxsize=512)
def _cached_shingles(name: str) -> set[str]:
    """Cache shingle sets per normalized name to avoid recomputation within a worker."""
    return _shingles(name)


@dataclass
class DedupCandidateIndexes:
    """Precomputed lookup structures that drive entity deduplication heuristics."""

    existing_nodes: list[EntityNode]
    nodes_by_uuid: dict[str, EntityNode]
    normalized_existing: defaultdict[str, list[EntityNode]]
    shingles_by_candidate: dict[str, set[str]]
    lsh_buckets: defaultdict[tuple[int, tuple[int, ...]], list[str]]


@dataclass
class DedupResolutionState:
    """Mutable resolution bookkeeping shared across deterministic and LLM passes."""

    resolved_nodes: list[EntityNode | None]
    uuid_map: dict[str, str]
    unresolved_indices: list[int]
    duplicate_pairs: list[tuple[EntityNode, EntityNode]] = field(default_factory=list)
    merge_stage: dict[str, str] = field(default_factory=dict)


def _build_candidate_indexes(existing_nodes: list[EntityNode]) -> DedupCandidateIndexes:
    """Precompute exact and fuzzy lookup structures once per dedupe run."""
    normalized_existing: defaultdict[str, list[EntityNode]] = defaultdict(list)
    nodes_by_uuid: dict[str, EntityNode] = {}
    shingles_by_candidate: dict[str, set[str]] = {}
    lsh_buckets: defaultdict[tuple[int, tuple[int, ...]], list[str]] = defaultdict(list)

    for candidate in existing_nodes:
        normalized = _normalize_string_exact(candidate.name)
        normalized_existing[normalized].append(candidate)
        deplural = _strip_plural(normalized)
        if deplural and deplural != normalized:
            normalized_existing[deplural].append(candidate)
        nodes_by_uuid[candidate.uuid] = candidate

        shingles = _cached_shingles(_normalize_name_for_fuzzy(candidate.name))
        shingles_by_candidate[candidate.uuid] = shingles

        signature = _minhash_signature(shingles)
        for band_index, band in enumerate(_lsh_bands(signature)):
            lsh_buckets[(band_index, band)].append(candidate.uuid)

    return DedupCandidateIndexes(
        existing_nodes=existing_nodes,
        nodes_by_uuid=nodes_by_uuid,
        normalized_existing=normalized_existing,
        shingles_by_candidate=shingles_by_candidate,
        lsh_buckets=lsh_buckets,
    )


def _resolve_with_similarity(
    extracted_nodes: list[EntityNode],
    indexes: DedupCandidateIndexes,
    state: DedupResolutionState,
) -> None:
    """Attempt deterministic resolution using exact name hits and fuzzy MinHash comparisons."""
    for idx, node in enumerate(extracted_nodes):
        normalized_exact = _normalize_string_exact(node.name)
        normalized_deplural = _strip_plural(normalized_exact)
        normalized_fuzzy = _normalize_name_for_fuzzy(node.name)

        exact_candidates: list[EntityNode] = []
        exact_candidates.extend(indexes.normalized_existing.get(normalized_exact, []))
        if normalized_deplural and normalized_deplural != normalized_exact:
            exact_candidates.extend(indexes.normalized_existing.get(normalized_deplural, []))

        if exact_candidates:
            # Deterministic choice: smallest UUID among candidates that pass safeguards.
            chosen: EntityNode | None = None
            chosen_stage: str = 'exact'
            for cand in sorted(exact_candidates, key=lambda c: c.uuid):
                merge_ok, stage = _should_merge_exact(node, cand)
                if not merge_ok:
                    continue
                chosen = cand
                chosen_stage = stage or 'exact'
                break
            if chosen is not None:
                state.resolved_nodes[idx] = chosen
                state.uuid_map[node.uuid] = chosen.uuid
                state.merge_stage[node.uuid] = chosen_stage
                if chosen.uuid != node.uuid:
                    state.duplicate_pairs.append((node, chosen))
                logger.debug(
                    'dedupe_exact name=%s alias=%s canonical=%s stage=%s',
                    node.name,
                    node.uuid,
                    chosen.uuid,
                    chosen_stage,
                )
                continue
            # No candidate passed safeguards -> defer to LLM
            state.unresolved_indices.append(idx)
            continue

        if not _has_high_entropy(normalized_fuzzy):
            state.unresolved_indices.append(idx)
            continue

        shingles = _cached_shingles(normalized_fuzzy)
        signature = _minhash_signature(shingles)
        candidate_ids: set[str] = set()
        for band_index, band in enumerate(_lsh_bands(signature)):
            candidate_ids.update(indexes.lsh_buckets.get((band_index, band), []))

        best_candidate: EntityNode | None = None
        best_score = 0.0
        for candidate_id in candidate_ids:
            candidate_shingles = indexes.shingles_by_candidate.get(candidate_id, set())
            score = _jaccard_similarity(shingles, candidate_shingles)
            if score > best_score:
                best_score = score
                best_candidate = indexes.nodes_by_uuid.get(candidate_id)

        if best_candidate is not None and best_score >= _FUZZY_JACCARD_THRESHOLD:
            state.resolved_nodes[idx] = best_candidate
            state.uuid_map[node.uuid] = best_candidate.uuid
            state.merge_stage[node.uuid] = 'fuzzy'
            if best_candidate.uuid != node.uuid:
                state.duplicate_pairs.append((node, best_candidate))
            continue

        state.unresolved_indices.append(idx)


@functools.lru_cache(maxsize=1)
def _geo_hint_sets() -> tuple[set[str], set[str]]:
    """Load country and subdivision name sets, using pycountry if available."""
    countries: set[str] = set()
    subdivisions: set[str] = set()
    if pycountry:
        try:
            for c in pycountry.countries:
                countries.add(c.name.lower())
                if getattr(c, 'official_name', None):
                    countries.add(c.official_name.lower())
                if getattr(c, 'alpha_2', None):
                    countries.add(c.alpha_2.lower())
                if getattr(c, 'alpha_3', None):
                    countries.add(c.alpha_3.lower())
            for s in pycountry.subdivisions:
                subdivisions.add(s.name.lower())
        except Exception:
            pass
    if not countries:
        countries.update({'france', 'united states', 'usa', 'mexico', 'canada', 'uk', 'england'})
    if not subdivisions:
        subdivisions.update({'texas', 'california', 'ile-de-france'})
    return countries, subdivisions


def _has_label(node: 'EntityNode', label: str) -> bool:
    return label in getattr(node, 'labels', [])


def _extract_geo_hints(node: 'EntityNode') -> set[str]:
    hints: set[str] = set()
    attrs = getattr(node, 'attributes', {}) or {}
    for key in ('country', 'state', 'region', 'location_name'):
        val = attrs.get(key)
        if isinstance(val, str):
            hints.add(val.lower())
    summary = getattr(node, 'summary', '') or ''
    text = summary.lower()
    countries, subs = _geo_hint_sets()
    for token in re.split(r'[^a-z0-9]+', text):
        if token in countries or token in subs:
            hints.add(token)
    return hints


def _extract_people_hint(node: 'EntityNode') -> str | None:
    attrs = getattr(node, 'attributes', {}) or {}
    person_name = attrs.get('person_name')
    if isinstance(person_name, str):
        return person_name.strip().lower()
    return None


def _extract_institution_hint(node: 'EntityNode') -> str | None:
    attrs = getattr(node, 'attributes', {}) or {}
    inst_name = attrs.get('institution_name')
    if isinstance(inst_name, str):
        return inst_name.strip().lower()
    return None


@functools.lru_cache(maxsize=1)
def _load_ror_index() -> dict[str, set[str]]:
    """Load a local ROR cache (fully offline)."""
    index: dict[str, set[str]] = {}
    cache_path_str = os.getenv('ROR_CACHE_FILE')
    if not cache_path_str:
        logger.debug('ROR cache not used: ROR_CACHE_FILE not set')
        return index
    cache_path = Path(cache_path_str)
    if not cache_path.exists():
        logger.warning('ROR cache file not found at %s; skipping ROR-based institution dedupe', cache_path)
        return index

    def _add(name: str, ror_id: str):
        key = _normalize_string_exact(name)
        if not key:
            return
        index.setdefault(key, set()).add(ror_id)

    try:
        if cache_path.suffix.lower() == '.zip':
            with zipfile.ZipFile(cache_path) as zf:
                json_name = next((z for z in zf.namelist() if z.endswith('.json')), None)
                if json_name is None:
                    return index
                with zf.open(json_name) as f:
                    data = json.load(f)
        else:
            with cache_path.open() as f:
                data = json.load(f)

        for org in data:
            ror_id = org.get('id')
            names = org.get('names') or []
            for name_entry in names:
                val = name_entry.get('value')
                if val:
                    _add(val, ror_id)
        logger.info('Loaded ROR cache with %d name entries from %s', len(index), cache_path)
        return index
    except Exception:
        logger.warning('Failed to load ROR cache from %s; skipping ROR-based dedupe', cache_path)
        return {}


def _ror_ids_for_name(name: str) -> set[str]:
    idx = _load_ror_index()
    return idx.get(_normalize_string_exact(name), set())


def _should_merge_exact(node: 'EntityNode', match: 'EntityNode') -> tuple[bool, str]:
    """Apply type-specific safeguards before auto-merging exact-name duplicates."""
    if _has_label(node, 'Location') or _has_label(match, 'Location'):
        hints_a = _extract_geo_hints(node)
        hints_b = _extract_geo_hints(match)
        if hints_a and hints_b:
            return (not hints_a.isdisjoint(hints_b), 'exact_geo')
        # If only one side has geo hints, allow the merge (still an exact-name match) but tag it.
        if hints_a or hints_b:
            return True, 'exact_geo_hint_partial'
        return True, 'exact_geo'

    if _has_label(node, 'People') or _has_label(match, 'People'):
        hint_a = _extract_people_hint(node)
        hint_b = _extract_people_hint(match)
        if hint_a and hint_b:
            return (hint_a == hint_b, 'exact_people' if hint_a == hint_b else '')
        # If one side lacks person_name, still merge exact names.
        return True, 'exact_people'

    if _has_label(node, 'Institution') or _has_label(match, 'Institution'):
        ror_a = _ror_ids_for_name(node.name)
        ror_b = _ror_ids_for_name(match.name)
        if ror_a and ror_b:
            if not ror_a.isdisjoint(ror_b):
                return True, 'exact_ror'
            return False, ''
        if ror_a or ror_b:
            return True, 'exact_ror_partial'
        hint_a = _extract_institution_hint(node)
        hint_b = _extract_institution_hint(match)
        if hint_a and hint_b:
            return (hint_a == hint_b, 'exact_institution' if hint_a == hint_b else '')
        if hint_a or hint_b:
            return True, 'exact_institution_partial'
        return True, 'exact'

    return True, 'exact'


__all__ = [
    'DedupCandidateIndexes',
    'DedupResolutionState',
    '_normalize_string_exact',
    '_normalize_name_for_fuzzy',
    '_has_high_entropy',
    '_minhash_signature',
    '_lsh_bands',
    '_jaccard_similarity',
    '_cached_shingles',
    '_FUZZY_JACCARD_THRESHOLD',
    '_build_candidate_indexes',
    '_resolve_with_similarity',
]


#v2 updated version
# from __future__ import annotations

# import functools
# import json
# import logging
# import math
# import os
# import re
# import zipfile
# from collections import defaultdict
# from collections.abc import Iterable
# from dataclasses import dataclass, field
# from functools import lru_cache
# from hashlib import blake2b
# from pathlib import Path
# from typing import TYPE_CHECKING, Iterable as TypingIterable

# if TYPE_CHECKING:
#     from graphiti_core.nodes import EntityNode

# _NAME_ENTROPY_THRESHOLD = 1.5
# _MIN_NAME_LENGTH = 6
# _MIN_TOKEN_COUNT = 2
# _FUZZY_JACCARD_THRESHOLD = 0.9
# _MINHASH_PERMUTATIONS = 32
# _MINHASH_BAND_SIZE = 4

# logger = logging.getLogger(__name__)
# try:
#     import pycountry  # type: ignore
# except Exception:
#     pycountry = None


# def _normalize_string_exact(name: str) -> str:
#     """Lowercase text and collapse whitespace so equal names map to the same key."""
#     normalized = re.sub(r'[\s]+', ' ', name.lower())
#     return normalized.strip()


# def _strip_plural(normalized: str) -> str:
#     """Best-effort singularization for exact matching (simple s/es stripping)."""
#     if not normalized:
#         return normalized
#     tokens = normalized.split()
#     stripped: list[str] = []
#     for tok in tokens:
#         if len(tok) > 3 and tok.endswith('es'):
#             stripped.append(tok[:-2])
#         elif len(tok) > 2 and tok.endswith('s'):
#             stripped.append(tok[:-1])
#         else:
#             stripped.append(tok)
#     return ' '.join(stripped).strip()


# def _normalize_name_for_fuzzy(name: str) -> str:
#     """Produce a fuzzier form that keeps alphanumerics and apostrophes for n-gram shingles."""
#     normalized = re.sub(r"[^a-z0-9' ]", ' ', _normalize_string_exact(name))
#     normalized = normalized.strip()
#     return re.sub(r'[\s]+', ' ', normalized)


# def _name_entropy(normalized_name: str) -> float:
#     """Approximate text specificity using Shannon entropy over characters.

#     We strip spaces, count how often each character appears, and sum
#     probability * -log2(probability). Short or repetitive names yield low
#     entropy, which signals we should defer resolution to the LLM instead of
#     trusting fuzzy similarity.
#     """
#     if not normalized_name:
#         return 0.0

#     counts: dict[str, int] = {}
#     for char in normalized_name.replace(' ', ''):
#         counts[char] = counts.get(char, 0) + 1

#     total = sum(counts.values())
#     if total == 0:
#         return 0.0

#     entropy = 0.0
#     for count in counts.values():
#         probability = count / total
#         entropy -= probability * math.log2(probability)

#     return entropy


# def _has_high_entropy(normalized_name: str) -> bool:
#     """Filter out very short or low-entropy names that are unreliable for fuzzy matching."""
#     token_count = len(normalized_name.split())
#     if len(normalized_name) < _MIN_NAME_LENGTH and token_count < _MIN_TOKEN_COUNT:
#         return False

#     return _name_entropy(normalized_name) >= _NAME_ENTROPY_THRESHOLD


# def _shingles(normalized_name: str) -> set[str]:
#     """Create 3-gram shingles from the normalized name for MinHash calculations."""
#     cleaned = normalized_name.replace(' ', '')
#     if len(cleaned) < 2:
#         return {cleaned} if cleaned else set()

#     return {cleaned[i : i + 3] for i in range(len(cleaned) - 2)}


# def _hash_shingle(shingle: str, seed: int) -> int:
#     """Generate a deterministic 64-bit hash for a shingle given the permutation seed."""
#     digest = blake2b(f'{seed}:{shingle}'.encode(), digest_size=8)
#     return int.from_bytes(digest.digest(), 'big')


# def _minhash_signature(shingles: Iterable[str]) -> tuple[int, ...]:
#     """Compute the MinHash signature for the shingle set across predefined permutations."""
#     if not shingles:
#         return tuple()

#     seeds = range(_MINHASH_PERMUTATIONS)
#     signature: list[int] = []
#     for seed in seeds:
#         min_hash = min(_hash_shingle(shingle, seed) for shingle in shingles)
#         signature.append(min_hash)

#     return tuple(signature)


# def _lsh_bands(signature: Iterable[int]) -> list[tuple[int, ...]]:
#     """Split the MinHash signature into fixed-size bands for locality-sensitive hashing."""
#     signature_list = list(signature)
#     if not signature_list:
#         return []

#     bands: list[tuple[int, ...]] = []
#     for start in range(0, len(signature_list), _MINHASH_BAND_SIZE):
#         band = tuple(signature_list[start : start + _MINHASH_BAND_SIZE])
#         if len(band) == _MINHASH_BAND_SIZE:
#             bands.append(band)
#     return bands


# def _jaccard_similarity(a: set[str], b: set[str]) -> float:
#     """Return the Jaccard similarity between two shingle sets, handling empty edge cases."""
#     if not a and not b:
#         return 1.0
#     if not a or not b:
#         return 0.0

#     intersection = len(a.intersection(b))
#     union = len(a.union(b))
#     return intersection / union if union else 0.0


# @lru_cache(maxsize=512)
# def _cached_shingles(name: str) -> set[str]:
#     """Cache shingle sets per normalized name to avoid recomputation within a worker."""
#     return _shingles(name)


# @dataclass
# class DedupCandidateIndexes:
#     """Precomputed lookup structures that drive entity deduplication heuristics."""

#     existing_nodes: list[EntityNode]
#     nodes_by_uuid: dict[str, EntityNode]
#     normalized_existing: defaultdict[str, list[EntityNode]]
#     shingles_by_candidate: dict[str, set[str]]
#     lsh_buckets: defaultdict[tuple[int, tuple[int, ...]], list[str]]


# @dataclass
# class DedupResolutionState:
#     """Mutable resolution bookkeeping shared across deterministic and LLM passes."""

#     resolved_nodes: list[EntityNode | None]
#     uuid_map: dict[str, str]
#     unresolved_indices: list[int]
#     duplicate_pairs: list[tuple[EntityNode, EntityNode]] = field(default_factory=list)
#     merge_stage: dict[str, str] = field(default_factory=dict)


# def _build_candidate_indexes(existing_nodes: list[EntityNode]) -> DedupCandidateIndexes:
#     """Precompute exact and fuzzy lookup structures once per dedupe run."""
#     normalized_existing: defaultdict[str, list[EntityNode]] = defaultdict(list)
#     nodes_by_uuid: dict[str, EntityNode] = {}
#     shingles_by_candidate: dict[str, set[str]] = {}
#     lsh_buckets: defaultdict[tuple[int, tuple[int, ...]], list[str]] = defaultdict(list)

#     for candidate in existing_nodes:
#         normalized = _normalize_string_exact(candidate.name)
#         normalized_existing[normalized].append(candidate)
#         deplural = _strip_plural(normalized)
#         if deplural and deplural != normalized:
#             normalized_existing[deplural].append(candidate)
#         nodes_by_uuid[candidate.uuid] = candidate

#         shingles = _cached_shingles(_normalize_name_for_fuzzy(candidate.name))
#         shingles_by_candidate[candidate.uuid] = shingles

#         signature = _minhash_signature(shingles)
#         for band_index, band in enumerate(_lsh_bands(signature)):
#             lsh_buckets[(band_index, band)].append(candidate.uuid)

#     return DedupCandidateIndexes(
#         existing_nodes=existing_nodes,
#         nodes_by_uuid=nodes_by_uuid,
#         normalized_existing=normalized_existing,
#         shingles_by_candidate=shingles_by_candidate,
#         lsh_buckets=lsh_buckets,
#     )


# def _resolve_with_similarity(
#     extracted_nodes: list[EntityNode],
#     indexes: DedupCandidateIndexes,
#     state: DedupResolutionState,
# ) -> None:
#     """Attempt deterministic resolution using exact name hits and fuzzy MinHash comparisons."""
#     for idx, node in enumerate(extracted_nodes):
#         normalized_exact = _normalize_string_exact(node.name)
#         normalized_deplural = _strip_plural(normalized_exact)
#         normalized_fuzzy = _normalize_name_for_fuzzy(node.name)

#         exact_candidates: list[EntityNode] = []
#         exact_candidates.extend(indexes.normalized_existing.get(normalized_exact, []))
#         if normalized_deplural and normalized_deplural != normalized_exact:
#             exact_candidates.extend(indexes.normalized_existing.get(normalized_deplural, []))

#         if exact_candidates:
#             # Deterministic choice: smallest UUID among candidates that pass safeguards.
#             chosen: EntityNode | None = None
#             chosen_stage: str = 'exact'
#             for cand in sorted(exact_candidates, key=lambda c: c.uuid):
#                 merge_ok, stage = _should_merge_exact(node, cand)
#                 if not merge_ok:
#                     continue
#                 chosen = cand
#                 chosen_stage = stage or 'exact'
#                 break
#             if chosen is not None:
#                 state.resolved_nodes[idx] = chosen
#                 state.uuid_map[node.uuid] = chosen.uuid
#                 state.merge_stage[node.uuid] = chosen_stage
#                 if chosen.uuid != node.uuid:
#                     state.duplicate_pairs.append((node, chosen))
#                 logger.debug(
#                     'dedupe_exact name=%s alias=%s canonical=%s stage=%s',
#                     node.name,
#                     node.uuid,
#                     chosen.uuid,
#                     chosen_stage,
#                 )
#                 continue
#             # No candidate passed safeguards -> defer to LLM
#             state.unresolved_indices.append(idx)
#             continue

#         if not _has_high_entropy(normalized_fuzzy):
#             state.unresolved_indices.append(idx)
#             continue

#         shingles = _cached_shingles(normalized_fuzzy)
#         signature = _minhash_signature(shingles)
#         candidate_ids: set[str] = set()
#         for band_index, band in enumerate(_lsh_bands(signature)):
#             candidate_ids.update(indexes.lsh_buckets.get((band_index, band), []))

#         best_candidate: EntityNode | None = None
#         best_score = 0.0
#         for candidate_id in candidate_ids:
#             candidate_shingles = indexes.shingles_by_candidate.get(candidate_id, set())
#             score = _jaccard_similarity(shingles, candidate_shingles)
#             if score > best_score:
#                 best_score = score
#                 best_candidate = indexes.nodes_by_uuid.get(candidate_id)

#         if best_candidate is not None and best_score >= _FUZZY_JACCARD_THRESHOLD:
#             state.resolved_nodes[idx] = best_candidate
#             state.uuid_map[node.uuid] = best_candidate.uuid
#             state.merge_stage[node.uuid] = 'fuzzy'
#             if best_candidate.uuid != node.uuid:
#                 state.duplicate_pairs.append((node, best_candidate))
#             continue

#         state.unresolved_indices.append(idx)


# @functools.lru_cache(maxsize=1)
# def _geo_hint_sets() -> tuple[set[str], set[str]]:
#     """Load country and subdivision name sets, using pycountry if available."""
#     countries: set[str] = set()
#     subdivisions: set[str] = set()
#     if pycountry:
#         try:
#             for c in pycountry.countries:
#                 countries.add(c.name.lower())
#                 if getattr(c, 'official_name', None):
#                     countries.add(c.official_name.lower())
#                 if getattr(c, 'alpha_2', None):
#                     countries.add(c.alpha_2.lower())
#                 if getattr(c, 'alpha_3', None):
#                     countries.add(c.alpha_3.lower())
#             for s in pycountry.subdivisions:
#                 subdivisions.add(s.name.lower())
#         except Exception:
#             pass
#     if not countries:
#         countries.update({'france', 'united states', 'usa', 'mexico', 'canada', 'uk', 'england'})
#     if not subdivisions:
#         subdivisions.update({'texas', 'california', 'ile-de-france'})
#     return countries, subdivisions


# def _has_label(node: 'EntityNode', label: str) -> bool:
#     return label in getattr(node, 'labels', [])


# def _extract_geo_hints(node: 'EntityNode') -> set[str]:
#     hints: set[str] = set()
#     attrs = getattr(node, 'attributes', {}) or {}
#     for key in ('country', 'state', 'region', 'location_name'):
#         val = attrs.get(key)
#         if isinstance(val, str):
#             hints.add(val.lower())
#     summary = getattr(node, 'summary', '') or ''
#     text = summary.lower()
#     countries, subs = _geo_hint_sets()
#     for token in re.split(r'[^a-z0-9]+', text):
#         if token in countries or token in subs:
#             hints.add(token)
#     return hints


# def _extract_people_hint(node: 'EntityNode') -> str | None:
#     attrs = getattr(node, 'attributes', {}) or {}
#     person_name = attrs.get('person_name')
#     if isinstance(person_name, str):
#         return person_name.strip().lower()
#     return None


# def _extract_institution_hint(node: 'EntityNode') -> str | None:
#     attrs = getattr(node, 'attributes', {}) or {}
#     inst_name = attrs.get('institution_name')
#     if isinstance(inst_name, str):
#         return inst_name.strip().lower()
#     return None


# @functools.lru_cache(maxsize=1)
# def _load_ror_index() -> dict[str, set[str]]:
#     """Load a local ROR cache (fully offline)."""
#     index: dict[str, set[str]] = {}
#     cache_path_str = os.getenv('ROR_CACHE_FILE')
#     if not cache_path_str:
#         logger.debug('ROR cache not used: ROR_CACHE_FILE not set')
#         return index
#     cache_path = Path(cache_path_str)
#     if not cache_path.exists():
#         logger.warning('ROR cache file not found at %s; skipping ROR-based institution dedupe', cache_path)
#         return index

#     def _add(name: str, ror_id: str):
#         key = _normalize_string_exact(name)
#         if not key:
#             return
#         index.setdefault(key, set()).add(ror_id)

#     try:
#         if cache_path.suffix.lower() == '.zip':
#             with zipfile.ZipFile(cache_path) as zf:
#                 json_name = next((z for z in zf.namelist() if z.endswith('.json')), None)
#                 if json_name is None:
#                     return index
#                 with zf.open(json_name) as f:
#                     data = json.load(f)
#         else:
#             with cache_path.open() as f:
#                 data = json.load(f)

#         for org in data:
#             ror_id = org.get('id')
#             names = org.get('names') or []
#             for name_entry in names:
#                 val = name_entry.get('value')
#                 if val:
#                     _add(val, ror_id)
#         logger.info('Loaded ROR cache with %d name entries from %s', len(index), cache_path)
#         return index
#     except Exception:
#         logger.warning('Failed to load ROR cache from %s; skipping ROR-based dedupe', cache_path)
#         return {}


# def _ror_ids_for_name(name: str) -> set[str]:
#     idx = _load_ror_index()
#     return idx.get(_normalize_string_exact(name), set())


# def _should_merge_exact(node: 'EntityNode', match: 'EntityNode') -> tuple[bool, str]:
#     """Apply type-specific safeguards before auto-merging exact-name duplicates."""
#     if _has_label(node, 'Location') or _has_label(match, 'Location'):
#         hints_a = _extract_geo_hints(node)
#         hints_b = _extract_geo_hints(match)
#         if hints_a and hints_b:
#             return (not hints_a.isdisjoint(hints_b), 'exact_geo')
#         # If only one side has geo hints, allow the merge (still an exact-name match) but tag it.
#         if hints_a or hints_b:
#             return True, 'exact_geo_hint_partial'
#         return True, 'exact_geo'

#     if _has_label(node, 'People') or _has_label(match, 'People'):
#         hint_a = _extract_people_hint(node)
#         hint_b = _extract_people_hint(match)
#         if hint_a and hint_b:
#             return (hint_a == hint_b, 'exact_people' if hint_a == hint_b else '')
#         # If one side lacks person_name, still merge exact names.
#         return True, 'exact_people'

#     if _has_label(node, 'Institution') or _has_label(match, 'Institution'):
#         ror_a = _ror_ids_for_name(node.name)
#         ror_b = _ror_ids_for_name(match.name)
#         if ror_a and ror_b:
#             if not ror_a.isdisjoint(ror_b):
#                 return True, 'exact_ror'
#             return False, ''
#         if ror_a or ror_b:
#             return True, 'exact_ror_partial'
#         hint_a = _extract_institution_hint(node)
#         hint_b = _extract_institution_hint(match)
#         if hint_a and hint_b:
#             return (hint_a == hint_b, 'exact_institution' if hint_a == hint_b else '')
#         if hint_a or hint_b:
#             return True, 'exact_institution_partial'
#         return True, 'exact'

#     return True, 'exact'


# __all__ = [
#     'DedupCandidateIndexes',
#     'DedupResolutionState',
#     '_normalize_string_exact',
#     '_normalize_name_for_fuzzy',
#     '_has_high_entropy',
#     '_minhash_signature',
#     '_lsh_bands',
#     '_jaccard_similarity',
#     '_cached_shingles',
#     '_FUZZY_JACCARD_THRESHOLD',
#     '_build_candidate_indexes',
#     '_resolve_with_similarity',
# ]





#v1-Base version


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

# from __future__ import annotations

# import functools
# import json
# import logging
# import math
# import os
# import re
# import zipfile
# from collections import defaultdict
# from collections.abc import Iterable
# from dataclasses import dataclass, field
# from functools import lru_cache
# from hashlib import blake2b
# from pathlib import Path
# from typing import TYPE_CHECKING, Iterable as TypingIterable

# if TYPE_CHECKING:
#     from graphiti_core.nodes import EntityNode

# _NAME_ENTROPY_THRESHOLD = 1.5
# _MIN_NAME_LENGTH = 6
# _MIN_TOKEN_COUNT = 2
# _FUZZY_JACCARD_THRESHOLD = 0.9
# _MINHASH_PERMUTATIONS = 32
# _MINHASH_BAND_SIZE = 4

# logger = logging.getLogger(__name__)
# try:
#     import pycountry  # type: ignore
# except Exception:
#     pycountry = None


# def _normalize_string_exact(name: str) -> str:
#     """Lowercase text and collapse whitespace so equal names map to the same key."""
#     normalized = re.sub(r'[\s]+', ' ', name.lower())
#     return normalized.strip()


# def _normalize_name_for_fuzzy(name: str) -> str:
#     """Produce a fuzzier form that keeps alphanumerics and apostrophes for n-gram shingles."""
#     normalized = re.sub(r"[^a-z0-9' ]", ' ', _normalize_string_exact(name))
#     normalized = normalized.strip()
#     return re.sub(r'[\s]+', ' ', normalized)


# def _name_entropy(normalized_name: str) -> float:
#     """Approximate text specificity using Shannon entropy over characters.

#     We strip spaces, count how often each character appears, and sum
#     probability * -log2(probability). Short or repetitive names yield low
#     entropy, which signals we should defer resolution to the LLM instead of
#     trusting fuzzy similarity.
#     """
#     if not normalized_name:
#         return 0.0

#     counts: dict[str, int] = {}
#     for char in normalized_name.replace(' ', ''):
#         counts[char] = counts.get(char, 0) + 1

#     total = sum(counts.values())
#     if total == 0:
#         return 0.0

#     entropy = 0.0
#     for count in counts.values():
#         probability = count / total
#         entropy -= probability * math.log2(probability)

#     return entropy


# def _has_high_entropy(normalized_name: str) -> bool:
#     """Filter out very short or low-entropy names that are unreliable for fuzzy matching."""
#     token_count = len(normalized_name.split())
#     if len(normalized_name) < _MIN_NAME_LENGTH and token_count < _MIN_TOKEN_COUNT:
#         return False

#     return _name_entropy(normalized_name) >= _NAME_ENTROPY_THRESHOLD


# def _shingles(normalized_name: str) -> set[str]:
#     """Create 3-gram shingles from the normalized name for MinHash calculations."""
#     cleaned = normalized_name.replace(' ', '')
#     if len(cleaned) < 2:
#         return {cleaned} if cleaned else set()

#     return {cleaned[i : i + 3] for i in range(len(cleaned) - 2)}


# def _hash_shingle(shingle: str, seed: int) -> int:
#     """Generate a deterministic 64-bit hash for a shingle given the permutation seed."""
#     digest = blake2b(f'{seed}:{shingle}'.encode(), digest_size=8)
#     return int.from_bytes(digest.digest(), 'big')


# def _minhash_signature(shingles: Iterable[str]) -> tuple[int, ...]:
#     """Compute the MinHash signature for the shingle set across predefined permutations."""
#     if not shingles:
#         return tuple()

#     seeds = range(_MINHASH_PERMUTATIONS)
#     signature: list[int] = []
#     for seed in seeds:
#         min_hash = min(_hash_shingle(shingle, seed) for shingle in shingles)
#         signature.append(min_hash)

#     return tuple(signature)


# def _lsh_bands(signature: Iterable[int]) -> list[tuple[int, ...]]:
#     """Split the MinHash signature into fixed-size bands for locality-sensitive hashing."""
#     signature_list = list(signature)
#     if not signature_list:
#         return []

#     bands: list[tuple[int, ...]] = []
#     for start in range(0, len(signature_list), _MINHASH_BAND_SIZE):
#         band = tuple(signature_list[start : start + _MINHASH_BAND_SIZE])
#         if len(band) == _MINHASH_BAND_SIZE:
#             bands.append(band)
#     return bands


# def _jaccard_similarity(a: set[str], b: set[str]) -> float:
#     """Return the Jaccard similarity between two shingle sets, handling empty edge cases."""
#     if not a and not b:
#         return 1.0
#     if not a or not b:
#         return 0.0

#     intersection = len(a.intersection(b))
#     union = len(a.union(b))
#     return intersection / union if union else 0.0


# @lru_cache(maxsize=512)
# def _cached_shingles(name: str) -> set[str]:
#     """Cache shingle sets per normalized name to avoid recomputation within a worker."""
#     return _shingles(name)


# @dataclass
# class DedupCandidateIndexes:
#     """Precomputed lookup structures that drive entity deduplication heuristics."""

#     existing_nodes: list[EntityNode]
#     nodes_by_uuid: dict[str, EntityNode]
#     normalized_existing: defaultdict[str, list[EntityNode]]
#     shingles_by_candidate: dict[str, set[str]]
#     lsh_buckets: defaultdict[tuple[int, tuple[int, ...]], list[str]]


# @dataclass
# class DedupResolutionState:
#     """Mutable resolution bookkeeping shared across deterministic and LLM passes."""

#     resolved_nodes: list[EntityNode | None]
#     uuid_map: dict[str, str]
#     unresolved_indices: list[int]
#     duplicate_pairs: list[tuple[EntityNode, EntityNode]] = field(default_factory=list)
#     merge_stage: dict[str, str] = field(default_factory=dict)


# def _build_candidate_indexes(existing_nodes: list[EntityNode]) -> DedupCandidateIndexes:
#     """Precompute exact and fuzzy lookup structures once per dedupe run."""
#     normalized_existing: defaultdict[str, list[EntityNode]] = defaultdict(list)
#     nodes_by_uuid: dict[str, EntityNode] = {}
#     shingles_by_candidate: dict[str, set[str]] = {}
#     lsh_buckets: defaultdict[tuple[int, tuple[int, ...]], list[str]] = defaultdict(list)

#     for candidate in existing_nodes:
#         normalized = _normalize_string_exact(candidate.name)
#         normalized_existing[normalized].append(candidate)
#         nodes_by_uuid[candidate.uuid] = candidate

#         shingles = _cached_shingles(_normalize_name_for_fuzzy(candidate.name))
#         shingles_by_candidate[candidate.uuid] = shingles

#         signature = _minhash_signature(shingles)
#         for band_index, band in enumerate(_lsh_bands(signature)):
#             lsh_buckets[(band_index, band)].append(candidate.uuid)

#     return DedupCandidateIndexes(
#         existing_nodes=existing_nodes,
#         nodes_by_uuid=nodes_by_uuid,
#         normalized_existing=normalized_existing,
#         shingles_by_candidate=shingles_by_candidate,
#         lsh_buckets=lsh_buckets,
#     )


# def _resolve_with_similarity(
#     extracted_nodes: list[EntityNode],
#     indexes: DedupCandidateIndexes,
#     state: DedupResolutionState,
# ) -> None:
#     """Attempt deterministic resolution using exact name hits and fuzzy MinHash comparisons."""
#     for idx, node in enumerate(extracted_nodes):
#         normalized_exact = _normalize_string_exact(node.name)
#         normalized_fuzzy = _normalize_name_for_fuzzy(node.name)

#         existing_matches = indexes.normalized_existing.get(normalized_exact, [])
#         if len(existing_matches) == 1:
#             match = existing_matches[0]
#             merge_ok, stage = _should_merge_exact(node, match)
#             if merge_ok:
#                 state.resolved_nodes[idx] = match
#                 state.uuid_map[node.uuid] = match.uuid
#                 state.merge_stage[node.uuid] = stage or 'exact'
#                 if match.uuid != node.uuid:
#                     state.duplicate_pairs.append((node, match))
#                 logger.debug(
#                     'dedupe_exact name=%s alias=%s canonical=%s stage=%s',
#                     node.name,
#                     node.uuid,
#                     match.uuid,
#                     stage or 'exact',
#                 )
#             else:
#                 state.unresolved_indices.append(idx)
#             continue
#         if len(existing_matches) > 1:
#             state.unresolved_indices.append(idx)
#             continue

#         if not _has_high_entropy(normalized_fuzzy):
#             state.unresolved_indices.append(idx)
#             continue

#         shingles = _cached_shingles(normalized_fuzzy)
#         signature = _minhash_signature(shingles)
#         candidate_ids: set[str] = set()
#         for band_index, band in enumerate(_lsh_bands(signature)):
#             candidate_ids.update(indexes.lsh_buckets.get((band_index, band), []))

#         best_candidate: EntityNode | None = None
#         best_score = 0.0
#         for candidate_id in candidate_ids:
#             candidate_shingles = indexes.shingles_by_candidate.get(candidate_id, set())
#             score = _jaccard_similarity(shingles, candidate_shingles)
#             if score > best_score:
#                 best_score = score
#                 best_candidate = indexes.nodes_by_uuid.get(candidate_id)

#         if best_candidate is not None and best_score >= _FUZZY_JACCARD_THRESHOLD:
#             state.resolved_nodes[idx] = best_candidate
#             state.uuid_map[node.uuid] = best_candidate.uuid
#             state.merge_stage[node.uuid] = 'fuzzy'
#             if best_candidate.uuid != node.uuid:
#                 state.duplicate_pairs.append((node, best_candidate))
#             continue

#         state.unresolved_indices.append(idx)


# @functools.lru_cache(maxsize=1)
# def _geo_hint_sets() -> tuple[set[str], set[str]]:
#     """Load country and subdivision name sets, using pycountry if available."""
#     countries: set[str] = set()
#     subdivisions: set[str] = set()
#     if pycountry:
#         try:
#             for c in pycountry.countries:
#                 countries.add(c.name.lower())
#                 if getattr(c, 'official_name', None):
#                     countries.add(c.official_name.lower())
#                 if getattr(c, 'alpha_2', None):
#                     countries.add(c.alpha_2.lower())
#                 if getattr(c, 'alpha_3', None):
#                     countries.add(c.alpha_3.lower())
#             for s in pycountry.subdivisions:
#                 subdivisions.add(s.name.lower())
#         except Exception:
#             pass
#     if not countries:
#         countries.update({'france', 'united states', 'usa', 'mexico', 'canada', 'uk', 'england'})
#     if not subdivisions:
#         subdivisions.update({'texas', 'california', 'ile-de-france'})
#     return countries, subdivisions


# def _has_label(node: 'EntityNode', label: str) -> bool:
#     return label in getattr(node, 'labels', [])


# def _extract_geo_hints(node: 'EntityNode') -> set[str]:
#     hints: set[str] = set()
#     attrs = getattr(node, 'attributes', {}) or {}
#     for key in ('country', 'state', 'region', 'location_name'):
#         val = attrs.get(key)
#         if isinstance(val, str):
#             hints.add(val.lower())
#     summary = getattr(node, 'summary', '') or ''
#     text = summary.lower()
#     countries, subs = _geo_hint_sets()
#     for token in re.split(r'[^a-z0-9]+', text):
#         if token in countries or token in subs:
#             hints.add(token)
#     return hints


# def _extract_people_hint(node: 'EntityNode') -> str | None:
#     attrs = getattr(node, 'attributes', {}) or {}
#     person_name = attrs.get('person_name')
#     if isinstance(person_name, str):
#         return person_name.strip().lower()
#     return None


# def _extract_institution_hint(node: 'EntityNode') -> str | None:
#     attrs = getattr(node, 'attributes', {}) or {}
#     inst_name = attrs.get('institution_name')
#     if isinstance(inst_name, str):
#         return inst_name.strip().lower()
#     return None


# @functools.lru_cache(maxsize=1)
# def _load_ror_index() -> dict[str, set[str]]:
#     """Load a local ROR cache (fully offline)."""
#     index: dict[str, set[str]] = {}
#     cache_path_str = os.getenv('ROR_CACHE_FILE')
#     if not cache_path_str:
#         logger.debug('ROR cache not used: ROR_CACHE_FILE not set')
#         return index
#     cache_path = Path(cache_path_str)
#     if not cache_path.exists():
#         logger.warning('ROR cache file not found at %s; skipping ROR-based institution dedupe', cache_path)
#         return index

#     def _add(name: str, ror_id: str):
#         key = _normalize_string_exact(name)
#         if not key:
#             return
#         index.setdefault(key, set()).add(ror_id)

#     try:
#         if cache_path.suffix.lower() == '.zip':
#             with zipfile.ZipFile(cache_path) as zf:
#                 json_name = next((z for z in zf.namelist() if z.endswith('.json')), None)
#                 if json_name is None:
#                     return index
#                 with zf.open(json_name) as f:
#                     data = json.load(f)
#         else:
#             with cache_path.open() as f:
#                 data = json.load(f)

#         for org in data:
#             ror_id = org.get('id')
#             names = org.get('names') or []
#             for name_entry in names:
#                 val = name_entry.get('value')
#                 if val:
#                     _add(val, ror_id)
#         logger.info('Loaded ROR cache with %d name entries from %s', len(index), cache_path)
#         return index
#     except Exception:
#         logger.warning('Failed to load ROR cache from %s; skipping ROR-based dedupe', cache_path)
#         return {}


# def _ror_ids_for_name(name: str) -> set[str]:
#     idx = _load_ror_index()
#     return idx.get(_normalize_string_exact(name), set())


# def _should_merge_exact(node: 'EntityNode', match: 'EntityNode') -> tuple[bool, str]:
#     """Apply type-specific safeguards before auto-merging exact-name duplicates."""
#     if _has_label(node, 'Location') or _has_label(match, 'Location'):
#         hints_a = _extract_geo_hints(node)
#         hints_b = _extract_geo_hints(match)
#         if hints_a and hints_b:
#             return (not hints_a.isdisjoint(hints_b), 'exact_geo')
#         if (hints_a and not hints_b) or (hints_b and not hints_a):
#             return False, ''
#         return True, 'exact_geo'

#     if _has_label(node, 'People') or _has_label(match, 'People'):
#         hint_a = _extract_people_hint(node)
#         hint_b = _extract_people_hint(match)
#         if hint_a and hint_b:
#             return (hint_a == hint_b, 'exact_people' if hint_a == hint_b else '')
#         return False, ''

#     if _has_label(node, 'Institution') or _has_label(match, 'Institution'):
#         ror_a = _ror_ids_for_name(node.name)
#         ror_b = _ror_ids_for_name(match.name)
#         if ror_a and ror_b:
#             if not ror_a.isdisjoint(ror_b):
#                 return True, 'exact_ror'
#             return False, ''
#         hint_a = _extract_institution_hint(node)
#         hint_b = _extract_institution_hint(match)
#         if hint_a and hint_b:
#             return (hint_a == hint_b, 'exact_institution' if hint_a == hint_b else '')
#         return False, ''

#     return True, 'exact'


# __all__ = [
#     'DedupCandidateIndexes',
#     'DedupResolutionState',
#     '_normalize_string_exact',
#     '_normalize_name_for_fuzzy',
#     '_has_high_entropy',
#     '_minhash_signature',
#     '_lsh_bands',
#     '_jaccard_similarity',
#     '_cached_shingles',
#     '_FUZZY_JACCARD_THRESHOLD',
#     '_build_candidate_indexes',
#     '_resolve_with_similarity',
# ]
