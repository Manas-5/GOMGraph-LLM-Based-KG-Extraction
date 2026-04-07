#v2
"""
Temporal Knowledge Graph Pipeline CLI.

This script provides a Typer-based CLI with Hydra configuration management
for creating temporal knowledge graphs from text documents.

Usage:
    python run_pipeline.py create-tkg --override "file.path=/path/to/file.txt"
    python run_pipeline.py create-tkg --print-config
    python run_pipeline.py list-graphs
    python run_pipeline.py list-graphs --host 192.168.1.100 --port 6380
    python run_pipeline.py drop-graph my_graph_name
    python run_pipeline.py drop-graph my_graph_name --host 192.168.1.100 --port 6380
"""

import json
from pathlib import Path

import typer
from dotenv import load_dotenv
from loguru import logger

from agro_temporal_kg.configs import CreateTemporalKGConfig, compose_config
from agro_temporal_kg.falkordb_client import FalkorDBClient
from agro_temporal_kg.pipelines import create_temporal_kg

try:
    from falkordb import FalkorDB
except ImportError:
    FalkorDB = None

load_dotenv()

app = typer.Typer(
    name="agro-tkg",
    help="Agro Temporal Knowledge Graph Pipeline CLI",
    add_completion=False,
)


# ============================================================================
# Commands
# ============================================================================

@app.command()
def create_tkg(
    config_dir: Path | None = typer.Option(
        None,
        "--config-dir",
        help="Directory containing config files (defaults to 'configs' in package root)",
    ),
    override: str | None = typer.Option(
        None,
        "--override",
        help=(
            "Override configuration values using key=value pairs "
            "(e.g., 'file.path=/data/book.txt falkor_db.port=6380'). "
            "Multiple overrides can be space-separated."
        ),
    ),
    print_config: bool = typer.Option(
        False,
        "--print-config",
        help="Print the final configuration and exit without running the pipeline",
    ),
) -> None:
    """
    Create a Temporal Knowledge Graph from text documents.

    This command runs the full pipeline:
    1. Load text file from config.file.path
    2. Split text into chunks
    3. Initialize Graphiti with all components
    4. Ingest chunks as episodes into the knowledge graph
    """
    # Parse overrides from space-separated string (filter out empties)
    overrides = [o for o in override.split(" ") if o] if override else None

    # Compose configuration using Hydra
    cfg = compose_config(
        config_name="create_tkg",
        config_dir=config_dir,
        overrides=overrides,
    )
    logger.info(f"Loaded configuration:\n{cfg}")

    # Convert to Pydantic config
    config = CreateTemporalKGConfig.from_omegaconf(cfg)

    if print_config:
        # Original raw dump
        typer.echo(config.model_dump_json(indent=2))

        # Friendlier edge_type_map with tuple keys stringified, shown separately
        try:
            cfg_dict = config.model_dump(exclude_none=False)
            etm = cfg_dict.get("edge_type_map")
            if isinstance(etm, dict):
                friendly = dict(cfg_dict)
                friendly_etm: dict[str, list[str]] = {}
                for k, v in etm.items():
                    if isinstance(k, (list, tuple)) and len(k) == 2:
                        key = ",".join(str(part) for part in k)
                    else:
                        key = str(k)
                    friendly_etm[key] = v
                friendly["edge_type_map"] = friendly_etm
                typer.echo("\n# edge_type_map_resolved\n" + json.dumps(friendly, indent=2))
        except Exception:
            pass
        return

    # Drop existing graph if present before running
    try:
        db_name = config.falkor_db.database
        client = FalkorDBClient(host=config.falkor_db.host, port=config.falkor_db.port)
        graphs = client.list_graphs()
        if db_name in graphs:
            logger.info(f"Dropping existing graph '{db_name}' before ingestion")
            client.delete_graph(db_name)
    except Exception as e:
        logger.warning(f"Skipping pre-drop check (error: {e})")

    # Validate required config
    if not config.file.path:
        logger.error("No input file specified. Use --override 'file.path=/path/to/file.txt'")
        raise typer.Exit(code=1)

    # Run the pipeline
    try:
        create_temporal_kg(config)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise typer.Exit(code=1)


