#!/usr/bin/env python3
"""Read-only architecture smell checks for Ditto.

Checks only stable, low-noise smells that are already agreed upon and cleaned up:

1. f-string logging calls in source code (use lazy formatting instead)
2. Missing __init__.py in Python package directories
3. Oversized source files (>800 lines)
4. Platform must not contain business table prefixes
5. Production packages must not import ditto_analysis
6. Kernel must not import ditto_platform
7. Packages must not re-export symbols imported from other Ditto packages
8. Execution sqlite legacy storage must not grow permanent modules
9. Apps non-registry modules must not import capability package internals
10. Runtime package __version__ constants must not be reintroduced
11. Data must not own derived feature/factor publication semantics
12. Platform must not contain domain/business vocabulary
13. Active source docstrings/comments must not use stale architecture terms
14. Empty analysis placeholder namespaces must not imply available capability
15. Active architecture docs must not imply reserved analysis capabilities exist
16. Application providers must not read environment variables directly
17. Generic helpers/utils source paths must have owned architecture allowances
18. Every src __init__.py must declare an explicit __all__
19. Experiment sources must not use TYPE_CHECKING to hide import cycles
20. The process provider must declare wiring classes only

Usage:
    python scripts/architecture/check_architecture_smells.py
    python scripts/architecture/check_architecture_smells.py --verbose
"""

import argparse
import ast
import io
import re
import sys
import tokenize
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SRC_ROOTS = [
    ROOT / "packages",
]

MAX_FILE_LINES = 800
MIN_PACKAGE_SOURCE_PATH_PARTS = 5

# Logger methods that should NOT use f-strings (lazy formatting is preferred).
FORBIDDEN_FSTRING_LOG_PATTERNS = (
    "logger.debug(f",
    "logger.info(f",
    "logger.warning(f",
    "logger.error(f",
    "logger.critical(f",
)

# Business table prefixes that must not appear in platform source files.
BUSINESS_TABLE_PREFIXES = (
    "execution_",
    "strategy_",
    "portfolio_",
    "risk_",
    "features_",
)

# Known safe metric/config names in platform that contain business prefixes.
PLATFORM_PREFIX_ALLOWLIST = frozenset(
    {
        "portfolio_value",
        "portfolio_drawdown",
        "portfolio_drawdown_3d",
    }
)

PRODUCTION_PACKAGES = (
    "ditto_data",
    "ditto_features",
    "ditto_strategy",
    "ditto_portfolio",
    "ditto_risk",
    "ditto_execution",
    "ditto_backtest",
    "ditto_application",
)


@dataclass(frozen=True)
class CompositionImportAllowance:
    path: str
    allowed_modules: frozenset[str]
    owner: str
    reason: str


@dataclass(frozen=True)
class ProductionAnalysisWiringAllowance:
    path: str
    owner: str
    reason: str


@dataclass(frozen=True)
class GenericHelperNamespaceAllowance:
    path: str
    owner: str
    reason: str


EXECUTION_SIMULATION_OWNERSHIP_TERMS = (
    "BacktestBrokerage",
    "BrokerageModel",
    "AShareFillModel",
    "SimpleFillModel",
    "ClosingAuctionFillModel",
    "AShareSettlementModel",
    "SimpleSettlementModel",
    "FixedBpsSlippage",
    "VolumeShareSlippage",
)

EXECUTION_SQLITE_LEGACY_STORAGE_PREFIX = (
    "packages/execution/src/ditto_execution/storage/sqlite/legacy/"
)

APPS_REGISTRY_SOURCE_PREFIX = "packages/apps/src/ditto_apps/registry/"

APPS_CAPABILITY_IMPORT_ROOTS = frozenset(
    {
        "ditto_analysis",
        "ditto_backtest",
        "ditto_data",
        "ditto_execution",
        "ditto_features",
        "ditto_portfolio",
        "ditto_risk",
        "ditto_strategy",
    }
)

DATA_FORBIDDEN_SEMANTIC_TERMS = frozenset(
    {
        "features/",
        "factors/",
        "publication_safety",
        "publication_shadow",
        "ditto_data.storage.runtime.publication_safety",
        "ditto_data.storage.runtime.publication_shadow_sqlite",
    }
)

PLATFORM_FORBIDDEN_DOMAIN_TERMS = frozenset(
    {
        "instrument_id",
        "trade_date",
        "factor_",
        "portfolio_",
        "risk.",
        "dq_",
        "golden_dataset",
        "ticker",
    }
)

# Exact semantic ownership exceptions only. Each entry must be tied to a
# design-boundary reason before being added here.
DATA_FORBIDDEN_SEMANTIC_ALLOWLIST: dict[str, frozenset[str]] = {}
PLATFORM_FORBIDDEN_DOMAIN_ALLOWLIST: dict[str, frozenset[str]] = {}

SEMANTIC_SCAN_SKIP_PATH_PARTS = frozenset(
    {
        "tests",
        "docs",
        "migrations",
        "changelog",
        "changelogs",
        "archive",
        "archives",
    }
)

APPS_HOST_COMPOSITION_ALLOWANCES = (
    CompositionImportAllowance(
        path="packages/apps/src/ditto_apps/jobs/context.py",
        allowed_modules=frozenset(
            {
                "ditto_data.quality",
                "ditto_data.quality.protocols",
            }
        ),
        owner="apps Prefect host composition",
        reason=(
            "Prefect task context owns task-level DQ container lookup only; "
            "ordinary routes and jobs must use application facades or registry "
            "composition instead of direct capability imports."
        ),
    ),
    CompositionImportAllowance(
        path="packages/apps/src/ditto_apps/jobs/tasks/monitoring.py",
        allowed_modules=frozenset({"ditto_data.quality.quality_types"}),
        owner="apps ingestion monitoring task",
        reason=(
            "Ingestion monitoring task uses DQResult type annotations for "
            "task signatures; types are frozen dataclasses from the quality "
            "migration (B8.1)."
        ),
    ),
    CompositionImportAllowance(
        path="packages/apps/src/ditto_apps/registry/infra/protocol_adapters.py",
        allowed_modules=frozenset(
            {
                "ditto_data.quality.protocols",
                "ditto_data.services.source_accessor",
                "ditto_data.sources.tdx.source",
                "ditto_data.storage.metadata.instrument",
                "ditto_data.storage.runtime.quality",
                "ditto_features.compile_cache",
            }
        ),
        owner="apps registry Protocol adapter provider",
        reason=(
            "ProtocolAdapterProvider bridges concrete infrastructure types "
            "to Protocol interfaces for DI resolution. This is the composition "
            "root's responsibility — concrete imports are intentional."
        ),
    ),
)

APPS_HOST_COMPOSITION_IMPORT_ALLOWLIST: dict[str, frozenset[str]] = {
    allowance.path: allowance.allowed_modules
    for allowance in APPS_HOST_COMPOSITION_ALLOWANCES
}

APPS_REGISTRY_COMPOSITION_ALLOWANCES = (
    CompositionImportAllowance(
        path="packages/apps/src/ditto_apps/registry/container.py",
        allowed_modules=frozenset(
            {
                "ditto_analysis.di",
                "ditto_data.di",
                "ditto_execution.di",
                "ditto_features.di",
                "ditto_strategy.di",
            }
        ),
        owner="apps registry root container",
        reason=(
            "The registry container is the host composition root for capability "
            "provider sets; ordinary apps modules must use application facades."
        ),
    ),
    CompositionImportAllowance(
        path="packages/apps/src/ditto_apps/registry/contexts/bundle.py",
        allowed_modules=frozenset(
            {
                "ditto_data.sources.exchange_transformers",
                "ditto_strategy.contracts",
            }
        ),
        owner="apps registry context bundle",
        reason=(
            "The context bundle owns typed composition references shared across "
            "registry context factories only."
        ),
    ),
    CompositionImportAllowance(
        path="packages/apps/src/ditto_apps/registry/contexts/ingestion.py",
        allowed_modules=frozenset(
            {
                "ditto_data.catalog",
                "ditto_data.catalog.fallback_policy",
                "ditto_data.ingestion.freeze_store",
                "ditto_data.ingestion.ingestion_cursor_store",
                "ditto_data.ingestion.ingestion_log_store",
                "ditto_data.lineage",
                "ditto_data.services.capital_store",
                "ditto_data.services.fundamental_store",
                "ditto_data.services.macro_service",
                "ditto_data.services.market_service",
                "ditto_data.services.market_write_service",
                "ditto_data.services.metadata_service",
                "ditto_data.services.source_accessor",
                "ditto_data.sources.exchange_transformers",
                "ditto_data.sources.registry",
            }
        ),
        owner="apps ingestion registry context",
        reason=(
            "Ingestion registry context owns data service and runtime policy "
            "Protocol wiring for application ingestion handlers."
        ),
    ),
    CompositionImportAllowance(
        path="packages/apps/src/ditto_apps/registry/contexts/query.py",
        allowed_modules=frozenset(
            {
                "ditto_data.services.capital_store",
                "ditto_data.services.fundamental_store",
                "ditto_data.services.macro_service",
                "ditto_data.services.market_service",
                "ditto_data.services.metadata_service",
            }
        ),
        owner="apps query registry context",
        reason=(
            "Query registry context owns data query service wiring behind "
            "application query facades."
        ),
    ),
    CompositionImportAllowance(
        path="packages/apps/src/ditto_apps/registry/contexts/strategy.py",
        allowed_modules=frozenset(
            {
                "ditto_strategy.storage.sqlite.services.strategy_catalog_service",
                "ditto_strategy.storage.sqlite.services.strategy_run_service",
                "ditto_strategy.governance.service",
                "ditto_strategy.models",
            }
        ),
        owner="apps strategy registry context",
        reason=(
            "Strategy registry context owns concrete strategy storage and "
            "governance wiring (seed draft/publish via GovernanceService plus "
            "StrategySpecRecord construction) for application execution facades."
        ),
    ),
    CompositionImportAllowance(
        path="packages/apps/src/ditto_apps/registry/contexts/r3_recovery.py",
        allowed_modules=frozenset(
            {
                "ditto_analysis.storage.sqlite.experiments",
                "ditto_analysis.storage.sqlite.experiments.schema",
                "ditto_data.config.data_store",
                "ditto_strategy.governance.service",
                "ditto_strategy.storage.sqlite.strategy_governance_schema",
                "ditto_strategy.storage.sqlite.strategy_governance_store",
            }
        ),
        owner="apps R3 recovery composition boundary",
        reason=(
            "The offline recovery verifier owns exact schema inspection and "
            "reopens canonical governance/research adapters after restore; "
            "ordinary apps paths remain on application facades."
        ),
    ),
    CompositionImportAllowance(
        path="packages/apps/src/ditto_apps/registry/infra/protocol_adapters.py",
        allowed_modules=frozenset(
            {
                "ditto_data.quality.protocols",
                "ditto_data.services.source_accessor",
                "ditto_data.sources.tdx.source",
                "ditto_data.storage.metadata.instrument",
                "ditto_data.storage.runtime.quality",
                "ditto_features.compile_cache",
            }
        ),
        owner="apps registry Protocol adapter provider",
        reason=(
            "ProtocolAdapterProvider bridges concrete infrastructure types "
            "to Protocol interfaces for DI resolution. This is the composition "
            "root's responsibility — concrete imports are intentional."
        ),
    ),
    CompositionImportAllowance(
        path="packages/apps/src/ditto_apps/registry/infra/config.py",
        allowed_modules=frozenset(
            {
                "ditto_data.config",
                "ditto_data.config.data_source_validation",
                "ditto_data.config.data_store",
                "ditto_data.quality.config",
                "ditto_features.config",
            }
        ),
        owner="apps registry infrastructure config",
        reason=(
            "Host config initialization owns capability config object assembly; "
            "runtime apps code must consume the resulting settings."
        ),
    ),
    CompositionImportAllowance(
        path="packages/apps/src/ditto_apps/registry/infra/observability.py",
        allowed_modules=frozenset(
            {
                "ditto_backtest.observability.metrics",
                "ditto_data.config.data_store",
                "ditto_data.observability.metrics",
                "ditto_execution.observability.metrics",
                "ditto_features.observability.metrics",
                "ditto_portfolio.observability",
                "ditto_risk.observability.metrics",
                "ditto_strategy.observability.metrics",
            }
        ),
        owner="apps registry observability bootstrap",
        reason=(
            "Host observability bootstrap owns capability metric definition "
            "registration before runtime services start."
        ),
    ),
)

