"""CLI 运维命令组 - 数据集状态与质量检查."""

from __future__ import annotations

import datetime
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import polars as pl
import typer
from ditto_application.commands.quality_reconciliation import (
    ReconcileSourcesCommand,
    ReconcileSourcesHandler,
)
from ditto_application.config import get_all_datasets
from ditto_application.exceptions import AppError
from ditto_application.processes.quality.patrol import QualityPatrolService
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
from ditto_kernel.exceptions import DittoError
from ditto_platform.foundation.storage.sqlite_backup import (
    SQLiteBackupError,
    backup_database,
    inspect_database,
    restore_database,
)

from ditto_apps.cli.utils.output import output_json_dict, output_json_dicts
from ditto_apps.jobs.flows.eod import run_eod_pipeline
from ditto_apps.jobs.flows.repair import run_sparse_pit_reattestation
from ditto_apps.registry.container import Container, make_app_container
from ditto_apps.registry.contexts.materialization import materialize_governed_factor

app = typer.Typer(help="运维命令")

# 从 Dataset StrEnum 派生, 保证单一事实来源(自动包含 index_weight)
_KNOWN_DATASETS = [dataset.value for dataset in get_all_datasets()]

# 核心数据集 (dq 默认检查范围), 从 Dataset 枚举派生避免硬编码
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


def _output_sqlite_failure(reason: str, error: SQLiteBackupError) -> None:
    output_json_dict(
        {
            "status": "failed",
            "reason": reason,
            "detail": str(error),
        }
    )
    raise typer.Exit(1)


@app.command("backup-sqlite")
def backup_sqlite(
    source: Path = typer.Option(..., "--source", help="活动 SQLite 数据库路径"),
    destination: Path = typer.Option(
        ...,
        "--destination",
        help="新的备份文件路径; 已存在时拒绝覆盖",
    ),
) -> None:
    """使用 SQLite online backup API 创建并验证原子备份。"""
    try:
        report = backup_database(source, destination)
    except SQLiteBackupError as error:
        _output_sqlite_failure("SQLITE_BACKUP_FAILED", error)
        return
    output_json_dict({"status": "completed", **asdict(report)})


@app.command("verify-sqlite")
def verify_sqlite(
    database: Path = typer.Option(..., "--database", help="待验证 SQLite 文件路径"),
) -> None:
    """验证 SQLite 完整性并输出 checksum 与逐表行数 evidence。"""
    try:
        report = inspect_database(database)
    except SQLiteBackupError as error:
        _output_sqlite_failure("SQLITE_VERIFY_FAILED", error)
        return
    output_json_dict({"status": "completed", **asdict(report)})


@app.command("restore-sqlite")
def restore_sqlite(
    backup: Path = typer.Option(..., "--backup", help="已验证的 SQLite 备份路径"),
    destination: Path = typer.Option(
        ...,
        "--destination",
        help="独立恢复库路径; 已存在时拒绝覆盖",
    ),
) -> None:
    """把备份恢复到新路径, 禁止覆盖原库, 并再次验证。"""
    try:
        report = restore_database(backup, destination)
    except SQLiteBackupError as error:
        _output_sqlite_failure("SQLITE_RESTORE_FAILED", error)
        return
    output_json_dict({"status": "completed", **asdict(report)})


@app.command("run-eod")
def run_eod(
    signal_date: str = typer.Option(..., "--signal-date", help="信号日 YYYY-MM-DD"),
    strategy_id: str = typer.Option(..., "--strategy-id", help="显式选择活动执行策略"),
    account_id: str = typer.Option(..., "--account-id", help="显式选择人工交易账户"),
    allow_experimental_data: bool = typer.Option(
        False,
        "--allow-experimental-data",
        help="显式允许实验级数据集进入本次 EOD 策略输入",
    ),
) -> None:
    """运行与 Prefect 共用的 EOD 业务入口并结构化输出结果。"""
    result = run_eod_pipeline(
        trade_date=signal_date,
        strategy_id=strategy_id,
        account_id=account_id,
        allow_experimental_data=allow_experimental_data,
    )
    output_json_dict(dict(result))
    strategies = result.get("strategies", [])
    if isinstance(strategies, list) and any(
        isinstance(item, dict)
        and cast("dict[str, object]", item).get("status")
        in {"blocked", "failed", "rerun_conflict"}
        for item in cast("list[object]", strategies)
    ):
        raise typer.Exit(1)


@app.command("reattest-sparse-pit")
def reattest_sparse_pit(
    dataset: str = typer.Option(
        ...,
        "--dataset",
        help="稀疏 PIT 数据集, 如 balance_sheet",
    ),
    signal_date: str = typer.Option(
        ...,
        "--signal-date",
        help="恢复截止信号日 YYYY-MM-DD",
    ),
    source: str = typer.Option(
        "tushare",
        "--source",
        help="需要重摄取并核验的具体数据源",
    ),
) -> None:
    """全量重摄取稀疏 PIT 历史并重建可验证 L1/L2 证据。"""
    result = run_sparse_pit_reattestation(
        dataset=dataset,
        signal_date=signal_date,
        source=source,
    )
    output_json_dict(result)
    if result.get("passed") is not True:
        raise typer.Exit(1)


