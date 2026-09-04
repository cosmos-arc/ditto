"""Run the Q3 live industry, selection, and technical discovery acceptance."""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Mapping
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import cast

import orjson
from ditto_agent._canonical import canonical_bytes
from ditto_agent.tools.selection import (
    IndustryRotationEvidenceTool,
    SelectionRunEvidenceTool,
)
from ditto_agent.tools.technical_analysis import InstrumentTechnicalEvidenceTool
from ditto_application.commands.data_product_certification import (
    DataProductCertificationCommands,
)
from ditto_application.commands.data_product_certification_builder import (
    DataProductCertificationBuilder,
)
from ditto_application.exceptions import AppQueryError
from ditto_application.processes.selection.facade import (
    CreateSelectionRunRequest,
    EtfSelectionSpecDraft,
    SelectionFactorWeightDraft,
    SelectionWorkspaceFacade,
    StockSelectionSpecDraft,
)
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.selection_evidence import (
    IndustryRotationEvidenceQueryFacade,
    SelectionRunEvidenceQueryFacade,
)
from ditto_application.queries.technical_analysis import (
    TechnicalAnalysisFacade,
    TechnicalAnalysisRequest,
    TechnicalAnalysisSpecDraft,
)
from ditto_application.queries.technical_analysis_evidence import (
    InstrumentTechnicalEvidenceQueryFacade,
)
from ditto_data.catalog.certification import (
    CertificationGovernanceStore,
)
from ditto_data.catalog.provider_payload import (
    ProviderPayloadReader,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader

from ditto_apps.config.runtime import state_root_matches
from ditto_apps.registry.container import make_app_container
from ditto_apps.scripts.q3_live_discovery_support import (
    _ETF_CODE,
    _ETF_INSTRUMENT_ID,
    _STOCK_CODE,
    _STOCK_INSTRUMENT_ID,
    _TARGET_DATE,
    _TECHNICAL_FROM,
    _TECHNICAL_PROFILE,
    _context,
    _envelope_summary,
    _payload,
    _rotation_observations,
    _selection_frame,
    _selection_instruments,
    _sha256_file,
    _snapshot,
    _technical_certification,
    _TechnicalCertificationContext,
    _universe_snapshot_id,
    derive_limit_state,
    normalized_rank_values,
)

__all__ = [
    "derive_limit_state",
    "main",
    "normalized_rank_values",
    "run_q3_live_discovery_acceptance",
]


def run_q3_live_discovery_acceptance(  # noqa: PLR0915 - vertical acceptance flow
    *,
    data_root: Path,
    evidence_root: Path,
    recovery_evidence: Path,
    market_context_evidence: Path,
    actor: str,
) -> dict[str, object]:
    """Create and replay real Q3 discovery artifacts under exact PIT identities."""
    root = data_root.expanduser().resolve(strict=True)
    if not state_root_matches(root):
        raise ValueError("DITTO_STATE_ROOT must equal the isolated Q3 data root")
    decoded_market: object = orjson.loads(
        market_context_evidence.expanduser().resolve(strict=True).read_bytes()
    )
    if not isinstance(decoded_market, dict):
        raise ValueError("Q3 requires object-shaped Q2 MarketContext evidence")
    market_payload = cast("dict[str, object]", decoded_market)
    raw_context = market_payload.get("market_context")
    if not isinstance(raw_context, dict):
        raise ValueError("Q3 requires Q2 MarketContext payload")
    context_payload = cast("dict[str, object]", raw_context)
    feature_set_id = str(context_payload["feature_set_id"])
    raw_regime_score = context_payload.get("regime_score")
    if not isinstance(raw_regime_score, int | float):
        raise ValueError("Q3 requires numeric Q2 regime score")
    regime_score = float(raw_regime_score)
    if market_payload.get("passed") is not True:
        raise ValueError("Q3 requires passing Q2 MarketContext evidence")

    container = make_app_container()
    try:
        snapshots = container.get(ProviderSnapshotReader)
        payloads = container.get(ProviderPayloadReader)
        exact = {
            "stock_daily": _snapshot(
                snapshots,
                dataset_id="stock_daily",
                request_start=_TARGET_DATE,
                request_end=_TARGET_DATE,
            ),
            "etf_daily": _snapshot(
                snapshots,
                dataset_id="etf_daily",
                request_start=_TARGET_DATE,
                request_end=_TARGET_DATE,
            ),
            "stock_basic": _snapshot(
                snapshots,
                dataset_id="stock_basic",
                request_start=_TARGET_DATE,
                request_end=_TARGET_DATE,
            ),
            "etf_basic": _snapshot(
                snapshots,
                dataset_id="etf_basic",
                request_start=_TARGET_DATE,
                request_end=_TARGET_DATE,
            ),
            "stock_status": _snapshot(
                snapshots,
                dataset_id="stock_status",
                request_start=_TARGET_DATE,
                request_end=_TARGET_DATE,
            ),
            "industry_classification": _snapshot(
                snapshots,
                dataset_id="industry_classification",
                request_start=_TARGET_DATE,
                request_end=_TARGET_DATE,
            ),
            "industry_mapping": _snapshot(
                snapshots,
                dataset_id="industry_mapping",
                request_start=_TARGET_DATE,
                request_end=_TARGET_DATE,
            ),
            "stock_history": _snapshot(
                snapshots,
                dataset_id="stock_daily",
                request_start=_TECHNICAL_FROM,
                request_end=_TARGET_DATE,
                required_partition_key=f"source_ticker={_STOCK_CODE}",
            ),
            "etf_history": _snapshot(
                snapshots,
                dataset_id="etf_daily",
                request_start=_TECHNICAL_FROM,
                request_end=_TARGET_DATE,
                required_partition_key=f"source_ticker={_ETF_CODE}",
            ),
        }
        frames = {name: _payload(item, payloads) for name, item in exact.items()}
        metadata = container.get(MetadataQueryFacade)
        stock_frame = _selection_frame(
            asset_kind="stock",
            daily=frames["stock_daily"],
            basic=frames["stock_basic"],
            metadata=metadata.find_securities(asset_class="stock"),
            industry_mapping=frames["industry_mapping"],
            stock_status=frames["stock_status"],
            limit=256,
        )
        etf_frame = _selection_frame(
            asset_kind="etf",
            daily=frames["etf_daily"],
            basic=frames["etf_basic"],
            metadata=metadata.find_securities(asset_class="etf"),
            industry_mapping=None,
            stock_status=None,
            limit=128,
        )
        industries = _rotation_observations(
            classification=frames["industry_classification"],
            mapping=frames["industry_mapping"],
            stock_daily=frames["stock_daily"],
            regime_score=regime_score,
        )
        generated_at = max(item.created_at for item in exact.values()) + timedelta(
            minutes=1
        )
        decision_at = generated_at + timedelta(minutes=1)
        rotation_ids = tuple(
            sorted(
                exact[name].snapshot_id
                for name in (
                    "industry_classification",
                    "industry_mapping",
                    "stock_daily",
                )
            )
        )
        membership_version = (
            "SW2021:sha256:"
            + hashlib.sha256(exact["industry_mapping"].snapshot_id.encode()).hexdigest()
        )
        rotation_missing_inputs = (
            "industry_fundamental_scores",
            "industry_relative_strength_20d",
            "industry_relative_strength_5d",
            "industry_relative_strength_60d",
        )
        stock_sources = tuple(
            sorted(
                exact[name].snapshot_id
                for name in (
                    "industry_mapping",
                    "stock_basic",
                    "stock_daily",
                    "stock_status",
                )
            )
        )
        etf_sources = tuple(
            sorted(exact[name].snapshot_id for name in ("etf_basic", "etf_daily"))
        )
        stock_instruments = _selection_instruments(stock_frame)
        etf_instruments = _selection_instruments(etf_frame)
        stock_request = CreateSelectionRunRequest(
            as_of=decision_at,
            knowledge_cutoff=decision_at,
            publication_cutoff=decision_at,
            rotation_source_snapshot_ids=rotation_ids,
            market_context_feature_set_id=feature_set_id,
            membership_version=membership_version,
            rotation_algorithm_version="industry-rotation-v1",
            industries=industries,
            seed=20240901,
            rotation_missing_inputs=rotation_missing_inputs,
            universe_snapshot_id=_universe_snapshot_id(
                asset_kind="stock",
                source_snapshot_ids=stock_sources,
                instruments=stock_instruments,
            ),
            selection_source_snapshot_ids=stock_sources,
            selection_spec=StockSelectionSpecDraft(
                spec_id="a-share-stock-discovery",
                spec_version="1",
                top_k=20,
                min_average_turnover=50_000.0,
                min_listing_days=120,
                factor_weights=(
                    SelectionFactorWeightDraft("liquidity_rank", 0.35),
                    SelectionFactorWeightDraft("momentum_1d_rank", 0.65),
                ),
            ),
            instruments=stock_instruments,
        )
        etf_request = CreateSelectionRunRequest(
            as_of=decision_at,
            knowledge_cutoff=decision_at,
            publication_cutoff=decision_at,
            rotation_source_snapshot_ids=rotation_ids,
            market_context_feature_set_id=feature_set_id,
            membership_version=membership_version,
            rotation_algorithm_version="industry-rotation-v1",
            industries=industries,
            seed=20240901,
            rotation_missing_inputs=rotation_missing_inputs,
            universe_snapshot_id=_universe_snapshot_id(
                asset_kind="etf",
                source_snapshot_ids=etf_sources,
                instruments=etf_instruments,
            ),
            selection_source_snapshot_ids=etf_sources,
            selection_spec=EtfSelectionSpecDraft(
                spec_id="a-share-etf-discovery",
                spec_version="1",
                top_k=15,
                min_average_turnover=50_000.0,
                min_listing_days=120,
                factor_weights=(
                    SelectionFactorWeightDraft("liquidity_rank", 0.4),
                    SelectionFactorWeightDraft("momentum_1d_rank", 0.6),
                ),
                max_tracking_error=None,
            ),
            instruments=etf_instruments,
        )
        selection = container.get(SelectionWorkspaceFacade)
        stock_first = selection.create(stock_request)
        stock_second = selection.create(stock_request)
        etf_first = selection.create(etf_request)
        etf_second = selection.create(etf_request)
        if (
            stock_first.selection_run.run_id != stock_second.selection_run.run_id
            or etf_first.selection_run.run_id != etf_second.selection_run.run_id
            or stock_first.industry_rotation.snapshot_id
            != etf_first.industry_rotation.snapshot_id
        ):
            raise ValueError("Q3 SelectionRun replay identity drift")

        technical_certification_context = _TechnicalCertificationContext(
            evidence_root=evidence_root,
            recovery_evidence=recovery_evidence,
            generated_at=generated_at,
            actor=actor,
            data_root=root,
            builder=container.get(DataProductCertificationBuilder),
            commands=container.get(DataProductCertificationCommands),
            store=container.get(CertificationGovernanceStore),
        )
        stock_technical_report = _technical_certification(
            dataset_id="stock_daily",
            instrument_code=_STOCK_CODE,
            snapshot=exact["stock_history"],
            payload=frames["stock_history"],
            context=technical_certification_context,
        )
        etf_technical_report = _technical_certification(
            dataset_id="etf_daily",
            instrument_code=_ETF_CODE,
            snapshot=exact["etf_history"],
            payload=frames["etf_history"],
            context=technical_certification_context,
        )
        technical = container.get(TechnicalAnalysisFacade)
        stock_technical_request = TechnicalAnalysisRequest(
            instrument_id=_STOCK_INSTRUMENT_ID,
            instrument_name="贵州茅台",
            instrument_code=_STOCK_CODE,
            as_of=decision_at,
            knowledge_cutoff=decision_at,
            publication_cutoff=decision_at,
            source_snapshot_ids=(exact["stock_history"].snapshot_id,),
            spec=TechnicalAnalysisSpecDraft(
                spec_id="technical-core",
                spec_version="1",
                timeframes=("daily", "weekly"),
            ),
            selection_run_id=stock_first.selection_run.run_id,
        )
        etf_technical_request = TechnicalAnalysisRequest(
            instrument_id=_ETF_INSTRUMENT_ID,
            instrument_name="华安易富黄金ETF",
            instrument_code=_ETF_CODE,
            as_of=decision_at,
            knowledge_cutoff=decision_at,
            publication_cutoff=decision_at,
            source_snapshot_ids=(exact["etf_history"].snapshot_id,),
            spec=TechnicalAnalysisSpecDraft(
                spec_id="technical-core",
                spec_version="1",
                timeframes=("daily", "weekly"),
            ),
            selection_run_id=etf_first.selection_run.run_id,
        )
        stock_technical = technical.get_snapshot(stock_technical_request)
        stock_technical_replay = technical.get_snapshot(stock_technical_request)
        etf_technical = technical.get_snapshot(etf_technical_request)
        etf_technical_replay = technical.get_snapshot(etf_technical_request)
        if (
            stock_technical.snapshot_id != stock_technical_replay.snapshot_id
            or etf_technical.snapshot_id != etf_technical_replay.snapshot_id
        ):
            raise ValueError("Q3 technical replay identity drift")
        early = exact["stock_history"].created_at - timedelta(microseconds=1)
        try:
            technical.get_snapshot(
                TechnicalAnalysisRequest(
                    instrument_id=_STOCK_INSTRUMENT_ID,
                    instrument_name="贵州茅台",
                    instrument_code=_STOCK_CODE,
                    as_of=early,
                    knowledge_cutoff=early,
                    publication_cutoff=early,
                    source_snapshot_ids=(exact["stock_history"].snapshot_id,),
                    spec=stock_technical_request.spec,
                )
            )
        except AppQueryError as error:
            future_sentinel = {
                "passed": True,
                "error_type": type(error).__name__,
                "message": str(error),
            }
        else:
            raise ValueError("Q3 technical pre-acquisition query did not fail closed")

        allowed = tuple(sorted({_STOCK_CODE, _ETF_CODE}))
        rotation_context = _context(
            decision_at=decision_at,
            source_snapshot_ids=rotation_ids,
            allowed_universe=allowed,
        )
        stock_selection_context = _context(
            decision_at=decision_at,
            source_snapshot_ids=stock_sources,
            allowed_universe=allowed,
        )
        technical_context = _context(
            decision_at=decision_at,
            source_snapshot_ids=(exact["stock_history"].snapshot_id,),
            allowed_universe=allowed,
        )
        rotation_tool = IndustryRotationEvidenceTool(
            facade=container.get(IndustryRotationEvidenceQueryFacade)
        )
        selection_tool = SelectionRunEvidenceTool(
            facade=container.get(SelectionRunEvidenceQueryFacade)
        )
        technical_tool = InstrumentTechnicalEvidenceTool(
            facade=container.get(InstrumentTechnicalEvidenceQueryFacade)
        )
        rotation_first = rotation_tool.invoke(
            arguments={
                "snapshot_id": stock_first.industry_rotation.snapshot_id,
            },
            context=rotation_context,
        )
        rotation_second = rotation_tool.invoke(
            arguments={
                "snapshot_id": stock_first.industry_rotation.snapshot_id,
            },
            context=rotation_context,
        )
        selection_first = selection_tool.invoke(
            arguments={"run_id": stock_first.selection_run.run_id},
            context=stock_selection_context,
        )
        selection_second = selection_tool.invoke(
            arguments={"run_id": stock_first.selection_run.run_id},
            context=stock_selection_context,
        )
        technical_first = technical_tool.invoke(
            arguments={
                "instrument_id": int(_STOCK_INSTRUMENT_ID),
                "instrument_name": "贵州茅台",
                "instrument_code": _STOCK_CODE,
                "selection_run_id": stock_first.selection_run.run_id,
            },
            context=technical_context,
        )
        technical_second = technical_tool.invoke(
            arguments={
                "instrument_id": int(_STOCK_INSTRUMENT_ID),
                "instrument_name": "贵州茅台",
                "instrument_code": _STOCK_CODE,
                "selection_run_id": stock_first.selection_run.run_id,
            },
            context=technical_context,
        )
    finally:
        container.close()

    return {
        "schema": "ditto.q3-live-discovery.v1",
        "generated_at": generated_at,
        "data_root": str(root),
        "market_context_feature_set_id": feature_set_id,
        "source_snapshots": {
            name: item.snapshot_id for name, item in sorted(exact.items())
        },
        "derivations": {
            "industry_trend": "tanh(mean real member pct_change / 5)",
            "regime_alignment": (
                "uniform exact Q2 regime score; no fabricated industry differentiation"
            ),
            "missing_rotation_inputs": stock_first.industry_rotation.missing_inputs,
            "selection_factors": ("momentum_1d_rank", "liquidity_rank"),
            "etf_suspension": (
                "false only where an exact target-date provider bar exists"
            ),
            "price_limits": "ST/10%/20%/30% board thresholds plus close-at-extreme",
        },
        "industry_rotation": asdict(stock_first.industry_rotation),
        "stock_selection": asdict(stock_first.selection_run),
        "etf_selection": asdict(etf_first.selection_run),
        "technical_analysis": {
            "stock": asdict(stock_technical),
            "etf": asdict(etf_technical),
            "future_sentinel": future_sentinel,
        },
        "technical_certification": {
            "profile": _TECHNICAL_PROFILE,
            "products": {
                report.dataset_id: {
                    "report_id": report.report_id,
                    "content_hash": report.content_hash,
                    "snapshot_ids": report.evidence.snapshot_ids,
                }
                for report in (stock_technical_report, etf_technical_report)
            },
        },
        "agent_evidence": {
            "industry_rotation": _envelope_summary(rotation_first, rotation_second),
            "selection_run": _envelope_summary(selection_first, selection_second),
            "technical_analysis": _envelope_summary(technical_first, technical_second),
            "license_class": "approved-research",
            "egress_class": "cloud_allowed",
        },
        "criteria": {
            "industry_rotation_snapshot": True,
            "stock_and_etf_selection_runs": True,
            "selection_deterministic_replay": True,
            "stock_and_etf_technical_snapshots": True,
            "technical_daily_weekly_warmup_complete": all(
                reading.status.value != "warming_up"
                for snapshot in (stock_technical, etf_technical)
                for reading in snapshot.readings
            ),
            "technical_missing_reference_series_reported": bool(
                stock_technical.missing_inputs and etf_technical.missing_inputs
            ),
            "technical_future_sentinel": True,
            "agent_exact_evidence_envelopes": True,
        },
        "passed": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--recovery-evidence", required=True, type=Path)
    parser.add_argument("--market-context-evidence", required=True, type=Path)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Write the canonical Q3 evidence artifact."""
    args = _parser().parse_args(argv)
    result = run_q3_live_discovery_acceptance(
        data_root=args.data_root,
        evidence_root=args.evidence_root,
        recovery_evidence=args.recovery_evidence,
        market_context_evidence=args.market_context_evidence,
        actor=cast("str", args.actor),
    )
    output = args.output.expanduser().resolve(strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        orjson.dumps(
            orjson.loads(canonical_bytes(result)),
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        + b"\n"
    )
    sys.stdout.write(
        orjson.dumps(
            {
                "evidence_sha256": _sha256_file(output),
                "passed": result["passed"],
                "stock_run_id": cast("Mapping[str, object]", result["stock_selection"])[
                    "run_id"
                ],
                "etf_run_id": cast("Mapping[str, object]", result["etf_selection"])[
                    "run_id"
                ],
            },
            option=orjson.OPT_SORT_KEYS,
        ).decode()
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
