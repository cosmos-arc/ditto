"""SID 分配器，用于管理唯一的证券标识符。"""

from ditto_foundation import SQLitePool, logger, span

from ..models import AssetSidRange


class SidAllocator:
    """SID 分配器，用于管理唯一的证券标识符。"""

    def __init__(self, sqlite_pool: SQLitePool) -> None:
        """Initialize SID allocator."""
        self._pool = sqlite_pool

    def allocate(self, asset_class: str) -> int:
        """Allocate new SID (atomic operation)."""
        with span("sid_allocator.allocate", asset_class=asset_class):
            return self._allocate_impl(asset_class)

    def _allocate_impl(self, asset_class: str) -> int:
        """Internal implementation of SID allocation."""
        # 获取资产类别的SID范围
        min_sid, max_sid = AssetSidRange.get_range(asset_class)

        logger.info(
            "sid_allocate_start",
            event="sid_allocate",
            asset_class=asset_class,
        )

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
                    logger.error(
                        "sid_allocate_exhausted",
                        event="sid_allocate",
                        asset_class=asset_class,
                        max_sid=max_sid,
                    )
                    raise OverflowError(f"SID exhausted for {asset_class}")

                # 更新当前最大值
                self._pool.execute(
                    "UPDATE sid_sequence SET current_max = ? WHERE asset_class = ?",
                    [new_sid, asset_class],
                )

            # 提交事务
            self._pool.commit()

            logger.info(
                "sid_allocate_complete",
                event="sid_allocate",
                asset_class=asset_class,
                sid=new_sid,
            )
            return new_sid

        except Exception as e:
            # 发生任何错误都要回滚
            self._pool.rollback()
            logger.error(
                "sid_allocate_failed",
                event="sid_allocate",
                asset_class=asset_class,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise
