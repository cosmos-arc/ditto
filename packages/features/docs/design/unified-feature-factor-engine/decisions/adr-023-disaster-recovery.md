> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# ADR-023: 灾备恢复策略

**状态**: ⏸️ 暂缓

**重启条件**: 确认上游数据源支持断点续传后重启。预估 Phase 5+。

**修订说明**: 明确"上游可重发"决策，细化盘中恢复和历史回补的区分。

---

## 背景

因子引擎依赖 QuestDB（热层）和 Kvrocks（状态层）两个存储组件。需要明确灾难恢复策略，确保在数据丢失或损坏时能够快速恢复服务。

---

## 核心原则

> **QuestDB 和 Kvrocks 均为可重建派生层，Parquet 是唯一真相层。**

这意味着：
- QuestDB/Kvrocks 数据丢失不会导致永久性数据损失
- 所有热层数据都可以从 Parquet 或上游数据源重建
- 恢复优先级：服务可用性 > 数据完整性 > 历史连续性

---

## 决策

| 决策项 | 决策 | 理由 |
|--------|------|------|
| **分钟级数据灾备** | **上游可重发** | 把复杂度推给数据源，本地存储保持简单 |
| **日线级数据灾备** | **从 Parquet 回补** | Parquet 是唯一真相层 |
| **Kvrocks 状态灾备** | **从 Parquet 重建** | 状态可从历史数据重新计算 |
| **Parquet 冷备** | **不记录实时流分钟数据** | 避免存储翻倍，实时数据有时效性 |

---

## 存储层级与恢复能力

| 存储层 | 数据类型 | 恢复方式 | RTO |
|--------|---------|---------|-----|
| **Parquet（真相层）** | 日线级行情、因子 | 云存储备份/多副本 | 永久 |
| **QuestDB（热层）** | 分钟级行情、热序列因子 | 上游重发 + Parquet 回补 | 分钟级 |
| **Kvrocks（状态层）** | 最新状态、快照 | 从 Parquet 重算 | 分钟级 |

---

## 恢复流程

### QuestDB 恢复流程

```
QuestDB 故障恢复流程：
    │
    ├─ 1. 判断故障范围
    │      ├─ 仅热数据丢失 → 从 Parquet 回补
    │      └─ 包含分钟数据 → 从数据源重放
    │
    ├─ 2. 从 Parquet 回补
    │      └─ Parquet bar_1d → QuestDB bar_1m_hot（如有必要）
    │
    ├─ 3. 从数据源重放（如需要）
    │      └─ 上游支持断点续传 → 重放分钟数据
    │
    └─ 4. 重建状态
           └─ Polars 重算因子 → Kvrocks 状态初始化
```

### Kvrocks 恢复流程

```
Kvrocks 故障恢复流程：
    │
    ├─ 1. 判断故障范围
    │      ├─ 部分状态丢失 → 按需重建
    │      └─ 全部状态丢失 → 批量初始化
    │
    └─ 2. 从 Parquet 重建
           ├─ 盘前：批量初始化 STATE 因子快照
           └─ 盘中：按需从 QuestDB 现算
```

---

## 上游可重发要求

### 数据源能力要求

| 数据源 | 断点续传 | 历史回放 | 要求 |
|--------|---------|---------|------|
| Tushare | ✅ 支持 | ✅ 支持 | 记录最后成功摄取时间戳 |
| 实时行情源 | 需确认 | ❌ 通常不支持 | 依赖 QuestDB TTL 内数据 |

### 检查点管理

```python
# Kvrocks 中存储检查点
# Key: ditto:checkpoint:{source}:{data_type}
# Value: {"last_ts": "2026-03-10T14:30:00", "offset": 12345}

async def save_checkpoint(source: str, data_type: str, last_ts: datetime, offset: int) -> None:
    """保存检查点"""
    key = f"ditto:checkpoint:{source}:{data_type}"
    await kvrocks.set(key, orjson.dumps({
        "last_ts": last_ts.isoformat(),
        "offset": offset,
    }))

async def get_checkpoint(source: str, data_type: str) -> dict | None:
    """获取检查点"""
    key = f"ditto:checkpoint:{source}:{data_type}"
    data = await kvrocks.get(key)
    return orjson.loads(data) if data else None
```

