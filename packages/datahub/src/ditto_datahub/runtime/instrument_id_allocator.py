"""Instrument ID 分配器，用于管理唯一的证券标识符。"""

from ditto_foundation import SQLitePool, logger, span

from ..models import InstrumentIdRange


class InstrumentIdAllocator:
    """Instrument ID 分配器，用于管理唯一的证券标识符。"""

    def __init__(self, sqlite_pool: SQLitePool) -> None:
        """Initialize Instrument ID allocator."""
        self._pool = sqlite_pool

    def allocate(self, asset_class: str) -> int:
        """Allocate new instrument_id (atomic operation)."""
        with span("instrument_id_allocator.allocate", asset_class=asset_class):
            return self._allocate_impl(asset_class)

    def _allocate_impl(self, asset_class: str) -> int:
        """Internal implementation of instrument_id allocation."""
        # 获取资产类别的 ID 范围
        min_id, max_id = InstrumentIdRange.get_range(asset_class)

        logger.info(
            "instrument_id_allocate_start",
            event="instrument_id_allocate",
            asset_class=asset_class,
        )

        try:
            # 开始事务
            self._pool.execute("BEGIN IMMEDIATE")

            # 查询当前最大值
            row = self._pool.execute(
                "SELECT current_max FROM instrument_id_sequence WHERE asset_class = ?",
                [asset_class],
            ).fetchone()

            if not row:
                # 首次分配, 插入新记录
                new_id = min_id
                self._pool.execute(
                    "INSERT INTO instrument_id_sequence "  # noqa: S608
                    + "(asset_class, current_max) VALUES (?, ?)",
                    [asset_class, new_id],
                )
            else:
                # 计算下一个 ID
                new_id = row["current_max"] + 1

                # 检查是否超出范围
                if new_id > max_id:
                    self._pool.execute("ROLLBACK")
                    logger.error(
                        "instrument_id_allocate_exhausted",
                        event="instrument_id_allocate",
                        asset_class=asset_class,
                        max_id=max_id,
                    )
                    raise OverflowError(f"Instrument ID exhausted for {asset_class}")

                # 更新当前最大值
                self._pool.execute(
                    "UPDATE instrument_id_sequence "
                    + "SET current_max = ? WHERE asset_class = ?",
                    [new_id, asset_class],
                )

            # 提交事务
            self._pool.commit()

            logger.info(
                "instrument_id_allocate_complete",
                event="instrument_id_allocate",
                asset_class=asset_class,
                instrument_id=new_id,
            )
            return new_id

        except Exception as e:
            # 发生任何错误都要回滚
            self._pool.rollback()
            logger.error(
                "instrument_id_allocate_failed",
                event="instrument_id_allocate",
                asset_class=asset_class,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise
