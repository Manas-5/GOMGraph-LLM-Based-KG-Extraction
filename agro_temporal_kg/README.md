# Agro Temporal Knowledge Graph

A specialized knowledge graph system for extracting and structuring agricultural and horticultural information from historical gardening texts, with a focus on temporal relationships and seasonal gardening practices.

## 🌱 Overview

This project leverages the [Graphiti](https://github.com/getzep/graphiti) framework to build temporal knowledge graphs from agricultural texts, particularly French gardening manuals. It extracts structured information about plants, tasks, timing, environments, and their relationships to create a comprehensive agricultural knowledge base.

## ✨ Key Features

- **Temporal Knowledge Extraction**: Extracts time-based agricultural information from historical texts
- **Rich Entity Modeling**: Comprehensive entity types for plants, tasks, environments, materials, and tools
- **Relationship Mapping**: Captures complex relationships between agricultural concepts
- **Multi-Modal Processing**: Supports text processing with chunking and semantic understanding
- **FalkorDB Integration**: Uses FalkorDB as the graph database backend
- **OpenAI Integration**: Leverages OpenAI models for entity extraction and embeddings
- **Ollama Local Model Integration**: Leverages Ollama models available for download to do entity extractions and embeddings truly locally.

## 🏗️ Architecture

### Entity Types

The system defines 8 core entity types:

- **Plant**: Cultivated plants, crops, varieties, and cultivars
- **Task**: Horticultural operations and gardening actions
- **TimePeriod**: Temporal references for scheduling
- **Environment**: Growing environments and cultural systems
- **Material**: Inputs, amendments, and resources
- **Tool**: Gardening implements and equipment
- **Condition**: Environmental and soil conditions
- **Threat**: Biotic and abiotic threats to crops

### Relationship Types

15 relationship types capture agricultural relationships:

- **Temporal**: `SowIn`, `PlantIn`, `TransplantIn`, `PruneIn`, `HarvestIn`, `PerformIn`
- **Functional**: `AppliesTo`, `RequiresEnvironment`, `PerformedInEnvironment`
- **Resource**: `UsesInput`, `RequiresTool`
- **Environmental**: `PrefersSoil`, `IndicatedBy`
- **Protective**: `ThreatenedBy`, `ProtectsFrom`
- **Sequential**: `Precedes`

## 🚀 Quick Start

### Prerequisites

- Python 3.10-3.12
- Docker and Docker Compose
- OpenAI API key
- OpenRouter API key (optional, for alternative models)

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd agro_temporal_kg
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   uv sync --active
   ```

3. **Set up environment variables**:
   Create a `.env` file with:
   ```env
   OPENAI_API_KEY=your_openai_api_key
   OPENROUTER_API_KEY=your_openrouter_api_key
   OPENROUTER_MODEL_NAME=your_preferred_model
   ```

4. **Start the database**:
   ```bash
   docker-compose up -d
   ```

### Basic Usage

```python
import asyncio
from agro_temporal_kg.builder import get_graphiti
from agro_temporal_kg.entities import entity_types, edge_types

async def process_gardening_text():
    # Initialize the knowledge graph
    graphiti = get_graphiti("my-agro-graph")
    
    # Process a text chunk
    result = await graphiti.add_episode(
        name="january-gardening",
        source_description="January gardening tasks from French manual",
        episode_body="In January, sow asparagus seeds in pots...",
        entity_types=entity_types,
        edge_types=edge_types,
        reference_time=datetime(1880, 1, 1)
    )
    
    return result

# Run the processing
asyncio.run(process_gardening_text())
```

## 📁 Project Structure

```
agro_temporal_kg/
├── agro_temporal_kg/           # Main package
│   ├── __init__.py
│   ├── builder.py             # Graphiti configuration
│   └── entities.py            # Entity and relationship definitions
├── scripts/                   # Example scripts
│   ├── test.py               # French gardening text processing
│   └── test_2.py             # Generic entity extraction example
├── tests/                     # Test suite
├── docker-compose.yml         # FalkorDB setup
├── Makefile                   # Development commands
└── pyproject.toml            # Project configuration
```

## 🛠️ Development

### Code Quality

The project uses several tools for code quality:

- **Ruff**: Linting and formatting
- **MyPy**: Type checking
- **Pytest**: Testing framework

Run all checks:
```bash
make run_checks
```

### Database Management

Start FalkorDB with browser interface:
```bash
docker-compose up -d
```

Access the browser at `http://localhost:3000` to explore the graph.

### Testing

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=agro_temporal_kg
```

## 📊 Data Processing Pipeline

1. **Text Input**: Historical gardening texts (e.g., French manuals)
2. **Chunking**: Text is split into manageable chunks with overlap
3. **Entity Extraction**: LLM extracts entities and relationships
4. **Graph Construction**: Entities and relationships are stored in FalkorDB
5. **Querying**: The graph can be queried for agricultural insights

## 🔍 Example Queries

Once your knowledge graph is populated, you can query it for insights:

```python
# Find all plants that should be sown in January
query = """
MATCH (p:Plant)-[r:SowIn]->(t:TimePeriod)
WHERE t.month = 'January'
RETURN p.common_name, r.notes
"""

# Find tasks that protect from frost
query = """
MATCH (task:Task)-[r:ProtectsFrom]->(threat:Threat)
WHERE threat.threat_type = 'weather'
RETURN task.description, r.mechanism
"""
```

## 🌍 Use Cases

- **Historical Agriculture Research**: Analyze historical farming practices
- **Seasonal Planning**: Extract timing information for modern gardening
- **Crop Management**: Understand plant requirements and relationships
- **Knowledge Preservation**: Digitize and structure traditional agricultural knowledge
- **Educational Tools**: Create interactive agricultural learning systems

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run the quality checks: `make run_checks`
5. Submit a pull request

## 📄 License

This project is part of the GOMgraph research initiative. Please refer to the main repository for licensing information.

## 🔗 Related Projects

- [Graphiti](https://github.com/IBM/graphiti): The underlying knowledge graph framework
- [FalkorDB](https://falkordb.com/): The graph database backend
- [GOMgraph](https://github.com/your-org/GOMgraph): The parent research project

## 📞 Support

For questions and support, please open an issue in the repository or contact the maintainers.

---

*Built with ❤️ for agricultural knowledge preservation and research*

<!-- # Agro Temporal Knowledge Graph

A specialized knowledge graph system for extracting and structuring agricultural and horticultural information from historical gardening texts, with a focus on temporal relationships and seasonal gardening practices.

## 🌱 Overview

This project leverages the [Graphiti](https://github.com/IBM/graphiti) framework to build temporal knowledge graphs from agricultural texts, particularly French gardening manuals. It extracts structured information about plants, tasks, timing, environments, and their relationships to create a comprehensive agricultural knowledge base.

## ✨ Key Features

- **Temporal Knowledge Extraction**: Extracts time-based agricultural information from historical texts
- **Rich Entity Modeling**: Comprehensive entity types for plants, tasks, environments, materials, and tools
- **Relationship Mapping**: Captures complex relationships between agricultural concepts
- **Multi-Modal Processing**: Supports text processing with chunking and semantic understanding
- **FalkorDB Integration**: Uses FalkorDB as the graph database backend
- **OpenAI Integration**: Leverages OpenAI models for entity extraction and embeddings
- **Ollama Local Model Integration**: Leverages Ollama models available for download to do entity extractions and embeddings truly locally.

## 🏗️ Architecture

### Entity Types

The system defines 8 core entity types:

- **Plant**: Cultivated plants, crops, varieties, and cultivars
- **Task**: Horticultural operations and gardening actions
- **TimePeriod**: Temporal references for scheduling
- **Environment**: Growing environments and cultural systems
- **Material**: Inputs, amendments, and resources
- **Tool**: Gardening implements and equipment
- **Condition**: Environmental and soil conditions
- **Threat**: Biotic and abiotic threats to crops

### Relationship Types

15 relationship types capture agricultural relationships:

- **Temporal**: `SowIn`, `PlantIn`, `TransplantIn`, `PruneIn`, `HarvestIn`, `PerformIn`
- **Functional**: `AppliesTo`, `RequiresEnvironment`, `PerformedInEnvironment`
- **Resource**: `UsesInput`, `RequiresTool`
- **Environmental**: `PrefersSoil`, `IndicatedBy`
- **Protective**: `ThreatenedBy`, `ProtectsFrom`
- **Sequential**: `Precedes`

## 🚀 Quick Start

### Prerequisites

- Python 3.10-3.12
- Docker and Docker Compose
- OpenAI API key
- OpenRouter API key (optional, for alternative models)

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd agro_temporal_kg
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Set up environment variables**:
   Create a `.env` file with:
   ```env
   OPENAI_API_KEY=your_openai_api_key
   OPENROUTER_API_KEY=your_openrouter_api_key
   OPENROUTER_MODEL_NAME=your_preferred_model
   ```

4. **Start the database**:
   ```bash
   docker-compose up -d
   ```

### Basic Usage

```python
import asyncio
from agro_temporal_kg.builder import get_graphiti
from agro_temporal_kg.entities import entity_types, edge_types

async def process_gardening_text():
    # Initialize the knowledge graph
    graphiti = get_graphiti("my-agro-graph")
    
    # Process a text chunk
    result = await graphiti.add_episode(
        name="january-gardening",
        source_description="January gardening tasks from French manual",
        episode_body="In January, sow asparagus seeds in pots...",
        entity_types=entity_types,
        edge_types=edge_types,
        reference_time=datetime(1880, 1, 1)
    )
    
    return result

# Run the processing
asyncio.run(process_gardening_text())
```

## 📁 Project Structure

```
agro_temporal_kg/
├── agro_temporal_kg/           # Main package
│   ├── __init__.py
│   ├── builder.py             # Graphiti configuration
│   └── entities.py            # Entity and relationship definitions
├── scripts/                   # Example scripts
│   ├── test.py               # French gardening text processing
│   └── test_2.py             # Generic entity extraction example
├── tests/                     # Test suite
├── docker-compose.yml         # FalkorDB setup
├── Makefile                   # Development commands
└── pyproject.toml            # Project configuration
```

## 🛠️ Development

### Code Quality

The project uses several tools for code quality:

- **Ruff**: Linting and formatting
- **MyPy**: Type checking
- **Pytest**: Testing framework

Run all checks:
```bash
make run_checks
```

### Database Management

Start FalkorDB with browser interface:
```bash
docker-compose up -d
```

Access the browser at `http://localhost:3000` to explore the graph.

### Testing

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=agro_temporal_kg
```

## 📊 Data Processing Pipeline

1. **Text Input**: Historical gardening texts (e.g., French manuals)
2. **Chunking**: Text is split into manageable chunks with overlap
3. **Entity Extraction**: LLM extracts entities and relationships
4. **Graph Construction**: Entities and relationships are stored in FalkorDB
5. **Querying**: The graph can be queried for agricultural insights

## 🔍 Example Queries

Once your knowledge graph is populated, you can query it for insights:

```python
# Find all plants that should be sown in January
query = """
MATCH (p:Plant)-[r:SowIn]->(t:TimePeriod)
WHERE t.month = 'January'
RETURN p.common_name, r.notes
"""

# Find tasks that protect from frost
query = """
MATCH (task:Task)-[r:ProtectsFrom]->(threat:Threat)
WHERE threat.threat_type = 'weather'
RETURN task.description, r.mechanism
"""
```

## 🌍 Use Cases

- **Historical Agriculture Research**: Analyze historical farming practices
- **Seasonal Planning**: Extract timing information for modern gardening
- **Crop Management**: Understand plant requirements and relationships
- **Knowledge Preservation**: Digitize and structure traditional agricultural knowledge
- **Educational Tools**: Create interactive agricultural learning systems

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run the quality checks: `make run_checks`
5. Submit a pull request

## 📄 License

This project is part of the GOMgraph research initiative. Please refer to the main repository for licensing information.

## 🔗 Related Projects

- [Graphiti](https://github.com/IBM/graphiti): The underlying knowledge graph framework
- [FalkorDB](https://falkordb.com/): The graph database backend
- [GOMgraph](https://github.com/your-org/GOMgraph): The parent research project

## 📞 Support

For questions and support, please open an issue in the repository or contact the maintainers.

---

*Built with ❤️ for agricultural knowledge preservation and research* -->
