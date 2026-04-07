"""
FalkorDB Client and Connection utilities.

Provides high-level abstractions for interacting with FalkorDB,
including graph listing, statistics, and deletion operations.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import redis
import typer
import re

try:
    from falkordb import FalkorDB
except ImportError:
    FalkorDB = None

if TYPE_CHECKING:
    from falkordb import Graph as FalkorGraph

from agro_temporal_kg.configs import CreateTemporalKGConfig, compose_config


class FalkorDBConnection:
    """
    Context manager for FalkorDB Redis connection.

    Handles connection setup, testing, and error handling.
    """

    def __init__(self, host: str, port: int):
        """
        Initialize connection parameters.

        Args:
            host: FalkorDB host address
            port: FalkorDB port number
        """
        self.host = host
        self.port = port
        self._client: redis.Redis | None = None

    def __enter__(self) -> redis.Redis:
        """Create and test Redis connection."""
        try:
            self._client = redis.Redis(host=self.host, port=self.port, decode_responses=True)
            self._client.ping()
            return self._client
        except redis.ConnectionError as e:
            typer.echo(f"❌ Error connecting to FalkorDB at {self.host}:{self.port}: {e}", err=True)
            raise typer.Exit(code=1)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close connection if needed."""
        if self._client:
            self._client.close()
        return False


