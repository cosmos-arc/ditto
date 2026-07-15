"""CLI 运维命令组 - 数据集状态与质量检查."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

import typer
from ditto_application.commands.catalog import (
    DatasetMaturityPromotionRevokeCommand,
    DatasetMaturityPromotionRevokeResult,
    DatasetPromotionReviewCommand,
    DatasetPromotionReviewResult,
    ReviewDatasetPromotionEvidenceHandler,
    RevokeDatasetMaturityPromotionHandler,
)
from ditto_application.config import get_all_datasets
from ditto_application.exceptions import AppError
from ditto_application.processes.quality.patrol import QualityPatrolService
from ditto_application.queries.catalog import (
    CatalogMaturityPromotionHistoryItem,
    CatalogQueryFacade,
)
from ditto_application.queries.evaluation import (
    EvaluationOptions,
    FactorEvaluationFacade,
)
from ditto_application.queries.factor_ic_report import render_factor_ic_markdown
from ditto_application.queries.ingestion_status import (
    DatasetMaturitySummary,
    IngestionStatusQueryFacade,
    summarize_status_by_maturity,
)
from ditto_application.queries.promotion_evidence import (
    PromotionEvidenceCollector,
    PromotionEvidenceReport,
)

from ditto_apps.cli.utils.output import output_json_dict, output_json_dicts
from ditto_apps.jobs.flows.eod import eod_flow
from ditto_apps.registry.container import Container, make_app_container

app = typer.Typer(help="运维命令")

type MaturityPromotionRevocationReason = Literal[
    "policy_regression",
    "failed_revalidation",
    "manual_override",
    "evidence_invalidated",
]

# 从 Dataset StrEnum 派生，保证单一事实来源（自动包含 index_weight）
_KNOWN_DATASETS = [dataset.value for dataset in get_all_datasets()]

# 核心数据集 (dq 默认检查范围)，从 Dataset 枚举派生避免硬编码
_CORE_DATASET_NAMES = {"etf_daily", "stock_daily", "index_daily", "adj_factor"}
_CORE_DATASETS = [
    dataset.value
    for dataset in get_all_datasets()
    if dataset.value in _CORE_DATASET_NAMES
]

# 表格列宽
_COL_DATASET = 24
_COL_DATE = 14
_COL_STATUS = 10
_COL_RECORDS = 10


@app.command("run-eod")
def run_eod(
    signal_date: str = typer.Option(..., "--signal-date", help="信号日 YYYY-MM-DD"),
    strategy_id: str | None = typer.Option(
        None, "--strategy-id", help="仅运行指定策略"
    ),
) -> None:
    """运行与 Prefect 共用的 EOD 业务入口并结构化输出结果。"""
    result = eod_flow(trade_date=signal_date, strategy_id=strategy_id)
    output_json_dict(dict(result))
    strategies = result.get("strategies", [])
    if isinstance(strategies, list) and any(
        isinstance(item, dict)
        and cast("dict[str, object]", item).get("status")
        in {"blocked", "failed", "rerun_conflict"}
        for item in cast("list[object]", strategies)
    ):
        raise typer.Exit(1)


def _status_color(status: str | None) -> str:
    """根据摄取状态返回终端颜色."""
    if status == "success":
        return typer.colors.GREEN
    if status == "failed":
        return typer.colors.RED
    if status is not None:
        return typer.colors.YELLOW
    return typer.colors.WHITE


def _print_status_table(rows: list[dict[str, Any]]) -> None:
    """打印摄取状态表格."""
    header = (
        f"{'DATASET':<{_COL_DATASET}}"
        f"{'LATEST_DATE':<{_COL_DATE}}"
        f"{'STATUS':<{_COL_STATUS}}"
        f"{'RECORDS':<{_COL_RECORDS}}"
    )
    typer.secho(header, bold=True)
    typer.echo("-" * len(header))

    for row in rows:
        latest_date = row["latest_date"] or "-"
        status = row["latest_status"] or "-"
        records = str(row["record_count"])
        color = _status_color(row["latest_status"])
        line = (
            f"{row['dataset']:<{_COL_DATASET}}"
            f"{latest_date:<{_COL_DATE}}"
            f"{status:<{_COL_STATUS}}"
            f"{records:<{_COL_RECORDS}}"
        )
        typer.secho(line, fg=color)


def _print_dq_table(rows: list[dict[str, Any]]) -> None:
    """打印 DQ 检查结果表格."""
    header = f"{'DATASET':<{_COL_DATASET}}{'PASSED':<10}{'ISSUES':<10}{'ALERTS':<10}"
    typer.secho(header, bold=True)
    typer.echo("-" * len(header))

    for row in rows:
        passed_fg = typer.colors.GREEN if row["passed"] else typer.colors.RED
        passed = typer.style(str(row["passed"]), fg=passed_fg)
        issues = str(row["issue_count"])
        alerts = str(row["alert_count"])
        typer.echo(
            f"{row['dataset']:<{_COL_DATASET}}{passed:<10}{issues:<10}{alerts:<10}"
        )

        if row.get("error"):
            typer.secho(f"  error: {row['error']}", fg=typer.colors.RED)


def _maturity_summary_rows(
    summaries: list[DatasetMaturitySummary],
) -> list[dict[str, Any]]:
    """Return JSON-friendly maturity summary rows."""
    return [
        {
            "maturity": s.maturity,
            "dataset_count": s.dataset_count,
            "fresh_count": s.fresh_count,
            "stale_count": s.stale_count,
            "missing_count": s.missing_count,
            "not_applicable_count": s.not_applicable_count,
            "failed_count": s.failed_count,
            "warning_count": s.warning_count,
            "promotion_ready_count": s.promotion_ready_count,
            "promotion_blocked_count": s.promotion_blocked_count,
        }
        for s in summaries
    ]


def _print_history_table(
    items: list[dict[str, Any]],
) -> None:
    """打印摄取历史表格."""
    for item in items:
        color = _status_color(item["status"])
        line = (
            f"{item['dataset']:<{_COL_DATASET}}"
            f"{item['trade_date']:<{_COL_DATE}}"
            f"{item['status']:<{_COL_STATUS}}"
            f"rows={item['rows'] or '-':<10}"
        )
        typer.secho(line, fg=color)
        if item["error_message"]:
            typer.secho(f"  error: {item['error_message']}", fg=typer.colors.RED)


def _fetch_status_facade() -> tuple[Container, IngestionStatusQueryFacade]:
    """获取 IngestionStatusQueryFacade, 失败时退出."""
    container: Container = make_app_container()
    try:
        return container, container.get(IngestionStatusQueryFacade)
    except Exception as exc:
        typer.secho(f"获取服务失败: {exc}", fg=typer.colors.RED, err=True)
        container.close()
        raise typer.Exit(1) from exc


def _fetch_patrol_service() -> tuple[Container, QualityPatrolService]:
    """获取 QualityPatrolService, 失败时退出."""
    container: Container = make_app_container()
    try:
        return container, container.get(QualityPatrolService)
    except Exception as exc:
        typer.secho(f"获取服务失败: {exc}", fg=typer.colors.RED, err=True)
        container.close()
        raise typer.Exit(1) from exc


def _fetch_promotion_review_handler() -> tuple[
    Container,
    ReviewDatasetPromotionEvidenceHandler,
]:
    """获取 promotion review handler, 失败时退出."""
    container: Container = make_app_container()
    try:
        return container, container.get(ReviewDatasetPromotionEvidenceHandler)
    except Exception as exc:
        typer.secho(f"获取服务失败: {exc}", fg=typer.colors.RED, err=True)
        container.close()
        raise typer.Exit(1) from exc


def _fetch_catalog_query_facade() -> tuple[Container, CatalogQueryFacade]:
    """获取 CatalogQueryFacade, 失败时退出."""
    container: Container = make_app_container()
    try:
        return container, container.get(CatalogQueryFacade)
    except Exception as exc:
        typer.secho(f"获取服务失败: {exc}", fg=typer.colors.RED, err=True)
        container.close()
        raise typer.Exit(1) from exc


def _fetch_promotion_revoke_handler() -> tuple[
    Container,
    RevokeDatasetMaturityPromotionHandler,
]:
    """获取 promotion revoke handler, 失败时退出."""
    container: Container = make_app_container()
    try:
        return container, container.get(RevokeDatasetMaturityPromotionHandler)
    except Exception as exc:
        typer.secho(f"获取服务失败: {exc}", fg=typer.colors.RED, err=True)
        container.close()
        raise typer.Exit(1) from exc


def _promotion_review_row(result: DatasetPromotionReviewResult) -> dict[str, Any]:
    """Return JSON-friendly promotion review result."""
    return {
        "dataset_id": result.dataset_id,
        "reviewed_criterion": result.reviewed_criterion,
        "evidence_uri": result.evidence_uri,
        "reviewed_by": result.reviewed_by,
        "passed": result.passed,
        "reviewed_at": result.reviewed_at.isoformat(),
        "promotion_status": result.promotion_status,
        "missing_criteria": list(result.missing_criteria),
        "satisfied_criteria": list(result.satisfied_criteria),
        "rejected_criteria": list(result.rejected_criteria),
        "metadata_promoted": result.metadata_promoted,
        "dataset_maturity_before": result.dataset_maturity_before,
        "dataset_maturity_after": result.dataset_maturity_after,
    }


def _promotion_history_row(
    item: CatalogMaturityPromotionHistoryItem,
) -> dict[str, Any]:
    """Return JSON-friendly promotion history event."""
    return {
        "dataset_id": item.dataset_id,
        "action": item.action,
        "previous_maturity": item.previous_maturity,
        "next_maturity": item.next_maturity,
        "actor": item.actor,
        "action_at": item.action_at.isoformat() if item.action_at is not None else None,
        "evidence_uri": item.evidence_uri,
        "revocation_reason": item.revocation_reason,
        "notes": item.notes,
    }


def _promotion_revoke_row(
    result: DatasetMaturityPromotionRevokeResult,
) -> dict[str, Any]:
    """Return JSON-friendly promotion revoke result."""
    return {
        "dataset_id": result.dataset_id,
        "revoked_by": result.revoked_by,
        "revoked_at": result.revoked_at.isoformat(),
        "dataset_maturity_before": result.dataset_maturity_before,
        "dataset_maturity_after": result.dataset_maturity_after,
        "evidence_uri": result.evidence_uri,
        "revocation_reason": result.revocation_reason,
        "notes": result.notes,
    }


@app.command()
def status(
    date: str | None = typer.Option(None, "--date", "-d", help="查询日期 YYYY-MM-DD"),
    json: bool = typer.Option(False, "--json", help="JSON 格式输出"),
) -> None:
    """显示数据集摄取状态."""
    container, facade = _fetch_status_facade()

    try:
        if date is not None:
            all_history: list[dict[str, Any]] = []
            for dataset in _KNOWN_DATASETS:
                history = facade.get_history(dataset, limit=50)
                for item in history:
                    if item.trade_date == date:
                        all_history.append(
                            {
                                "dataset": item.dataset,
                                "trade_date": item.trade_date,
                                "status": item.status,
                                "rows": item.rows,
                                "error_message": item.error_message,
                                "attempts": item.attempts,
                                "last_attempt_at": item.last_attempt_at,
                            }
                        )

            if json:
                output_json_dicts(all_history)
            elif not all_history:
                typer.echo(f"日期 {date} 无摄取记录")
            else:
                _print_history_table(all_history)
        else:
            statuses = facade.get_status(_KNOWN_DATASETS)
            rows = [
                {
                    "dataset": s.dataset,
                    "latest_date": s.latest_date,
                    "latest_status": s.latest_status,
                    "dataset_maturity": s.dataset_maturity,
                    "dataset_maturity_warning": s.dataset_maturity_warning,
                    "dataset_promotion_criteria": list(s.dataset_promotion_criteria),
                    "dataset_promotion_status": s.dataset_promotion_status,
                    "dataset_promotion_missing_criteria": list(
                        s.dataset_promotion_missing_criteria
                    ),
                    "dataset_promotion_satisfied_criteria": list(
                        s.dataset_promotion_satisfied_criteria
                    ),
                    "dataset_promotion_rejected_criteria": list(
                        s.dataset_promotion_rejected_criteria
                    ),
                    "record_count": s.record_count,
                    "last_attempt": s.last_attempt,
                    "catalog_freshness_at": s.catalog_freshness_at.isoformat()
                    if s.catalog_freshness_at is not None
                    else None,
                    "catalog_storage_uri": s.catalog_storage_uri,
                    "catalog_schema_hash": s.catalog_schema_hash,
                    "catalog_row_count": s.catalog_row_count,
                    "catalog_freshness_status": s.catalog_freshness_status,
                    "catalog_freshness_sla_hours": s.catalog_freshness_sla_hours,
                }
                for s in statuses
            ]

            if json:
                output_json_dict(
                    {
                        "datasets": rows,
                        "maturity_summary": _maturity_summary_rows(
                            summarize_status_by_maturity(statuses)
                        ),
                    }
                )
            else:
                _print_status_table(rows)
    except Exception as exc:
        typer.secho(f"查询失败: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    finally:
        container.close()


@app.command("promotion-review")
def promotion_review(
    dataset_id: str = typer.Argument(..., help="数据集 ID"),
    criterion: str = typer.Option(..., "--criterion", help="被审核的晋级条件"),
    evidence_uri: str = typer.Option(..., "--evidence-uri", help="审核证据 URI"),
    reviewed_by: str = typer.Option(..., "--reviewed-by", help="审核人或审核主体"),
    passed: bool = typer.Option(True, "--passed/--rejected", help="审核是否通过"),
    notes: str | None = typer.Option(None, "--notes", help="审核备注"),
    json: bool = typer.Option(False, "--json", help="JSON 格式输出"),
) -> None:
    """写入数据集晋级条件的 reviewer evidence."""
    container, handler = _fetch_promotion_review_handler()
    try:
        result = handler.handle(
            DatasetPromotionReviewCommand(
                dataset_id=dataset_id,
                criterion=criterion,
                evidence_uri=evidence_uri,
                reviewed_by=reviewed_by,
                passed=passed,
                notes=notes,
            )
        )
        row = _promotion_review_row(result)
        if json:
            output_json_dict(row)
        else:
            status = row["promotion_status"]
            criterion = row["reviewed_criterion"]
            typer.echo(f"{row['dataset_id']} {status} criterion={criterion}")
    except Exception as exc:
        typer.secho(f"审核失败: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    finally:
        container.close()


@app.command("promotion-history")
def promotion_history(
    dataset_id: str = typer.Argument(..., help="数据集 ID"),
    json: bool = typer.Option(False, "--json", help="JSON 格式输出"),
) -> None:
    """查看数据集成熟度晋级治理历史."""
    container, facade = _fetch_catalog_query_facade()
    try:
        events = facade.list_maturity_promotion_history(dataset_id)
        rows = [_promotion_history_row(event) for event in events]
        if json:
            output_json_dict({"events": rows})
        else:
            for row in rows:
                action_at = row["action_at"] or "-"
                transition = f"{row['previous_maturity']}->{row['next_maturity']}"
                typer.echo(
                    " ".join(
                        [
                            str(row["dataset_id"]),
                            str(row["action"]),
                            transition,
                            f"actor={row['actor']}",
                            f"at={action_at}",
                        ]
                    )
                )
    except Exception as exc:
        typer.secho(f"查询失败: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    finally:
        container.close()


@app.command("promotion-revoke")
def promotion_revoke(
    dataset_id: str = typer.Argument(..., help="数据集 ID"),
    revoked_by: str = typer.Option(..., "--revoked-by", help="撤销人或撤销主体"),
    reason: str = typer.Option(..., "--reason", help="撤销原因分类"),
    notes: str | None = typer.Option(None, "--notes", help="撤销备注"),
    json: bool = typer.Option(False, "--json", help="JSON 格式输出"),
) -> None:
    """撤销数据集成熟度晋级 override."""
    container, handler = _fetch_promotion_revoke_handler()
    try:
        result = handler.handle(
            DatasetMaturityPromotionRevokeCommand(
                dataset_id=dataset_id,
                revoked_by=revoked_by,
                revocation_reason=cast(MaturityPromotionRevocationReason, reason),
                notes=notes,
            )
        )
        row = _promotion_revoke_row(result)
        if json:
            output_json_dict(row)
        else:
            before = row["dataset_maturity_before"]
            after = row["dataset_maturity_after"]
            transition = f"{before}->{after}"
            typer.echo(
                " ".join(
                    [
                        str(row["dataset_id"]),
                        transition,
                        f"revoked_by={row['revoked_by']}",
                        f"reason={row['revocation_reason']}",
                    ]
                )
            )
    except Exception as exc:
        typer.secho(f"撤销失败: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    finally:
        container.close()


def _fetch_promotion_evidence_collector() -> tuple[
    Container,
    PromotionEvidenceCollector,
]:
    """获取 promotion evidence collector, 失败时退出."""
    container: Container = make_app_container()
    try:
        return container, container.get(PromotionEvidenceCollector)
    except Exception as exc:
        typer.secho(f"获取服务失败: {exc}", fg=typer.colors.RED, err=True)
        container.close()
        raise typer.Exit(1) from exc


def _render_promotion_evidence_markdown(report: PromotionEvidenceReport) -> str:
    """Render a promotion evidence report as Markdown."""
    lines = [
        f"# Promotion Evidence Report: {report.dataset_id}",
        "",
        f"- Maturity: `{report.maturity}`",
        f"- Generated at: {report.generated_at.isoformat()}",
        "",
        "## Criteria",
        "",
    ]
    for item in report.criteria:
        lines.append(f"### {item.criterion}")
        lines.append("")
        lines.append(f"- Status: `{item.status}`")
        for material in item.materials:
            lines.append(f"  - {material}")
        if item.suggestion:
            lines.append(f"- Suggestion: {item.suggestion}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "> Objective evidence only. Final pass/fail is a reviewer decision "
        + "submitted via `ditto ops promotion-review`."
    )
    return "\n".join(lines)


@app.command("promotion-collect")
def promotion_collect(
    dataset_id: str = typer.Argument(..., help="数据集 ID"),
    output: str | None = typer.Option(
        None, "--output", help="写入文件路径 (默认输出到 stdout)"
    ),
) -> None:
    """收集数据集晋级证据，生成 Markdown 证据报告。"""
    container, collector = _fetch_promotion_evidence_collector()
    try:
        report = collector.collect(dataset_id)
    except ValueError as exc:
        typer.secho(f"收集失败: {exc}", fg=typer.colors.RED, err=True)
        container.close()
        raise typer.Exit(1) from exc
    finally:
        container.close()
    markdown = _render_promotion_evidence_markdown(report)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        typer.echo(str(path))
    else:
        typer.echo(markdown)


@app.command()
def dq(
    date: str = typer.Argument(..., help="交易日期 YYYY-MM-DD"),
    dataset: str | None = typer.Option(
        None, "--dataset", help="数据集名称 (未指定则检查核心数据集)"
    ),
    json: bool = typer.Option(False, "--json", help="JSON 格式输出"),
) -> None:
    """运行数据质量检查."""
    container, patrol = _fetch_patrol_service()

    datasets = [dataset] if dataset else _CORE_DATASETS

    try:
        results: list[dict[str, Any]] = []
        for ds in datasets:
            result = patrol.check_dataset(ds, date)
            row: dict[str, Any] = {
                "dataset": result.dataset,
                "trade_date": result.trade_date,
                "passed": result.passed,
                "issue_count": result.issue_count,
                "alert_count": result.alert_count,
            }
            if result.has_error:
                row["error"] = result.error
            if result.issues:
                row["issues"] = [
                    {
                        "rule": issue.rule_name,
                        "severity": issue.severity.value,
                        "message": issue.message,
                    }
                    for issue in result.issues
                ]
            results.append(row)

        if json:
            output_json_dicts(results)
        else:
            _print_dq_table(results)

            total = len(results)
            passed = sum(1 for r in results if r["passed"])
            typer.echo()
            typer.echo(f"检查完成: {passed}/{total} 通过")
    except Exception as exc:
        typer.secho(f"DQ 检查失败: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    finally:
        container.close()


# ---------------------------------------------------------------------------
# factor-ic: 离线因子 IC 诊断报告
# ---------------------------------------------------------------------------


def _fetch_factor_evaluation_facade() -> tuple[Container, FactorEvaluationFacade]:
    """获取因子评估 facade, 失败时退出."""
    container: Container = make_app_container()
    try:
        return container, container.get(FactorEvaluationFacade)
    except Exception as exc:
        typer.secho(f"获取服务失败: {exc}", fg=typer.colors.RED, err=True)
        container.close()
        raise typer.Exit(1) from exc


@app.command("factor-ic")
def factor_ic(  # noqa: PLR0913 — CLI 命令回调，参数由 Typer 注入
    factor: str = typer.Argument(..., help="因子 ID (derived artifact identifier)"),
    start: str = typer.Option(..., "--start", help="开始日期 YYYY-MM-DD"),
    end: str = typer.Option(..., "--end", help="结束日期 YYYY-MM-DD"),
    version: int | None = typer.Option(
        None, "--version", help="因子版本 (默认取 active version)"
    ),
    asset_class: str = typer.Option(
        "stock", "--asset-class", help="资产类别 stock/etf"
    ),
    holding_period: int = typer.Option(5, "--holding-period", help="前向收益持有天数"),
    n_quantiles: int = typer.Option(5, "--n-quantiles", help="分层组数"),
    regime: bool = typer.Option(False, "--regime", help="启用情景 IC 分析"),
    attribution: bool = typer.Option(False, "--attribution", help="启用绩效归因分析"),
    dataset_id: str = typer.Option("", "--dataset-id", help="评估使用的数据集 ID"),
    catalog_snapshot_id: str = typer.Option(
        "", "--catalog-snapshot-id", help="评估绑定的目录快照或证据 ID"
    ),
    universe: str = typer.Option("", "--universe", help="评估使用的 universe ID"),
    cost_bps: float = typer.Option(0.0, "--cost-bps", help="交易成本 (bps)"),
    output: str | None = typer.Option(
        None, "--output", help="写入文件路径 (默认 stdout)"
    ),
) -> None:
    """因子 IC 诊断: IC/ICIR/分层/多空/换手成本 Markdown 报告 (仅限非生产环境)."""
    container, facade = _fetch_factor_evaluation_facade()
    options = EvaluationOptions(
        start=start,
        end=end,
        holding_period=holding_period,
        n_quantiles=n_quantiles,
        asset_class=asset_class,
        run_regime_ic=regime,
        run_performance_attribution=attribution,
        dataset_id=dataset_id,
        catalog_snapshot_id=catalog_snapshot_id,
        universe=universe,
        cost_bps=cost_bps,
    )
    try:
        report = facade.evaluate(factor, version=version, options=options)
    except AppError as exc:
        typer.secho(f"诊断失败: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    finally:
        container.close()
    markdown = render_factor_ic_markdown(report)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        typer.echo(str(path))
    else:
        typer.echo(markdown)
