"""Catalog strategy digest 纵向传播回归测试。"""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

from ditto_application.builders import BacktestRuntimeBuilder, StrategyRuntimeBuilder
from ditto_application.processes.execution.backtest_process import (
    BacktestCatalogRequestConfig,
    BacktestService,
)
from ditto_backtest.manifest import RunManifest
from ditto_backtest.manifest_build import (
    RunManifestInputEvidence,
    build_run_manifest,
)
from ditto_data.provider import DataProvider
from ditto_data.services.metadata_service import MetadataService
from ditto_kernel.order import OrderType
from ditto_kernel.strategy import ImpactModel
from ditto_strategy.alpha.specs import (
    CostModelSpec,
    ExecutionSpec,
    ScorerSpec,
    SelectorSpec,
    StrategySpec,
)
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)

_EXPECTED_MARKET_HASH = (
    "3d4383741997e61203b384ed755c06d8e05df64ea09d66af1cc36230d32b2ff1"
)
_EXPECTED_LIMIT_HASH = (
    "443189820bdb94b539ecc072cf8d8e21a891d0c7134d2ae06af0c2912c743177"
)


def _make_record(default_order_type: OrderType) -> StrategySpecRecord:
    spec = StrategySpec(
        strategy_id="momentum-etf",
        name="Momentum ETF",
        template="etf_rotation",
        universe="cn_etf",
        asset_class="etf",
        scorer=ScorerSpec(method="rank"),
        selector=SelectorSpec(method="top_k", params={"k": 3}),
        execution=ExecutionSpec(
            frequency="M",
            method="calendar",
            cost_model=CostModelSpec(
                commission_rate=0.0005,
                slippage_bps=7.5,
                impact_model=ImpactModel.VOLUME_SHARE,
            ),
            default_order_type=default_order_type,
        ),
        params={
            "top_k": 3,
            "allocation_method": "score_weight",
            "cash_target": 0.05,
            "signal_column": "momentum_20d",
            "max_weight": 0.4,
            "max_positions": 3,
            "scoring_method": "rank",
            "scoring_ascending": True,
        },
        tags=("momentum", "etf"),
        required_datasets=("etf_daily",),
    )
    return StrategySpecRecord(
        strategy_id=spec.strategy_id,
        name=spec.name,
        spec_json=asdict(spec),
        version=7,
        status="published",
        tags=spec.tags,
    )


def _build_manifest_from_record(record: StrategySpecRecord) -> RunManifest:
    catalog_service = MagicMock(spec=StrategyCatalogService)
    catalog_service.get_spec.return_value = record
    strategy_builder = StrategyRuntimeBuilder(catalog_service=catalog_service)
    metadata_service = MagicMock(spec=MetadataService)
    metadata_service.get_universe.return_value = [2_000_001]
    metadata_service.instrument.get_instrument.return_value = {
        "ticker": "510300",
        "exchange": "XSHG",
    }
    runtime_builder = BacktestRuntimeBuilder(
        strategy_runtime_builder=strategy_builder,
        metadata_service=metadata_service,
        data_provider=MagicMock(spec=DataProvider),
    )
    runtime = runtime_builder.build_published_runtime(
        config=BacktestCatalogRequestConfig(
            strategy_id=record.strategy_id,
            start_date="2026-01-10",
            end_date="2026-01-13",
            initial_cash=2_000_000.0,
        ),
        version=record.version,
        allow_experimental_data=True,
    )
    service = BacktestService(
        config=runtime.config,
        pipeline=runtime.pipeline,
        planner=runtime.planner,
        brokerage=runtime.brokerage,
        pre_trade_check=runtime.pre_trade_check,
        data_feed=runtime.data_feed,
    )
    engine_config = service._build_engine_config("run-canonical-vector")
    manifest = build_run_manifest(
        run_id="run-canonical-vector",
        config=engine_config,
        spec_hash=engine_config.spec_hash,
        input_evidence=RunManifestInputEvidence(
            input_instruments=set(),
            bar_fingerprints={},
        ),
        rule_refs=(),
        random_seed=42,
    )

    assert runtime.config.spec_hash == engine_config.spec_hash
    assert engine_config.spec_hash == manifest.spec_hash
    assert manifest.strategy_version == str(record.version)
    catalog_service.get_spec.assert_called_once_with(record.strategy_id, record.version)
    return manifest


def test_default_order_type_changes_real_catalog_to_manifest_digest() -> None:
    """Record→adapter/runtime→service→engine→manifest 保留固定真实 digest。"""
    market_manifest = _build_manifest_from_record(_make_record(OrderType.MARKET))
    limit_manifest = _build_manifest_from_record(_make_record(OrderType.LIMIT))

    assert market_manifest.spec_hash == _EXPECTED_MARKET_HASH
    assert limit_manifest.spec_hash == _EXPECTED_LIMIT_HASH
    assert market_manifest.spec_hash != limit_manifest.spec_hash
