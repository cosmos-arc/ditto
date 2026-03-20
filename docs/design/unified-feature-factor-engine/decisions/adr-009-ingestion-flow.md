# ADR-009: 特征/因子摄取完整流程

**状态**: 已决策（2026-03-04）

---

## 处理模式

采用 **"批量 + 增量"** 双模式架构，预留流式扩展

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Ditto 处理模式                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     批量模式（Full Mode）                             │    │
│  │                                                                      │    │
│  │  适用场景：                                                           │    │
│  │  - 新因子首次上线（cold start）                                       │    │
│  │  - 历史数据回算（backfill）                                           │    │
│  │  - Spec 表达式变更（spec_hash 变化）                                  │    │
│  │                                                                      │    │
│  │  特点：                                                               │    │
│  │  - 从指定开始日期全量计算，忽略 watermark                              │    │
│  │  - 结果完整但耗时较长                                                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     增量模式（Incremental Mode）                      │    │
│  │                                                                      │    │
│  │  适用场景：                                                           │    │
│  │  - 日常 T+1 更新（daily run）                                         │    │
│  │  - 数据修正后局部回补（基于 invalidation）                             │    │
│  │  - 快速补数据（patch）                                                │    │
│  │                                                                      │    │
│  │  特点：                                                               │    │
│  │  - 基于 watermark 增量，lookback 预热                                 │    │
│  │  - 效率高，日常默认使用                                                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     流式模式（Streaming）- Phase 2+ 预留              │    │
│  │                                                                      │    │
│  │  适用场景：                                                           │    │
│  │  - 分钟级因子（intraday）                                             │    │
│  │  - 实时信号（real-time signal）                                       │    │
│  │  - Tick 级计算（high-frequency）                                      │    │
│  │                                                                      │    │
│  │  特点：                                                               │    │
│  │  - 事件驱动，低延迟                                                   │    │
│  │  - 架构已预留扩展点                                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 模式选择决策表

| 场景 | 模式 | 命令示例 |
|------|------|---------|
| 新因子首次上线 | 批量 | `ditto materialize --id alpha_new --mode full --start 2020-01-01` |
| 日常 T+1 更新 | 增量 | `ditto materialize --id alpha_001 --mode incremental` |
| 历史回算 | 批量 | `ditto materialize --id alpha_001 --mode full --start 2018-01-01` |
| 数据修正后回补 | 增量 | 自动触发（基于 invalidation） |
| Spec 变更 | 批量 | `ditto materialize --id alpha_001 --mode full --force` |

---

## 端到端流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           T1 原始数据摄入完成                                  │
│                    market.daily, fundamental.*, capital.*                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        T2 特征物化（Feature Materialization）                  │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │ 1. 解析 Spec → 编译 Expression → 分析依赖/lookback/requires_full_day   │   │
│  │ 2. 加载输入数据（source domains + 依赖 features）                       │   │
│  │ 3. 执行 Polars 计算                                                    │   │
│  │ 4. 写入 Parquet（year 分区）                                           │   │
│  │ 5. 更新 Catalog（checkpoint + state）                                  │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│  输出: features/technical/indicators_narrow/{year}.parquet                   │
│        features/fundamental/{feature_id}/{year}.parquet                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        T3 因子物化（Factor Materialization）                   │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │ 1. 解析 Spec → 编译 Expression → 分析依赖                              │   │
│  │ 2. 加载输入数据（source domains + 依赖 features + 依赖 factors）        │   │
│  │ 3. 执行 Polars 计算 → raw_value                                        │   │
│  │ 4. 应用标准化管线（Rank → ZScore）→ exposure                            │   │
│  │ 5. PIT 规整（effective_from/effective_to）                             │   │
│  │ 6. 写入 Parquet（year 分区）                                           │   │
│  │ 7. 更新 Catalog                                                        │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│  输出: factors/factors_narrow/{year}.parquet                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        T4 发布（Publication）                                 │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │ 1. 校验数据质量（null_rate, 分布检查）                                  │   │
│  │ 2. 更新 latest 指针                                                    │   │
│  │ 3. 生成报告（coverage, stats）                                         │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 与现有摄取流程集成

```python
# 现有: daily_ingestion_flow
@flow(name="daily_ingestion")
def daily_ingestion_flow(trade_date: date):
    T0_meta_sync()
    T1_market_daily(trade_date)
    T1_fundamental(trade_date)
    # ...

# 新增: daily_materialization_flow
@flow(name="daily_materialization")
def daily_materialization_flow(trade_date: date, mode: Literal["full", "incremental"]):
    # Phase 1: 特征物化
    for feature_spec in FEATURE_SPECS:
        materialize_feature(feature_spec, trade_date, mode)

    # Phase 2: 因子物化（依赖特征）
    for factor_spec in FACTOR_SPECS:
        materialize_factor(factor_spec, trade_date, mode)

    # Phase 3: 发布
    publish_derived(trade_date)

# 组合: daily_pipeline_flow
@flow(name="daily_pipeline")
def daily_pipeline_flow(trade_date: date):
    # 1. 摄取原始数据
    daily_ingestion_flow(trade_date)

    # 2. 物化特征/因子
    daily_materialization_flow(trade_date, mode="incremental")
```

---

## 盘中与盘后路径分离

> 详见 [ADR-029: 盘中实时路径与盘后批量路径](adr-029-intraday-postmarket-paths.md)

上述流程主要描述**盘后批量路径**。盘中实时路径有独立的数据流：

### 盘后批量路径（本 ADR 主内容）

```
Tushare/数据源 → Parquet（唯一真相层）
                        │
                        ▼
                  Polars 因子计算
                        │
                        ▼
           QuestDB（热层回补） + Kvrocks（状态初始化）
```

### 盘中实时路径

```
行情源 → Kvrocks Streams（队列）
                │
                ▼
          消费者处理
                │
                ▼
           QuestDB（bar 表写入）
                │
                ▼
          因子计算（热点因子）
                │
                ▼
           Kvrocks（最新因子值）
```

### 路径选择依据

| 因子类型 | FactorServeMode | 盘后路径 | 盘中路径 |
|---------|-----------------|---------|---------|
| 实时热因子 | SERIES | ✅ 回补热层 | ✅ 实时计算 |
| 状态类因子 | STATE | ✅ 初始化状态 | ✅ 增量更新 |
| 按需计算因子 | DERIVE | ❌ | ✅ 现算 |
| 纯离线因子 | OFFLINE | ✅ 仅 Parquet | ❌ |
