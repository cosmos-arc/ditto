"""SID allocator for managing unique security identifiers."""

from typing import TYPE_CHECKING

from ..types import SidRange

if TYPE_CHECKING:
    from .sqlite_pool import SQLitePool


class SidAllocator:
    """SID allocator for managing unique security identifiers."""

    def __init__(self, sqlite_pool: "SQLitePool") -> None:
        """Initialize SID allocator."""
        self._pool = sqlite_pool

    def allocate(self, asset_class: str) -> int:
        """Allocate new SID (atomic operation)."""
        # 获取资产类别的SID范围
        min_sid, max_sid = SidRange.get_range(asset_class)

        try:
            # 开始事务
            self._pool.execute("BEGIN IMMEDIATE")

            # 查询当前最大值
            row = self._pool.execute(
                "SELECT current_max FROM sid_sequence WHERE asset_class = ?",
                [asset_class],
            ).fetchone()

            if not row:
                # 首次分配, 插入新记录
                new_sid = min_sid
                self._pool.execute(
                    "INSERT INTO sid_sequence (asset_class, current_max) VALUES (?, ?)",
                    [asset_class, new_sid],
                )
            else:
                # 计算下一个SID
                new_sid = row["current_max"] + 1

                # 检查是否超出范围
                if new_sid > max_sid:
                    self._pool.execute("ROLLBACK")
                    raise OverflowError(f"SID exhausted for {asset_class}")

                # 更新当前最大值
                self._pool.execute(
                    "UPDATE sid_sequence SET current_max = ? WHERE asset_class = ?",
                    [new_sid, asset_class],
                )

            # 提交事务
            self._pool.commit()
            return new_sid

        except Exception:
            # 发生任何错误都要回滚
            self._pool.rollback()
            raise