@app.command()
def list_graphs(
    host: str = typer.Option(
        "localhost",
        "--host",
        "-h",
        help="FalkorDB host address",
    ),
    port: int = typer.Option(
        # 6379,
        6380,
        "--port",
        "-p",
        help="FalkorDB port",
    ),
    config_dir: Path | None = typer.Option(
        None,
        "--config-dir",
        help="Use connection settings from config file instead of --host/--port",
    ),
) -> None:
    """
    List all graphs stored in FalkorDB.

    By default connects to localhost:6379. Use --host and --port to override,
    or --config-dir to load connection settings from a Hydra config file.
    """
    client = FalkorDBClient(host=host, port=port, config_dir=config_dir)

    try:
        graphs = client.list_graphs()
    except SystemExit:
        raise  # Re-raise typer.Exit

    if not graphs:
        typer.echo(f"No graphs found in FalkorDB ({client.host}:{client.port})")
        return

    typer.echo(f"📊 Graphs in FalkorDB ({client.host}:{client.port}):")
    typer.echo("-" * 80)

    # Query statistics if falkordb library is available
    if FalkorDB is not None:
        for graph_name in graphs:
            try:
                stats = client.get_graph_statistics(graph_name)

                # Display graph info
                typer.echo(f"  • {graph_name}")
                typer.echo(f"    Nodes: {stats['node_count']}")
                typer.echo(f"    Relations: {stats['total_relations']}")
                if stats['rel_type_counts']:
                    typer.echo(f"    Relation Types ({len(stats['rel_type_counts'])}):")
                    for rel_type, count in sorted(stats['rel_type_counts'].items()):
                        typer.echo(f"      - {rel_type}: {count}")
                else:
                    typer.echo(f"    Relation Types: (none)")
                typer.echo()
            except Exception as e:
                # If we can't query stats, just show the name
                typer.echo(f"  • {graph_name} (unable to query statistics: {e})")
                typer.echo()
    else:
        # Fallback: just list graph names if falkordb library not available
        for graph_name in graphs:
            typer.echo(f"  • {graph_name}")

    typer.echo("-" * 80)
    typer.echo(f"Total: {len(graphs)} graph(s)")


