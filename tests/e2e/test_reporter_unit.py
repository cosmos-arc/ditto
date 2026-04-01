"""E2EReporter 单元测试。

测试 reporter.py 中的以下组件：
- StageResult.total 属性计算
- StageResult.pass_rate 属性计算（包括 total=0 边界情况）
- E2EReporter.record() 方法
- E2EReporter._all_passed() 方法（包括空结果情况）
- E2EReporter._build_report() 输出格式
- E2EReporter.generate_markdown() 文件生成

参考文档：docs/plans/2026-02-17-e2e-validation-plan.md
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# 确保 tests 目录在 sys.path 中（支持 xdist 并行测试）
_tests_root = Path(__file__).parent.parent
if str(_tests_root) not in sys.path:
    sys.path.insert(0, str(_tests_root))

import pytest  # noqa: E402
from ditto_data.quality import GoldenDatasetSpec  # noqa: E402

from tests.e2e.reporter import E2EReporter, StageResult  # noqa: E402


def _make_result(
    name: str,
    passed: int = 0,
    failed: int = 0,
    skipped: int = 0,
    errors: list[str] | None = None,
) -> StageResult:
    """创建 StageResult 的辅助函数。"""
    return StageResult(
        name=name,
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors or [],
    )


def _make_reporter(tickers: list[str] | None = None) -> E2EReporter:
    """创建 E2EReporter 的辅助函数。"""
    spec = GoldenDatasetSpec(tickers=tickers or ["000001.SZ"])
    return E2EReporter(spec)


# ==============================================================================
# StageResult.total 属性测试
# ==============================================================================


@pytest.mark.unit
def test_stage_result_total_returns_sum_of_all_counts() -> None:
    """测试 total 返回通过、失败、跳过数量的总和。"""
    # Arrange
    result = _make_result(name="Ingestion", passed=5, failed=2, skipped=3)

    # Act
    total = result.total

    # Assert
    assert total == 10


@pytest.mark.unit
def test_stage_result_total_returns_zero_when_all_zero() -> None:
    """测试所有计数为零时 total 返回零。"""
    # Arrange
    result = _make_result(name="Empty")

    # Act
    total = result.total

    # Assert
    assert total == 0


# ==============================================================================
# StageResult.pass_rate 属性测试
# ==============================================================================


@pytest.mark.unit
def test_stage_result_pass_rate_returns_percentage() -> None:
    """测试 pass_rate 返回正确的百分比。"""
    # Arrange
    result = _make_result(name="Ingestion", passed=8, failed=2)

    # Act
    pass_rate = result.pass_rate

    # Assert
    assert pass_rate == 80.0


@pytest.mark.unit
def test_stage_result_pass_rate_handles_partial_passed() -> None:
    """测试部分通过时的 pass_rate 计算。"""
    # Arrange
    result = _make_result(name="Ingestion", passed=1)

    # Act
    pass_rate = result.pass_rate

    # Assert
    assert pass_rate == 100.0


@pytest.mark.unit
def test_stage_result_pass_rate_returns_zero_when_total_is_zero() -> None:
    """测试 total=0 边界情况返回 0.0。"""
    # Arrange
    result = _make_result(name="Empty")

    # Act
    pass_rate = result.pass_rate

    # Assert
    assert pass_rate == 0.0


@pytest.mark.unit
def test_stage_result_pass_rate_includes_skipped_in_total() -> None:
    """测试 pass_rate 计算时包含跳过数量。"""
    # Arrange: 5 passed, 2 failed, 3 skipped = 10 total
    result = _make_result(name="Mixed", passed=5, failed=2, skipped=3)

    # Act
    pass_rate = result.pass_rate

    # Assert: 5/10 = 50%
    assert pass_rate == 50.0


# ==============================================================================
# E2EReporter.record() 方法测试
# ==============================================================================


@pytest.mark.unit
def test_record_stages_result_in_results_dict() -> None:
    """测试 record 方法将结果存入 results 字典。"""
    # Arrange
    reporter = _make_reporter()
    result = _make_result(name="Ingestion", passed=5)

    # Act
    reporter.record("Ingestion", result)

    # Assert
    assert "Ingestion" in reporter.results
    assert reporter.results["Ingestion"] == result


@pytest.mark.unit
def test_record_overwrites_existing_stage_result() -> None:
    """测试 record 方法覆盖同名阶段的已有结果。"""
    # Arrange
    reporter = _make_reporter()
    first_result = _make_result(name="Ingestion", passed=3, failed=1)
    second_result = _make_result(name="Ingestion", passed=5)

    # Act
    reporter.record("Ingestion", first_result)
    reporter.record("Ingestion", second_result)

    # Assert
    assert reporter.results["Ingestion"] == second_result
    assert reporter.results["Ingestion"].passed == 5


@pytest.mark.unit
def test_record_stores_multiple_different_stages() -> None:
    """测试 record 方法存储多个不同阶段的结果。"""
    # Arrange
    reporter = _make_reporter()
    ingestion = _make_result(name="Ingestion", passed=5)
    quality = _make_result(name="Quality", passed=10, failed=1)

    # Act
    reporter.record("Ingestion", ingestion)
    reporter.record("Quality", quality)

    # Assert
    assert len(reporter.results) == 2
    assert reporter.results["Ingestion"] == ingestion
    assert reporter.results["Quality"] == quality


# ==============================================================================
# E2EReporter._all_passed() 方法测试
# ==============================================================================


@pytest.mark.unit
def test_all_passed_returns_true_when_no_failures() -> None:
    """测试所有阶段无失败时返回 True。"""
    # Arrange
    reporter = _make_reporter()
    reporter.record("Ingestion", _make_result(name="Ingestion", passed=5))
    reporter.record("Quality", _make_result(name="Quality", passed=10, skipped=2))

    # Act
    all_passed = reporter._all_passed()

    # Assert
    assert all_passed is True


@pytest.mark.unit
def test_all_passed_returns_false_when_any_failure() -> None:
    """测试任意阶段有失败时返回 False。"""
    # Arrange
    reporter = _make_reporter()
    reporter.record("Ingestion", _make_result(name="Ingestion", passed=5))
    reporter.record("Quality", _make_result(name="Quality", passed=8, failed=2))

    # Act
    all_passed = reporter._all_passed()

    # Assert
    assert all_passed is False


@pytest.mark.unit
def test_all_passed_returns_true_when_results_empty() -> None:
    """测试空结果情况返回 True（all() 对空序列返回 True）。"""
    # Arrange
    reporter = _make_reporter()

    # Act
    all_passed = reporter._all_passed()

    # Assert: all() on empty iterable returns True
    assert all_passed is True


# ==============================================================================
# E2EReporter._build_report() 输出格式测试
# ==============================================================================


@pytest.mark.unit
def test_build_report_contains_header_and_metadata() -> None:
    """测试报告包含标题和元数据。"""
    # Arrange
    reporter = _make_reporter(tickers=["000001.SZ", "000002.SZ"])

    # Act
    report = reporter._build_report()

    # Assert
    assert "# Ditto E2E 验收报告" in report
    assert "**日期**:" in report
    assert "**黄金数据集**: 2 标的" in report


@pytest.mark.unit
def test_build_report_shows_passed_status_when_all_passed() -> None:
    """测试全部通过时显示通过状态。"""
    # Arrange
    reporter = _make_reporter()
    reporter.record("Ingestion", _make_result(name="Ingestion", passed=5))

    # Act
    report = reporter._build_report()

    # Assert
    assert "**整体状态**: ✅ 通过" in report


@pytest.mark.unit
def test_build_report_shows_failed_status_when_any_failure() -> None:
    """测试有失败时显示未通过状态。"""
    # Arrange
    reporter = _make_reporter()
    reporter.record("Ingestion", _make_result(name="Ingestion", passed=3, failed=2))

    # Act
    report = reporter._build_report()

    # Assert
    assert "**整体状态**: ❌ 未通过" in report


@pytest.mark.unit
def test_build_report_contains_stage_summary_table() -> None:
    """测试报告包含阶段汇总表格。"""
    # Arrange
    reporter = _make_reporter()
    reporter.record("Ingestion", _make_result(name="Ingestion", passed=8, failed=2))
    reporter.record("Quality", _make_result(name="Quality", passed=10))

    # Act
    report = reporter._build_report()

    # Assert
    assert "## 阶段汇总" in report
    assert "| 阶段 | 状态 | 通过率 | 备注 |" in report
    assert "| Ingestion | ❌ | 80% |" in report
    assert "| Quality | ✅ | 100% |" in report


@pytest.mark.unit
def test_build_report_contains_issue_list_with_errors() -> None:
    """测试报告包含错误的问题清单。"""
    # Arrange
    reporter = _make_reporter()
    reporter.record(
        "Ingestion",
        _make_result(
            name="Ingestion",
            passed=3,
            failed=2,
            errors=["数据缺失", "格式错误"],
        ),
    )

    # Act
    report = reporter._build_report()

    # Assert
    assert "## 问题清单" in report
    assert "| Ingestion | ERROR | 数据缺失 | 待处理 |" in report
    assert "| Ingestion | ERROR | 格式错误 | 待处理 |" in report


@pytest.mark.unit
def test_build_report_contains_conclusion_when_all_passed() -> None:
    """测试全部通过时包含结论部分。"""
    # Arrange
    reporter = _make_reporter()
    reporter.record("Ingestion", _make_result(name="Ingestion", passed=5))

    # Act
    report = reporter._build_report()

    # Assert
    assert "## 结论" in report
    assert "系统已通过端到端验证" in report


@pytest.mark.unit
def test_build_report_excludes_conclusion_when_has_failures() -> None:
    """测试有失败时不包含结论部分。"""
    # Arrange
    reporter = _make_reporter()
    reporter.record("Ingestion", _make_result(name="Ingestion", passed=3, failed=2))

    # Act
    report = reporter._build_report()

    # Assert
    assert "## 结论" not in report


@pytest.mark.unit
def test_build_report_uses_current_date() -> None:
    """测试报告使用当前日期。"""
    # Arrange
    reporter = _make_reporter()
    expected_date = date.today().strftime("%Y-%m-%d")

    # Act
    report = reporter._build_report()

    # Assert
    assert expected_date in report


# ==============================================================================
# E2EReporter.generate_markdown() 文件生成测试
# ==============================================================================


@pytest.mark.unit
def test_generate_markdown_creates_file_at_specified_path(tmp_path: Path) -> None:
    """测试 generate_markdown 在指定路径创建文件。"""
    # Arrange
    reporter = _make_reporter()
    reporter.record("Ingestion", _make_result(name="Ingestion", passed=5))
    output_path = tmp_path / "reports" / "e2e_report.md"

    # Act
    reporter.generate_markdown(output_path)

    # Assert
    assert output_path.exists()


@pytest.mark.unit
def test_generate_markdown_creates_parent_directories(tmp_path: Path) -> None:
    """测试 generate_markdown 自动创建父目录。"""
    # Arrange
    reporter = _make_reporter()
    output_path = tmp_path / "deeply" / "nested" / "path" / "report.md"

    # Act
    reporter.generate_markdown(output_path)

    # Assert
    assert output_path.parent.exists()
    assert output_path.exists()


@pytest.mark.unit
def test_generate_markdown_writes_report_content(tmp_path: Path) -> None:
    """测试 generate_markdown 写入报告内容。"""
    # Arrange
    reporter = _make_reporter()
    reporter.record("Ingestion", _make_result(name="Ingestion", passed=5))
    output_path = tmp_path / "report.md"

    # Act
    reporter.generate_markdown(output_path)

    # Assert
    content = output_path.read_text(encoding="utf-8")
    assert "# Ditto E2E 验收报告" in content
    assert "Ingestion" in content


@pytest.mark.unit
def test_generate_markdown_uses_utf8_encoding(tmp_path: Path) -> None:
    """测试 generate_markdown 使用 UTF-8 编码。"""
    # Arrange
    reporter = _make_reporter()
    reporter.record("Test", _make_result(name="Test", passed=1))
    output_path = tmp_path / "report.md"

    # Act
    reporter.generate_markdown(output_path)

    # Assert: 文件包含中文内容，能正常读取说明编码正确
    content = output_path.read_text(encoding="utf-8")
    assert "验收报告" in content
    assert "✅" in content


@pytest.mark.unit
def test_generate_markdown_overwrites_existing_file(tmp_path: Path) -> None:
    """测试 generate_markdown 覆盖已存在的文件。"""
    # Arrange
    reporter = _make_reporter()
    output_path = tmp_path / "report.md"

    # 第一次写入
    reporter.record("First", _make_result(name="First", passed=1))
    reporter.generate_markdown(output_path)

    # 第二次写入（覆盖）
    reporter.results.clear()
    reporter.record("Second", _make_result(name="Second", passed=2))
    reporter.generate_markdown(output_path)
    second_content = output_path.read_text(encoding="utf-8")

    # Assert
    assert "First" not in second_content
    assert "Second" in second_content
