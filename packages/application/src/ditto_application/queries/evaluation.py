"""App-layer factor evaluation facade."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ditto_features.errors import DerivedError
from ditto_features.evaluation.evaluator import (
    EvaluationConfig,
    FactorEvaluator,
)
from ditto_features.evaluation.report import FactorEvaluationReport
from ditto_features.services import DerivedArtifactReader

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.forward_return_service import ForwardReturnService

__all__ = ["EvaluationOptions", "FactorEvaluationFacade"]


@dataclass(frozen=True)
class EvaluationOptions:
    """
    评估配置参数.

    Attributes:
        start: 评估起始日期（``YYYY-MM-DD``）。``None`` 时取 artifact 中最早日期。
        end: 评估结束日期（``YYYY-MM-DD``）。``None`` 时取 artifact 中最新日期。
        holding_period: 前向收益持有期（交易日）。
        n_quantiles: 分位组数。
        asset_class: ``"stock"`` 或 ``"etf"``。
        adj: 复权类型（``"none"``、``"qfq"``、``"hfq"``）。
        run_regime_ic: 是否计算情景调整 IC（默认关闭）。
        run_performance_attribution: 是否计算绩效归因（默认关闭）。
        dataset_id: 评估使用的数据集标识。
        catalog_snapshot_id: 评估绑定的目录快照或证据标识。
        universe: 评估使用的 universe 标识。
        cost_bps: 成本后收益指标使用的换手成本（bps）。

    """

    start: str | None = None
    end: str | None = None
    holding_period: int = 5
    n_quantiles: int = 5
    asset_class: str = "stock"
    adj: str = "none"
    run_regime_ic: bool = False
    run_performance_attribution: bool = False
    dataset_id: str = ""
    catalog_snapshot_id: str = ""
    universe: str = ""
    cost_bps: float = 0.0


_DEFAULT_OPTIONS = EvaluationOptions()


class FactorEvaluationFacade:
    """
    App-layer entry point for factor evaluation.

    Coordinates artifact loading via :class:`DerivedArtifactReader`,
    forward-return computation via :class:`ForwardReturnService`, and
    metric aggregation via :class:`FactorEvaluator`.
    """

    def __init__(
        self,
        *,
        artifact_reader: DerivedArtifactReader,
        forward_return_service: ForwardReturnService,
    ) -> None:
        self._artifact_reader = artifact_reader
        self._forward_return_service = forward_return_service

    def evaluate(
        self,
        factor_id: str,
        version: int | None = None,
        *,
        options: EvaluationOptions = _DEFAULT_OPTIONS,
    ) -> FactorEvaluationReport:
        """
        评估单个因子并返回完整报告.

        Args:
            factor_id: 衍生 artifact 标识符。
            version: artifact 版本。``None`` 时通过
                :meth:`DerivedArtifactReader.resolve_offline_version` 解析当前
                离线版本。解析失败（``DerivedError``）会被包装为
                :class:`AppQueryError`，并在 details 中保留 ``factor_id``。
            options: 评估配置。省略时使用合理默认值。

        Returns:
            :class:`FactorEvaluationReport`，``factor_id`` 与
            ``factor_version`` 来自请求参数（version 为解析后的值）。

        Raises:
            AppQueryError: version 解析失败时抛出，保留原始 ``DerivedError``
                为 ``__cause__``。

        """
        resolved_version = self._resolve_version(factor_id, version)

        factor_df = self._artifact_reader.read_frame(
            derived_id=factor_id,
            version=resolved_version,
            start=options.start,
            end=options.end,
        )

        evaluator = FactorEvaluator(
            forward_return_provider=self._forward_return_service,
        )
        config = EvaluationConfig(
            asset_class=options.asset_class,
            adj=options.adj,
            holding_period=options.holding_period,
            n_quantiles=options.n_quantiles,
            run_regime_ic=options.run_regime_ic,
            run_performance_attribution=options.run_performance_attribution,
        )
        report = evaluator.evaluate(
            factor_df,
            config=config,
            start=options.start,
            end=options.end,
        )

        # The evaluator defaults to factor_id="unknown". Stamp request-level
        # identity and launch contract context so the report is auditable.
        return replace(
            report,
            factor_id=factor_id,
            factor_version=resolved_version,
            dataset_id=options.dataset_id,
            catalog_snapshot_id=options.catalog_snapshot_id,
            universe=options.universe,
            cost_bps=options.cost_bps,
        )

    def _resolve_version(
        self,
        factor_id: str,
        version: int | None,
    ) -> int:
        """
        解析 artifact 版本；version 为 None 时查询当前离线版本.

        ``DerivedError`` 是 features 域异常（非 ``AppError`` 子类），必须包装为
        :class:`AppQueryError` 以保持 application 边界异常语义，同时保留
        ``__cause__`` 链与 ``factor_id`` 上下文。

        """
        if version is not None:
            return version
        try:
            return self._artifact_reader.resolve_offline_version(factor_id)
        except DerivedError as exc:
            raise AppQueryError(
                f"无法解析因子 artifact 版本: factor_id={factor_id}",
                details={"factor_id": factor_id},
            ) from exc
