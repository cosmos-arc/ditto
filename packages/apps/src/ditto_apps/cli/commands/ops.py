"""CLI 运维命令组 - 数据集状态与质量检查."""

from __future__ import annotations

from typing import Any

import typer
from ditto_application.config import Dataset
from ditto_application.processes.quality.patrol import QualityPatrolService
from ditto_application.queries.ingestion_status import IngestionStatusQueryFacade

from ditto_apps.cli.utils.output import output_json_dicts
from ditto_apps.registry.container import Container, make_app_container

app = typer.Typer(help="运维命令")

# 从 Dataset StrEnum 派生，保证单一事实来源（自动包含 index_weight）
_KNOWN_DATASETS = Dataset.all_datasets()

# 核心数据集 (dq 默认检查范围)，从 Dataset 枚举派生避免硬编码
_CORE_DATASETS = [
    d.value
    for d in (
        Dataset.ETF_DAILY,
        Dataset.STOCK_DAILY,
        Dataset.INDEX_DAILY,
        Dataset.ADJ_FACTOR,
    )
]

# 表格列宽
_COL_DATASET = 24
_COL_DATE = 14
_COL_STATUS = 10
_COL_RECORDS = 10


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
                    "record_count": s.record_count,
                    "last_attempt": s.last_attempt,
                }
                for s in statuses
            ]

            if json:
                output_json_dicts(rows)
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