APPS_REGISTRY_COMPOSITION_IMPORT_ALLOWLIST: dict[str, frozenset[str]] = {
    allowance.path: allowance.allowed_modules
    for allowance in APPS_REGISTRY_COMPOSITION_ALLOWANCES
}

PRODUCTION_ANALYSIS_WIRING_ALLOWANCES = (
    ProductionAnalysisWiringAllowance(
        path="packages/application/src/ditto_application/providers.py",
        owner="application DI providers",
        reason=(
            "Application providers wire analysis dependencies into the host "
            "container; ordinary application services and queries must not "
            "directly depend on analysis."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path="packages/application/src/ditto_application/providers_market.py",
        owner="application DI providers",
        reason=(
            "Application market providers wire analysis dependencies into the "
            "host container; ordinary application services and queries must "
            "not directly depend on analysis."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path="packages/application/src/ditto_application/providers_portfolio.py",
        owner="application DI providers",
        reason=(
            "Application portfolio providers are explicit host wiring modules; "
            "ordinary application services and queries must not directly depend "
            "on analysis."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path="packages/application/src/ditto_application/providers_strategy.py",
        owner="application DI providers",
        reason=(
            "Application strategy providers are explicit host wiring modules; "
            "ordinary application services and queries must not directly depend "
            "on analysis."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path="packages/application/src/ditto_application/providers_process.py",
        owner="application research process DI provider",
        reason=(
            "The process composition root wires approved experiment persistence "
            "ports into the application research planning boundary."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/execution/"
            "_research_replay_artifacts.py"
        ),
        owner="application R3 verified replay artifact boundary",
        reason=(
            "The verified-read boundary reuses the analysis-owned immutable "
            "Schema v1 artifact contract through a narrow indexed port; it "
            "performs no storage I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "evidence.py"
        ),
        owner="application R3 review evidence assembler",
        reason=(
            "The pure assembler evaluates the analysis-owned two-layer gate "
            "engine and freezes an immutable review packet; it performs no "
            "storage or execution I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_selection_evidence_artifact.py"
        ),
        owner="application R3 durable selection-evidence boundary",
        reason=(
            "The pre-holdout boundary rebuilds the analysis-owned typed trial "
            "ledger and verifies its immutable Schema v1 indexed artifact; "
            "storage access remains behind approved reader and artifact ports."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "selection_evidence_reader.py"
        ),
        owner="application R3 selection-evidence read boundary",
        reason=(
            "The read-only boundary resolves the content-addressed selection "
            "ledger via the analysis-owned experiment reader contract and "
            "delegates verification to the durable selection-evidence service; "
            "it performs no storage or execution I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "comparison_reader.py"
        ),
        owner="application R3 candidate-comparison read boundary",
        reason=(
            "The read-only boundary reuses the analysis-owned walk-forward "
            "evidence assembler and experiment reader contract to project a "
            "candidate comparison without holdout or review publication; it "
            "performs no storage writes or execution I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/strategy/promotion.py"
        ),
        owner="application R3 strategy promotion process",
        reason=(
            "The promotion process reads the analysis-owned immutable review "
            "packet and gate outcomes to gate a governance publish/activate; "
            "it performs no direct storage I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "coordinator.py"
        ),
        owner="application experiment execution coordinator",
        reason=(
            "The first-run coordinator consumes the analysis-owned Task 7 lease, "
            "fold, and attempt contracts through a narrow application scheduler "
            "store; it owns no persistence implementation."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_coordinator_stage_drivers.py"
        ),
        owner="application experiment stage-progression helpers",
        reason=(
            "The extracted stage-progression helpers drive the analysis-owned "
            "EVIDENCE-stage review-packet collector and failed-candidate fold "
            "cancellation through the same narrow scheduler store as the host "
            "coordinator; they perform no direct storage I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/commands/strategy_governance.py"
        ),
        owner="application R3 evidence-gated publish command boundary",
        reason=(
            "The evidence-gated publish command reads the analysis-owned immutable "
            "review packet through a narrow reader port and forwards it to the "
            "promotion process; it performs no direct storage I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_control_runtime.py"
        ),
        owner="application experiment control runtime",
        reason=(
            "The R3 control-only runtime wires analysis-owned fold/attempt "
            "contracts into the placeholder first-attempt factory, logging "
            "notifier and transient retry-lease helper; it performs no storage "
            "or execution I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "execution_bundle.py"
        ),
        owner="application experiment execution evidence compiler",
        reason=(
            "The pure execution compiler freezes analysis-owned content hashes "
            "and canonical payload identities into the per-attempt evidence bundle; "
            "it performs no storage or execution I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_comparison_evidence.py"
        ),
        owner="application R3 comparison evidence values",
        reason=(
            "The approved R3 evidence boundary validates analysis-owned metric, "
            "identity, and persistence value types without storage writes."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_factor_diagnostics_evidence.py"
        ),
        owner="application R3 factor diagnostics evidence boundary",
        reason=(
            "The read-only lineage envelope binds exact analysis-owned experiment, "
            "fold, snapshot, and content identities to a diagnostics projection."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_oos_fold_registration.py"
        ),
        owner="application R3 OOS fold registration boundary",
        reason=(
            "The immutable registration reuses analysis-owned fold and date-window "
            "value contracts for the approved walk-forward protocol."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_persisted_execution_evidence.py"
        ),
        owner="application R3 persisted execution evidence boundary",
        reason=(
            "The approved read-only authority seam validates exact analysis-owned "
            "fold and terminal-attempt projections loaded through the reader port."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_report_evidence.py"
        ),
        owner="application R3 backtest report evidence boundary",
        reason=(
            "The pure report hasher emits an analysis-owned content identity over "
            "the complete result fields consumed by R3 metrics."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_report_artifact_validation.py"
        ),
        owner="application R3 immutable report artifact validation boundary",
        reason=(
            "The immutable report receipt/read validator directly checks "
            "analysis-owned manifests and canonical byte measurements; it is "
            "pure and performs no storage or file I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_walk_forward_evidence.py"
        ),
        owner="application R3 walk-forward evidence values",
        reason=(
            "The immutable evidence values carry analysis-owned fold and content "
            "identities without persistence or execution I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_walk_forward_evidence_collection.py"
        ),
        owner="application R3 walk-forward evidence collection boundary",
        reason=(
            "The typed read boundary selects exact terminal analysis-owned fold "
            "and attempt projections, then verifies immutable report artifacts "
            "through a narrow reader port; it performs no writes or execution."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_walk_forward_execution_semantics.py"
        ),
        owner="application R3 walk-forward execution-semantics evidence boundary",
        reason=(
            "The narrow resolver validates immutable analysis-owned fold and "
            "attempt identities against exact execution semantics; it performs "
            "no storage writes or execution."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "comparison.py"
        ),
        owner="application R3 candidate comparison process",
        reason=(
            "The approved comparison process binds persisted experiment identities "
            "to versioned analysis-owned metric projections."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "trial_evidence_bridge.py"
        ),
        owner="application R3 trial evidence bridge",
        reason=(
            "The approved bridge converts validated walk-forward evidence into "
            "analysis-owned logical trial outcomes without persistence I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "walk_forward.py"
        ),
        owner="application R3 walk-forward aggregation",
        reason=(
            "The approved aggregation process recomputes analysis-owned metrics "
            "from validated out-of-sample result evidence."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_execution_resolution_evidence.py"
        ),
        owner="application durable research execution evidence boundary",
        reason=(
            "The private evidence boundary reconstructs exact analysis launch and "
            "status DTOs for the builder-owned resolver without storage or "
            "moving-state fallback."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "lease_authority.py"
        ),
        owner="application experiment scheduler lease authority",
        reason=(
            "The serialized authority owns the latest analysis scheduler fence "
            "and normalizes lease and integrity failures before application writes."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "scheduler_store.py"
        ),
        owner="application experiment scheduler persistence adapter",
        reason=(
            "The narrow adapter preserves the analysis-owned Task 7 reader, "
            "writer, revision, and lease-fence contracts for first-run scheduling."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/worker.py"
        ),
        owner="application experiment first-attempt worker",
        reason=(
            "The execution boundary consumes frozen analysis attempt, fold, hash, "
            "and failure contracts while delegating numerical work to BacktestService."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "planning.py"
        ),
        owner="application experiment planning process",
        reason=(
            "The pure work planner reuses the analysis-owned failure-policy value "
            "that is frozen into the approved launch contract; it performs no I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "planning_process.py"
        ),
        owner="application experiment planning process",
        reason=(
            "The approved R3 planning boundary assembles analysis-owned launch "
            "identities and delegates persistence through narrow protocols."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "planning_contracts.py"
        ),
        owner="application experiment planning contracts",
        reason=(
            "The neutral request contract freezes the analysis-owned failure "
            "policy selected by the operator; it contains no orchestration or I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_executor_probe.py"
        ),
        owner="application experiment executor probe boundary",
        reason=(
            "The private probe boundary seals an analysis-owned canonical payload "
            "before and after calling an untrusted executor adapter."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_launch_material.py"
        ),
        owner="application experiment launch material compiler",
        reason=(
            "The private compiler materializes every immutable analysis launch row "
            "before computing the operator-confirmed content hash."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_launch_saga.py"
        ),
        owner="application experiment launch saga",
        reason=(
            "The private launch saga owns exact replay and readback over the "
            "analysis experiment reader and writer protocols."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_launch_reconstruction.py"
        ),
        owner="application experiment launch reconstruction boundary",
        reason=(
            "The private fail-closed codec reconstructs analysis-owned launch, "
            "gate, and fold value rows before the saga's first writer call."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_preflight_codec.py"
        ),
        owner="application experiment preflight codec",
        reason=(
            "The private persisted-report codec verifies analysis-owned fold, "
            "window, failure-policy, and canonical payload identities."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/research_validation_windows.py"
        ),
        owner="application validation protocol compiler",
        reason=(
            "The research validation compiler reuses analysis-owned date-window "
            "and fold-role value contracts without storage or runtime I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path="packages/application/src/ditto_application/queries/experiments.py",
        owner="application experiment query facade",
        reason=(
            "The experiment query facade is the approved application boundary "
            "for durable analysis control-plane reads."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path="packages/application/src/ditto_application/queries/research.py",
        owner="application research query facade",
        reason=(
            "The research query facade is the production-facing boundary for "
            "analysis reads; other application query paths must use that facade "
            "instead of importing analysis directly."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/queries/"
            "research_certification.py"
        ),
        owner="application research certification query adapter",
        reason=(
            "The read-only certification adapter resolves one exact immutable "
            "research snapshot through the approved analysis catalog boundary."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path="packages/application/src/ditto_application/queries/research_helpers.py",
        owner="application research query facade (extracted helpers)",
        reason=(
            "Extracted helper functions for the research query facade; same "
            "analysis import allowance as the parent facade module."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/builders/"
            "research_input_resolver.py"
        ),
        owner="application indexed frozen research inputs resolver",
        reason=(
            "The production resolver reads analysis-owned indexed artifact bytes "
            "through the narrow ResearchArtifactService port and rebuilds the "
            "frozen input trust boundary; it performs no storage I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/builders/"
            "research_artifact_loader.py"
        ),
        owner="application indexed research artifact loader",
        reason=(
            "The production loader reads analysis-owned indexed artifact bytes "
            "through the narrow ResearchArtifactService port and rebuilds "
            "verified frame and instrument-rules trust boundaries; it performs "
            "no storage I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/providers_research_execution.py"
        ),
        owner="application R3 research execution bundle DI provider",
        reason=(
            "The DI provider wires the C1 indexed builders and durable execution "
            "resolver into a complete attempt dispatch graph; it only injects "
            "analysis-owned ExperimentReaderProtocol and ResearchArtifactService "
            "ports that are already registered in the host container."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_evidence_inputs.py"
        ),
        owner="application R3 evidence-input assembly boundary",
        reason=(
            "The pure assembler binds persisted fold and attempt views with their "
            "artifact record and optional backtest report into analysis-owned "
            "CandidateFoldEvidence rows; it performs no storage or execution I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "evidence_collector.py"
        ),
        owner="application R3 review-packet collector",
        reason=(
            "The collector loads one durable experiment snapshot, projects the "
            "persisted preflight detail onto the analysis-owned HardGateEvidenceView, "
            "and freezes the evaluated gates into an immutable ReviewPacket via the "
            "analysis-owned assembler; storage I/O is delegated to the injected "
            "ExperimentReaderProtocol and ExperimentWriterProtocol."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_fold_selection_trace_artifacts.py"
        ),
        owner="application R3 fold-selection-trace artifact contract boundary",
        reason=(
            "The pure typed contract module freezes the analysis-owned attempt, "
            "fold, content-hash, date-window, lease-fence, canonical-payload, and "
            "relative-path value contracts into deterministic artifact identities, "
            "fixed four-record receipts, and narrow publisher/reader/index protocols; "
            "it performs no storage or execution I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_fold_selection_trace_artifact_validation.py"
        ),
        owner="application R3 fold-selection-trace artifact validation boundary",
        reason=(
            "The pure no-I/O validator verifies the four analysis-owned immutable "
            "ArtifactRecord, ContentHash, LeaseFence, ArtifactManifest, and canonical "
            "parquet byte-measurement contracts against canonical selection-evidence "
            "trace frames and the attempt test window; it performs no storage or "
            "execution I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/builders/"
            "fold_selection_trace_artifact_adapter.py"
        ),
        owner="application R3 fold-selection-trace indexed artifact adapter",
        reason=(
            "The indexed builder publishes and reads the four attempt-scoped fold "
            "selection trace Parquet facts through the analysis-owned "
            "ResearchArtifactService and a narrow index-reader port, reusing the "
            "immutable ArtifactRecord, LeaseFence, and ArtifactPublicationSpec value "
            "contracts; storage access remains behind the injected indexed service "
            "and reader ports and the adapter performs no direct storage I/O."
        ),
    ),
)

GENERIC_HELPER_NAMESPACE_ALLOWANCES = (
    GenericHelperNamespaceAllowance(
        path="packages/application/src/ditto_application/config/helpers.py",
        owner="application config",
        reason=(
            "Extracted now_iso() helper; pure utility re-exported by config barrel."
        ),
    ),
    GenericHelperNamespaceAllowance(
        path="packages/application/src/ditto_application/processes/materialization/helpers.py",
        owner="application materialization process",
        reason=(
            "Existing local process helper module; future growth needs "
            "semantic naming review."
        ),
    ),
    GenericHelperNamespaceAllowance(
        path="packages/apps/src/ditto_apps/api/utils/__init__.py",
        owner="apps API adapter",
        reason=(
            "Existing transport adapter utility namespace; future growth needs "
            "semantic naming review."
        ),
    ),
    GenericHelperNamespaceAllowance(
        path="packages/apps/src/ditto_apps/api/utils/identifier.py",
        owner="apps API adapter",
        reason="Existing identifier adapter helpers for API boundaries.",
    ),
    GenericHelperNamespaceAllowance(
        path="packages/apps/src/ditto_apps/cli/utils/__init__.py",
        owner="apps CLI adapter",
        reason=(
            "Existing CLI adapter utility namespace; future growth needs "
            "semantic naming review."
        ),
    ),
    GenericHelperNamespaceAllowance(
        path="packages/apps/src/ditto_apps/cli/utils/identifier.py",
        owner="apps CLI adapter",
        reason="Existing identifier adapter helpers for CLI boundaries.",
    ),
    GenericHelperNamespaceAllowance(
        path="packages/apps/src/ditto_apps/cli/utils/output.py",
        owner="apps CLI adapter",
        reason="Existing CLI output formatting adapter helpers.",
    ),
    GenericHelperNamespaceAllowance(
        path="packages/apps/src/ditto_apps/cli/utils/params.py",
        owner="apps CLI adapter",
        reason="Existing CLI parameter adapter helpers.",
    ),
    GenericHelperNamespaceAllowance(
        path="packages/apps/src/ditto_apps/cli/utils/validation.py",
        owner="apps CLI adapter",
        reason="Existing CLI validation adapter helpers.",
    ),
    GenericHelperNamespaceAllowance(
        path="packages/data/src/ditto_data/helpers/__init__.py",
        owner="data compatibility helpers",
        reason=(
            "Existing data helper namespace; future growth needs semantic "
            "naming review."
        ),
    ),
    GenericHelperNamespaceAllowance(
        path="packages/data/src/ditto_data/helpers/adjustment.py",
        owner="data adjustment helpers",
        reason="Existing data adjustment helper module.",
    ),
    GenericHelperNamespaceAllowance(
        path="packages/data/src/ditto_data/helpers/pit/__init__.py",
        owner="data point-in-time helpers",
        reason="Existing point-in-time helper namespace.",
    ),
    GenericHelperNamespaceAllowance(
        path="packages/data/src/ditto_data/helpers/pit/dataframe.py",
        owner="data point-in-time helpers",
        reason="Existing point-in-time dataframe helper module.",
    ),
    GenericHelperNamespaceAllowance(
        path="packages/data/src/ditto_data/helpers/pit/policy.py",
        owner="data point-in-time helpers",
        reason="Existing point-in-time policy helper module.",
    ),
    GenericHelperNamespaceAllowance(
        path="packages/data/src/ditto_data/helpers/pit/sql.py",
        owner="data point-in-time helpers",
        reason="Existing point-in-time SQL helper module.",
    ),
    GenericHelperNamespaceAllowance(
        path="packages/data/src/ditto_data/sources/tushare/utils/__init__.py",
        owner="data Tushare source adapter",
        reason="Existing source adapter utility namespace.",
    ),
    GenericHelperNamespaceAllowance(
        path="packages/data/src/ditto_data/sources/tushare/utils/http_utils.py",
        owner="data Tushare source adapter",
        reason="Existing source adapter HTTP utility module.",
    ),
    GenericHelperNamespaceAllowance(
        path="packages/data/src/ditto_data/sources/tushare/utils/rate_limiter.py",
        owner="data Tushare source adapter",
        reason="Existing source adapter rate limiting utility module.",
    ),
    GenericHelperNamespaceAllowance(
        path="packages/data/src/ditto_data/utils/__init__.py",
        owner="data compatibility utilities",
        reason=(
            "Existing data utility namespace; future growth needs semantic "
            "naming review."
        ),
    ),
    GenericHelperNamespaceAllowance(
        path="packages/data/src/ditto_data/utils/ticker_utils.py",
        owner="data ticker utilities",
        reason="Existing ticker normalization utility module.",
    ),
    GenericHelperNamespaceAllowance(
        path="packages/data/src/ditto_data/utils/timezone_utils.py",
        owner="data timezone utilities",
        reason="Existing timezone utility module.",
    ),
)

GENERIC_HELPER_NAMESPACE_ALLOWLIST = frozenset(
    allowance.path for allowance in GENERIC_HELPER_NAMESPACE_ALLOWANCES
)

# AI rule files that should use current package names.
AI_RULE_ROOTS = [
    ROOT / "CLAUDE.md",
    ROOT / "AGENTS.md",
    ROOT / ".claude" / "rules",
    ROOT / ".claude" / "commands",
    ROOT / ".claude" / "checklists",
    ROOT / ".factory" / "commands",
]

# Active package docs (CLAUDE.md, README.md under packages/) roots.
PACKAGE_DOC_ROOTS = [
    ROOT / "packages",
]

# Stale package references that should not appear in active AI rules.
STALE_AI_RULE_REFERENCES = (
    "ditto_infra",
    "ditto_interfaces",
    "ditto_app.",  # ditto_application is OK, ditto_app. is stale
    "ditto_analytics",
    "ditto_engine",
    "packages/infra",
    "packages/app/",  # packages/application is OK
    "packages/analytics",
    "packages/engine",
    "interfaces/src",
    "interfaces/tests",
)

# Stale package references that should not appear in active package docs
# (CLAUDE.md, README.md under packages/).
STALE_ACTIVE_PACKAGE_REFERENCES = (
    "ditto_app.",  # ditto_application / ditto_apps are OK
    "ditto_analytics",
    "ditto_engine",
    "ditto_interfaces",
    "ditto_infra",
    "packages/app/",
    "packages/analytics",
    "packages/engine",
    "packages/infra",
    "interfaces/",
    "interfaces/tests",
    "interfaces/src",
    "apps → analytics",
    "analytics →",
    "→ analytics",
    "Analytics",
)

STALE_SOURCE_ARCHITECTURE_TERMS = (
    "Interfaces 层",
    "interfaces/",
    "infra/",
    "analytics layer",
    "engine 层",
)

ANALYSIS_PLACEHOLDER_INIT_PATHS = (
    "packages/analysis/src/ditto_analysis/experiments/__init__.py",
)

EXPERIMENT_APPLICATION_SOURCE_PREFIX = (
    "packages/application/src/ditto_application/processes/experiments/"
)
EXPERIMENT_APPLICATION_SOURCE_PATHS = frozenset(
    {
        "packages/application/src/ditto_application/commands/experiments.py",
        "packages/application/src/ditto_application/queries/experiments.py",
    }
)
TASK8_VALIDATION_AUTHORITY_SOURCE_PATHS = frozenset(
    {
        (
            "packages/application/src/ditto_application/builders/"
            "research_executor_probe.py"
        ),
        (
            "packages/application/src/ditto_application/builders/"
            "research_validation_authority.py"
        ),
        (
            "packages/application/src/ditto_application/"
            "research_certification_contracts.py"
        ),
        ("packages/application/src/ditto_application/research_validation_contracts.py"),
        ("packages/application/src/ditto_application/research_validation_calendar.py"),
        (
            "packages/application/src/ditto_application/"
            "research_validation_eligibility.py"
        ),
        ("packages/application/src/ditto_application/research_validation_protocol.py"),
        ("packages/application/src/ditto_application/research_validation_windows.py"),
    }
)
TYPE_CHECKING_MODULES = frozenset({"typing", "typing_extensions"})
PROCESS_PROVIDER_SOURCE_PATH = (
    "packages/application/src/ditto_application/providers_process.py"
)

ANALYSIS_PLACEHOLDER_ACTIVE_DOC_PATHS = (
    ".claude/rules/architecture.md",
    "CLAUDE.md",
    "README.md",
    "docs/architecture/boundaries-and-abstraction-standards.md",
    "docs/architecture/agent-context-pack.md",
    "packages/apps/README.md",
)

ANALYSIS_PLACEHOLDER_ACTIVE_DOC_GLOBS = ("packages/*/README.md",)

ANALYSIS_PLACEHOLDER_ACTIVE_DOC_STALE_CLAIMS = (
    "纯研究分析（报告、诊断、实验）",  # noqa: RUF001 - exact stale doc phrase
    "报告、诊断、实验、研究数据集",
    "报告、诊断、实验、筛选",
    "研究报告",
    "诊断工具",
    "实验与筛选",
    "研究/报告/诊断",
    "研究/评估",
    "纯研究分析",
    "它描述”报告、诊断、实验、研究”",
    "是否处理报告、诊断、实验、研究",
    "Reports, diagnostics, experiments, research",
    "research / reporting 编排",
)

ANALYSIS_DOC_CONTEXT_ANCHORS = (
    "analysis/",
    "ditto_analysis",
    "packages/analysis",
)

ANALYSIS_DOC_RESERVED_NAMESPACE_CLAIMS = (
    "evaluation/",
    "experiments/",
)

ANALYSIS_DOC_RESERVED_CONTEXT_MARKERS = (
    "reserved",
    "future",
    "not current",
    "no public runtime",
    "保留",
    "未来",
    "不是现有",
    "当前只是",
)

PLACEHOLDER_MISLEADING_AVAILABILITY_PHRASES = (
    "提供",
    "支持",
    "负责",
    "生成",
    "管理",
    "工具",
    "筛选器",
    "available",
    "contains",
    "handles",
    "provides",
    "responsible for",
    "supports",
)

PLACEHOLDER_REQUIRED_RESERVED_PHRASES = (
    "Reserved namespace",
    "future analysis product work",
    "No public runtime API is exported yet",
    "Production code must not import this namespace for behavior",
)


@dataclass(frozen=True)
class CrossPackageExport:
    """A public symbol exported from a package that does not own it."""

    path: str
    exported_name: str
    imported_from: str
    owner_package: str
    source_package: str


def iter_source_files() -> list[Path]:
    """Collect all Python source files under SRC_ROOTS."""
    files: list[Path] = []
    for root in SRC_ROOTS:
        files.extend(root.glob("**/src/**/*.py"))
    return sorted(files)


def _is_package_source(rel_path: str, *packages: str) -> bool:
    if "/tests/" in rel_path:
        return False
    return any(pkg in rel_path for pkg in packages)


def _is_semantic_scan_target(rel_path: str) -> bool:
    return not any(
        part in SEMANTIC_SCAN_SKIP_PATH_PARTS for part in Path(rel_path).parts
    )


def _has_import(source: str, module: str) -> bool:
    return f"from {module}" in source or f"import {module}" in source


def check_fstring_logging(source: str, rel_path: str) -> list[str]:
    """Check for f-string usage in logger calls."""
    errors: list[str] = []
    for pattern in FORBIDDEN_FSTRING_LOG_PATTERNS:
        if pattern in source:
            errors.append(f"{rel_path}: contains {pattern!r}")
    return errors


def check_missing_init_py() -> list[str]:
    """Check for Python directories under src/ that lack __init__.py."""
    errors: list[str] = []
    for root in SRC_ROOTS:
        src_dirs = root.glob("**/src")
        for src_dir in src_dirs:
            for py_dir in src_dir.rglob("*"):
                if not py_dir.is_dir():
                    continue
                if any(
                    skip in py_dir.name
                    for skip in ("__pycache__", ".pixi", ".egg-info", "egg-info")
                ):
                    continue
                init_file = py_dir / "__init__.py"
                if not init_file.exists():
                    has_py = any(py_dir.glob("*.py"))
                    if has_py:
                        errors.append(
                            f"{py_dir.relative_to(ROOT)}: missing __init__.py"
                        )
    return errors


def check_missing_dunder_all(root: Path = ROOT) -> list[str]:
    """Check that every src ``__init__.py`` declares an explicit ``__all__``.

    Forces package surface to be explicit (CLAUDE.md: consumers must import from
    leaf modules; an ``__init__.py`` must not mix re-export with inline
    definitions). Both ``__all__ = [...]`` and ``__all__: list[str] = [...]``
    satisfy this check.
    """
    errors: list[str] = []
    for src_dir in (root / "packages").glob("**/src"):
        for init_file in src_dir.rglob("__init__.py"):
            try:
                tree = ast.parse(init_file.read_text(encoding="utf-8"))
            except SyntaxError:
                errors.append(f"{init_file.relative_to(root)}: cannot parse module")
                continue
            if not any(_is_all_assignment(node) for node in tree.body):
                errors.append(
                    f"{init_file.relative_to(root)}: missing __all__ declaration"
                )
    return errors


def check_oversized_files(line_count: int, rel_path: str) -> list[str]:
    """Check for source files exceeding the line limit."""
    if line_count > MAX_FILE_LINES:
        return [f"{rel_path}: {line_count} lines (max {MAX_FILE_LINES})"]
    return []


def check_platform_business_tables(source: str, rel_path: str) -> list[str]:
    """Check for business table prefixes in platform source files."""
    if not _is_package_source(rel_path, "ditto_platform"):
        return []
    errors: list[str] = []
    for prefix in BUSINESS_TABLE_PREFIXES:
        for quote in ('"', "'"):
            idx = 0
            search_key = f"{quote}{prefix}"
            while True:
                idx = source.find(search_key, idx)
                if idx == -1:
                    break
                end_idx = source.find(quote, idx + 1)
                if end_idx == -1:
                    idx += 1
                    continue
                full_name = source[idx + 1 : end_idx]
                if full_name not in PLATFORM_PREFIX_ALLOWLIST:
                    msg = (
                        f"{rel_path}: platform has business "
                        f"prefix {quote}{prefix}...{quote} "
                        f"({full_name!r})"
                    )
                    errors.append(msg)
                idx = end_idx + 1
    return errors


def _matches_production_analysis_wiring_allowance(rel_path: str) -> bool:
    return any(
        rel_path == allowance.path
        for allowance in PRODUCTION_ANALYSIS_WIRING_ALLOWANCES
    )


def check_production_no_analysis(source: str, rel_path: str) -> list[str]:
    """Check production packages do not import ditto_analysis."""
    if not _is_package_source(rel_path, *PRODUCTION_PACKAGES):
        return []
    if _matches_production_analysis_wiring_allowance(rel_path):
        return []
    if _has_import(source, "ditto_analysis"):
        msg = f"{rel_path}: production imports ditto_analysis (check import-linter)"
        return [msg]
    return []


def check_kernel_no_platform(source: str, rel_path: str) -> list[str]:
    """Check kernel does not import ditto_platform."""
    if not _is_package_source(rel_path, "ditto_kernel"):
        return []
    if _has_import(source, "ditto_platform"):
        msg = f"{rel_path}: kernel imports ditto_platform (must be platform-free)"
        return [msg]
    return []


def check_execution_no_simulation_ownership(source: str, rel_path: str) -> list[str]:
    """Check execution source does not own backtest simulation names."""
    if not _is_package_source(rel_path, "ditto_execution"):
        return []
    return [
        f"{rel_path}: execution owns backtest simulation term {term!r}"
        for term in EXECUTION_SIMULATION_OWNERSHIP_TERMS
        if term in source
    ]


def check_execution_sqlite_legacy_not_extension_point(rel_path: str) -> list[str]:
    """Check execution sqlite legacy storage does not grow permanent modules."""
    if not rel_path.startswith(EXECUTION_SQLITE_LEGACY_STORAGE_PREFIX):
        return []
    return [
        f"{rel_path}: execution sqlite legacy storage is not a permanent "
        "extension point; use ditto_execution.storage.sqlite.trade"
    ]


def _imported_modules_from_source(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                candidate = f"{node.module}.{alias.name}"
                if _repo_python_module_exists(candidate):
                    modules.add(candidate)
                else:
                    modules.add(node.module)
    return modules


def _wildcard_import_modules_from_source(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and any(alias.name == "*" for alias in node.names)
    }


def _repo_python_module_exists(module: str) -> bool:
    module_path = Path(*module.split("."))
    for src_root in (ROOT / "packages").glob("*/src"):
        if (src_root / module_path).with_suffix(".py").is_file():
            return True
        if (src_root / module_path / "__init__.py").is_file():
            return True
    return False


def check_apps_non_registry_capability_imports(source: str, rel_path: str) -> list[str]:
    """Check apps source imports capability internals only from owned composition."""
    if not _is_package_source(rel_path, "ditto_apps"):
        return []

    is_registry = rel_path.startswith(APPS_REGISTRY_SOURCE_PREFIX)
    allowed_modules = (
        APPS_REGISTRY_COMPOSITION_IMPORT_ALLOWLIST.get(rel_path, frozenset())
        if is_registry
        else APPS_HOST_COMPOSITION_IMPORT_ALLOWLIST.get(rel_path, frozenset())
    )
    errors: list[str] = []
    for module in sorted(_wildcard_import_modules_from_source(source)):
        root = module.split(".")[0]
        if root not in APPS_CAPABILITY_IMPORT_ROOTS or module not in allowed_modules:
            continue
        if is_registry:
            errors.append(
                f"{rel_path}: apps registry composition allowance cannot use "
                f"wildcard import from {module!r}; import explicit owned "
                "symbols or protocols"
            )
        else:
            errors.append(
                f"{rel_path}: apps host composition allowance cannot use "
                f"wildcard import from {module!r}; import explicit owned "
                "symbols or protocols"
            )
    for module in sorted(_imported_modules_from_source(source)):
        root = module.split(".")[0]
        if root not in APPS_CAPABILITY_IMPORT_ROOTS or module in allowed_modules:
            continue
        if is_registry:
            errors.append(
                f"{rel_path}: apps registry module imports unowned capability "
                f"package {module!r}; add an owned exact registry composition "
                "allowance or use application facades"
            )
            continue
        errors.append(
            f"{rel_path}: apps non-registry module imports capability package "
            f"{module!r}; use application facades or registry composition"
        )
    return errors


def _is_os_environ_expr(node: ast.AST, os_names: set[str]) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id in os_names
    )


def _is_imported_environ_expr(node: ast.AST, environ_names: set[str]) -> bool:
    return (
        isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id in environ_names
    )


def _environment_expr_kind(
    node: ast.AST,
    os_names: set[str],
    environ_names: set[str],
) -> str | None:
    if _is_os_environ_expr(node, os_names):
        return "os.environ"
    if _is_imported_environ_expr(node, environ_names):
        return "environ"
    return None


def _is_environment_expr_consumed_by_parent(
    node: ast.AST,
    parent_by_node: dict[ast.AST, ast.AST],
) -> bool:
    parent = parent_by_node.get(node)
    return (isinstance(parent, ast.Subscript) and parent.value is node) or (
        isinstance(parent, ast.Attribute) and parent.value is node
    )


def _environment_subscript_read_kind(
    node: ast.Subscript,
    os_names: set[str],
    environ_names: set[str],
) -> str | None:
    return _environment_expr_kind(node.value, os_names, environ_names)


def _environment_attribute_call_read_kind(
    func: ast.Attribute,
    os_names: set[str],
    environ_names: set[str],
) -> str | None:
    if func.attr == "get" and _is_os_environ_expr(func.value, os_names):
        return "os.environ.get"
    if (
        func.attr == "get"
        and isinstance(func.value, ast.Name)
        and func.value.id in environ_names
    ):
        return "environ.get"
    if (
        func.attr == "getenv"
        and isinstance(func.value, ast.Name)
        and func.value.id in os_names
    ):
        return "os.getenv"
    return _environment_expr_kind(func.value, os_names, environ_names)


def _environment_call_read_kind(
    node: ast.Call,
    os_names: set[str],
    environ_names: set[str],
    getenv_names: set[str],
) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        return _environment_attribute_call_read_kind(
            func,
            os_names,
            environ_names,
        )
    if isinstance(func, ast.Name) and func.id in getenv_names:
        return "getenv"
    return None


def _environment_read_kind(
    node: ast.AST,
    os_names: set[str],
    environ_names: set[str],
    getenv_names: set[str],
    parent_by_node: dict[ast.AST, ast.AST],
) -> str | None:
    if isinstance(node, ast.Subscript):
        return _environment_subscript_read_kind(node, os_names, environ_names)
    if isinstance(node, ast.Call):
        return _environment_call_read_kind(
            node,
            os_names,
            environ_names,
            getenv_names,
        )
    if _is_environment_expr_consumed_by_parent(node, parent_by_node):
        return None
    return _environment_expr_kind(node, os_names, environ_names)


def _os_environment_import_names(
    tree: ast.AST,
) -> tuple[set[str], set[str], set[str]]:
    os_names: set[str] = set()
    environ_names: set[str] = set()
    getenv_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                imported_name = alias.asname or alias.name
                if alias.name == "environ":
                    environ_names.add(imported_name)
                elif alias.name == "getenv":
                    getenv_names.add(imported_name)
    return os_names, environ_names, getenv_names


def is_application_provider_module_path(rel_path: str) -> bool:
    """Return whether a source path is an application provider module."""
    path = Path(rel_path)
    return (
        path.parent.as_posix() == "packages/application/src/ditto_application"
        and path.suffix == ".py"
        and (path.name == "providers.py" or path.name.startswith("providers_"))
    )


def check_application_provider_no_environment_reads(
    source: str,
    rel_path: str,
) -> list[str]:
    """Check application provider modules do not read process environment."""
    if not is_application_provider_module_path(rel_path):
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    os_names, environ_names, getenv_names = _os_environment_import_names(tree)
    parent_by_node = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    errors: list[str] = []
    for node in ast.walk(tree):
        kind = _environment_read_kind(
            node,
            os_names,
            environ_names,
            getenv_names,
            parent_by_node,
        )
        if kind is None:
            continue
        errors.append(
            f"{rel_path}: application provider reads environment via {kind}; "
            "route configuration through apps/platform settings"
        )
    return errors


def check_experiment_source_no_type_checking(
    source: str,
    rel_path: str,
) -> list[str]:
    """Reject TYPE_CHECKING imports across the Task 8 planning boundary."""
    if not (
        rel_path.startswith(EXPERIMENT_APPLICATION_SOURCE_PREFIX)
        or rel_path in EXPERIMENT_APPLICATION_SOURCE_PATHS
        or rel_path in TASK8_VALIDATION_AUTHORITY_SOURCE_PATHS
    ):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    imports_type_checking_directly = any(
        isinstance(node, ast.ImportFrom)
        and node.module in TYPE_CHECKING_MODULES
        and any(alias.name == "TYPE_CHECKING" for alias in node.names)
        for node in ast.walk(tree)
    )
    type_checking_module_aliases = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name in TYPE_CHECKING_MODULES
    }
    simple_name_aliases = {
        (target.id, node.value.id)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign | ast.AnnAssign)
        and isinstance(node.value, ast.Name)
        for target in (node.targets if isinstance(node, ast.Assign) else (node.target,))
        if isinstance(target, ast.Name)
    }
    aliases_changed = True
    while aliases_changed:
        aliases_changed = False
        for alias_name, source_name in simple_name_aliases:
            if (
                source_name in type_checking_module_aliases
                and alias_name not in type_checking_module_aliases
            ):
                type_checking_module_aliases.add(alias_name)
                aliases_changed = True
    accesses_type_checking_attribute = any(
        isinstance(node, ast.Attribute)
        and node.attr == "TYPE_CHECKING"
        and isinstance(node.value, ast.Name)
        and node.value.id in type_checking_module_aliases
        for node in ast.walk(tree)
    )
    if not (imports_type_checking_directly or accesses_type_checking_attribute):
        return []
    return [
        f"{rel_path}: experiment source imports TYPE_CHECKING; extract a neutral "
        "contract instead of hiding an import cycle"
    ]


def check_process_provider_wiring_only(
    source: str,
    rel_path: str,
) -> list[str]:
    """Reject public behavior classes declared in the process DI provider."""
    if rel_path != PROCESS_PROVIDER_SOURCE_PATH:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    behavior_classes = (
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and not node.name.startswith("_")
        and node.name != "AppProcessProvider"
    )
    return [
        f"{rel_path}: application process provider declares behavior class "
        f"{class_name!r}; move behavior to its owning query, builder, or process "
        "adapter module"
        for class_name in behavior_classes
    ]


def is_generic_helper_namespace_path(rel_path: str) -> bool:
    """Return whether a production source path uses generic helpers/utils names."""
    parts = Path(rel_path).parts
    if (
        len(parts) < MIN_PACKAGE_SOURCE_PATH_PARTS
        or parts[0] != "packages"
        or parts[2] != "src"
    ):
        return False
    if not rel_path.endswith(".py"):
        return False
    if "tests" in parts:
        return False

    return (
        Path(rel_path).stem in {"helper", "helpers", "util", "utils"}
        or "helpers" in parts
        or "utils" in parts
    )


def check_generic_helper_namespace_allowance(rel_path: str) -> list[str]:
    """Check generic helpers/utils source paths are explicitly allowed."""
    if not is_generic_helper_namespace_path(rel_path):
        return []
    if rel_path in GENERIC_HELPER_NAMESPACE_ALLOWLIST:
        return []
    return [
        f"{rel_path}: generic helpers/utils namespace requires architecture "
        "review; rename to a semantic module or add an owned, reasoned allowance"
    ]


def check_data_no_derived_feature_ownership(source: str, rel_path: str) -> list[str]:
    """Check data source does not own derived feature/factor semantics."""
    if not _is_package_source(rel_path, "ditto_data"):
        return []

    allowed_terms = DATA_FORBIDDEN_SEMANTIC_ALLOWLIST.get(rel_path, frozenset())
    return [
        f"{rel_path}: data owns derived feature semantic term {term!r}; "
        "move ownership to ditto_features/application boundary"
        for term in sorted(DATA_FORBIDDEN_SEMANTIC_TERMS)
        if term in source and term not in allowed_terms
    ]


def check_platform_no_domain_semantics(source: str, rel_path: str) -> list[str]:
    """Check platform source stays free of domain/business semantics."""
    if not _is_package_source(rel_path, "ditto_platform"):
        return []

    allowed_terms = PLATFORM_FORBIDDEN_DOMAIN_ALLOWLIST.get(rel_path, frozenset())
    return [
        f"{rel_path}: platform owns domain semantic term {term!r}; "
        "keep platform as technical infrastructure"
        for term in sorted(PLATFORM_FORBIDDEN_DOMAIN_TERMS)
        if term in source and term not in allowed_terms
    ]


def _iter_source_comment_and_docstring_text(source: str) -> list[str]:
    texts: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(
                node,
                ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
            ):
                docstring = ast.get_docstring(node, clean=False)
                if docstring is not None:
                    texts.append(docstring)

    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT:
                texts.append(token.string)
    except tokenize.TokenError:
        pass
    return texts


def check_source_architecture_terms(source: str, rel_path: str) -> list[str]:
    """Check active source docstrings/comments for stale architecture terms."""
    text = "\n".join(_iter_source_comment_and_docstring_text(source))
    return [
        f"{rel_path}: contains stale source architecture term {term!r}"
        for term in STALE_SOURCE_ARCHITECTURE_TERMS
        if term in text
    ]


def _check_per_file(verbose: bool) -> list[str]:
    """Run per-file checks (f-string logging, oversized files, boundary checks)."""
    errors: list[str] = []
    fstring_count = 0
    oversized_count = 0

    for path in iter_source_files():
        if "__pycache__" in path.parts or ".pixi" in path.parts:
            continue

        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        rel_path = str(path.relative_to(ROOT))
        line_count = len(source.splitlines())

        fstring_errors = check_fstring_logging(source, rel_path)
        if fstring_errors:
            fstring_count += len(fstring_errors)
            errors.extend(fstring_errors)

        oversized_errors = check_oversized_files(line_count, rel_path)
        if oversized_errors:
            oversized_count += len(oversized_errors)
            errors.extend(oversized_errors)

        errors.extend(check_platform_business_tables(source, rel_path))
        errors.extend(check_production_no_analysis(source, rel_path))
        errors.extend(check_kernel_no_platform(source, rel_path))
        errors.extend(check_execution_no_simulation_ownership(source, rel_path))
        errors.extend(check_execution_sqlite_legacy_not_extension_point(rel_path))
        errors.extend(check_apps_non_registry_capability_imports(source, rel_path))
        errors.extend(check_application_provider_no_environment_reads(source, rel_path))
        errors.extend(check_experiment_source_no_type_checking(source, rel_path))
        errors.extend(check_process_provider_wiring_only(source, rel_path))
        errors.extend(check_generic_helper_namespace_allowance(rel_path))
        errors.extend(check_source_architecture_terms(source, rel_path))
        if _is_semantic_scan_target(rel_path):
            errors.extend(check_data_no_derived_feature_ownership(source, rel_path))
            errors.extend(check_platform_no_domain_semantics(source, rel_path))

    if verbose:
        if fstring_count == 0:
            print("[OK] No f-string logging calls found")
        if oversized_count == 0:
            print("[OK] No oversized files found")

    return errors


def check_ai_rule_stale_references() -> list[str]:
    """Check active AI rule files for stale package references."""
    errors: list[str] = []
    for root in AI_RULE_ROOTS:
        if root.is_file():
            files_to_check = [root]
        elif root.is_dir():
            files_to_check = sorted(root.rglob("*.md"))
            files_to_check.extend(sorted(root.rglob("*.py")))
        else:
            continue

        for path in files_to_check:
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = str(path.relative_to(ROOT))
            for stale in STALE_AI_RULE_REFERENCES:
                if stale in content:
                    errors.append(f"{rel}: contains stale AI rule reference {stale!r}")
    return errors


def check_package_doc_stale_references() -> list[str]:
    """Check active package docs (CLAUDE.md, README.md) for stale references."""
    errors: list[str] = []
    for root in PACKAGE_DOC_ROOTS:
        if not root.is_dir():
            continue
        files_to_check: list[Path] = []
        for name in ("CLAUDE.md", "README.md"):
            files_to_check.extend(sorted(root.rglob(name)))
        for path in files_to_check:
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = str(path.relative_to(ROOT))
            for stale in STALE_ACTIVE_PACKAGE_REFERENCES:
                if stale in content:
                    errors.append(f"{rel}: contains stale package reference {stale!r}")
    return errors


_IMPORT_TO_PKG: dict[str, str] = {
    "ditto_kernel": "kernel",
    "ditto_platform": "platform",
    "ditto_data": "data",
    "ditto_features": "features",
    "ditto_strategy": "strategy",
    "ditto_portfolio": "portfolio",
    "ditto_risk": "risk",
    "ditto_execution": "execution",
    "ditto_backtest": "backtest",
    "ditto_analysis": "analysis",
    "ditto_application": "application",
    "ditto_apps": "apps",
}

_PKG_TO_DEP = {v: f"ditto-{v}" for v in _IMPORT_TO_PKG.values()}
_PKG_TO_IMPORT = {v: k for k, v in _IMPORT_TO_PKG.items()}

_EXTERNAL_IMPORT_TO_DEP: dict[str, str] = {
    "cachebox": "cachebox",
    "click": "click",
    "cvxpy": "cvxpy",
    "dishka": "dishka",
    "dotenv": "python-dotenv",
    "duckdb": "duckdb",
    "filelock": "filelock",
    "fastapi": "fastapi",
    "granian": "granian",
    "httpx": "httpx",
    "jinja2": "jinja2",
    "keyring": "keyring",
    "limits": "limits",
    "loguru": "loguru",
    "numpy": "numpy",
    "opentelemetry": "opentelemetry-api",
    "orjson": "orjson",
    "pandas": "pandas",
    "polars": "polars",
    "prefect": "prefect",
    "pydantic": "pydantic",
    "pydantic_settings": "pydantic-settings",
    "rich": "rich",
    "scipy": "scipy",
    "starlette": "starlette",
    "structlog": "structlog",
    "tenacity": "tenacity",
    "typer": "typer",
    "typing_extensions": "typing-extensions",
    "xxhash": "xxhash",
    "yaml": "PyYAML",
}

_EXTERNAL_IMPORT_PREFIX_TO_DEP: tuple[tuple[str, str], ...] = (
    (
        "opentelemetry.exporter.otlp.proto.http",
        "opentelemetry-exporter-otlp-proto-http",
    ),
    ("opentelemetry.sdk", "opentelemetry-sdk"),
    ("opentelemetry", "opentelemetry-api"),
)

_STDLIB_MODULES = frozenset(sys.stdlib_module_names) | frozenset(
    sys.builtin_module_names
)
_DEP_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")

# Exact cross-package export exceptions only. Every entry must include a
# design-boundary reason in the value before it is added here.
_RESEARCH_SCHEDULER_FACADE = (
    "packages/application/src/ditto_application/processes/experiments/"
    "scheduler_store.py"
)
_RESEARCH_SCHEDULER_EXPORTS = frozenset(
    {
        "AttemptId",
        "AttemptView",
        "BacktestRunId",
        "CandidateId",
        "CheckpointRef",
        "ContentHash",
        "ExperimentDesiredState",
        "ExperimentFailureCode",
        "ExperimentId",
        "ExperimentProjection",
        "ExperimentStage",
        "ExperimentStatus",
        "FoldId",
        "FoldKey",
        "FoldView",
        "SchedulerLease",
    }
)
ALLOWED_CROSS_PACKAGE_EXPORTS: dict[tuple[str, str, str], str] = {
    (_RESEARCH_SCHEDULER_FACADE, name, "ditto_analysis.experiments"): (
        "The approved R3 scheduler facade is the sole application boundary for "
        "analysis-owned persistence identities and projections."
    )
    for name in _RESEARCH_SCHEDULER_EXPORTS
}
_MIN_PACKAGE_SOURCE_PARTS = 4

# Leaf public surfaces that have been hardened to expose only local symbols.
# Cross-package dependencies in these files must be imported as private
# implementation aliases, even when they are not listed in __all__.
STRICT_PRIVATE_CROSS_IMPORT_PREFIXES = (
    "packages/execution/src/ditto_execution/reality/",
    "packages/features/src/ditto_features/models/",
)


def _owner_package_for_source(path: Path, root: Path) -> str | None:
    try:
        rel_path = path.relative_to(root)
    except ValueError:
        return None
    if len(rel_path.parts) < _MIN_PACKAGE_SOURCE_PARTS:
        return None
    if rel_path.parts[0] != "packages" or rel_path.parts[2] != "src":
        return None
    return rel_path.parts[1]


def _is_all_target(target: ast.expr) -> bool:
    return isinstance(target, ast.Name) and target.id == "__all__"


def _literal_all_names(value: ast.expr) -> set[str]:
    if not isinstance(value, (ast.List, ast.Tuple)):
        return set()
    names: set[str] = set()
    for elt in value.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            names.add(elt.value)
    return names


def _all_assignment_value(node: ast.stmt) -> ast.expr | None:
    if isinstance(node, ast.Assign) and any(
        _is_all_target(target) for target in node.targets
    ):
        return node.value
    if isinstance(node, ast.AnnAssign) and _is_all_target(node.target):
        return node.value
    return None


def _collect_literal_all_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        value = _all_assignment_value(node)
        if value is not None:
            names.update(_literal_all_names(value))
    return names


def _is_all_assignment(node: ast.stmt) -> bool:
    if isinstance(node, ast.Assign):
        return any(_is_all_target(target) for target in node.targets)
    if isinstance(node, ast.AnnAssign):
        return _is_all_target(node.target)
    return False


def _is_module_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_pure_import_export_shim(tree: ast.Module) -> bool:
    for node in tree.body:
        if _is_module_docstring(node):
            continue
        if isinstance(node, ast.Import | ast.ImportFrom):
            continue
        if _is_all_assignment(node):
            continue
        return False
    return True


def _cross_package_imports(
    tree: ast.Module,
    owner_package: str,
) -> list[tuple[str, str, str]]:
    imports: list[tuple[str, str, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        source_package = _IMPORT_TO_PKG.get(node.module.split(".")[0])
        if source_package is None or source_package == owner_package:
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            imports.append((alias.asname or alias.name, node.module, source_package))
    return imports


def _find_cross_package_exports_in_file(
    path: Path,
    root: Path,
) -> list[CrossPackageExport]:
    owner_package = _owner_package_for_source(path, root)
    if owner_package is None:
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []

    rel_path = path.relative_to(root).as_posix()
    exported_names = _collect_literal_all_names(tree)
    cross_imports = _cross_package_imports(tree, owner_package)
    if not cross_imports:
        return []
    if not exported_names and _is_pure_import_export_shim(tree):
        exported_names = {name for name, _, _ in cross_imports}
    strict_private_imports = rel_path.startswith(STRICT_PRIVATE_CROSS_IMPORT_PREFIXES)

    exports: list[CrossPackageExport] = []
    for exported_name, imported_from, source_package in cross_imports:
        is_explicit_export = exported_name in exported_names
        is_public_strict_import = (
            strict_private_imports and not exported_name.startswith("_")
        )
        if not is_explicit_export and not is_public_strict_import:
            continue
        allow_key = (rel_path, exported_name, imported_from)
        if allow_key in ALLOWED_CROSS_PACKAGE_EXPORTS:
            continue
        exports.append(
            CrossPackageExport(
                path=rel_path,
                exported_name=exported_name,
                imported_from=imported_from,
                owner_package=owner_package,
                source_package=source_package,
            )
        )
    return exports


def find_cross_package_exports(root: Path = ROOT) -> list[CrossPackageExport]:
    """Find unapproved symbols re-exported from other Ditto packages."""
    packages_root = root / "packages"
    if not packages_root.is_dir():
        return []

    exports: list[CrossPackageExport] = []
    for path in sorted(packages_root.glob("*/src/**/*.py")):
        if "__pycache__" in path.parts or "tests" in path.parts:
            continue
        exports.extend(_find_cross_package_exports_in_file(path, root))

    return sorted(
        exports,
        key=lambda item: (
            item.path,
            item.exported_name,
            item.imported_from,
            item.owner_package,
            item.source_package,
        ),
    )


def check_cross_package_exports(root: Path = ROOT) -> list[str]:
    """Check for unapproved cross-package re-exports."""
    return [
        (
            f"{export.path}: cross-package re-export {export.exported_name!r} "
            f"from {export.imported_from!r} "
            f"({export.owner_package} re-exports {export.source_package})"
        )
        for export in find_cross_package_exports(root)
    ]


def _has_non_empty_literal_all(tree: ast.Module) -> bool:
    return bool(_collect_literal_all_names(tree))


def check_analysis_placeholder_honesty(root: Path = ROOT) -> list[str]:
    """Check empty analysis placeholders do not imply available capability."""
    errors: list[str] = []
    for rel_path in ANALYSIS_PLACEHOLDER_INIT_PATHS:
        path = root / rel_path
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"{rel_path}: cannot inspect placeholder docstring ({exc})")
            continue

        if _has_non_empty_literal_all(tree):
            continue

        docstring = ast.get_docstring(tree, clean=False) or ""
        folded_docstring = docstring.casefold()
        for phrase in PLACEHOLDER_REQUIRED_RESERVED_PHRASES:
            if phrase.casefold() not in folded_docstring:
                errors.append(
                    f"{rel_path}: empty analysis placeholder docstring is "
                    f"missing required reserved placeholder phrase {phrase!r}; "
                    "empty placeholders must advertise reservation, no public "
                    "runtime API, and no production behavior dependency"
                )
        for phrase in PLACEHOLDER_MISLEADING_AVAILABILITY_PHRASES:
            if phrase in folded_docstring:
                errors.append(
                    f"{rel_path}: empty analysis placeholder docstring contains "
                    f"misleading availability phrase {phrase!r}; mark it reserved "
                    "until a public __all__ contract exists"
                )
    return errors


def _analysis_placeholder_active_doc_paths(root: Path) -> tuple[str, ...]:
    rel_paths = set(ANALYSIS_PLACEHOLDER_ACTIVE_DOC_PATHS)
    for pattern in ANALYSIS_PLACEHOLDER_ACTIVE_DOC_GLOBS:
        for path in root.glob(pattern):
            if path.is_file():
                rel_paths.add(path.relative_to(root).as_posix())
    return tuple(sorted(rel_paths))


def _is_reserved_analysis_doc_context(text: str) -> bool:
    folded = text.casefold()
    return any(
        marker.casefold() in folded for marker in ANALYSIS_DOC_RESERVED_CONTEXT_MARKERS
    )


def _has_analysis_doc_anchor(text: str) -> bool:
    folded = text.casefold()
    return any(anchor.casefold() in folded for anchor in ANALYSIS_DOC_CONTEXT_ANCHORS)


def _analysis_placeholder_stale_claim_errors(
    rel_path: str,
    line_no: int,
    line: str,
) -> list[str]:
    errors: list[str] = []
    if _is_reserved_analysis_doc_context(line):
        return errors
    folded_line = line.casefold()
    for phrase in ANALYSIS_PLACEHOLDER_ACTIVE_DOC_STALE_CLAIMS:
        if phrase.casefold() not in folded_line:
            continue
        errors.append(
            f"{rel_path}:{line_no}: active docs imply reserved "
            f"analysis capability "
            f"{phrase!r}; describe research control-plane as current and "
            "reports/diagnostics/experiments/screeners as reserved/future"
        )
    return errors


def _analysis_placeholder_namespace_claim_errors(
    rel_path: str,
    line_no: int,
    lines: list[str],
) -> list[str]:
    line = lines[line_no - 1]
    errors: list[str] = []
    for namespace in ANALYSIS_DOC_RESERVED_NAMESPACE_CLAIMS:
        if namespace.casefold() not in line.casefold():
            continue
        context = "\n".join(lines[max(0, line_no - 4) : min(len(lines), line_no + 1)])
        if not _has_analysis_doc_anchor(context):
            continue
        if _is_reserved_analysis_doc_context(context):
            continue
        errors.append(
            f"{rel_path}:{line_no}: active docs list reserved or "
            f"absent analysis namespace {namespace!r}; describe "
            "research control-plane as current and "
            "reports/diagnostics/experiments/screeners as reserved/future"
        )
    return errors


def check_analysis_placeholder_active_docs(root: Path = ROOT) -> list[str]:
    """Check active docs do not claim reserved analysis capabilities exist."""
    errors: list[str] = []
    for rel_path in _analysis_placeholder_active_doc_paths(root):
        path = root / rel_path
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{rel_path}: cannot inspect active analysis docs ({exc})")
            continue

        lines = content.splitlines()
        for line_no, line in enumerate(lines, start=1):
            errors.extend(
                _analysis_placeholder_stale_claim_errors(rel_path, line_no, line)
            )
            errors.extend(
                _analysis_placeholder_namespace_claim_errors(rel_path, line_no, lines)
            )
    return errors


def _scan_pkg_imports(src_dir: Path, pkg_name: str) -> set[str]:
    """Scan actual internal ditto-* imports from a package's src/."""
    actual: set[str] = set()
    for py_file in src_dir.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for mod in mods:
                dep = _IMPORT_TO_PKG.get(mod.split(".")[0])
                if dep and dep != pkg_name:
                    actual.add(_PKG_TO_DEP[dep])
    return actual


def _normalize_dep_name(name: str) -> str:
    """Normalize distribution names for dependency metadata comparisons."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared_dependency_names(pyproject: Path) -> set[str]:
    """Read normalized project dependency names from pyproject.toml."""
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    declared: set[str] = set()
    for dependency in data.get("project", {}).get("dependencies", []):
        match = _DEP_NAME_RE.match(str(dependency))
        if match:
            declared.add(_normalize_dep_name(match.group(1)))
    return declared


def _package_local_top_level_modules(src_dir: Path) -> set[str]:
    """Collect import roots owned by a package's own src/ tree."""
    modules: set[str] = set()
    for child in src_dir.iterdir():
        if child.name == "__pycache__":
            continue
        if child.is_file() and child.suffix == ".py" and child.stem != "__init__":
            modules.add(child.stem)
        elif child.is_dir() and (child / "__init__.py").exists():
            modules.add(child.name)
    return modules


def _external_dependency_for_module(module: str) -> str:
    """Map an import module name to its distribution dependency name."""
    for prefix, dependency in _EXTERNAL_IMPORT_PREFIX_TO_DEP:
        if module == prefix or module.startswith(f"{prefix}."):
            return dependency
    root = module.split(".", maxsplit=1)[0]
    return _EXTERNAL_IMPORT_TO_DEP.get(root, root)


def _is_optional_import_guard(handler: ast.excepthandler) -> bool:
    """Return True when an except handler catches missing optional imports."""
    if any(isinstance(node, ast.Raise) for node in ast.walk(handler)):
        return False
    error = handler.type
    if error is None:
        return False
    if isinstance(error, ast.Name):
        return error.id in {"ImportError", "ModuleNotFoundError"}
    if isinstance(error, ast.Tuple):
        return any(
            isinstance(elt, ast.Name)
            and elt.id in {"ImportError", "ModuleNotFoundError"}
            for elt in error.elts
        )
    return False


def _optional_import_nodes(tree: ast.AST) -> set[ast.AST]:
    """Find import nodes inside try bodies guarded by ImportError handlers."""
    optional_nodes: set[ast.AST] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not any(_is_optional_import_guard(handler) for handler in node.handlers):
            continue
        for body_node in node.body:
            for nested in ast.walk(body_node):
                if isinstance(nested, ast.Import | ast.ImportFrom):
                    optional_nodes.add(nested)
    return optional_nodes


def _external_imports_in_file(path: Path, local_modules: set[str]) -> set[str]:
    """Scan direct external import roots from one Python source file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()

    optional_imports = _optional_import_nodes(tree)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if node in optional_imports:
            continue
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0 or node.module is None:
                continue
            modules = [node.module]

        for module in modules:
            root = module.split(".")[0]
            if (
                root in local_modules
                or root in _STDLIB_MODULES
                or root == "__future__"
                or root.startswith("ditto_")
            ):
                continue
            imports.add(_external_dependency_for_module(module))
    return imports


def _is_external_runtime_import_source(path: Path) -> bool:
    """Return whether a source file should contribute runtime dependencies."""
    return (
        "__pycache__" not in path.parts
        and "tests" not in path.parts
        and (path.name != "testing.py")
    )


def _scan_external_pkg_imports(src_dir: Path) -> set[str]:
    """Scan direct runtime external dependencies imported from a package's src/."""
    local_modules = _package_local_top_level_modules(src_dir)
    deps: set[str] = set()
    for py_file in sorted(src_dir.rglob("*.py")):
        if not _is_external_runtime_import_source(py_file):
            continue
        for import_root in _external_imports_in_file(py_file, local_modules):
            deps.add(import_root)
    return deps


def check_external_package_metadata(root: Path) -> list[str]:
    """Check package pyproject.toml deps declare direct external runtime imports."""
    errors: list[str] = []
    for pkg_dir in sorted((root / "packages").iterdir()):
        if not pkg_dir.is_dir():
            continue
        pyproject = pkg_dir / "pyproject.toml"
        src_dir = pkg_dir / "src"
        if not pyproject.exists() or not src_dir.is_dir():
            continue

        actual = _scan_external_pkg_imports(src_dir)
        declared = _declared_dependency_names(pyproject)
        missing = [
            dep for dep in sorted(actual) if _normalize_dep_name(dep) not in declared
        ]
        if missing:
            errors.append(
                f"{pyproject.relative_to(root)}: "
                f"missing external runtime dependencies {missing}"
            )
    return errors


def _check_version_mismatch(
    pyproject: Path,
    src_dir: Path,
    pkg_dir_name: str,
    pyproject_version: str | None,
    root: Path,
) -> list[str]:
    """Check _version.py matches pyproject.toml version."""
    if not pyproject_version:
        return []
    import_pkg = _PKG_TO_IMPORT.get(pkg_dir_name, pkg_dir_name.replace("-", "_"))
    version_file = src_dir / import_pkg / "_version.py"
    if not version_file.exists():
        return []
    for line in version_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            src_ver = line.split("=")[1].strip().strip("\"'")
            if src_ver != pyproject_version:
                msg = (
                    f"{pyproject.relative_to(root)}:"
                    f" version {pyproject_version}"
                    f" != {version_file.relative_to(root)} {src_ver}"
                )
                return [msg]
            break
    return []


def check_runtime_package_versions_removed(root: Path) -> list[str]:
    """Check package roots do not duplicate package metadata as __version__."""
    errors: list[str] = []
    for pkg_dir in sorted((root / "packages").iterdir()):
        if not pkg_dir.is_dir():
            continue
        src_dir = pkg_dir / "src"
        import_pkg = _PKG_TO_IMPORT.get(pkg_dir.name, pkg_dir.name.replace("-", "_"))
        pkg_root = src_dir / import_pkg
        if not pkg_root.is_dir():
            continue
        version_file = pkg_root / "_version.py"
        if version_file.exists():
            errors.append(
                f"{version_file.relative_to(root)}: remove runtime _version.py; "
                "use package metadata instead"
            )
        init_file = pkg_root / "__init__.py"
        if init_file.exists() and "__version__" in init_file.read_text(
            encoding="utf-8"
        ):
            errors.append(
                f"{init_file.relative_to(root)}: remove runtime __version__; "
                "use package metadata instead"
            )

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        version_files = (
            data.get("tool", {}).get("commitizen", {}).get("version_files", [])
        )
        bad_entries = [
            str(entry)
            for entry in version_files
            if "__version__" in str(entry) or "_version.py" in str(entry)
        ]
        if bad_entries:
            errors.append(
                "pyproject.toml: commitizen version_files must not manage "
                f"runtime package versions {bad_entries}"
            )
    return errors


def check_package_metadata(root: Path) -> list[str]:
    """Check pyproject.toml deps match actual source imports."""
    errors: list[str] = []
    for pkg_dir in sorted((root / "packages").iterdir()):
        if not pkg_dir.is_dir():
            continue
        pyproject = pkg_dir / "pyproject.toml"
        src_dir = pkg_dir / "src"
        if not pyproject.exists() or not src_dir.is_dir():
            continue

        actual = _scan_pkg_imports(src_dir, pkg_dir.name)
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        declared = set(data.get("project", {}).get("dependencies", []))

        missing = actual - declared
        stale = declared - actual - {d for d in declared if not d.startswith("ditto-")}
        if missing:
            errors.append(
                f"{pyproject.relative_to(root)}: missing dependencies {sorted(missing)}"
            )
        if stale:
            errors.append(
                f"{pyproject.relative_to(root)}: stale dependencies {sorted(stale)}"
            )

        pv = data.get("project", {}).get("version")
        errors.extend(
            _check_version_mismatch(pyproject, src_dir, pkg_dir.name, pv, root)
        )
    return errors


def _collect(errors: list[str], new: list[str], ok_msg: str, verbose: bool) -> None:
    if new:
        errors.extend(new)
    elif verbose:
        print(ok_msg)


# ============ Route Maturity Annotations ============

# Non-initial-focus routes must declare maturity in their module docstring.
_ROUTE_MATURITY_EXPECTED: dict[str, str] = {
    "capital.py": "experimental",
    "commodity.py": "experimental",
    "fundamental.py": "experimental",
    "fx.py": "experimental",
    "macro.py": "experimental",
    "ingestion.py": "infrastructure",
    "source.py": "infrastructure",
    "debug.py": "debug",
}

_ROUTES_DIR = "packages/apps/src/ditto_apps/api/routes"


def check_route_maturity_annotations(root: Path = ROOT) -> list[str]:
    """Check non-initial-focus route modules declare maturity in docstring."""
    errors: list[str] = []
    for filename, expected_level in _ROUTE_MATURITY_EXPECTED.items():
        path = root / _ROUTES_DIR / filename
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"{_ROUTES_DIR}/{filename}: cannot parse ({exc})")
            continue
        docstring = ast.get_docstring(tree, clean=False) or ""
        if f"maturity: {expected_level}" not in docstring:
            errors.append(
                f"{_ROUTES_DIR}/{filename}: module docstring must declare "
                + f"'maturity: {expected_level}' (capability-maturity.md)",
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Architecture smell checks for Ditto")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose output including passing checks",
    )
    args = parser.parse_args()

    errors: list[str] = []

    # Check 1: Missing __init__.py
    _collect(
        errors,
        check_missing_init_py(),
        "[OK] All package directories have __init__.py",
        args.verbose,
    )

    # Check 2: src __init__.py must declare an explicit __all__
    _collect(
        errors,
        check_missing_dunder_all(ROOT),
        "[OK] All src __init__.py declare an explicit __all__",
        args.verbose,
    )

    # Check 2: Per-file checks
    errors.extend(_check_per_file(args.verbose))

    # Check: AI rule stale references
    _collect(
        errors,
        check_ai_rule_stale_references(),
        "[OK] No stale AI rule references found",
        args.verbose,
    )

    # Check: Package doc stale references
    _collect(
        errors,
        check_package_doc_stale_references(),
        "[OK] No stale package doc references found",
        args.verbose,
    )

    # Check: Cross-package re-exports
    _collect(
        errors,
        check_cross_package_exports(ROOT),
        "[OK] No cross-package re-exports found",
        args.verbose,
    )

    # Check: Empty analysis placeholders do not imply available capability
    _collect(
        errors,
        check_analysis_placeholder_honesty(ROOT),
        "[OK] Empty analysis placeholders are explicit reservations",
        args.verbose,
    )

    # Check: Active architecture docs do not imply reserved analysis capability
    _collect(
        errors,
        check_analysis_placeholder_active_docs(ROOT),
        "[OK] Active architecture docs treat analysis placeholders as reserved",
        args.verbose,
    )

    # Check: Runtime package __version__ removed
    _collect(
        errors,
        check_runtime_package_versions_removed(ROOT),
        "[OK] Runtime package __version__ constants are absent",
        args.verbose,
    )

    # Check: Package metadata matches source imports
    _collect(
        errors,
        check_package_metadata(ROOT),
        "[OK] Package metadata matches source imports",
        args.verbose,
    )
    _collect(
        errors,
        check_external_package_metadata(ROOT),
        "[OK] Package metadata declares external runtime imports",
        args.verbose,
    )

    # Check: Route maturity annotations
    _collect(
        errors,
        check_route_maturity_annotations(ROOT),
        "[OK] API route maturity annotations are present and consistent",
        args.verbose,
    )

    if errors:
        print("\nArchitecture smell check failed:\n")
        for error in errors:
            print(f"  {error}")
        print(f"\nTotal issues: {len(errors)}")
        return 1

    print("Architecture smell check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
