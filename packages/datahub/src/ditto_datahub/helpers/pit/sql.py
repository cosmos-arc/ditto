"""
PIT SQL 辅助函数模块.

提供半自动的 PIT (Point-in-Time) SQL 生成辅助函数。
"""

from __future__ import annotations

import re

from ditto_datahub.helpers.pit.policy import PIT_QUERY_OPERATOR


class PitHelper:
    """
    PIT SQL 辅助函数类.

    提供半自动的 PIT SQL 生成，帮助开发者编写符合 PIT 安全规则的查询。

    注意：
    - 这是辅助函数，不是全自动解决方案
    - 开发者仍需理解 PIT 概念和规则
    - 参考 .claude/skills/pit-guide/SKILL.md 了解详情
    """

    @staticmethod
    def _validate_date_string(date_str: str) -> None:
        """
        验证日期字符串格式，防止 SQL 注入.

        Args:
        ----
            date_str: 日期字符串

        Raises:
        ------
            ValueError: 当日期格式无效时

        """
        # 使用正则表达式验证日期格式：YYYY-MM-DD
        # 只允许数字和短横线，拒绝其他字符（包括单引号、分号、注释符号等）
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            raise ValueError(f"Invalid date format: {date_str}")

    @staticmethod
    def _validate_sql_identifier(identifier: str, name: str = "identifier") -> None:
        """
        验证 SQL 标识符格式，防止 SQL 注入.

        Args:
        ----
            identifier: SQL 标识符（表名、列名、CTE名等）
            name: 参数名称（用于错误消息）

        Raises:
        ------
            ValueError: 当标识符格式无效时

        """
        # 只允许字母、数字、下划线，且必须以字母或下划线开头
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier):
            raise ValueError(f"Invalid {name}: {identifier}")

    @staticmethod
    def add_pit_filter(
        query: str,
        knowledge_date: str,
        date_column: str = "knowledge_date",
    ) -> str:
        """
        为查询添加 PIT 过滤条件.

        Args:
        ----
            query: 原始 SQL 查询
            knowledge_date: 知识日期 (PIT 时间点)
            date_column: 日期列名，默认为 "knowledge_date"

        Returns:
        -------
            添加了 PIT 过滤条件的 SQL 查询

        Examples:
        --------
            >>> query = "SELECT * FROM stock_daily"
            >>> PitHelper.add_pit_filter(query, "2024-01-15")
            "SELECT * FROM stock_daily WHERE knowledge_date <= '2024-01-15'"

        """
        # 验证日期格式和列名，防止 SQL 注入
        PitHelper._validate_date_string(knowledge_date)
        PitHelper._validate_sql_identifier(date_column, "date_column")

        query = query.strip()

        # 检测 ORDER BY / LIMIT / GROUP BY / HAVING 子句
        # 如果存在这些子句，需要使用 CTE 包装
        if re.search(r"\b(ORDER BY|LIMIT|GROUP BY|HAVING)\b", query, re.IGNORECASE):
            # 使用 CTE 包装以避免破坏原有 SQL 结构
            pit_filter = f"{date_column} {PIT_QUERY_OPERATOR} '{knowledge_date}'"
            wrapped = (
                f"WITH _pit_original AS ({query}) "  # noqa: S608
                f"SELECT * FROM _pit_original WHERE {pit_filter}"
            )
            return wrapped

        # 检查是否已有 WHERE 子句（使用正则表达式，不区分大小写）
        # \bWHERE\b 确保匹配完整的 WHERE 关键字，避免匹配到包含 WHERE 的其他词
        if re.search(r"\bWHERE\b", query, re.IGNORECASE):
            # 已有 WHERE，添加 AND 条件
            return f"{query} AND {date_column} {PIT_QUERY_OPERATOR} '{knowledge_date}'"
        # 没有 WHERE，添加 WHERE 子句
        return f"{query} WHERE {date_column} {PIT_QUERY_OPERATOR} '{knowledge_date}'"

    @staticmethod
    def add_pit_join(
        left_table: str,
        right_table: str,
        join_keys: list[str],
        asof_date: str,
        date_column: str = "trade_date",
    ) -> str:
        """
        生成 PIT ASOF JOIN SQL.

        ASOF JOIN 用于将时间序列数据与另一个表的时间点数据进行关联，
        使用 "<=" 条件而非 "="，确保使用 "已知" 的数据进行关联。

        Args:
        ----
            left_table: 左表名称
            right_table: 右表名称
            join_keys: 连接键列表（不包含时间列）
            asof_date: ASOF 日期
            date_column: 右表的时间列名，默认 "trade_date"

        Returns:
        -------
            PIT ASOF JOIN SQL 片段

        Examples:
        --------
            >>> PitHelper.add_pit_join(
            ...     "stock_daily s",
            ...     "adj_factor a",
            ...     ["s.instrument_id = a.instrument_id"],
            ...     "2024-01-15"
            ... )
            "stock_daily s LEFT JOIN adj_factor a ON s.instrument_id = a.instrument_id "
            "AND a.trade_date <= '2024-01-15'"

            >>> PitHelper.add_pit_join(
            ...     "stock_daily s",
            ...     "adj_factor a",
            ...     ["s.instrument_id = a.instrument_id"],
            ...     "2024-01-15",
            ...     date_column="effective_from"
            ... )
            "stock_daily s LEFT JOIN adj_factor a ON s.instrument_id = a.instrument_id "
            "AND a.effective_from <= '2024-01-15'"

        """
        # 验证日期格式和列名，防止 SQL 注入
        PitHelper._validate_date_string(asof_date)
        PitHelper._validate_sql_identifier(date_column, "date_column")

        # 构建 ON 子句
        on_clause = " AND ".join(join_keys)

        # 提取右表别名
        # right_table 格式: "table_name alias" 或 "table_name alias"
        _MIN_TABLE_PARTS = 2
        parts = right_table.strip().split()
        right_alias = parts[-1] if len(parts) >= _MIN_TABLE_PARTS else right_table

        # 添加 PIT 条件（使用指定的 date_column）
        pit_condition = f"{right_alias}.{date_column} {PIT_QUERY_OPERATOR}"
        return (
            f"{left_table} LEFT JOIN {right_table} "
            f"ON {on_clause} AND {pit_condition} '{asof_date}'"
        )

    @staticmethod
    def wrap_pit_cte(
        query: str,
        cte_name: str = "pit_data",
        asof_date: str | None = None,
    ) -> str:
        """
        将查询包装为 PIT CTE.

        CTE (Common Table Expression) 包装可以简化 PIT 查询，
        特别是对于复杂的子查询。

        Args:
        ----
            query: 原始 SQL 查询
            cte_name: CTE 名称
            asof_date: 可选的 ASOF 日期（如果需要额外过滤）

        Returns:
        -------
            包装了 CTE 的 SQL 查询

        Examples:
        --------
            >>> query = "SELECT instrument_id, close FROM stock_daily"
            >>> PitHelper.wrap_pit_cte(query, "pit_data", "2024-01-15")
            "WITH pit_data AS (SELECT instrument_id, close FROM stock_daily) "
            "SELECT * FROM pit_data WHERE trade_date <= '2024-01-15'"

        """
        # 验证 CTE 名称和日期格式，防止 SQL 注入
        PitHelper._validate_sql_identifier(cte_name, "cte_name")
        if asof_date:
            PitHelper._validate_date_string(asof_date)

        query = query.strip()

        # 构建 CTE
        cte = f"WITH {cte_name} AS ({query}) SELECT * FROM {cte_name}"  # noqa: S608 - cte_name 已通过验证

        # 如果提供了 asof_date，添加 WHERE 子句
        if asof_date:
            # 假设 CTE 结果中有 trade_date 列
            # 实际使用时需要根据具体情况调整
            cte += f" WHERE trade_date {PIT_QUERY_OPERATOR} '{asof_date}'"

        return cte

    @staticmethod
    def get_safe_trade_date(
        base_column: str = "trade_date",
        knowledge_date: str = "$asof",
    ) -> str:
        """
        生成安全的 trade_date 过滤条件.

        这是 PIT 查询中最常用的模式：确保只使用
        knowledge_date 之前的数据。

        Args:
        ----
            base_column: 基础日期列名
            knowledge_date: 知识日期（默认使用 $asof 占位符）

        Returns:
        -------
            SQL 过滤条件字符串

        Examples:
        --------
            >>> PitHelper.get_safe_trade_date()
            "trade_date <= $asof"

            >>> PitHelper.get_safe_trade_date(knowledge_date="2024-01-15")
            "trade_date <= '2024-01-15'"

        """
        # 验证列名和日期格式，防止 SQL 注入
        PitHelper._validate_sql_identifier(base_column, "base_column")
        if not knowledge_date.startswith("$"):
            PitHelper._validate_date_string(knowledge_date)

        if knowledge_date.startswith("$"):
            # 占位符，不加引号
            return f"{base_column} {PIT_QUERY_OPERATOR} {knowledge_date}"
        # 具体日期，加引号
        return f"{base_column} {PIT_QUERY_OPERATOR} '{knowledge_date}'"


__all__ = [
    "PitHelper",
]
