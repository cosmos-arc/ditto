"""E2E 验收报告生成器。

提供端到端验证测试的报告生成功能，支持 Markdown 格式输出。

参考文档：docs/plans/2026-02-17-e2e-validation-design.md 第 5 节
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ditto_data.quality import GoldenDatasetSpec


@dataclass
class StageResult:
    """单个验证阶段结果。

    Attributes:
        name: 阶段名称。
        passed: 通过的测试数量。
        failed: 失败的测试数量。
        skipped: 跳过的测试数量。
        errors: 错误信息列表。

    """

    name: str
    passed: int
    failed: int
    skipped: int
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        """总测试数量（通过 + 失败 + 跳过）。"""
        return self.passed + self.failed + self.skipped

    @property
    def pass_rate(self) -> float:
        """通过率（百分比）。"""
        return self.passed / self.total * 100 if self.total > 0 else 0.0


class E2EReporter:
    """E2E 验收报告生成器。

    负责收集各验证阶段的结果，并生成 Markdown 格式的验收报告。

    Attributes:
        golden_spec: 黄金数据集配置。
        results: 各阶段结果的字典，键为阶段名称。

    Example:
        >>> reporter = E2EReporter(golden_spec)
        >>> reporter.record("Ingestion", StageResult("Ingestion", 5, 0, 0))
        >>> reporter.generate_markdown(Path("reports/e2e.md"))

    """

    def __init__(self, golden_spec: GoldenDatasetSpec) -> None:
        """初始化报告生成器。

        Args:
            golden_spec: 黄金数据集配置。

        """
        self.golden_spec = golden_spec
        self.results: dict[str, StageResult] = {}

    def record(self, stage: str, result: StageResult) -> None:
        """记录阶段结果。

        Args:
            stage: 阶段名称。
            result: 阶段结果对象。

        """
        self.results[stage] = result

    def generate_markdown(self, output_path: Path) -> None:
        """生成 Markdown 验收报告。

        创建报告文件到指定路径，自动创建父目录。

        Args:
            output_path: 报告输出路径。

        """
        content = self._build_report()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")

    def _all_passed(self) -> bool:
        """检查所有阶段是否全部通过（无失败）。"""
        return all(r.failed == 0 for r in self.results.values())

    def _build_report(self) -> str:
        """构建报告内容。

        Returns:
            Markdown 格式的报告字符串。

        """
        lines = [
            "# Ditto E2E 验收报告",
            "",
            f"**日期**: {date.today():%Y-%m-%d}",
            f"**黄金数据集**: {len(self.golden_spec.tickers)} 标的",
            f"**整体状态**: {'✅ 通过' if self._all_passed() else '❌ 未通过'}",
            "",
            "## 阶段汇总",
            "",
            "| 阶段 | 状态 | 通过率 | 备注 |",
            "|------|------|--------|------|",
        ]
        for name, result in self.results.items():
            status = "✅" if result.failed == 0 else "❌"
            lines.append(f"| {name} | {status} | {result.pass_rate:.0f}% | - |")

        lines.extend(
            [
                "",
                "## 问题清单",
                "",
                "| 编号 | 严重度 | 描述 | 状态 |",
                "|------|--------|------|------|",
            ]
        )
        for name, result in self.results.items():
            for err in result.errors:
                lines.append(f"| {name} | ERROR | {err} | 待处理 |")

        if self._all_passed():
            lines.extend(
                [
                    "",
                    "## 结论",
                    "",
                    "系统已通过端到端验证，具备上线条件。",  # noqa: RUF001
                ]
            )

        return "\n".join(lines)
