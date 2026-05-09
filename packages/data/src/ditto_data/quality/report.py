"""DQ report generators."""

from io import StringIO
from pathlib import Path

from ditto_data.quality.kernel_types import DQIssue, DQLevel, DQResult, DQSeverity


class DQReportGenerator:
    """DQ 检查报告生成器。"""

    def generate_markdown_report(self, result: DQResult) -> str:
        """
        生成 Markdown 格式报告。

        Args:
            result: DQ 检查结果

        Returns:
            Markdown 报告文本

        """
        buffer = StringIO()

        # 标题
        buffer.write("# 数据质量检查报告\n\n")
        buffer.write(f"**数据集**: {result.dataset}\n")
        buffer.write(f"**状态**: {'✅ 通过' if result.passed else '❌ 失败'}\n")
        buffer.write(f"**问题总数**: {result.total_count}\n\n")

        # 按级别分组
        l1_issues = [i for i in result.issues if i.level == DQLevel.TECHNICAL]
        l2_issues = [i for i in result.issues if i.level == DQLevel.BUSINESS]
        l3_issues = [i for i in result.issues if i.level == DQLevel.STATISTICAL]

        # L1 技术校验
        buffer.write("## L1 技术校验(阻断写入)\n\n")
        if l1_issues:
            for issue in l1_issues:
                buffer.write(f"- **{issue.rule_name}**: {issue.message}\n")
                buffer.write(f"  - 影响行数: {issue.affected_rows}\n")
                buffer.write(f"  - 严重级别: {issue.severity.value}\n")
        else:
            buffer.write("无问题 ✅\n")

        # L2 业务规则
        buffer.write("\n## L2 业务规则(警告记录)\n\n")
        if l2_issues:
            for issue in l2_issues:
                buffer.write(f"- **{issue.rule_name}**: {issue.message}\n")
                buffer.write(f"  - 影响行数: {issue.affected_rows}\n")
        else:
            buffer.write("无问题 ✅\n")

        # L3 统计异常
        buffer.write("\n## L3 统计异常(告警通知)\n\n")
        if l3_issues:
            for issue in l3_issues:
                buffer.write(f"- **{issue.rule_name}**: {issue.message}\n")
                buffer.write(f"  - 影响行数: {issue.affected_rows}\n")
        else:
            buffer.write("无问题 ✅\n")

        # 统计摘要
        buffer.write("\n## 统计摘要\n\n")
        buffer.write("| 指标 | 数值 |\n")
        buffer.write("|------|------|\n")
        buffer.write(f"| ERROR | {result.error_count} |\n")
        buffer.write(f"| WARNING | {result.warn_count} |\n")
        buffer.write(f"| ALERT | {result.alert_count} |\n")
        buffer.write(f"| 总计 | {result.total_count} |\n")

        return buffer.getvalue()

    def generate_html_report(self, result: DQResult) -> str:
        """
        生成 HTML 格式报告。

        Args:
            result: DQ 检查结果

        Returns:
            HTML 报告文本

        """
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>DQ 报告 - {result.dataset}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #666; border-bottom: 1px solid #ddd; padding-bottom: 10px; }}
        .status {{ padding: 10px; border-radius: 5px; margin: 10px 0; }}
        .status.pass {{ background-color: #d4edda; color: #155724; }}
        .status.fail {{ background-color: #f8d7da; color: #721c24; }}
        .issue {{ margin: 10px 0; padding: 10px; border-left: 3px solid #ddd; }}
        .issue.error {{ border-left-color: #dc3545; background-color: #f8d7da; }}
        .issue.warning {{ border-left-color: #ffc107; background-color: #fff3cd; }}
        .issue.alert {{ border-left-color: #fd7e14; background-color: #ffe5d0; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .summary {{ display: flex; gap: 20px; }}
        .summary-item {{ flex: 1; }}
        .summary-value {{ font-size: 24px; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>数据质量检查报告</h1>
    <div class="status {"pass" if result.passed else "fail"}">
        <strong>状态:</strong> {"&#10003; 通过" if result.passed else "&#10060; 失败"}
        <strong>数据集:</strong> {result.dataset}
    </div>

    <div class="summary">
        <div class="summary-item">
            <div>ERROR</div>
            <div class="summary-value" style="color: #dc3545">{result.error_count}</div>
        </div>
        <div class="summary-item">
            <div>WARNING</div>
            <div class="summary-value" style="color: #ffc107">{result.warn_count}</div>
        </div>
        <div class="summary-item">
            <div>ALERT</div>
            <div class="summary-value" style="color: #fd7e14">{result.alert_count}</div>
        </div>
    </div>

    <h2>L1 技术校验(阻断写入)</h2>
    {
            self._render_issues_html(
                [i for i in result.issues if i.level == DQLevel.TECHNICAL]
            )
        }

    <h2>L2 业务规则(警告记录)</h2>
    {
            self._render_issues_html(
                [i for i in result.issues if i.level == DQLevel.BUSINESS]
            )
        }

    <h2>L3 统计异常(告警通知)</h2>
    {
            self._render_issues_html(
                [i for i in result.issues if i.level == DQLevel.STATISTICAL]
            )
        }

</body>
</html>"""
        return html

    def _render_issues_html(self, issues: list[DQIssue]) -> str:
        """
        渲染问题列表为 HTML。

        Args:
            issues: 问题列表

        Returns:
            HTML 片段

        """
        if not issues:
            return "<p>无问题 &#10003;</p>"

        html: list[str] = []
        for issue in issues:
            severity_class = (
                "error"
                if issue.severity == DQSeverity.ERROR
                else "warning"
                if issue.severity == DQSeverity.WARNING
                else "alert"
            )
            html.append(f"""
            <div class="issue {severity_class}">
                <strong>{issue.rule_name}</strong>: {issue.message}<br>
                <small>影响行数: {issue.affected_rows}</small>
            </div>
            """)

        return "\n".join(html)

    def save_report(
        self,
        result: DQResult,
        output_path: str | Path,
        report_format: str = "markdown",
    ) -> None:
        """
        保存报告到文件。

        Args:
            result: DQ 检查结果
            output_path: 输出文件路径
            report_format: 报告格式（markdown 或 html）

        """
        output_path = Path(output_path)

        if report_format == "markdown":
            content = self.generate_markdown_report(result)
            suffix = ".md"
        elif report_format == "html":
            content = self.generate_html_report(result)
            suffix = ".html"
        else:
            raise ValueError(f"Unsupported format: {report_format}")

        # 确保目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 添加后缀（如果没有）
        if not output_path.suffix:
            output_path = output_path.with_suffix(suffix)

        output_path.write_text(content, encoding="utf-8")

    def generate_batch_summary(
        self,
        results: dict[str, DQResult],
        trade_date: str | None = None,
    ) -> str:
        """
        生成批量检查摘要报告。

        Args:
            results: 数据集 -> DQResult 的映射
            trade_date: 交易日期

        Returns:
            Markdown 摘要报告

        """
        buffer = StringIO()

        buffer.write("# DQ 批量检查摘要\n\n")

        if trade_date:
            buffer.write(f"**交易日期**: {trade_date}\n")

        total_issues = sum(len(r.issues) for r in results.values())
        total_errors = sum(r.error_count for r in results.values())
        total_warnings = sum(r.warn_count for r in results.values())
        total_alerts = sum(r.alert_count for r in results.values())
        passed_count = sum(1 for r in results.values() if r.passed)

        buffer.write("\n## 总体统计\n\n")
        buffer.write(f"- 检查数据集: {len(results)}\n")
        buffer.write(f"- 通过数据集: {passed_count}\n")
        buffer.write(f"- 失败数据集: {len(results) - passed_count}\n")
        buffer.write(f"- ERROR 总数: {total_errors}\n")
        buffer.write(f"- WARNING 总数: {total_warnings}\n")
        buffer.write(f"- ALERT 总数: {total_alerts}\n")
        buffer.write(f"- 问题总数: {total_issues}\n\n")

        # 各数据集详情
        buffer.write("## 数据集详情\n\n")
        for dataset, result in results.items():
            status = "✅" if result.passed else "❌"
            buffer.write(f"### {status} {dataset}\n")
            buffer.write(f"- ERROR: {result.error_count}\n")
            buffer.write(f"- WARNING: {result.warn_count}\n")
            buffer.write(f"- ALERT: {result.alert_count}\n")
            buffer.write(f"- 总计: {result.total_count}\n\n")

        return buffer.getvalue()