def _reconcile_primary(
    container: Container, date: str, dataset: str
) -> tuple[pl.DataFrame, Path]:
    """按数据集读取主源帧与数据根目录（未配置读取器/由调用方处理空帧）."""
    from ditto_apps.registry.infra.protocol_adapters import (  # noqa: PLC0415
        FinancialReconcileContextProtocol,
        MarketReaders,
        MarketService,
    )

    if dataset == "adj_factor":
        # adj_factor 主源：当日因子帧（比例所需回看窗由 handler 上下文提供）
        market = container.get(MarketService)
        return market.get_adj_factors(date, date), container.get(Path)
    if dataset in {"index_daily", "etf_nav"}:
        readers = container.get(MarketReaders)
        reader = readers.index_bars if dataset == "index_daily" else readers.etf_nav
        if reader is None:
            typer.secho(f"主源 {dataset} 读取器未配置", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        return reader.read(start_date=date, end_date=date), reader.data_root
    if dataset in {"income_statement", "balance_sheet", "cash_flow"}:
        # 财务主源：黄金集标的最新有效 vintage（辅源无历史 vintage 查询，
        # as-of 取当日与辅源同基线；DATE 参数仅作报告标签）
        financial_context = container.get(FinancialReconcileContextProtocol)
        return (
            financial_context.latest_statements(
                dataset, datetime.date.today().isoformat()
            ),
            container.get(Path),
        )
    stock_bars_reader = container.get(MarketReaders).stock_bars
    return (
        stock_bars_reader.read(start_date=date, end_date=date),
        stock_bars_reader.data_root,
    )


@app.command("reconcile")
def reconcile(
    date: str = typer.Argument(..., help="对账交易日 (YYYY-MM-DD)"),
    dataset: str = typer.Option(
        "stock_daily",
        "--dataset",
        help=(
            "对账数据集(stock_daily/adj_factor/index_daily/etf_nav/"
            "income_statement/balance_sheet/cash_flow)"
        ),
    ),
) -> None:
    """跨源对账: 主源存量 vs 辅源 fuyao(instrument_id+trade_date 同口径比较)."""
    supported = {
        "stock_daily",
        "adj_factor",
        "index_daily",
        "etf_nav",
        "income_statement",
        "balance_sheet",
        "cash_flow",
    }
    if dataset not in supported:
        typer.secho(f"暂不支持 {dataset} 对账", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    container: Container = make_app_container()
    try:
        handler = container.get(ReconcileSourcesHandler)
        primary_df, data_root = _reconcile_primary(container, date, dataset)
        if primary_df.is_empty():
            typer.secho(
                f"主源 {dataset} 在 {date} 无存量数据(先摄取再对账)",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)
        typer.echo(f"主源行数: {primary_df.height}")
        result = handler.handle(
            ReconcileSourcesCommand(
                primary_df=primary_df, trade_date=date, dataset=dataset
            )
        )
        typer.echo(
            "对账统计: "
            f"主侧={result.primary_count} 辅侧={result.secondary_count} "
            f"匹配={result.matched_count} "
            f"主侧未匹配={result.primary_unmatched_count} "
            f"辅侧未匹配={result.secondary_unmatched_count} "
            f"主侧重复键={result.primary_duplicate_keys} "
            f"辅侧重复键={result.secondary_duplicate_keys} "
            f"差异数={result.diff_count} "
            f"事件不可推导={result.secondary_underivable_count} "
            f"披露日错配={result.secondary_vintage_mismatch_count} "
            f"字段比较数={result.field_matched_counts}"
        )
        skipped = f" (skipped: {result.skip_reason})" if result.skipped else ""
        comparable = "可比" if result.comparable else "不可比较(无有效数值对)"
        color = typer.colors.GREEN if result.passed else typer.colors.RED
        typer.secho(
            f"对账结果: passed={result.passed} 比较={comparable} "
            f"issues={result.issue_count}{skipped}",
            fg=color,
        )
        if not result.passed:
            typer.secho(
                f"error: {result.error}"
                if result.error
                else f"对账未通过(详见 {data_root}/quarantine/quality_comparison/)",
                fg=typer.colors.RED,
            )
            raise typer.Exit(1)
    finally:
        container.close()


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
# factor-materialize: 治理因子物化（注册→计算→derived artifact）
# ---------------------------------------------------------------------------


@app.command("factor-materialize")
def factor_materialize(
    factor: str = typer.Argument(..., help="治理因子 ID, 当前治理集仅 momentum_1m"),
    start: str = typer.Option(..., "--start", help="请求窗口起始日 YYYY-MM-DD"),
    end: str = typer.Option(..., "--end", help="请求窗口结束日 YYYY-MM-DD"),
    version: int = typer.Option(1, "--version", min=1, help="物化版本号"),
    mode: str = typer.Option("full", "--mode", help="物化模式: full 或 incremental"),
) -> None:
    """治理因子物化: 幂等注册 DerivedSpec → 计算窗口 → 保存 derived artifact."""
    if mode not in {"full", "incremental"}:
        raise typer.BadParameter(
            f"非法物化模式: {mode!r}, 允许 full/incremental", param_hint="--mode"
        )
    try:
        output_json_dict(
            materialize_governed_factor(
                factor=factor, version=version, mode=mode, start=start, end=end
            )
        )
    except DittoError as exc:
        typer.secho(f"物化失败: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc


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
