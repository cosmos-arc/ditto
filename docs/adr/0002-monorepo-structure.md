# 0002 - Monorepo Structure

Status: Accepted

Date: 2024-01-01

## Context

Ditto consists of multiple components that share code:
- Data access layer (datahub)
- Business logic (core)
- Shared utilities (foundation)
- API server
- Web UI

We need to organize these components while allowing code sharing and independent versioning.

## Decision

We adopt a **monorepo with package separation** structure:

```
ditto/
├── interfaces/      # Application entry (API/CLI/Jobs + DI Composition Root)
├── packages/
│   ├── engine/      # Core engine (alpha/portfolio/backtest/execution/risk)
│   ├── data/        # Data access layer (storage/sources/query/quality)
│   ├── app/         # Application orchestration (CQRS: query/process/command)
│   ├── analytics/   # Expression compilation + materialization + factors + research
│   ├── kernel/      # Shared kernel (zero-dependency types)
│   └── infra/       # Infrastructure (config, observability, cache, etc.)
├── config/          # Environment configuration
├── data/            # Data storage
├── docs/            # Documentation
└── scripts/         # Utility scripts
```

### Key Principles

1. **Editable installation**: Local packages installed in editable mode
2. **Import path**: All packages use `from ditto_xxx import` style
3. **Independent testing**: Each package has its own test directory
4. **Shared dependencies**: Managed via pixi workspaces

## Consequences

### Positive
- **Code sharing**: Foundation package shared across all components
- **Atomic commits**: Changes across multiple packages in one commit
- **Unified CI**: Single pipeline for all code
- **Simplified dependency management**: pixi handles cross-package dependencies

### Negative
- **Larger repository**: All code in one place
- **Longer CI**: Testing all packages takes more time
- **Slower git operations**: Large monorepo has more history

## Alternatives Considered

### Multi-repo (one repo per package)
**Rejected**: Too much overhead for small team. Code sharing becomes complex with separate repos and versioning.

### Single package (everything in ditto-core)
**Rejected**: No clear boundaries. Would violate separation of concerns and make testing harder.

### Submodule approach
**Rejected**: Git submodules add complexity and are error-prone for our use case.

## Related Decisions

- [ADR 0001 - Project Stack Selection](0001-project-stack-selection.md)
