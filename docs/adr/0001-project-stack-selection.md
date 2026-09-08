# 0001 - Project Stack Selection

Status: Accepted（工具链于 2026-09-06 按 #101 修订）

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
- **Python 3.13**: Primary language for codebase
- **TypeScript/React/Vite**: Web UI

### Data Processing
- **Polars**: Primary data manipulation library (chosen over Pandas)
- **DuckDB**: SQL engine for analytics queries
- **SQLite**: Metadata storage and transactional data

### Application Framework
- **FastAPI**: API server
- **Prefect 3.x**: Workflow orchestration for data ingestion

### Package & Environment Management
- **uv**: Python workspace and a shared lock; PyPI wheels on the three supported platforms
- **Task**: Root cross-stack task graph
- **Bun + Node LTS**: Bun installs Web dependencies and runs Bun-specific scripts; pinned Node runs Node CLIs
- **pyproject.toml**: Standard Python project configuration

### Quality & Testing
- **Ruff**: Linting and formatting
- **Pyright**: Static type checking
- **Pytest**: Testing framework
- **Pre-commit hooks**: Automated quality checks

### Observability
- **Loguru**: Structured logging
- **OpenTelemetry**: Tracing and metrics
- **VictoriaMetrics**: Metrics storage

## Consequences

### Positive
- **Polars** provides 10-100x faster data processing than Pandas
- **uv** locks Python dependencies across supported platforms
- **Monorepo structure** allows code sharing between packages
- **Strict type checking** catches errors early
- **Comprehensive observability** aids debugging

### Negative
- **Polars** has a smaller ecosystem than Pandas (fewer third-party integrations)
- Native PyPI wheels must be validated on each supported platform; Conda ABI assumptions do not transfer
- **Strict type checking** requires more upfront development time
- **Windows-only** deployment limits collaboration options

## Alternatives Considered

### Pandas vs Polars
**Rejected**: Pandas is slower and uses more memory. While it has a larger ecosystem, Polars' performance advantages are critical for our use case.

### uv and Task
The current 13-package workspace has no demonstrated Conda-only runtime requirement. uv owns Python packaging; Task preserves the cross-stack DAG. Native wheels and actual API/solver behavior remain release gates. Bun is retained for installation efficiency and existing Bun APIs; its Node CLI execution and lock drift are checked explicitly.

### Airflow vs Prefect
**Rejected**: Airflow is too heavy for a single-user Windows system. Prefect 3.x is more lightweight and has better Python-native workflows.

### Django vs FastAPI
**Rejected**: Django is too heavyweight for our needs. FastAPI provides async support and automatic API docs with less boilerplate.

## Related Decisions

- [ADR 0002 - Monorepo Structure](0002-monorepo-structure.md)
- [ADR 0003 - Data Storage Strategy](0003-data-storage-strategy.md)
