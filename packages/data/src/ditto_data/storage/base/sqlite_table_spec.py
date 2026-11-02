"""SqliteTableSpec — frozen dataclass for parameterizing SQLite table structure."""

from __future__ import annotations

from dataclasses import dataclass

# PIT 列形态阈值：>=3 含知识轴（knowledge/from/to），>=2 仅版本区间
_PIT_KNOWLEDGE_FORM = 3
_PIT_INTERVAL_FORM = 2


@dataclass(frozen=True)
class SqliteTableSpec:
    """SQLite 表查询规格，参数化表结构差异。"""

    table: str
    columns: tuple[str, ...]
    id_column: str
    date_column: str | None = None
    nullable_columns: frozenset[str] = frozenset()
    pit_columns: tuple[str, ...] = ("knowledge_date", "effective_from", "effective_to")
    order_by_column: str | None = None
    # KEEP_LAST upsert 的冲突目标（表主键）；None 表示该表只支持默认的
    # 冲突忽略（KEEP_FIRST）语义，KEEP_LAST 写入响亮失败。
    conflict_columns: tuple[str, ...] | None = None
    # 事实业务键（PIT 修订收敛的分区分键）；None 表示 (id_column, date_column)。
    # 同键多行视为同一事实的修订版本，键外列（如 corporate_actions 的
    # action_type）参与键时，同日不同类型行动不会被误收敛（#628）。
    fact_key_columns: tuple[str, ...] | None = None

    @property
    def all_columns(self) -> tuple[str, ...]:
        """完整列集：id + date + pit + business columns。"""
        cols: tuple[str, ...] = (self.id_column,)
        if self.date_column:
            cols = (*cols, self.date_column)
        return (*cols, *self.pit_columns, *self.columns)

    @property
    def knowledge_column(self) -> str | None:
        """知识轴列名（三列 PIT 形态），两列形态无知识轴。"""
        if len(self.pit_columns) >= _PIT_KNOWLEDGE_FORM:
            return self.pit_columns[-_PIT_KNOWLEDGE_FORM]
        return None

    @property
    def effective_from_column(self) -> str | None:
        """版本生效列名。"""
        if len(self.pit_columns) >= _PIT_INTERVAL_FORM:
            return self.pit_columns[-_PIT_INTERVAL_FORM]
        return None

    @property
    def effective_to_column(self) -> str | None:
        """版本关闭列名。"""
        if self.pit_columns:
            return self.pit_columns[-1]
        return None
