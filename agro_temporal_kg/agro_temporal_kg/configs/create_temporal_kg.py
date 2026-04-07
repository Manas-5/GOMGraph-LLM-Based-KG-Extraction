#v2

"""
Configuration classes for the temporal knowledge graph pipeline.

These Pydantic models integrate with Hydra/OmegaConf for flexible configuration management.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from omegaconf import OmegaConf

if TYPE_CHECKING:
    from omegaconf import DictConfig


class TextSplitterConfig(BaseModel):
    """Configuration for text chunking."""

    chunk_size: int = Field(default=1_000, description="Maximum size of each text chunk")
    chunk_overlap: int = Field(default=150, description="Overlap between consecutive chunks")
    separators: list[str] = Field(
        default=["\n\n", "\n", ". ", " ", ""],
        description="Separator hierarchy for splitting",
    )



class LLMConfig(BaseModel):
    """Configuration for the language model."""

    model: str = Field(default="llama3.1:70b", description="Model name/identifier")
    temperature: float = Field(default=0.0, description="Sampling temperature")
    api_key: str | None = Field(default=None, description="API key for the LLM service")
    base_url: str | None = Field(default=None, description="Base URL for the LLM API")



class EmbedderConfig(BaseSettings):
    """Configuration for the embedding model."""

    api_key: SecretStr = Field(default="", description="API key for embedding service")
    base_url: str = Field(
        default="http://localhost:11434/v1", description="Base URL for embedding API"
    )
    embedding_model: str = Field(default="bge-m3:567m", description="Embedding model name")
    embedding_dim: int = Field(default=768, description="Embedding dimension size")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="EMBEDDER_",
        extra="allow",
    )


class FalkorDBConfig(BaseModel):
    """Configuration for FalkorDB connection."""

    host: str = Field(default="localhost", description="FalkorDB host address")
    port: int = Field(default=6380, description="FalkorDB port")
    database: str = Field(default="agro-database", description="Database name")


class FileConfig(BaseModel):
    """Configuration for input file and document metadata."""

    path: str = Field(default="", description="Path to input file")
    group_id: str = Field(
        default="agro-kg",
        description="Group identifier for organizing related episodes in the graph",
    )
    source_description: str = Field(
        default="French agricultural/horticultural text",
        description="Human-readable description of the source document",
    )
    reference_year: int = Field(
        default=1880,
        description="Reference year for temporal context of the document",
    )


class PromptTypeConfig(BaseModel):
    """Configuration for a specific prompt type."""

    system_version: str = Field(
        default="v0",
        description="Version identifier for the system prompt (e.g., 'v0', 'v1')",
    )
    user_version: str = Field(
        default="v0",
        description="Version identifier for the user prompt (e.g., 'v0', 'v1')",
    )


class PromptConfig(BaseModel):
    """Configuration for prompt selection and versioning."""

    extract_text: PromptTypeConfig | None = Field(
        default=None,
        description="Configuration for extract_text prompt. If None, uses graphiti defaults.",
    )
    extract_edges: PromptTypeConfig | None = Field(
        default=None,
        description="Configuration for extract_edges prompt. If None, uses graphiti defaults.",
    )
    summary_instructions_version: str | None = Field(
        default=None,
        description="Version identifier for summary_instructions snippet (e.g., 'v0', 'v1'). "
        "If None, uses default from snippets/default.yaml or graphiti defaults.",
    )
    # Future: Add other prompt types
    # extract_message: PromptTypeConfig | None = None
    # extract_json: PromptTypeConfig | None = None


class CreateTemporalKGConfig(BaseSettings):
    """Main configuration for the temporal knowledge graph creation pipeline."""

    embedder: EmbedderConfig = Field(default_factory=EmbedderConfig)
    falkor_db: FalkorDBConfig = Field(default_factory=FalkorDBConfig)
    text_splitter: TextSplitterConfig = Field(default_factory=TextSplitterConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    file: FileConfig = Field(default_factory=FileConfig)
    prompts: PromptConfig = Field(default_factory=PromptConfig)
    update_communities: bool = Field(default=False, description="Whether to update communities")
    entity_types: list[str] | None = Field(
        default=None,
        description="Entity types to use for the graph. Can be a list of type names or None to use defaults.",
    )
    edge_types: list[str] | None = Field(
        default=None,
        description="Edge/relation types to use for the graph. Can be a list of type names or None to use defaults.",
    )
    edge_type_map: dict[tuple[str, str], list[str]] | None = Field(
        default=None,
        description=(
            "Map from (source_label, target_label) to allowed edge type names. "
            "Keys may be provided as 'A,B' strings in YAML; they are converted to tuples."
        ),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    @classmethod
    def from_omegaconf(cls, cfg: DictConfig) -> "CreateTemporalKGConfig":
        """
        Create instance from OmegaConf DictConfig.

        This method converts the OmegaConf object to Pydantic models,
        handling nested configurations appropriately.

        Args:
            cfg: OmegaConf DictConfig object from Hydra composition.

        Returns:
            CreateTemporalKGConfig: Fully instantiated configuration object.

        Example:
            >>> cfg = compose_config("create_tkg")
            >>> config = CreateTemporalKGConfig.from_omegaconf(cfg)
        """
        cfg_dict = cast(dict, OmegaConf.to_container(cfg, resolve=True))

        # Map Hydra config group name `falkordb` (used in configs/) to the
        # Pydantic field name `falkor_db` expected by this settings model.
        # Some configs and override keys may use `falkordb`, while the
        # CreateTemporalKGConfig uses `falkor_db` (underscore). Accept both
        # so CLI overrides like `falkordb.database=...` work as expected.
        if "falkordb" in cfg_dict and "falkor_db" not in cfg_dict:
            cfg_dict["falkor_db"] = cfg_dict.pop("falkordb")

        # Handle nested entity_types structure from Hydra config groups
        # Hydra config groups create: entity_types: {types: [...]}
        # We want to flatten to: entity_types: [...]
        if "entity_types" in cfg_dict and isinstance(cfg_dict["entity_types"], dict):
            if "types" in cfg_dict["entity_types"]:
                cfg_dict["entity_types"] = cfg_dict["entity_types"]["types"]

        # Handle nested edge_types structure from Hydra config groups
        # Hydra config groups create: edge_types: {types: [...]}
        # We want to flatten to: edge_types: [...]
        if "edge_types" in cfg_dict and isinstance(cfg_dict["edge_types"], dict):
            if "types" in cfg_dict["edge_types"]:
                cfg_dict["edge_types"] = cfg_dict["edge_types"]["types"]

        # Handle nested edge_type_map structure from Hydra config groups.
        # Hydra config groups create: edge_type_map: {edge_type_map: {…}}
        # We want to flatten to: edge_type_map: {…}
        if "edge_type_map" in cfg_dict and isinstance(cfg_dict["edge_type_map"], dict):
            if "edge_type_map" in cfg_dict["edge_type_map"]:
                cfg_dict["edge_type_map"] = cfg_dict["edge_type_map"]["edge_type_map"]

        # Normalize edge_type_map keys (supports "A,B" string keys from YAML)
        if "edge_type_map" in cfg_dict and cfg_dict["edge_type_map"] is not None:
            parsed_map: dict[tuple[str, str], list[str]] = {}
            for raw_key, value in cfg_dict["edge_type_map"].items():
                # Accept tuple/list keys or comma-separated strings
                if isinstance(raw_key, (list, tuple)) and len(raw_key) == 2:
                    key = (str(raw_key[0]), str(raw_key[1]))
                elif isinstance(raw_key, str):
                    parts = [p.strip() for p in raw_key.split(",") if p.strip()]
                    if len(parts) == 2:
                        key = (parts[0], parts[1])
                    else:
                        # Skip malformed keys rather than breaking config load
                        continue
                else:
                    continue

                # Ensure the value is a list of strings
                if isinstance(value, (list, tuple)):
                    parsed_map[key] = [str(v) for v in value]
                else:
                    # Single string -> wrap
                    parsed_map[key] = [str(value)]

            cfg_dict["edge_type_map"] = parsed_map

        return cls(**cfg_dict)


#v1
# """
# Configuration classes for the temporal knowledge graph pipeline.

