"""
AI agent 经验记忆 — 决策日志的记录与查询。

提供 ``DecisionLog`` 数据模型、``ExperienceMemory`` Protocol 以及基于
Markdown 文件的 ``MarkdownExperienceMemory`` 实现。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = ["DecisionLog", "ExperienceMemory", "MarkdownExperienceMemory"]

_HEADER = "# Experience Memory\n\n"

# 摘要中展示的最近决策条数
_SUMMARY_RECENT_COUNT = 5


@dataclass(frozen=True)
class DecisionLog:
    """
    一条 AI 决策日志。

    Attributes:
        timestamp: ISO 8601 时间戳。
        context: 决策上下文描述。
        decision: 采取的决策。
        outcome: 决策结果。
        reflection: AI 对决策的反思。
        tags: 分类标签。

    """

    timestamp: str
    context: str
    decision: str
    outcome: str
    reflection: str
    tags: tuple[str, ...]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ExperienceMemory(Protocol):
    """经验记忆 Protocol — AI agent 决策历史的记录与查询。"""

    def record(self, log: DecisionLog) -> None:
        """记录一条决策日志。"""
        ...

    def query(
        self,
        tags: tuple[str, ...] | None = None,
        *,
        limit: int = 50,
    ) -> tuple[DecisionLog, ...]:
        """查询决策日志，可按 tags 过滤。"""
        ...

    def summarize(self) -> str:
        """返回结构化摘要。"""
        ...


# ---------------------------------------------------------------------------
# Markdown 实现
# ---------------------------------------------------------------------------


def _format_entry(log: DecisionLog) -> str:
    """将 DecisionLog 格式化为一个 markdown 段落。"""
    tags_str = ", ".join(log.tags)
    return (
        f"## {log.timestamp}\n"
        f"\n"
        f"- **Context**: {log.context}\n"
        f"- **Decision**: {log.decision}\n"
        f"- **Outcome**: {log.outcome}\n"
        f"- **Reflection**: {log.reflection}\n"
        f"- **Tags**: {tags_str}\n"
        f"\n"
    )


def _parse_file(content: str) -> tuple[DecisionLog, ...]:
    """
    解析 markdown 文件内容为 DecisionLog 列表（按文件顺序）。

    Returns:
        按文件中出现顺序的 DecisionLog 列表（最早在前）。

    """
    if not content.strip():
        return ()

    # 按 ## 分割为段落
    parts = re.split(r"(?=^## )", content, flags=re.MULTILINE)
    logs: list[DecisionLog] = []
    for raw_part in parts:
        section = raw_part.strip()
        if not section.startswith("## "):
            continue

        lines = section.split("\n")
        timestamp = lines[0][3:].strip()

        field_map: dict[str, str] = {}
        for line in lines[1:]:
            m = re.match(r"^- \*\*(\w+)\*\*: (.+)$", line)
            if m:
                field_map[m.group(1)] = m.group(2)

        tags_raw = field_map.get("Tags", "")
        tags = tuple(t.strip() for t in tags_raw.split(",")) if tags_raw else ()

        logs.append(
            DecisionLog(
                timestamp=timestamp,
                context=field_map.get("Context", ""),
                decision=field_map.get("Decision", ""),
                outcome=field_map.get("Outcome", ""),
                reflection=field_map.get("Reflection", ""),
                tags=tags,
            )
        )

    return tuple(logs)


class MarkdownExperienceMemory:
    """
    基于 Markdown 文件的经验记忆实现。

    每个 ``DecisionLog`` 写为一个 ``##`` 段落，格式人类可读、AI 可解析。

    Args:
        path: Markdown 文件路径。

    """

    def __init__(self, path: Path) -> None:
        """
        初始化 Markdown 经验记忆。

        Args:
            path: Markdown 文件存储路径。文件不存在时首次写入自动创建。

        """
        self._path = path

    # -- record ---------------------------------------------------------------

    def record(self, log: DecisionLog) -> None:
        """
        将 DecisionLog 追加到文件末尾。

        如果文件不存在，先写入 header。
        """
        entry = _format_entry(log)

        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(_HEADER + entry, encoding="utf-8")
        else:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(entry)

    # -- query ----------------------------------------------------------------

    def query(
        self,
        tags: tuple[str, ...] | None = None,
        *,
        limit: int = 50,
    ) -> tuple[DecisionLog, ...]:
        """
        查询决策日志。

        Args:
            tags: 如果不为 ``None``，只返回包含任意指定 tag 的记录。
            limit: 最大返回条数。

        Returns:
            最新在前（按文件中反序）的 DecisionLog 列表。

        """
        if not self._path.exists():
            return ()

        content = self._path.read_text(encoding="utf-8")
        all_logs = _parse_file(content)

        # 过滤
        if tags is not None:
            tag_set = set(tags)
            filtered = tuple(log for log in all_logs if tag_set & set(log.tags))
        else:
            filtered = all_logs

        # 反序（最新在前）+ limit
        return tuple(reversed(filtered))[:limit]

    # -- summarize ------------------------------------------------------------

    def summarize(self) -> str:
        """返回结构化摘要：总记录数、tag 统计、最近 N 条决策。"""
        if not self._path.exists():
            return "总记录数: 0\n"

        content = self._path.read_text(encoding="utf-8")
        all_logs = _parse_file(content)

        if not all_logs:
            return "总记录数: 0\n"

        # tag 统计
        tag_counts: dict[str, int] = {}
        for log in all_logs:
            for tag in log.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        tag_stats = "\n".join(
            f"  {tag}: {count}" for tag, count in sorted(tag_counts.items())
        )

        # 最近 N 条（最新在前）
        recent = tuple(reversed(all_logs))[:_SUMMARY_RECENT_COUNT]
        recent_lines = "\n".join(
            f"  [{log.timestamp}] {log.decision}" for log in recent
        )

        return (
            f"总记录数: {len(all_logs)}\n"
            f"\n"
            f"Tag 统计:\n"
            f"{tag_stats}\n"
            f"\n"
            f"最近决策:\n"
            f"{recent_lines}\n"
        )
