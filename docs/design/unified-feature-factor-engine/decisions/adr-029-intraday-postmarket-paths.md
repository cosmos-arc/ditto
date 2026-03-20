# ADR-029: 盘中实时路径与盘后批量路径

**状态**: 已决策（2026-03-10）

---

## 背景

因子计算有两条主要路径：
1. **盘中实时路径**：盘中持续计算热点因子，支持交易决策
2. **盘后批量路径**：盘后全量计算，支持研究回测和冷启动

需要明确：
1. 哪些因子走实时路径，哪些走批量路径
2. 两条路径如何协同（B 类因子的盘前冷算 + 盘中热更新）
3. 数据如何回补（冷层到热层的数据同步）

---

## 因子分级模型（FactorServeMode）

### 四类因子

| 类别 | 原名 | 特点 | 存储 | 例子 |
|------|------|------|------|------|
| **SERIES** | A 类 | 盘中高频反复用 | QuestDB 热序列 + Kvrocks 最新值 | 5m/20m 收益、20m 波动率、VWAP 偏离、盘口不平衡 |
| **STATE** | B 类 | 需要长历史背景 | 盘前 Parquet 算初值，盘中 QuestDB 增量/Kvrocks 快照 | 252d 波动率、120d/250d 趋势、长周期行业 regime |
| **DERIVE** | C 类 | 不预存 | 从 QuestDB 热基础数据小窗现算 | 临时 37m 偏离度、策略专用组合特征、临时诊断指标 |
| **OFFLINE** | D 类 | 只在研究/训练用 | Parquet/Polars | 长期研究因子、训练标签、实验性特征 |

### FactorServeMode 定义

```python
# packages/core/src/ditto_core/specs.py

from enum import Enum

class FactorServeMode(str, Enum):
    """因子服务模式"""

    SERIES = "SERIES"    # A 类：实时热因子
    STATE = "STATE"      # B 类：盘前冷算 + 盘中热更新
    DERIVE = "DERIVE"    # C 类：盘中按需现算
    OFFLINE = "OFFLINE"  # D 类：纯离线因子

    @property
    def is_online(self) -> bool:
        """是否需要在线计算"""
        return self in (self.SERIES, self.STATE, self.DERIVE)

    @property
    def needs_hot_storage(self) -> bool:
        """是否需要热层存储"""
        return self in (self.SERIES, self.STATE)
```

### FactorSpec 扩展

```python
class FactorSpec(BaseSpec):
    # ... 现有字段 ...

    serve_mode: FactorServeMode = FactorServeMode.OFFLINE

    # STATE 模式特有配置
    state_snapshot_enabled: bool = False  # 是否启用状态快照
    state_snapshot_strategy: Literal["hash", "blob"] = "hash"
```

---

## 数据流总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据流总览                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  【盘后批量路径】                                                 │
│                                                                  │
│  Tushare/数据源 → Parquet（唯一真相层）                           │
│                        │                                         │
│                        ▼                                         │
│                  Polars 因子计算                                  │
│                        │                                         │
│                        ▼                                         │
│           ┌───────────┴───────────┐                              │
│           ▼                       ▼                              │
│     QuestDB（热层回补）      Kvrocks（状态初始化）                 │
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  【盘中实时路径】                                                 │
│                                                                  │
│  行情源 → Kvrocks Streams（队列）                                 │
│                │                                                 │
│                ▼                                                 │
│          消费者处理                                               │
│                │                                                 │
│                ▼                                                 │
│           QuestDB（bar 表写入）                                   │
│                │                                                 │
│                ▼                                                 │
│          因子计算（热点因子）                                      │
│                │                                                 │
│                ▼                                                 │
│           Kvrocks（最新因子值）                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 盘后批量路径

### 执行流程

```
T1 摄取完成
    │
    ├── 全量因子计算（OFFLINE 因子）
    │       │
    │       └── Parquet 写入
    │
    └── 热层回补（SERIES/STATE 因子）
            │
            ├── QuestDB 回补热序列
            │
            └── Kvrocks 状态初始化
```

### Phase 1 实现

