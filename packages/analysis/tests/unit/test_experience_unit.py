"""DecisionLog 与 MarkdownExperienceMemory 单元测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from ditto_analysis.research.experience import (
    DecisionLog,
    ExperienceMemory,
    MarkdownExperienceMemory,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_log(
    timestamp: str = "2024-01-15T10:30:00",
    context: str = "回测 2024-01 ETF轮动",
    decision: str = "增加持仓集中度到 Top 3",
    outcome: str = "夏普比率从 0.8 提升到 1.2",
    reflection: str = "集中度策略在趋势市场中表现更好",
    tags: tuple[str, ...] = ("etf-rotation", "concentration", "backtest"),
) -> DecisionLog:
    """创建测试用 DecisionLog。"""
    return DecisionLog(
        timestamp=timestamp,
        context=context,
        decision=decision,
        outcome=outcome,
        reflection=reflection,
        tags=tags,
    )


def _exp_path(tmp_path: Path) -> Path:
    """返回测试用 markdown 文件路径。"""
    return tmp_path / "exp.md"


# ---------------------------------------------------------------------------
# 1. DecisionLog 创建与字段验证
# ---------------------------------------------------------------------------
class TestDecisionLog:
    def test_decision_log_creation(self) -> None:
        """创建 DecisionLog 并验证所有字段。"""
        log = _make_log()
        assert log.timestamp == "2024-01-15T10:30:00"
        assert log.context == "回测 2024-01 ETF轮动"
        assert log.decision == "增加持仓集中度到 Top 3"
        assert log.outcome == "夏普比率从 0.8 提升到 1.2"
        assert log.reflection == "集中度策略在趋势市场中表现更好"
        assert log.tags == ("etf-rotation", "concentration", "backtest")

    def test_decision_log_frozen(self) -> None:
        """frozen dataclass 不允许修改字段。"""
        log = _make_log()
        with pytest.raises(FrozenInstanceError):
            log.timestamp = "2024-02-01T00:00:00"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. MarkdownExperienceMemory
# ---------------------------------------------------------------------------
class TestMarkdownExperienceMemory:
    def test_markdown_memory_isinstance_protocol(self) -> None:
        """MarkdownExperienceMemory 满足 ExperienceMemory Protocol。"""
        mem = MarkdownExperienceMemory(Path("/tmp/dummy_exp.md"))
        assert isinstance(mem, ExperienceMemory)

    def test_markdown_memory_record_and_query(self, tmp_path: Path) -> None:
        """record 写入后 query 能读回一致的 DecisionLog。"""
        mem = MarkdownExperienceMemory(_exp_path(tmp_path))
        log = _make_log()
        mem.record(log)

        results = mem.query()
        assert len(results) == 1
        assert results[0] == log

    def test_markdown_memory_file_format(self, tmp_path: Path) -> None:
        """验证生成的 markdown 文件内容格式正确。"""
        path = _exp_path(tmp_path)
        mem = MarkdownExperienceMemory(path)
        log = _make_log()
        mem.record(log)

        content = path.read_text(encoding="utf-8")
        # 文件以 header 开头
        assert content.startswith("# Experience Memory\n\n")
        # 包含 ## 段落
        assert "## 2024-01-15T10:30:00\n" in content
        # 字段格式
        assert "- **Context**: 回测 2024-01 ETF轮动\n" in content
        assert "- **Decision**: 增加持仓集中度到 Top 3\n" in content
        assert "- **Outcome**: 夏普比率从 0.8 提升到 1.2\n" in content
        assert "- **Reflection**: 集中度策略在趋势市场中表现更好\n" in content
        assert "- **Tags**: etf-rotation, concentration, backtest\n" in content

    def test_markdown_memory_query_by_tags(self, tmp_path: Path) -> None:
        """按 tags 过滤记录。"""
        mem = MarkdownExperienceMemory(_exp_path(tmp_path))

        log_a = _make_log(
            timestamp="2024-01-15T10:00:00",
            tags=("etf-rotation",),
        )
        log_b = _make_log(
            timestamp="2024-01-16T14:00:00",
            tags=("momentum",),
        )
        mem.record(log_a)
        mem.record(log_b)

        # 过滤 etf-rotation
        results = mem.query(tags=("etf-rotation",))
        assert len(results) == 1
        assert results[0].timestamp == "2024-01-15T10:00:00"

        # 过滤 momentum
        results = mem.query(tags=("momentum",))
        assert len(results) == 1
        assert results[0].timestamp == "2024-01-16T14:00:00"

    def test_markdown_memory_query_no_match_returns_empty(self, tmp_path: Path) -> None:
        """无匹配 tags 返回空 tuple。"""
        mem = MarkdownExperienceMemory(_exp_path(tmp_path))
        mem.record(_make_log())

        results = mem.query(tags=("nonexistent",))
        assert results == ()

    def test_markdown_memory_summarize(self, tmp_path: Path) -> None:
        """summarize 返回结构化摘要。"""
        mem = MarkdownExperienceMemory(_exp_path(tmp_path))
        mem.record(_make_log(timestamp="2024-01-15T10:00:00", tags=("a", "b")))
        mem.record(_make_log(timestamp="2024-01-16T14:00:00", tags=("a", "c")))

        summary = mem.summarize()
        assert "总记录数: 2" in summary
        assert "a" in summary
        # 最近决策列表
        assert "2024-01-16T14:00:00" in summary

    def test_markdown_memory_empty_file_query(self, tmp_path: Path) -> None:
        """空文件 query 返回空 tuple。"""
        mem = MarkdownExperienceMemory(_exp_path(tmp_path))

        # 文件不存在时 query
        results = mem.query()
        assert results == ()

    def test_markdown_memory_multiple_records_order(self, tmp_path: Path) -> None:
        """多条记录 query 返回最新在前（按文件中反序）。"""
        mem = MarkdownExperienceMemory(_exp_path(tmp_path))

        mem.record(_make_log(timestamp="2024-01-10T08:00:00"))
        mem.record(_make_log(timestamp="2024-01-15T10:00:00"))
        mem.record(_make_log(timestamp="2024-01-20T12:00:00"))

        results = mem.query()
        assert len(results) == 3
        # 最新在前
        assert results[0].timestamp == "2024-01-20T12:00:00"
        assert results[1].timestamp == "2024-01-15T10:00:00"
        assert results[2].timestamp == "2024-01-10T08:00:00"
