#!/usr/bin/env python3
"""Read-only architecture smell checks for Ditto.

Enforces dependency, package metadata and runtime ownership boundaries.
Naming, line counts and wording belong in review, not the machine gate.

Usage:
    python scripts/architecture/check_architecture_smells.py
    python scripts/architecture/check_architecture_smells.py --verbose
"""

import argparse
import ast
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SRC_ROOTS = [
    ROOT / "packages",
    ROOT / "apps" / "backend",
]

MIN_PACKAGE_SOURCE_PATH_PARTS = 5
MIN_BACKEND_SOURCE_PATH_PARTS = 4

# Logger methods that should NOT use f-strings (lazy formatting is preferred).

# Business table prefixes that must not appear in platform source files.

# Known safe metric/config names in platform that contain business prefixes.

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

APPS_REGISTRY_SOURCE_PREFIX = "apps/backend/src/ditto_apps/registry/"

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


# Exact semantic ownership exceptions only. Each entry must be tied to a
# design-boundary reason before being added here.


APPS_HOST_COMPOSITION_ALLOWANCES = (
    CompositionImportAllowance(
        path="apps/backend/src/ditto_apps/jobs/context.py",
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
        path="apps/backend/src/ditto_apps/jobs/tasks/monitoring.py",
        allowed_modules=frozenset({"ditto_data.quality.quality_types"}),
        owner="apps ingestion monitoring task",
        reason=(
            "Ingestion monitoring task uses DQResult type annotations for "
            "task signatures; types are frozen dataclasses from the quality "
            "migration (B8.1)."
        ),
    ),
    CompositionImportAllowance(
        path="apps/backend/src/ditto_apps/registry/infra/protocol_adapters.py",
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
        path=("apps/backend/src/ditto_apps/scripts/r5_sandbox_live_acceptance.py"),
        allowed_modules=frozenset(
            {
                "ditto_analysis.experiments.generated_code",
                "ditto_analysis.experiments.models",
            }
        ),
        owner="apps Approval A3 physical acceptance entrypoint",
        reason=(
            "The explicit operator-run A3 entrypoint constructs Analysis-owned "
            "generated-code fixtures and binds them to the registry OCI adapter; "
            "ordinary API, CLI, and job modules remain behind Application facades."
        ),
    ),
    CompositionImportAllowance(
        path="apps/backend/src/ditto_apps/scripts/q2_live_market_context.py",
        allowed_modules=frozenset(
            {
                "ditto_data.catalog.certification",
                "ditto_data.catalog.metadata",
                "ditto_data.catalog.provider_payload",
                "ditto_data.catalog.source_snapshot",
            }
        ),
        owner="apps isolated Q2 live acceptance entrypoint",
        reason=(
            "The operator-run Q2 acceptance composes exact retained provider "
            "payloads and certification authorities under an isolated data root."
        ),
    ),
    CompositionImportAllowance(
        path=("apps/backend/src/ditto_apps/scripts/q3_live_discovery_support.py"),
        allowed_modules=frozenset(
            {
                "ditto_data.catalog.certification",
                "ditto_data.catalog.provider_payload",
                "ditto_data.catalog.source_snapshot",
            }
        ),
        owner="apps isolated Q3 live discovery composition",
        reason=(
            "The operator-run Q3 acceptance resolves exact provider snapshots, "
            "payloads, and certifications before invoking application facades."
        ),
    ),
    CompositionImportAllowance(
        path=("apps/backend/src/ditto_apps/scripts/q3_live_discovery.py"),
        allowed_modules=frozenset(
            {
                "ditto_data.catalog.certification",
                "ditto_data.catalog.provider_payload",
                "ditto_data.catalog.source_snapshot",
            }
        ),
        owner="apps isolated Q3 live discovery entrypoint",
        reason=(
            "The operator-run Q3 acceptance resolves exact provider snapshots, "
            "payloads, and certifications before invoking application facades."
        ),
    ),
    CompositionImportAllowance(
        path=("apps/backend/src/ditto_apps/scripts/q5_live_agent_author_support.py"),
        allowed_modules=frozenset({"ditto_strategy.models"}),
        owner="apps isolated Q5 Author acceptance composition",
        reason=(
            "The operator-run Q5 acceptance validates the model proposal against "
            "the strategy-owned canonical record before exposing an approval hash."
        ),
    ),
)