```python
@flow(name="postmarket_batch_flow")
async def postmarket_batch_flow(trade_date: date) -> None:
    """盘后批量计算流程"""

    # 1. 全量因子计算
    for spec in get_all_factor_specs():
        if spec.serve_mode == FactorServeMode.OFFLINE:
            await compute_and_write_to_parquet(spec, trade_date)

    # 2. 热层回补
    for spec in get_online_factor_specs():
        await backfill_to_questdb(spec, trade_date)
        await initialize_kvrocks_state(spec, trade_date)
```

---

## 盘中实时路径

### SERIES 因子流程

```
QuestDB bar_1m_hot (最近 20m bar)
        │
        ▼
   Polars 小窗计算
   (ts_mean, ts_std, ts_rank...)
        │
        ├──────────────────────┐
        ▼                      ▼
QuestDB f_1m_hot        Kvrocks state:feature:{factor}:{sid}
(完整热序列)            (最新值 + asof_ts + trade_date)
```

```python
async def compute_series_factor(spec: FactorSpec, bar_data: pl.DataFrame) -> None:
    """SERIES 因子计算"""

    # 1. 从 QuestDB 读取热数据
    bar_data = await questdb_reader.read_recent_bars(
        instrument_ids=universe,
        lookback=spec.lookback,
    )

    # 2. Polars 小窗计算
    result = factor_engine.compute(spec, bar_data)

    # 3. 双写
    await questdb_writer.write_factor_series(result)  # QuestDB 热序列
    await kvrocks_writer.write_factor_state(result)   # Kvrocks 最新值
```

### STATE 因子流程

```
Kvrocks state:feature:{factor}:{sid} (最新因子值)
        │
        ├──────────────────────┐
        ▼                      ▼
QuestDB bar_1m_hot       策略逻辑判断
(实时行情补充)            (信号条件检查)
        │                      │
        └──────────────────────┘
                    │
                    ▼
        Kvrocks state:signal:{strategy}:{sid}
        (signal_ts, action, strength, status)
```

```python
async def compute_state_factor(spec: FactorSpec) -> None:
    """STATE 因子计算"""

    # 1. 盘前：从 Parquet 计算初始快照
    if is_pre_market():
        initial_snapshot = await compute_from_parquet(spec)
        await kvrocks_writer.write_state_snapshot(
            spec.factor_id,
            snapshot=initial_snapshot,
            strategy=spec.state_snapshot_strategy,
        )

    # 2. 盘中：增量更新
    async for bar in bar_stream:
        # 读取当前状态
        current_state = await kvrocks_reader.read_state(spec.factor_id)

        # 增量更新
        updated_state = update_state(current_state, bar)

        # 写回
        await kvrocks_writer.write_state_snapshot(
            spec.factor_id,
            snapshot=updated_state,
            strategy=spec.state_snapshot_strategy,
        )
```

### DERIVE 因子流程

```python
async def compute_derive_factor(spec: FactorSpec, request: FactorRequest) -> pl.DataFrame:
    """DERIVE 因子计算（按需现算）"""

    # 1. 从 QuestDB 读取所需数据
    bar_data = await questdb_reader.read_recent_bars(
        instrument_ids=request.instrument_ids,
        lookback=spec.lookback,
    )

    # 2. 现算
    result = factor_engine.compute(spec, bar_data)

    # 3. 直接返回，不存储
    return result
```

---

## 回补机制

### 触发方式

| 触发方式 | 说明 | 实现时机 |
|---------|------|---------|
| **定时回补** | 每日盘后→盘前自动 | Phase 1 |
| **触发式回补** | CLI/API 主动触发 | Phase 1 |
| **自动检测回补** | 基于数据质量监控 | Phase 2（可选） |

### 定时回补流程

```python
@flow(name="daily_backfill_flow")
async def daily_backfill_flow() -> None:
    """每日盘前回补"""

    # 1. 回补最近 N 天数据
    lookback_days = 5
    end_date = get_previous_trade_date()
    start_date = end_date - timedelta(days=lookback_days)

    # 2. 回补 QuestDB
    await backfill_questdb_bars(start_date, end_date)

    # 3. 回补因子
    for spec in get_online_factor_specs():
        await backfill_questdb_factors(spec, start_date, end_date)
        await reinitialize_kvrocks_state(spec, end_date)
```

### 触发式回补（CLI）