# These Pydantic models integrate with Hydra/OmegaConf for flexible configuration management.
# """

# from __future__ import annotations

# from typing import TYPE_CHECKING, Any, cast

# from pydantic import BaseModel, Field, SecretStr
# from pydantic_settings import BaseSettings, SettingsConfigDict

# from omegaconf import OmegaConf

# if TYPE_CHECKING:
#     from omegaconf import DictConfig


# class TextSplitterConfig(BaseModel):
#     """Configuration for text chunking."""

#     chunk_size: int = Field(default=1_000, description="Maximum size of each text chunk")
#     chunk_overlap: int = Field(default=150, description="Overlap between consecutive chunks")
#     separators: list[str] = Field(
#         default=["\n\n", "\n", ". ", " ", ""],
#         description="Separator hierarchy for splitting",
#     )



# class LLMConfig(BaseModel):
#     """Configuration for the language model."""

#     model: str = Field(default="llama3.1:70b", description="Model name/identifier")
#     temperature: float = Field(default=0.0, description="Sampling temperature")
#     api_key: str | None = Field(default=None, description="API key for the LLM service")
#     base_url: str | None = Field(default=None, description="Base URL for the LLM API")



# class EmbedderConfig(BaseSettings):
#     """Configuration for the embedding model."""

#     api_key: SecretStr = Field(default="", description="API key for embedding service")
#     base_url: str = Field(
#         default="http://localhost:11434/v1", description="Base URL for embedding API"
#     )
#     embedding_model: str = Field(default="bge-m3:567m", description="Embedding model name")
#     embedding_dim: int = Field(default=768, description="Embedding dimension size")

#     model_config = SettingsConfigDict(
#         env_file=".env",
#         env_file_encoding="utf-8",
#         env_prefix="EMBEDDER_",
#         extra="allow",
#     )


# class FalkorDBConfig(BaseModel):
#     """Configuration for FalkorDB connection."""