APPS_HOST_COMPOSITION_IMPORT_ALLOWLIST: dict[str, frozenset[str]] = {
    allowance.path: allowance.allowed_modules
    for allowance in APPS_HOST_COMPOSITION_ALLOWANCES
}

APPS_REGISTRY_COMPOSITION_ALLOWANCES = (
    CompositionImportAllowance(
        path="apps/backend/src/ditto_apps/registry/research_case.py",
        allowed_modules=frozenset({"ditto_analysis.research.cases"}),
        owner="apps ResearchCase composition adapter",
        reason=(
            "The composition root converts an Application-owned SelectionRun "
            "handoff contract into the isolated Analysis ResearchCase domain; "
            "ordinary application processes never import Analysis."
        ),
    ),
    CompositionImportAllowance(
        path="apps/backend/src/ditto_apps/registry/fresh_runtime.py",
        allowed_modules=frozenset(
            {
                "ditto_analysis.storage.sqlite.experiments",
                "ditto_data.config.data_store",
                "ditto_execution.di",
            }
        ),
        owner="apps greenfield runtime composition root",
        reason=(
            "The pre-launch fresh-runtime builder composes authenticated "
            "current-schema "
            "storage owners into one empty isolated data root; ordinary API, CLI, and "
            "job modules remain behind application facades."
        ),
    ),
    CompositionImportAllowance(
        path="apps/backend/src/ditto_apps/registry/infra/trading_storage.py",
        allowed_modules=frozenset(
            {
                "ditto_data.config.data_store",
                "ditto_execution.di",
            }
        ),
        owner="apps trading recovery-unit composition",
        reason=(
            "The composition adapter owns the dedicated trading SQLite pool and "
            "binds execution storage to it; ordinary Apps consumers remain behind "
            "Application contracts."
        ),
    ),
    CompositionImportAllowance(
        path="apps/backend/src/ditto_apps/registry/performance_probes.py",
        allowed_modules=frozenset(
            {
                "ditto_data.catalog.certification",
                "ditto_features.technical_analysis.contracts",
                "ditto_features.technical_analysis.service",
                "ditto_portfolio.portfolio_comparison",
                "ditto_strategy.selection.contracts",
                "ditto_strategy.selection.pipeline",
            }
        ),
        owner="apps OPS-09 performance probe composition",
        reason=(
            "The evidence-only composition probe invokes exact deterministic "
            "capability paths under explicit p95 budgets; the generic benchmark "
            "harness contains no capability imports."
        ),
    ),
    CompositionImportAllowance(
        path="apps/backend/src/ditto_apps/registry/agent/provider.py",
        allowed_modules=frozenset({"ditto_analysis.experiments.campaign_persistence"}),
        owner="apps governed Agent provider",
        reason=(
            "The Agent composition provider binds the Analysis-owned durable "
            "Campaign reader to the Apps-owned transport runtime; feature and "
            "command consumers remain behind Application contracts."
        ),
    ),
    CompositionImportAllowance(
        path="apps/backend/src/ditto_apps/registry/agent/campaign_runtime.py",
        allowed_modules=frozenset(
            {
                "ditto_analysis.errors",
                "ditto_analysis.experiments.campaign_persistence",
                "ditto_analysis.experiments.models",
            }
        ),
        owner="apps governed Campaign runtime adapter",
        reason=(
            "The physical composition adapter projects Analysis-owned persisted "
            "Campaign facts through an Application-owned public runtime and joins "
            "them to Agent-owned durable idempotency records."
        ),
    ),
    CompositionImportAllowance(
        path="apps/backend/src/ditto_apps/registry/agent/oci_sandbox.py",
        allowed_modules=frozenset(
            {
                "ditto_analysis.experiments.generated_code",
                "ditto_analysis.experiments.models",
                "ditto_analysis.experiments.persistence",
            }
        ),
        owner="apps generated-candidate OCI sandbox adapter",
        reason=(
            "The physical composition adapter binds the Analysis-owned generated-code, "
            "resource-limit, manifest, and content-hash contracts to an "
            "Application-owned sandbox port; no ordinary Apps module may import these "
            "capability types."
        ),
    ),
    CompositionImportAllowance(
        path="apps/backend/src/ditto_apps/registry/agent/oci_sandbox_runner.py",
        allowed_modules=frozenset({"ditto_analysis.experiments.models"}),
        owner="apps generated-candidate OCI process runner",
        reason=(
            "The shell-free physical runner verifies Analysis-owned content hashes "
            "at the final Docker invocation boundary next to the approved adapter."
        ),
    ),
    CompositionImportAllowance(
        path=("apps/backend/src/ditto_apps/registry/agent/r5_sandbox_live_report.py"),
        allowed_modules=frozenset(
            {
                "ditto_analysis.experiments.generated_code",
                "ditto_analysis.experiments.models",
            }
        ),
        owner="apps Approval A3 evidence verifier",
        reason=(
            "The registry verifier reconstructs Analysis-owned manifests and "
            "content hashes to authenticate physical OCI acceptance evidence."
        ),
    ),
    CompositionImportAllowance(
        path="apps/backend/src/ditto_apps/registry/container.py",
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
        path="apps/backend/src/ditto_apps/registry/contexts/bundle.py",
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
        path="apps/backend/src/ditto_apps/registry/contexts/ingestion.py",
        allowed_modules=frozenset(
            {
                "ditto_data.catalog",
                "ditto_data.catalog.fallback_policy",
                "ditto_data.catalog.provider_payload",
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
        path="apps/backend/src/ditto_apps/registry/contexts/query.py",
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
        path="apps/backend/src/ditto_apps/registry/contexts/strategy.py",
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
        path="apps/backend/src/ditto_apps/registry/contexts/r3_recovery.py",
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
        path="apps/backend/src/ditto_apps/registry/infra/protocol_adapters.py",
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
        path="apps/backend/src/ditto_apps/registry/infra/config.py",
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
        path="apps/backend/src/ditto_apps/registry/infra/observability.py",
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
    CompositionImportAllowance(
        path="apps/backend/src/ditto_apps/registry/infra/risk_persistence.py",
        allowed_modules=frozenset({"ditto_risk.continuous_gate"}),
        owner="apps R4 risk persistence composition adapter",
        reason=(
            "The SQLite composition adapter reconstructs the risk-owned canonical "
            "snapshot type behind the application persistence port; schema and "
            "runtime consumers remain isolated from risk implementation modules."
        ),
    ),
    CompositionImportAllowance(
        path=("apps/backend/src/ditto_apps/registry/live/r2_live_certification.py"),
        allowed_modules=frozenset(
            {
                "ditto_data.catalog",
                "ditto_data.catalog.certification",
                "ditto_data.catalog.metadata",
                "ditto_data.catalog.source_snapshot",
            }
        ),
        owner="apps isolated R2 live certification composition",
        reason=(
            "Task 18 certification binds registry-resolved catalog, provider "
            "snapshot, and application governance ports for one isolated root."
        ),
    ),
    CompositionImportAllowance(
        path=("apps/backend/src/ditto_apps/registry/live/r3_live_snapshot_builder.py"),
        allowed_modules=frozenset(
            {
                "ditto_analysis.research.artifact_service",
                "ditto_analysis.research.catalog_service",
                "ditto_analysis.research.records",
                "ditto_data.catalog.certification",
                "ditto_data.catalog.source_snapshot",
            }
        ),
        owner="apps isolated R3 live snapshot composition",
        reason=(
            "Task 18 freezes analysis artifacts against exact active data "
            "certifications and provider snapshots in the isolated live root."
        ),
    ),
    CompositionImportAllowance(
        path=("apps/backend/src/ditto_apps/registry/live/r3_live_planning_builder.py"),
        allowed_modules=frozenset(
            {
                "ditto_analysis.experiments",
                "ditto_analysis.experiments.promotion_objective",
                "ditto_analysis.experiments.trial_ledger",
                "ditto_analysis.research.artifact_service",
                "ditto_analysis.research.catalog_service",
                "ditto_backtest.context_inputs",
                "ditto_data.catalog.certification",
                "ditto_data.catalog.source_snapshot",
                "ditto_strategy.alpha.seeds",
                "ditto_strategy.models",
                "ditto_strategy.storage.sqlite.services.strategy_catalog_service",
            }
        ),
        owner="apps isolated R3 live planning composition",
        reason=(
            "Task 18 composes frozen analysis planning inputs with the canonical "
            "seed catalog and exact certified live snapshot identities."
        ),
    ),
    CompositionImportAllowance(
        path=("apps/backend/src/ditto_apps/registry/live/r3_live_acceptance_driver.py"),
        allowed_modules=frozenset(
            {
                "ditto_analysis.research.artifact_service",
                "ditto_analysis.research.catalog_service",
                "ditto_data.catalog.certification",
                "ditto_data.catalog.source_snapshot",
                "ditto_strategy.storage.sqlite.services.strategy_catalog_service",
            }
        ),
        owner="apps isolated R3 live acceptance composition",
        reason=(
            "Task 18 owns the explicit production-port composition for golden "
            "lane, governance, and recovery evidence over an isolated root."
        ),
    ),
    CompositionImportAllowance(
        path=(
            "apps/backend/src/ditto_apps/registry/live/"
            "q4_live_account_acceptance_runtime.py"
        ),
        allowed_modules=frozenset(
            {
                "ditto_execution.paper.session",
                "ditto_execution.paper.sqlite_store",
                "ditto_execution.storage.sqlite.account_journal",
                "ditto_portfolio.account_ledger",
                "ditto_portfolio.account_projection",
            }
        ),
        owner="apps Q4/PAP-09 account acceptance composition",
        reason=(
            "The exact-approval acceptance runtime composes canonical Manual and "
            "Paper storage with Application handlers for an isolated, Paper-only "
            "evidence root; the CLI and ordinary Apps paths stay on Application "
            "contracts and the registry-owned runtime."
        ),
    ),
    CompositionImportAllowance(
        path=(
            "apps/backend/src/ditto_apps/registry/live/"
            "q4_accelerated_paper_acceptance_runtime.py"
        ),
        allowed_modules=frozenset({"ditto_execution.storage.sqlite.account_journal"}),
        owner="apps PAP-09 accelerated acceptance composition",
        reason=(
            "The exact-approval replay runtime creates its isolated Paper account "
            "against the canonical execution journal before delegating every day "
            "to the shared Q4 production Paper path."
        ),
    ),
    CompositionImportAllowance(
        path=(
            "apps/backend/src/ditto_apps/registry/live/"
            "q5_live_portfolio_acceptance_runtime.py"
        ),
        allowed_modules=frozenset(
            {
                "ditto_backtest.data_feed",
                "ditto_data.catalog",
                "ditto_data.catalog.provider_payload",
                "ditto_data.catalog.source_snapshot",
                "ditto_execution.paper.session",
                "ditto_portfolio.account_projection",
                "ditto_strategy.storage.sqlite.services.strategy_run_service",
            }
        ),
        owner="apps Q5 live portfolio acceptance composition",
        reason=(
            "The exact-approval acceptance runtime binds one frozen provider "
            "payload and snapshot to the published strategy, canonical Paper and "
            "Manual projections, EOD lifecycle, and read-only comparison evidence; "
            "ordinary API and CLI paths remain behind Application contracts."
        ),
    ),
    CompositionImportAllowance(
        path=(
            "apps/backend/src/ditto_apps/registry/live/q5_live_portfolio_proposal.py"
        ),
        allowed_modules=frozenset(
            {
                "ditto_backtest.data_feed",
                "ditto_data.services.metadata_service",
            }
        ),
        owner="apps Q5 live portfolio proposal composition",
        reason=(
            "The read-only proposal boundary resolves the published universe "
            "through canonical metadata and evaluates its exact provider slice "
            "before freezing the operator approval request."
        ),
    ),
    CompositionImportAllowance(
        path=(
            "apps/backend/src/ditto_apps/registry/live/"
            "q4_live_account_acceptance_store.py"
        ),
        allowed_modules=frozenset({"ditto_execution.storage.sqlite.account_journal"}),
        owner="apps Q4/PAP-09 acceptance recovery storage composition",
        reason=(
            "The restart-safe acceptance helper inspects the same isolated "
            "Manual journal composed by the Q4 runtime so interrupted receipt "
            "writes recover immutable account identity without replay drift."
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
            "packages/application/src/ditto_application/providers_research_memory.py"
        ),
        owner="R5 research-memory DI provider",
        reason=(
            "The dedicated composition boundary wires Analysis-owned Campaign "
            "persistence ports into PIT read and governed mutation facades."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/commands/campaign_manifest.py"
        ),
        owner="application governed Campaign manifest command boundary",
        reason=(
            "The strict command builder compiles an explicit public document into "
            "Analysis-owned immutable Campaign values without storage or execution I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=("packages/application/src/ditto_application/commands/research_memory.py"),
        owner="R5 governed research-memory command boundary",
        reason=(
            "The command boundary validates Analysis-owned immutable memory facts "
            "before append-only writes; Agent consumers use pure leaf contracts."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=("packages/application/src/ditto_application/queries/research_memory.py"),
        owner="R5 PIT research-memory query boundary",
        reason=(
            "The query boundary projects Analysis-owned PIT facts into a pure, "
            "content-addressed Application read model."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/research_memory_contracts.py"
        ),
        owner="R5 research-memory mutation contracts",
        reason=(
            "Human-approved promote and revoke commands retain the Analysis-owned "
            "scope and content-hash value types at the governed write boundary."
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
            "packages/application/src/ditto_application/processes/experiments/"
            "_coordinator_vocabulary.py"
        ),
        owner="application experiment coordinator snapshot vocabulary",
        reason=(
            "The extracted vocabulary binds the analysis-owned experiment, "
            "fold and attempt status enums into the immutable "
            "SnapshotVocabulary consumed by the host coordinator and its "
            "result builder; it performs no storage or execution I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_scheduler_models.py"
        ),
        owner="application experiment scheduler value models",
        reason=(
            "The extracted frozen dataclasses validate durable scheduler "
            "invariants against the analysis-owned attempt, fold and "
            "projection contracts at the boundary consumed by the scheduler "
            "store, coordinator and worker; they perform no storage I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/queries/"
            "_experiment_review_read_models.py"
        ),
        owner="application R3 review-packet read models",
        reason=(
            "The extracted read models and builder derive an "
            "application-owned view of the analysis-owned immutable "
            "ReviewPacket through its narrow gate-evaluation contract; they "
            "perform no storage or execution I/O."
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
            "_creation_identity.py"
        ),
        owner="application experiment creation identity fence",
        reason=(
            "The private fail-closed boundary validates the analysis-owned "
            "revision-zero event and reader projection before planning probes."
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
            "_launch_contracts.py"
        ),
        owner="application experiment launch immutable contracts",
        reason=(
            "The extracted contracts carry the analysis-owned immutable launch "
            "rows shared by compilation, strict replay, and persistence."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_launch_durable_reconstruction.py"
        ),
        owner="application experiment durable launch reconstruction",
        reason=(
            "The strict readback boundary reconstructs analysis-owned launch, "
            "gate, and fold rows before any durable enqueue can be replayed."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_launch_idempotency.py"
        ),
        owner="application experiment launch idempotency boundary",
        reason=(
            "The mutation boundary binds and verifies durable receipts over the "
            "analysis-owned experiment event and projection contracts."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_mutation_receipts.py"
        ),
        owner="application experiment control receipt boundary",
        reason=(
            "The typed receipt boundary validates analysis-owned status events "
            "and persists control responses through the approved scheduler port."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_planning_launch.py"
        ),
        owner="application experiment durable planning launch",
        reason=(
            "The extracted mutation path replays and persists analysis-owned "
            "experiment launch contracts after read-only preflight planning."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_scheduler_mutations.py"
        ),
        owner="application experiment scheduler mutation store",
        reason=(
            "The extracted mutation store implements exact operator transition "
            "and fold retry operations over the approved analysis persistence ports."
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
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_autonomous_campaign_contracts.py"
        ),
        owner="application governed Campaign contract boundary",
        reason=(
            "The immutable Campaign contracts bind analysis-owned campaign, metric, "
            "lease, and statistical-trial values into the finite authorization and "
            "scheduler ports consumed by the host coordinator; they perform no I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_autonomous_campaign_authorization.py"
        ),
        owner="application governed Campaign authorization lifecycle",
        reason=(
            "The private lifecycle boundary freezes Analysis-owned Campaign drafts "
            "and binds exact human authority before coordinator execution; all "
            "persistence remains behind injected protocols."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "_autonomous_campaign_support.py"
        ),
        owner="application governed Campaign persistence boundary",
        reason=(
            "The private support boundary reconstructs and validates exact "
            "analysis-owned campaign, lineage, ledger, and lease facts through "
            "injected reader and writer protocols; it owns no storage implementation."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "autonomous_campaign.py"
        ),
        owner="application governed Campaign coordinator",
        reason=(
            "The host-owned coordinator applies immutable authorization, finite "
            "budgets, stopping, cancellation, and crash recovery over analysis-owned "
            "campaign facts through narrow injected ports."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "campaign_scheduler.py"
        ),
        owner="application governed Campaign scheduler adapter",
        reason=(
            "The adapter maps Campaign trial and retry requests onto the existing "
            "analysis-owned R3 fold matrix and lease fence through the established "
            "application scheduler-store protocol."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "candidate_sandbox_port.py"
        ),
        owner="application generated-candidate sandbox contract boundary",
        reason=(
            "The consumer-owned port binds raw sandbox I/O and attestations to "
            "analysis-owned research-code, snapshot, and resource-limit values; "
            "it performs no sandbox or storage I/O."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "generated_candidate_evaluator.py"
        ),
        owner="application trusted generated-candidate evaluator",
        reason=(
            "The host-owned evaluator validates untrusted code and score artifacts "
            "before handing typed scores to the existing numerical authority; it "
            "consumes analysis-owned campaign identities without storage access."
        ),
    ),
    ProductionAnalysisWiringAllowance(
        path=(
            "packages/application/src/ditto_application/processes/experiments/"
            "generated_candidate_pit.py"
        ),
        owner="application generated-candidate PIT evaluation boundary",
        reason=(
            "The host-owned feed materializes one exact analysis-owned fold and "
            "snapshot behind an injected row-reader port, then supplies frozen "
            "PIT windows to a fresh sandbox without owning storage I/O."
        ),
    ),
)


# AI rule files that should use current package names.

# Active package docs (CLAUDE.md, README.md under packages/) roots.

# Stale package references that should not appear in active AI rules.

# Stale package references that should not appear in active package docs
# (CLAUDE.md, README.md under packages/).


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


def _has_import(source: str, module: str) -> bool:
    return any(
        imported == module or imported.startswith(f"{module}.")
        for imported in _imported_modules_from_source(source)
    )


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


def _check_per_file() -> list[str]:
    """Run executable source and runtime boundary checks."""
    errors: list[str] = []

    for path in iter_source_files():
        if "__pycache__" in path.parts or ".pixi" in path.parts:
            continue

        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        rel_path = str(path.relative_to(ROOT))
        errors.extend(check_production_no_analysis(source, rel_path))
        errors.extend(check_kernel_no_platform(source, rel_path))
        errors.extend(check_execution_no_simulation_ownership(source, rel_path))
        errors.extend(check_execution_sqlite_legacy_not_extension_point(rel_path))
        errors.extend(check_apps_non_registry_capability_imports(source, rel_path))
        errors.extend(check_application_provider_no_environment_reads(source, rel_path))
        errors.extend(check_experiment_source_no_type_checking(source, rel_path))
        errors.extend(check_process_provider_wiring_only(source, rel_path))

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
    "ditto_agent": "agent",
    "ditto_apps": "apps",
}

_PKG_TO_DEP = {v: f"ditto-{v}" for v in _IMPORT_TO_PKG.values()}
_PKG_TO_IMPORT = {v: k for k, v in _IMPORT_TO_PKG.items()}

_EXTERNAL_IMPORT_TO_DEP: dict[str, str] = {
    "agents": "openai-agents",
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
    errors.extend(_check_per_file())

    # Check: Cross-package re-exports
    _collect(
        errors,
        check_cross_package_exports(ROOT),
        "[OK] No cross-package re-exports found",
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