---

## 恢复脚本

### QuestDB 热层回补

```python
# scripts/restore_questdb.py

async def restore_questdb_hot_layer(
    start_date: date,
    end_date: date,
) -> None:
    """从 Parquet 回补 QuestDB 热层"""

    logger.info(f"Restoring QuestDB hot layer: {start_date} to {end_date}")

    # 1. 读取 Parquet 数据
    df = pl.read_parquet("data/market/cn/bar_1d/*.parquet").filter(
        pl.col("trade_date").is_between(start_date, end_date)
    )

    # 2. 写入 QuestDB
    writer = QuestDBWriter(host="localhost", port=9009)
    await writer.write_bar_1m(df_to_bars(df))

    logger.info(f"QuestDB hot layer restored: {len(df)} rows")

async def replay_minute_data_from_source(
    start: datetime,
    end: datetime,
) -> None:
    """从数据源重放分钟数据"""

    logger.info(f"Replaying minute data: {start} to {end}")

    # 获取检查点
    checkpoint = await get_checkpoint("tushare", "bar_1m")

    # 从检查点开始重放
    real_start = datetime.fromisoformat(checkpoint["last_ts"]) if checkpoint else start

    # 重放数据
    async for batch in tushare_client.stream_minute_bars(real_start, end):
        await questdb_writer.write_bar_1m(batch)

    logger.info(f"Minute data replay completed")
```

### Kvrocks 状态重建

```python
# scripts/restore_kvrocks_state.py

async def restore_kvrocks_state(
    factor_ids: list[str] | None = None,
) -> None:
    """从 Parquet 重建 Kvrocks 状态"""

    logger.info("Restoring Kvrocks state")

    # 获取所有 STATE 模式因子
    specs = await catalog.get_factor_specs(
        serve_mode=FactorServeMode.STATE,
        factor_ids=factor_ids,
    )

    for spec in specs:
        logger.info(f"Initializing state for {spec.id}")

        # 从 Parquet 计算快照
        historical_data = await parquet_reader.read_factor_series(
            spec.id,
            lookback=spec.lookback,
        )
        snapshot = compute_state_snapshot(spec, historical_data)

        # 写入 Kvrocks
        await kvrocks_writer.write_state_snapshot(
            spec.id,
            snapshot=snapshot,
            strategy=spec.state_snapshot_strategy,
        )

    logger.info(f"Kvrocks state restored: {len(specs)} factors")
```

---

## CLI 命令

```bash
# QuestDB 热层回补
ditto restore questdb --start 2026-03-01 --end 2026-03-10

# 从数据源重放分钟数据
ditto restore questdb --replay-minute --start "2026-03-10T09:30:00" --end "2026-03-10T15:00:00"

# Kvrocks 状态重建（全部）
ditto restore kvrocks

# Kvrocks 状态重建（指定因子）
ditto restore kvrocks --factors alpha_001,alpha_002
```

---

## 待办事项

- [x] 明确上游可重发决策
- [x] 区分盘中恢复和历史回补
- [ ] 实现检查点管理
- [ ] 实现恢复脚本
- [ ] 添加恢复自动化测试

---

## 相关 ADR

- [ADR-028: QuestDB 热表与物化视图 DDL](storage/adr-028-questdb-hot-tables.md) - 热层存储设计
- [ADR-029: 盘中实时路径与盘后批量路径](adr-029-intraday-postmarket-paths.md) - 回补机制
- [ADR-031: State Snapshot ABI](storage/adr-031-state-snapshot-abi.md) - 状态快照格式
