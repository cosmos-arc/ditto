# 物化术语分析与命名建议

> 本文档记录关于"物化"(Materialization) 术语的讨论结论，用于后续命名决策参考。

## 1. 核心概念区分

### 1.1 摄取 vs 物化

| 维度 | 摄取 (Ingestion) | 物化 (Materialization) |
|------|------------------|------------------------|
| **数据来源** | 外部系统（Tushare、Wind 等） | 内部已有数据 |
| **操作本质** | 搬运 | 计算 |
| **数据形态** | 原始数据基本不变 | 派生/聚合/变换 |
| **可复现性** | 依赖外部系统 | 完全由内部表达式定义 |
| **失效后处理** | 重新调用外部 API | 重新执行表达式 |

### 1.2 Ditto 架构中的定位

```
T0: 元数据同步          → 摄取（从 Tushare API）
T1: 日线/基本面/资金    → 摄取（从 Tushare API）
T2: 特征计算            → 物化（从 T1 数据计算）
T3: 因子计算            → 物化（从 T1+T2 数据计算）
T4: 发布                → 物化结果的版本管理
```

**分界线：数据是否来自外部 API**

---

## 2. 术语来源与业界命名

### 2.1 "物化"术语来源

**Materialized View（物化视图）** 起源于 **数据库领域**，不是量化特有术语：

| 年份 | 里程碑 |
|------|--------|
| 1980s | Oracle 首次实现物化视图（当时叫 Snapshot） |
| 1995 | PostgreSQL 引入 Materialized View |
| 2000s | 数据仓库（Teradata、Greenplum）广泛使用 |
| 2010s | 大数据时代（Hive、Spark、Presto）继承概念 |

### 2.2 不同领域的命名差异

| 领域 | 常用术语 | 典型系统 |
|------|---------|---------|
| **数据库** | Materialized View | Oracle, PostgreSQL, MySQL |
| **数据仓库** | ETL / 数据管道 / 聚合表 | Snowflake, BigQuery, Redshift |
| **大数据** | 离线计算 / 批处理 | Spark, Hive, Flink |
| **特征存储** | Feature Engineering / Transformation | Feast, Hopsworks, Tecton |
| **量化** | Alpha Generation / Signal Construction | WorldQuant, Two Sigma 内部系统 |

### 2.3 量化领域的实际命名

量化行业**没有统一的术语标准**：

| 命名 | 使用场景 | 来源 |
|------|---------|------|
| **Signal Construction** | 因子计算流程 | WorldQuant |
| **Alpha Generation** | 生成 alpha 信号 | Two Sigma |
| **Feature Pipeline** | 特征工程管道 | 通用 |
| **Factor Computation** | 因子计算 | 学术界 |
| **Data Transformation** | 数据变换 | 通用 |

---

## 3. 业界 Feature Store 命名对比

| 系统 | 命名 | API 示例 |
|------|------|---------|
| **Feast** | Feature View | `feast.apply(feature_view)` |
| **Tecton** | Feature Transformation | `@batch_feature_view` |
| **Hopsworks** | Feature Pipeline | `fs.create_feature_group()` |
| **Databricks** | Materialized View | `CREATE MATERIALIZED VIEW` |
| **Ditto（当前）** | Materialize | `service.materialize(request)` |

---

## 4. 术语表

### 4.1 Ditto 内部术语

| 术语 | 定义 | 使用场景 |
|------|------|---------|
| **Materialize / 物化** | 执行表达式计算并持久化结果到 Parquet | T2 特征、T3 因子计算 |
| **Ingest / 摄取** | 从外部数据源获取原始数据并存储 | T0 元数据、T1 行情/基本面 |
| **Spec** | 实体定义（表达式、元数据） | Feature/Factor 的声明式定义 |
| **RunConfig** | 运行配置（模式、范围、参数） | 控制物化执行边界 |
| **Watermark** | 已物化数据的最新时间点 | 增量计算的起点参考 |
| **Invalidation Set** | 需要重新计算的分区集合 | 上游变更时标记失效 |
| **Artifact** | 版本化工件（spec_hash 路径） | 确保可复现性 |

### 4.2 业界术语对照

| Ditto 术语 | 数据库术语 | Feature Store 术语 | 量化术语 |
|------------|-----------|-------------------|---------|
| Materialize | REFRESH MATERIALIZED VIEW | Transform / Compute | Generate Signal |
| Spec | View Definition | Feature Definition | Alpha Expression |
| Watermark | Checkpoint | Feature Timestamp | - |
| Invalidation | Stale Flag | - | - |
| Artifact | Materialized Data | Feature Value | Signal Value |

---

## 5. 命名建议

### 5.1 选项对比

| 命名选项 | 优点 | 缺点 | 适用团队背景 |
|---------|------|------|-------------|
| **Materialize（当前）** | 强调持久化，与数据库术语一致 | 对量化用户可能陌生 | 数据工程 |
| **Compute / Calculate** | 直观易懂 | 不强调持久化 | 通用 |
| **Generate / Build** | 量化领域常用 | 偏向一次性动作 | 量化研究 |
| **Transform** | 数据工程通用 | 不强调结果存储 | 数据工程 |

### 5.2 具体建议

**方案 A：保持当前命名（推荐）**

如果团队有数据工程背景，`Materialize` 是合理的选择：
- 强调结果的持久化特性
- 与数据库/数据仓库术语一致
- 区别于临时的计算（Compute）

```python
# API 保持不变
service.materialize(request)
daily_materialization_flow(trade_date)
```

**方案 B：调整为量化友好命名**

如果团队主要来自量化背景，可以考虑：
- 内部实现保持 `materialize` 命名
- 对外 API 使用更直观的名称

```python
# 对外 API
service.generate_factor(request)  # 或 compute_feature
daily_factor_flow(trade_date)     # 或 daily_signal_flow

# 内部实现保持不变
materialize_partition(...)
```

**方案 C：混合命名**

- 文档中保留"物化"概念解释
- 代码中根据调用方场景使用不同命名

```python
# Feature/Factor Service 层
factor_service.generate(...)      # 量化用户
feature_service.compute(...)      # 数据用户

# 底层 Engine 层
materialize_engine.run(...)       # 保持原样
```

---

## 6. 决策要点

在决定是否修改命名时，考虑以下问题：

1. **团队背景**：主要成员来自数据工程还是量化研究？
2. **用户群体**：系统的主要使用者更熟悉哪种术语？
3. **文档一致性**：现有文档中"物化"概念是否已经广泛使用？
4. **API 稳定性**：修改命名的迁移成本有多大？

---

## 7. 参考资料

- [Databricks Materialized View](https://docs.databricks.com/aws/en/optimizations/incremental-refresh)
- [Feast Feature Store](https://docs.feast.dev/)
- [WorldQuant Alpha101](https://arxiv.org/abs/1601.00991)
- [PostgreSQL Materialized Views](https://www.postgresql.org/docs/current/rules-materializedviews.html)

---

## 8. 变更记录

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-03-05 | 初始文档创建 | Claude |