class FalkorDBClient:
    """
    High-level client for FalkorDB operations.

    Provides methods for listing graphs, querying statistics,
    and managing graphs.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        config_dir: Path | None = None,
    ):
        """
        Initialize FalkorDB client.

        Args:
            host: Default host address
            port: Default port number
            config_dir: Optional config directory to load connection settings from
        """
        self.host, self.port = self._get_connection_params(host, port, config_dir)

    @staticmethod
    def _get_connection_params(
        host: str,
        port: int,
        config_dir: Path | None = None,
    ) -> tuple[str, int]:
        """
        Get FalkorDB connection parameters, optionally loading from config.

        Args:
            host: Default host address
            port: Default port number
            config_dir: Optional config directory to load connection settings from

        Returns:
            tuple[str, int]: (host, port) tuple
        """
        if config_dir is not None:
            cfg = compose_config(config_name="create_tkg", config_dir=config_dir)
            config = CreateTemporalKGConfig.from_omegaconf(cfg)
            return config.falkor_db.host, config.falkor_db.port
        return host, port

    @staticmethod
    def _decode_graph_name(graph: str | bytes) -> str:
        """
        Decode graph name from bytes or return string as-is.

        Args:
            graph: Graph name as string or bytes

        Returns:
            str: Graph name as string
        """
        return graph if isinstance(graph, str) else graph.decode("utf-8")

    def list_graphs(self) -> list[str]:
        """
        List all graphs in FalkorDB.

        Returns:
            list[str]: List of graph names

        Raises:
            typer.Exit: If connection or query fails
        """
        with FalkorDBConnection(self.host, self.port) as r:
            try:
                graphs = r.execute_command("GRAPH.LIST")
                return [self._decode_graph_name(graph) for graph in graphs]
            except redis.ResponseError as e:
                typer.echo(f"❌ FalkorDB error: {e}", err=True)
                raise typer.Exit(code=1)

    def get_graph_statistics(self, graph_name: str) -> dict[str, int | dict[str, int]]:
        """
        Query graph statistics (nodes, relations, relation types).

        Args:
            graph_name: Name of the graph to query

        Returns:
            dict with keys: node_count, total_relations, rel_type_counts

        Raises:
            ValueError: If falkordb library is not available
            Exception: If query fails
        """
        if FalkorDB is None:
            raise ValueError("falkordb library is required for querying statistics")

        falkor_db = FalkorDB(host=self.host, port=self.port)
        graph_obj = falkor_db.select_graph(graph_name)

        # Query node count
        node_result = graph_obj.query("MATCH (n) RETURN COUNT(n) AS count")
        node_count = node_result.result_set[0][0] if node_result.result_set else 0

        # Query relation types and counts in a single query
        rel_result = graph_obj.query(
            "MATCH ()-[r]->() RETURN type(r) AS rel_type, COUNT(r) AS count ORDER BY rel_type"
        )
        rel_type_counts: dict[str, int] = {}
        total_relations = 0
        if rel_result.result_set:
            for row in rel_result.result_set:
                rel_type = row[0]
                count = row[1]
                rel_type_counts[rel_type] = count
                total_relations += count

        return {
            "node_count": node_count,
            "total_relations": total_relations,
            "rel_type_counts": rel_type_counts,
        }

    def delete_graph(self, graph_name: str) -> bool:
        """
        Delete a graph from FalkorDB.

        Args:
            graph_name: Name of the graph to delete

        Returns:
            bool: True if graph was deleted, False if it didn't exist

        Raises:
            typer.Exit: If connection fails or graph not found
        """
        with FalkorDBConnection(self.host, self.port) as r:
            try:
                result = r.execute_command("GRAPH.DELETE", graph_name)
                return bool(result)
            except redis.ResponseError as e:
                error_msg = str(e)
                if "not found" in error_msg.lower() or "does not exist" in error_msg.lower():
                    return False
                typer.echo(f"❌ FalkorDB error: {e}", err=True)
                raise typer.Exit(code=1)

    @staticmethod
    def _escape_tsv_value(value: any) -> str:
        """
        Escape a value for TSV format.

        Handles None, lists, dicts, datetimes, and special characters.

        Args:
            value: Value to escape

        Returns:
            str: Escaped TSV-safe string
        """
        if value is None:
            return ""
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, datetime):
            return value.isoformat()
        # Convert to string and escape tabs, newlines, and backslashes
        str_value = str(value)
        return str_value.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")

    @staticmethod
    def _filter_embeddings_from_attributes(attributes: dict | None) -> dict:
        """
        Remove embedding fields from attributes dictionary.

        Args:
            attributes: Attributes dictionary that may contain embeddings

        Returns:
            dict: Attributes dictionary without embedding fields
        """
        if attributes is None:
            return {}
        if not isinstance(attributes, dict):
            return {}
        # Filter out any keys that contain 'embedding'
        return {k: v for k, v in attributes.items() if "embedding" not in k.lower()}

    @staticmethod
    def _format_labels(labels: list[str] | None) -> str:
        """Format labels list as JSON string."""
        if labels is None:
            return "[]"
        return json.dumps(labels, ensure_ascii=False)

    def export_graph_to_tsv(
        self,
        graph_name: str,
        output_dir: Path,
        group_id: str | None = None,
    ) -> tuple[Path, Path]:
        """
        Export a graph to TSV format (nodes.tsv and edges.tsv).

        Args:
            graph_name: Name of the graph to export
            output_dir: Directory to write TSV files
            group_id: Optional group_id filter (if None, exports all nodes/edges)

        Returns:
            tuple[Path, Path]: Paths to nodes.tsv and edges.tsv files

        Raises:
            ValueError: If falkordb library is not available
            typer.Exit: If graph not found or export fails
        """
        if FalkorDB is None:
            raise ValueError("falkordb library is required for exporting graphs")

        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        falkor_db = FalkorDB(host=self.host, port=self.port)
        graph_obj = falkor_db.select_graph(graph_name)

        # Build WHERE clause for group_id filtering
        # Escape single quotes in group_id to prevent Cypher injection
        if group_id:
            escaped_group_id = group_id.replace("'", "''")
            where_clause = f" WHERE n.group_id = '{escaped_group_id}'"
            e_where_clause = f" WHERE e.group_id = '{escaped_group_id}'"
            c_where_clause = f" WHERE c.group_id = '{escaped_group_id}'"
        else:
            where_clause = ""
            e_where_clause = ""
            c_where_clause = ""

        # Query all Entity nodes
        entity_query = f"""
            MATCH (n:Entity){where_clause}
            RETURN
                n.uuid AS uuid,
                'Entity' AS type,
                n.name AS name,
                n.group_id AS group_id,
                labels(n) AS labels,
                n.created_at AS created_at,
                n.summary AS summary,
                properties(n) AS attributes
        """
        entity_result = graph_obj.query(entity_query)

        # Query all Episodic nodes
        episodic_query = f"""
            MATCH (e:Episodic){e_where_clause}
            RETURN
                e.uuid AS uuid,
                'Episodic' AS type,
                e.name AS name,
                e.group_id AS group_id,
                ['Episodic'] AS labels,
                e.created_at AS created_at,
                '' AS summary,
                '' AS attributes,
                e.source AS source,
                e.source_description AS source_description,
                e.content AS content,
                e.valid_at AS valid_at,
                e.entity_edges AS entity_edges
        """
        episodic_result = graph_obj.query(episodic_query)

        # Query all Community nodes
        community_query = f"""
            MATCH (c:Community){c_where_clause}
            RETURN
                c.uuid AS uuid,
                'Community' AS type,
                c.name AS name,
                c.group_id AS group_id,
                ['Community'] AS labels,
                c.created_at AS created_at,
                c.summary AS summary,
                '' AS attributes
        """
        community_result = graph_obj.query(community_query)

        # Query all RELATES_TO edges (EntityEdge)
        relates_to_query = f"""
            MATCH (n:Entity)-[e:RELATES_TO]->(m:Entity){e_where_clause}
            RETURN
                e.uuid AS uuid,
                'RELATES_TO' AS type,
                n.uuid AS source_node_uuid,
                m.uuid AS target_node_uuid,
                e.group_id AS group_id,
                e.created_at AS created_at,
                e.name AS name,
                e.fact AS fact,
                e.episodes AS episodes,
                e.expired_at AS expired_at,
                e.valid_at AS valid_at,
                e.invalid_at AS invalid_at,
                properties(e) AS attributes
        """
        relates_to_result = graph_obj.query(relates_to_query)

        # Query all MENTIONS edges (EpisodicEdge)
        mentions_query = f"""
            MATCH (n:Episodic)-[e:MENTIONS]->(m:Entity){e_where_clause}
            RETURN
                e.uuid AS uuid,
                'MENTIONS' AS type,
                n.uuid AS source_node_uuid,
                m.uuid AS target_node_uuid,
                e.group_id AS group_id,
                e.created_at AS created_at
        """
        mentions_result = graph_obj.query(mentions_query)

        # Query all HAS_MEMBER edges (CommunityEdge)
        has_member_query = f"""
            MATCH (n:Community)-[e:HAS_MEMBER]->(m){e_where_clause}
            RETURN
                e.uuid AS uuid,
                'HAS_MEMBER' AS type,
                n.uuid AS source_node_uuid,
                m.uuid AS target_node_uuid,
                e.group_id AS group_id,
                e.created_at AS created_at
        """
        has_member_result = graph_obj.query(has_member_query)

        # Write nodes_<graph_name>.tsv (sanitize graph name for filesystem)
        sanitized_name = re.sub(r"[^A-Za-z0-9_.-]", "_", graph_name)
        nodes_file = output_dir / f"nodes_{sanitized_name}.tsv"
        with open(nodes_file, "w", encoding="utf-8") as f:
            # Write header
            f.write(
                "uuid\ttype\tname\tgroup_id\tlabels\tcreated_at\tsummary\tattributes\tsource\tsource_description\tcontent\tvalid_at\tentity_edges\n"
            )

            # Write Entity nodes
            header = [h[1] for h in entity_result.header]
            for row in entity_result.result_set:
                record = dict(zip(header, row))
                # Filter out embeddings from attributes
                attributes = self._filter_embeddings_from_attributes(record.get('attributes'))
                f.write(
                    f"{record.get('uuid', '')}\t"
                    f"{record.get('type', 'Entity')}\t"
                    f"{self._escape_tsv_value(record.get('name', ''))}\t"
                    f"{record.get('group_id', '')}\t"
                    f"{self._format_labels(record.get('labels'))}\t"
                    f"{self._escape_tsv_value(record.get('created_at', ''))}\t"
                    f"{self._escape_tsv_value(record.get('summary', ''))}\t"
                    f"{self._escape_tsv_value(attributes)}\t"
                    f"\t\t\t\t\n"  # Episodic-specific fields (empty for Entity)
                )

            # Write Episodic nodes
            header = [h[1] for h in episodic_result.header]
            for row in episodic_result.result_set:
                record = dict(zip(header, row))
                f.write(
                    f"{record.get('uuid', '')}\t"
                    f"{record.get('type', 'Episodic')}\t"
                    f"{self._escape_tsv_value(record.get('name', ''))}\t"
                    f"{record.get('group_id', '')}\t"
                    f"{self._format_labels(record.get('labels', ['Episodic']))}\t"
                    f"{self._escape_tsv_value(record.get('created_at', ''))}\t"
                    f"\t"  # summary (empty for Episodic)
                    f"\t"  # attributes (empty for Episodic)
                    f"{self._escape_tsv_value(record.get('source', ''))}\t"
                    f"{self._escape_tsv_value(record.get('source_description', ''))}\t"
                    f"{self._escape_tsv_value(record.get('content', ''))}\t"
                    f"{self._escape_tsv_value(record.get('valid_at', ''))}\t"
                    f"{self._escape_tsv_value(record.get('entity_edges', []))}\n"
                )

            # Write Community nodes
            header = [h[1] for h in community_result.header]
            for row in community_result.result_set:
                record = dict(zip(header, row))
                f.write(
                    f"{record.get('uuid', '')}\t"
                    f"{record.get('type', 'Community')}\t"
                    f"{self._escape_tsv_value(record.get('name', ''))}\t"
                    f"{record.get('group_id', '')}\t"
                    f"{self._format_labels(record.get('labels', ['Community']))}\t"
                    f"{self._escape_tsv_value(record.get('created_at', ''))}\t"
                    f"{self._escape_tsv_value(record.get('summary', ''))}\t"
                    f"\t"  # attributes (empty for Community)
                    f"\t\t\t\t\n"  # Episodic-specific fields (source, source_description, content, valid_at, entity_edges)
                )

        # Write edges_<graph_name>.tsv (sanitize graph name for filesystem)
        edges_file = output_dir / f"edges_{sanitized_name}.tsv"
        with open(edges_file, "w", encoding="utf-8") as f:
            # Write header
            f.write(
                "uuid\ttype\tsource_node_uuid\ttarget_node_uuid\tgroup_id\tcreated_at\tname\tfact\tepisodes\texpired_at\tvalid_at\tinvalid_at\tattributes\n"
            )

            # Write RELATES_TO edges
            header = [h[1] for h in relates_to_result.header]
            for row in relates_to_result.result_set:
                record = dict(zip(header, row))
                # Filter out embeddings from attributes
                attributes = self._filter_embeddings_from_attributes(record.get('attributes'))
                f.write(
                    f"{record.get('uuid', '')}\t"
                    f"{record.get('type', 'RELATES_TO')}\t"
                    f"{record.get('source_node_uuid', '')}\t"
                    f"{record.get('target_node_uuid', '')}\t"
                    f"{record.get('group_id', '')}\t"
                    f"{self._escape_tsv_value(record.get('created_at', ''))}\t"
                    f"{self._escape_tsv_value(record.get('name', ''))}\t"
                    f"{self._escape_tsv_value(record.get('fact', ''))}\t"
                    f"{self._escape_tsv_value(record.get('episodes', []))}\t"
                    f"{self._escape_tsv_value(record.get('expired_at', ''))}\t"
                    f"{self._escape_tsv_value(record.get('valid_at', ''))}\t"
                    f"{self._escape_tsv_value(record.get('invalid_at', ''))}\t"
                    f"{self._escape_tsv_value(attributes)}\n"
                )

            # Write MENTIONS edges
            header = [h[1] for h in mentions_result.header]
            for row in mentions_result.result_set:
                record = dict(zip(header, row))
                f.write(
                    f"{record.get('uuid', '')}\t"
                    f"{record.get('type', 'MENTIONS')}\t"
                    f"{record.get('source_node_uuid', '')}\t"
                    f"{record.get('target_node_uuid', '')}\t"
                    f"{record.get('group_id', '')}\t"
                    f"{self._escape_tsv_value(record.get('created_at', ''))}\t"
                    f"\t\t\t\t\t\t\n"  # EntityEdge-specific fields (empty for MENTIONS)
                )

            # Write HAS_MEMBER edges
            header = [h[1] for h in has_member_result.header]
            for row in has_member_result.result_set:
                record = dict(zip(header, row))
                f.write(
                    f"{record.get('uuid', '')}\t"
                    f"{record.get('type', 'HAS_MEMBER')}\t"
                    f"{record.get('source_node_uuid', '')}\t"
                    f"{record.get('target_node_uuid', '')}\t"
                    f"{record.get('group_id', '')}\t"
                    f"{self._escape_tsv_value(record.get('created_at', ''))}\t"
                    f"\t\t\t\t\t\t\n"  # EntityEdge-specific fields (empty for HAS_MEMBER)
                )

        return nodes_file, edges_file

