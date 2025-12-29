"""
PIT SQL 辅助函数.

提供半自动的 PIT (Point-in-Time) SQL 生成辅助函数。
"""

from __future__ import annotations

from typing import Any


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
        query = query.strip()

        # 检查是否已有 WHERE 子句
        if " where " in query.lower():
            # 已有 WHERE，添加 AND 条件
            return f"{query} AND {date_column} <= '{knowledge_date}'"
        else:
            # 没有 WHERE，添加 WHERE 子句
            return f"{query} WHERE {date_column} <= '{knowledge_date}'"

    @staticmethod
    def add_pit_join(
        left_table: str,
        right_table: str,
        join_keys: list[str],
        asof_date: str,
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

        Returns:
        -------
            PIT ASOF JOIN SQL 片段

        Examples:
        --------
            >>> PitHelper.add_pit_join(
            ...     "stock_daily s",
            ...     "adj_factor a",
            ...     ["s.sid = a.sid"],
            ...     "2024-01-15"
            ... )
            "stock_daily s LEFT JOIN adj_factor a ON s.sid = a.sid "
            "AND a.trade_date <= '2024-01-15'"

        """
        # 构建 ON 子句
        on_clause = " AND ".join(join_keys)

        # 提取右表别名
        # right_table 格式: "table_name alias" 或 "table_name alias"
        parts = right_table.strip().split()
        right_alias = parts[-1] if len(parts) >= 2 else right_table

        # 添加 PIT 条件 (假设右表有 trade_date 列)
        # 注意：这里使用 trade_date 作为示例，实际应根据表结构调整
        return (
            f"{left_table} LEFT JOIN {right_table} "
            f"ON {on_clause} AND {right_alias}.trade_date <= '{asof_date}'"
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
            >>> query = "SELECT sid, close FROM stock_daily"
            >>> PitHelper.wrap_pit_cte(query, "pit_data", "2024-01-15")
            "WITH pit_data AS (SELECT sid, close FROM stock_daily) "
            "SELECT * FROM pit_data WHERE trade_date <= '2024-01-15'"

        """
        query = query.strip()

        # 构建 CTE
        cte = f"WITH {cte_name} AS ({query}) SELECT * FROM {cte_name}"

        # 如果提供了 asof_date，添加 WHERE 子句
        if asof_date:
            # 假设 CTE 结果中有 trade_date 列
            # 实际使用时需要根据具体情况调整
            cte += f" WHERE trade_date <= '{asof_date}'"

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
        if knowledge_date.startswith("$"):
            # 占位符，不加引号
            return f"{base_column} <= {knowledge_date}"
        else:
            # 具体日期，加引号
            return f"{base_column} <= '{knowledge_date}'"