@app.command()
def drop_graph(
    graph_name: str = typer.Argument(
        ...,
        help="Name of the graph to delete",
    ),
    host: str = typer.Option(
        "localhost",
        "--host",
        "-h",
        help="FalkorDB host address",
    ),
    port: int = typer.Option(
        # 6379,
        6380,
        "--port",
        "-p",
        help="FalkorDB port",
    ),
    config_dir: Path | None = typer.Option(
        None,
        "--config-dir",
        help="Use connection settings from config file instead of --host/--port",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
) -> None:
    """
    Delete a graph from FalkorDB.

    By default connects to localhost:6379. Use --host and --port to override,
    or --config-dir to load connection settings from a Hydra config file.

    This operation is irreversible and will permanently delete the graph and all its data.
    """
    client = FalkorDBClient(host=host, port=port, config_dir=config_dir)

    # Confirm deletion unless --force is used
    if not force:
        typer.echo(f"⚠️  Warning: This will permanently delete graph '{graph_name}' from FalkorDB ({client.host}:{client.port})")
        if not typer.confirm("Are you sure you want to continue?", default=False):
            typer.echo("Operation cancelled.")
            raise typer.Exit(code=0)

    try:
        result = client.delete_graph(graph_name)
        if result:
            typer.echo(f"✅ Successfully deleted graph '{graph_name}' from FalkorDB ({client.host}:{client.port})")
        else:
            typer.echo(f"⚠️  Graph '{graph_name}' not found in FalkorDB ({client.host}:{client.port})")
            raise typer.Exit(code=0)
    except SystemExit:
        raise  # Re-raise typer.Exit


@app.command()
def export_graph(
    graph_name: str = typer.Argument(
        ...,
        help="Name of the graph to export",
    ),
    output_dir: Path = typer.Option(
        Path.cwd() / "exported_data",
        "--output-dir",
        "-o",
        help="Directory to write TSV files (default: current directory)",
    ),
    group_id: str | None = typer.Option(
        None,
        "--group-id",
        "-g",
        help="Filter nodes and edges by group_id (optional)",
    ),
    host: str = typer.Option(
        "localhost",
        "--host",
        "-h",
        help="FalkorDB host address",
    ),
    port: int = typer.Option(
        # 6379,
        6380,
        "--port",
        "-p",
        help="FalkorDB port",
    ),
    config_dir: Path | None = typer.Option(
        None,
        "--config-dir",
        help="Use connection settings from config file instead of --host/--port",
    ),
) -> None:
    """
    Export a graph to TSV format (nodes.tsv and edges.tsv).

    By default connects to localhost:6379. Use --host and --port to override,
    or --config-dir to load connection settings from a Hydra config file.

    The export creates two files:
    - nodes.tsv: Contains all nodes (Entity, Episodic, Community)
    - edges.tsv: Contains all edges (RELATES_TO, MENTIONS, HAS_MEMBER)

    Use --group-id to filter the export to a specific group_id.
    """
    client = FalkorDBClient(host=host, port=port, config_dir=config_dir)

    # Verify graph exists
    graphs = client.list_graphs()
    if graph_name not in graphs:
        typer.echo(f"❌ Graph '{graph_name}' not found in FalkorDB ({client.host}:{client.port})", err=True)
        typer.echo(f"Available graphs: {', '.join(graphs) if graphs else '(none)'}")
        raise typer.Exit(code=1)

    try:
        # Get statistics before export
        stats = client.get_graph_statistics(graph_name)
        typer.echo(f"📊 Exporting graph '{graph_name}' ({stats['node_count']} nodes, {stats['total_relations']} edges)")

        # Export to TSV
        nodes_file, edges_file = client.export_graph_to_tsv(
            graph_name=graph_name,
            output_dir=output_dir,
            group_id=group_id,
        )

        typer.echo(f"✅ Successfully exported graph '{graph_name}' to:")
        typer.echo(f"   • Nodes: {nodes_file}")
        typer.echo(f"   • Edges: {edges_file}")
        if group_id:
            typer.echo(f"   (Filtered by group_id: {group_id})")

    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"❌ Export failed: {e}", err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

#v1
# """
# Temporal Knowledge Graph Pipeline CLI.

# This script provides a Typer-based CLI with Hydra configuration management
# for creating temporal knowledge graphs from text documents.

# Usage:
#     python run_pipeline.py create-tkg --override "file.path=/path/to/file.txt"
#     python run_pipeline.py create-tkg --print-config
#     python run_pipeline.py list-graphs
#     python run_pipeline.py list-graphs --host 192.168.1.100 --port 6380
#     python run_pipeline.py drop-graph my_graph_name
#     python run_pipeline.py drop-graph my_graph_name --host 192.168.1.100 --port 6380
# """

# from pathlib import Path

# import typer
# from dotenv import load_dotenv
# from loguru import logger

# from agro_temporal_kg.configs import CreateTemporalKGConfig, compose_config
# from agro_temporal_kg.falkordb_client import FalkorDBClient
# from agro_temporal_kg.pipelines import create_temporal_kg

# try:
#     from falkordb import FalkorDB
# except ImportError:
#     FalkorDB = None

# load_dotenv()

# app = typer.Typer(
#     name="agro-tkg",
#     help="Agro Temporal Knowledge Graph Pipeline CLI",
#     add_completion=False,
# )


# # ============================================================================
# # Commands
# # ============================================================================

# @app.command()
# def create_tkg(
#     config_dir: Path | None = typer.Option(
#         None,
#         "--config-dir",
#         help="Directory containing config files (defaults to 'configs' in package root)",
#     ),
#     override: str | None = typer.Option(
#         None,
#         "--override",
#         help=(
#             "Override configuration values using key=value pairs "
#             "(e.g., 'file.path=/data/book.txt falkor_db.port=6380'). "
#             "Multiple overrides can be space-separated."
#         ),
#     ),
#     print_config: bool = typer.Option(
#         False,
#         "--print-config",
#         help="Print the final configuration and exit without running the pipeline",
#     ),
# ) -> None:
#     """
#     Create a Temporal Knowledge Graph from text documents.

#     This command runs the full pipeline:
#     1. Load text file from config.file.path
#     2. Split text into chunks
#     3. Initialize Graphiti with all components
#     4. Ingest chunks as episodes into the knowledge graph
#     """
#     # Parse overrides from space-separated string (filter out empties)
#     overrides = [o for o in override.split(" ") if o] if override else None

#     # Compose configuration using Hydra
#     cfg = compose_config(
#         config_name="create_tkg",
#         config_dir=config_dir,
#         overrides=overrides,
#     )
#     logger.info(f"Loaded configuration:\n{cfg}")

#     # Convert to Pydantic config
#     config = CreateTemporalKGConfig.from_omegaconf(cfg)

#     if print_config:
#         typer.echo(config.model_dump_json(indent=2))
#         return

#     # Drop existing graph if present before running
#     try:
#         db_name = config.falkor_db.database
#         client = FalkorDBClient(host=config.falkor_db.host, port=config.falkor_db.port)
#         graphs = client.list_graphs()
#         if db_name in graphs:
#             logger.info(f"Dropping existing graph '{db_name}' before ingestion")
#             client.delete_graph(db_name)
#     except Exception as e:
#         logger.warning(f"Skipping pre-drop check (error: {e})")

#     # Validate required config
#     if not config.file.path:
#         logger.error("No input file specified. Use --override 'file.path=/path/to/file.txt'")
#         raise typer.Exit(code=1)

#     # Run the pipeline
#     try:
#         create_temporal_kg(config)
#     except Exception as e:
#         logger.error(f"Pipeline failed: {e}")
#         raise typer.Exit(code=1)


# @app.command()
# def list_graphs(
#     host: str = typer.Option(
#         "localhost",
#         "--host",
#         "-h",
#         help="FalkorDB host address",
#     ),
#     port: int = typer.Option(
#         # 6379,
#         6380,
#         "--port",
#         "-p",
#         help="FalkorDB port",
#     ),
#     config_dir: Path | None = typer.Option(
#         None,
#         "--config-dir",
#         help="Use connection settings from config file instead of --host/--port",
#     ),
# ) -> None:
#     """
#     List all graphs stored in FalkorDB.

#     By default connects to localhost:6379. Use --host and --port to override,
#     or --config-dir to load connection settings from a Hydra config file.
#     """
#     client = FalkorDBClient(host=host, port=port, config_dir=config_dir)

#     try:
#         graphs = client.list_graphs()
#     except SystemExit:
#         raise  # Re-raise typer.Exit

#     if not graphs:
#         typer.echo(f"No graphs found in FalkorDB ({client.host}:{client.port})")
#         return

#     typer.echo(f"📊 Graphs in FalkorDB ({client.host}:{client.port}):")
#     typer.echo("-" * 80)

#     # Query statistics if falkordb library is available
#     if FalkorDB is not None:
#         for graph_name in graphs:
#             try:
#                 stats = client.get_graph_statistics(graph_name)

#                 # Display graph info
#                 typer.echo(f"  • {graph_name}")
#                 typer.echo(f"    Nodes: {stats['node_count']}")
#                 typer.echo(f"    Relations: {stats['total_relations']}")
#                 if stats['rel_type_counts']:
#                     typer.echo(f"    Relation Types ({len(stats['rel_type_counts'])}):")
#                     for rel_type, count in sorted(stats['rel_type_counts'].items()):
#                         typer.echo(f"      - {rel_type}: {count}")
#                 else:
#                     typer.echo(f"    Relation Types: (none)")
#                 typer.echo()
#             except Exception as e:
#                 # If we can't query stats, just show the name
#                 typer.echo(f"  • {graph_name} (unable to query statistics: {e})")
#                 typer.echo()
#     else:
#         # Fallback: just list graph names if falkordb library not available
#         for graph_name in graphs:
#             typer.echo(f"  • {graph_name}")

#     typer.echo("-" * 80)
#     typer.echo(f"Total: {len(graphs)} graph(s)")


# @app.command()
# def drop_graph(
#     graph_name: str = typer.Argument(
#         ...,
#         help="Name of the graph to delete",
#     ),
#     host: str = typer.Option(
#         "localhost",
#         "--host",
#         "-h",
#         help="FalkorDB host address",
#     ),
#     port: int = typer.Option(
#         # 6379,
#         6380,
#         "--port",
#         "-p",
#         help="FalkorDB port",
#     ),
#     config_dir: Path | None = typer.Option(
#         None,
#         "--config-dir",
#         help="Use connection settings from config file instead of --host/--port",
#     ),
#     force: bool = typer.Option(
#         False,
#         "--force",
#         "-f",
#         help="Skip confirmation prompt",
#     ),
# ) -> None:
#     """
#     Delete a graph from FalkorDB.

#     By default connects to localhost:6379. Use --host and --port to override,
#     or --config-dir to load connection settings from a Hydra config file.

#     This operation is irreversible and will permanently delete the graph and all its data.
#     """
#     client = FalkorDBClient(host=host, port=port, config_dir=config_dir)

#     # Confirm deletion unless --force is used
#     if not force:
#         typer.echo(f"⚠️  Warning: This will permanently delete graph '{graph_name}' from FalkorDB ({client.host}:{client.port})")
#         if not typer.confirm("Are you sure you want to continue?", default=False):
#             typer.echo("Operation cancelled.")
#             raise typer.Exit(code=0)

#     try:
#         result = client.delete_graph(graph_name)
#         if result:
#             typer.echo(f"✅ Successfully deleted graph '{graph_name}' from FalkorDB ({client.host}:{client.port})")
#         else:
#             typer.echo(f"⚠️  Graph '{graph_name}' not found in FalkorDB ({client.host}:{client.port})")
#             raise typer.Exit(code=0)
#     except SystemExit:
#         raise  # Re-raise typer.Exit


# @app.command()
# def export_graph(
#     graph_name: str = typer.Argument(
#         ...,
#         help="Name of the graph to export",
#     ),
#     output_dir: Path = typer.Option(
#         Path.cwd() / "exported_data",
#         "--output-dir",
#         "-o",
#         help="Directory to write TSV files (default: current directory)",
#     ),
#     group_id: str | None = typer.Option(
#         None,
#         "--group-id",
#         "-g",
#         help="Filter nodes and edges by group_id (optional)",
#     ),
#     host: str = typer.Option(
#         "localhost",
#         "--host",
#         "-h",
#         help="FalkorDB host address",
#     ),
#     port: int = typer.Option(
#         # 6379,
#         6380,
#         "--port",
#         "-p",
#         help="FalkorDB port",
#     ),
#     config_dir: Path | None = typer.Option(
#         None,
#         "--config-dir",
#         help="Use connection settings from config file instead of --host/--port",
#     ),
# ) -> None:
#     """
#     Export a graph to TSV format (nodes.tsv and edges.tsv).

#     By default connects to localhost:6379. Use --host and --port to override,
#     or --config-dir to load connection settings from a Hydra config file.

#     The export creates two files:
#     - nodes.tsv: Contains all nodes (Entity, Episodic, Community)
#     - edges.tsv: Contains all edges (RELATES_TO, MENTIONS, HAS_MEMBER)

#     Use --group-id to filter the export to a specific group_id.
#     """
#     client = FalkorDBClient(host=host, port=port, config_dir=config_dir)

#     # Verify graph exists
#     graphs = client.list_graphs()
#     if graph_name not in graphs:
#         typer.echo(f"❌ Graph '{graph_name}' not found in FalkorDB ({client.host}:{client.port})", err=True)
#         typer.echo(f"Available graphs: {', '.join(graphs) if graphs else '(none)'}")
#         raise typer.Exit(code=1)

#     try:
#         # Get statistics before export
#         stats = client.get_graph_statistics(graph_name)
#         typer.echo(f"📊 Exporting graph '{graph_name}' ({stats['node_count']} nodes, {stats['total_relations']} edges)")

#         # Export to TSV
#         nodes_file, edges_file = client.export_graph_to_tsv(
#             graph_name=graph_name,
#             output_dir=output_dir,
#             group_id=group_id,
#         )

#         typer.echo(f"✅ Successfully exported graph '{graph_name}' to:")
#         typer.echo(f"   • Nodes: {nodes_file}")
#         typer.echo(f"   • Edges: {edges_file}")
#         if group_id:
#             typer.echo(f"   (Filtered by group_id: {group_id})")

#     except ValueError as e:
#         typer.echo(f"❌ Error: {e}", err=True)
#         raise typer.Exit(code=1)
#     except Exception as e:
#         typer.echo(f"❌ Export failed: {e}", err=True)
#         raise typer.Exit(code=1)


# if __name__ == "__main__":
#     app()
