# GOMGraph — LLM-Based Knowledge Graph Extraction from Historical Texts

> **Code by Manas Raaj × Pablo Sánchez Martín × Claude (Anthropic).**
> Research supervision: David Colliaux, Alessandra Toniato, Pablo Sánchez Martín — Sony CSL Paris and Sony AI.

End-to-end LLM-based knowledge-graph extraction pipeline applied to the **Good Old Manuals (GOM)** corpus — a collection of 19th- and early 20th-century French market-gardening manuals — built as part of a collaborative research initiative between Sony CSL Paris and Sony AI.

The system ingests multilingual long-form historical documents into a temporal knowledge graph in **FalkorDB** with episodic, semantic, and community memory tiers, using LLMs (LLaMA 3.1/3.3 70B, Mistral, Qwen 2.5, Mixtral, GPT-4) for entity and relation extraction, with embedding-based entity / edge deduplication and a custom prompt registry for reproducible experiments.

## Repository layout

| Path | Contents |
|---|---|
| [`agro_temporal_kg/`](./agro_temporal_kg) | **Main project** — pipeline, configs, entity ontology, prompt registry, dedup. See [`agro_temporal_kg/README.md`](./agro_temporal_kg/README.md) for full docs. |
| [`graphiti/`](./graphiti) | Vendored [Graphiti](https://github.com/getzep/graphiti) framework with runtime patches applied at startup (no fork). |
| [`dedup/`](./dedup) | Standalone deduplication experiments. |
| [`translate/`](./translate) | DeepL translation utilities for multilingual ingest. |
| [`data/`](./data) | Raw and curated corpus snapshots used during the thesis. |

## Highlights

- **~14k lines** of project Python (excluding the vendored Graphiti core).
- **Custom Ollama LLM client** (`agro_temporal_kg/agro_temporal_kg/ollama_graphiti_client.py`) conforming to Graphiti's interface, enabling hot-swap between OpenRouter, OpenAI, and locally hosted models.
- **Runtime edge patches** (`agro_temporal_kg/agro_temporal_kg/patches/edge_patches.py`) that wire Graphiti's existing `extract_edge_dates` and `get_edge_contradictions` primitives into the standard extraction loop without forking the framework.
- **YAML-driven prompt registry** with system/user version pinning across six prompt families (`extract_text`, `extract_edges`, `dedupe_nodes`, `dedupe_edges`, `invalidate_edges`, `extract_edge_dates`), shifting prompt experiments from code edits to config diffs.
- **Domain ontology** of 27 edge types and 51 entity pairs, evaluated on TXT2KGBench across precision, recall, F1, schema adherence, and hallucination.
- **Embedding-based entity / edge dedup** (multi-threshold cosine clustering + LLM-based canonical-representative selection) that collapsed 688 raw edge names to 115 canonical relations and eliminated 100% of duplicate node instances across 1,533 extracted nodes.
- **BERT + SBERT dual-encoder classifier** trained on 13 semantic classes via a custom data-annotation tool (80% test accuracy, 0.64 macro F1).

## Thesis

Full thesis: [Internship_Theses/main.pdf](https://github.com/Manas-5/Internship_Theses/blob/main/main.pdf).

## License

This repository contains a vendored copy of [Graphiti](https://github.com/getzep/graphiti) (Apache 2.0, © Zep Software, Inc.) under [`graphiti/`](./graphiti). All other code is the work of the contributors listed above; please contact the author for reuse terms.
