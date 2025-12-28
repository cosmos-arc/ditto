# 0001 - Project Stack Selection

Status: Accepted

Date: 2024-01-01

## Context

Building a quantitative trading system requires careful technology selection. The system must:
- Handle large volumes of time-series data efficiently
- Support complex numerical computations
- Provide reliable backtesting capabilities
- Integrate with external data sources
- Run on Windows (single-user environment)

## Decision

We selected the following technology stack:

### Core Languages & Frameworks
- **Python 3.11+**: Primary language for codebase
- **TypeScript/Next.js**: Web UI (future)

### Data Processing
- **Polars**: Primary data manipulation library (chosen over Pandas)
- **DuckDB**: SQL engine for analytics queries
- **SQLite**: Metadata storage and transactional data

### Application Framework
- **FastAPI**: API server
- **Prefect 3.x**: Workflow orchestration for data ingestion

### Package & Environment Management
- **Pixi**: Cross-platform package management (replaces conda/pip)
- **pyproject.toml**: Standard Python project configuration

### Quality & Testing
- **Ruff**: Linting and formatting
- **MyPy**: Static type checking
- **Pytest**: Testing framework
- **Pre-commit hooks**: Automated quality checks

### Observability
- **Loguru**: Structured logging
- **OpenTelemetry**: Tracing and metrics
- **VictoriaMetrics**: Metrics storage

## Consequences

### Positive
- **Polars** provides 10-100x faster data processing than Pandas
- **Pixi** ensures reproducible environments across platforms
- **Monorepo structure** allows code sharing between packages
- **Strict type checking** catches errors early
- **Comprehensive observability** aids debugging

### Negative
- **Polars** has a smaller ecosystem than Pandas (fewer third-party integrations)
- **Pixi** is relatively new, less mature than conda
- **Strict type checking** requires more upfront development time
- **Windows-only** deployment limits collaboration options

## Alternatives Considered

### Pandas vs Polars
**Rejected**: Pandas is slower and uses more memory. While it has a larger ecosystem, Polars' performance advantages are critical for our use case.

### Conda vs Pixi
**Rejected**: Conda is slower to solve environments and has more complex configuration. Pixi uses the same conda-forge packages but with faster dependency resolution.

### Poetry vs Pixi
**Rejected**: Poetry doesn't support conda packages well, which we need for some scientific computing libraries.

### Airflow vs Prefect
**Rejected**: Airflow is too heavy for a single-user Windows system. Prefect 3.x is more lightweight and has better Python-native workflows.

### Django vs FastAPI
**Rejected**: Django is too heavyweight for our needs. FastAPI provides async support and automatic API docs with less boilerplate.

## Related Decisions

- [ADR 0002 - Monorepo Structure](0002-monorepo-structure.md)
- [ADR 0003 - Data Storage Strategy](0003-data-storage-strategy.md)