```bash
# 手动触发回补
ditto factor backfill \
    --factor-id alpha_001 \
    --start 2026-03-01 \
    --end 2026-03-10 \
    --target questdb,kvrocks
```

### 回补范围判断

```python
def determine_backfill_range(
    spec: FactorSpec,
    request_start: date,
    request_end: date,
) -> tuple[date, date]:
    """确定回补范围"""

    # 1. 查询当前水位
    current_watermark = await catalog.get_watermark(spec.factor_id)

    if current_watermark is None:
        # 无数据，全量回补
        return request_start, request_end

    if request_start > current_watermark:
        # 已有数据覆盖，增量回补
        return current_watermark + timedelta(days=1), request_end

    if request_end <= current_watermark:
        # 回补历史，需要重算
        return request_start, request_end

    # 跨越水位，分段处理
    return request_start, request_end
```

---

## 在线查询路径

### 查询路由规则

| 查询类型 | SERIES | STATE | DERIVE | OFFLINE |
|---------|--------|-------|--------|---------|
| 最新值 | Kvrocks | Kvrocks | 现算 | ❌ |
| 最近 N 分钟序列 | QuestDB | ❌ | 现算 | ❌ |
| 历史日期 | QuestDB（TTL 内） | QuestDB（TTL 内） | ❌ | Parquet |
| 回测/研究 | Parquet | Parquet | ❌ | Parquet |

### 查询接口

```python
class FactorQueryService:
    async def get_latest_value(
        self,
        factor_id: str,
        instrument_ids: list[str],
    ) -> dict[str, float]:
        """获取最新因子值"""
        spec = await catalog.get_factor_spec(factor_id)

        if spec.serve_mode == FactorServeMode.SERIES:
            return await kvrocks_reader.get_latest_values(factor_id, instrument_ids)

        if spec.serve_mode == FactorServeMode.STATE:
            return await kvrocks_reader.get_state_snapshot(factor_id, instrument_ids)

        if spec.serve_mode == FactorServeMode.DERIVE:
            return await compute_derive_factor(spec, instrument_ids)

        raise ValueError(f"OFFLINE factor {factor_id} has no online data")

    async def get_time_series(
        self,
        factor_id: str,
        instrument_id: str,
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        """获取时间序列"""
        spec = await catalog.get_factor_spec(factor_id)

        if spec.serve_mode == FactorServeMode.SERIES:
            # QuestDB 热序列
            return await questdb_reader.read_factor_series(
                factor_id, instrument_id, start, end
            )

        if spec.serve_mode == FactorServeMode.OFFLINE:
            # Parquet 冷序列
            return await parquet_reader.read_factor_series(
                factor_id, instrument_id, start, end
            )

        raise ValueError(f"Factor {factor_id} does not support time series query")
```

---

## Phase 规划

### Phase 1：批量路径优先

```
Phase 1.1: 核心框架
    ├── FactorServeMode 定义
    ├── FactorSpec 扩展
    └── Catalog 字段更新

Phase 1.2: 盘后批量路径
    ├── OFFLINE 因子计算
    ├── 热层回补（QuestDB + Kvrocks）
    └── CLI backfill 命令
```

### Phase 2：实时路径完善

```
Phase 2.1: SERIES 因子
    ├── 实时计算引擎
    ├── QuestDB ILP 写入
    └── Kvrocks 双写

Phase 2.2: STATE 因子
    ├── 状态快照机制
    ├── 增量更新逻辑
    └── 盘前初始化

Phase 2.3: DERIVE 因子
    ├── 按需计算 API
    └── 查询路由
```

---

## 相关 ADR

- [ADR-027: 表达式 Pushdown 策略](storage/adr-027-pushdown-strategy.md) - QuestDB 下推
- [ADR-028: QuestDB 热表与物化视图 DDL](storage/adr-028-questdb-hot-tables.md) - 热层存储
- [ADR-030: Online Data Access Boundary](adr-030-online-data-access-boundary.md) - 在线查询边界
- [ADR-031: State Snapshot ABI](storage/adr-031-state-snapshot-abi.md) - STATE 因子快照格式
- [ADR-010: Catalog 完整表结构与存储架构](adr-010-catalog-schema.md) - serve_mode 字段