#     host: str = Field(default="localhost", description="FalkorDB host address")
#     port: int = Field(default=6380, description="FalkorDB port")
#     database: str = Field(default="agro-database", description="Database name")


# class FileConfig(BaseModel):
#     """Configuration for input file and document metadata."""

#     path: str = Field(default="", description="Path to input file")
#     group_id: str = Field(
#         default="agro-kg",
#         description="Group identifier for organizing related episodes in the graph",
#     )
#     source_description: str = Field(
#         default="French agricultural/horticultural text",
#         description="Human-readable description of the source document",
#     )
#     reference_year: int = Field(
#         default=1880,
#         description="Reference year for temporal context of the document",
#     )


# class PromptTypeConfig(BaseModel):
#     """Configuration for a specific prompt type."""

#     system_version: str = Field(
#         default="v0",
#         description="Version identifier for the system prompt (e.g., 'v0', 'v1')",
#     )
#     user_version: str = Field(
#         default="v0",
#         description="Version identifier for the user prompt (e.g., 'v0', 'v1')",
#     )


# class PromptConfig(BaseModel):
#     """Configuration for prompt selection and versioning."""

#     extract_text: PromptTypeConfig | None = Field(
#         default=None,
#         description="Configuration for extract_text prompt. If None, uses graphiti defaults.",
#     )
#     extract_edges: PromptTypeConfig | None = Field(
#         default=None,
#         description="Configuration for extract_edges prompt. If None, uses graphiti defaults.",
#     )
#     summary_instructions_version: str | None = Field(
#         default=None,
#         description="Version identifier for summary_instructions snippet (e.g., 'v0', 'v1'). "
#         "If None, uses default from snippets/default.yaml or graphiti defaults.",
#     )
#     # Future: Add other prompt types
#     # extract_message: PromptTypeConfig | None = None
#     # extract_json: PromptTypeConfig | None = None


# class CreateTemporalKGConfig(BaseSettings):
#     """Main configuration for the temporal knowledge graph creation pipeline."""

#     embedder: EmbedderConfig = Field(default_factory=EmbedderConfig)
#     falkor_db: FalkorDBConfig = Field(default_factory=FalkorDBConfig)
#     text_splitter: TextSplitterConfig = Field(default_factory=TextSplitterConfig)
#     llm: LLMConfig = Field(default_factory=LLMConfig)
#     file: FileConfig = Field(default_factory=FileConfig)
#     prompts: PromptConfig = Field(default_factory=PromptConfig)
#     update_communities: bool = Field(default=False, description="Whether to update communities")
#     entity_types: list[str] | None = Field(
#         default=None,
#         description="Entity types to use for the graph. Can be a list of type names or None to use defaults.",
#     )
#     edge_types: list[str] | None = Field(
#         default=None,
#         description="Edge/relation types to use for the graph. Can be a list of type names or None to use defaults.",
#     )
#     edge_type_map: list[tuple[str, str]] | None = Field(
#         default=None, description="Edge type map to use for the graph"
#     )

#     model_config = SettingsConfigDict(
#         env_file=".env",
#         env_file_encoding="utf-8",
#         extra="allow",
#     )

#     @classmethod
#     def from_omegaconf(cls, cfg: DictConfig) -> "CreateTemporalKGConfig":
#         """
#         Create instance from OmegaConf DictConfig.

#         This method converts the OmegaConf object to Pydantic models,
#         handling nested configurations appropriately.

#         Args:
#             cfg: OmegaConf DictConfig object from Hydra composition.

#         Returns:
#             CreateTemporalKGConfig: Fully instantiated configuration object.

#         Example:
#             >>> cfg = compose_config("create_tkg")
#             >>> config = CreateTemporalKGConfig.from_omegaconf(cfg)
#         """
#         cfg_dict = cast(dict, OmegaConf.to_container(cfg, resolve=True))

#         # Map Hydra config group name `falkordb` (used in configs/) to the
#         # Pydantic field name `falkor_db` expected by this settings model.
#         # Some configs and override keys may use `falkordb`, while the
#         # CreateTemporalKGConfig uses `falkor_db` (underscore). Accept both
#         # so CLI overrides like `falkordb.database=...` work as expected.
#         if "falkordb" in cfg_dict and "falkor_db" not in cfg_dict:
#             cfg_dict["falkor_db"] = cfg_dict.pop("falkordb")

#         # Handle nested entity_types structure from Hydra config groups
#         # Hydra config groups create: entity_types: {types: [...]}
#         # We want to flatten to: entity_types: [...]
#         if "entity_types" in cfg_dict and isinstance(cfg_dict["entity_types"], dict):
#             if "types" in cfg_dict["entity_types"]:
#                 cfg_dict["entity_types"] = cfg_dict["entity_types"]["types"]

#         # Handle nested edge_types structure from Hydra config groups
#         # Hydra config groups create: edge_types: {types: [...]}
#         # We want to flatten to: edge_types: [...]
#         if "edge_types" in cfg_dict and isinstance(cfg_dict["edge_types"], dict):
#             if "types" in cfg_dict["edge_types"]:
#                 cfg_dict["edge_types"] = cfg_dict["edge_types"]["types"]

#         return cls(**cfg_dict)
