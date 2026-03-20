# 统一派生引擎 - 差距补齐清单

> **文档状态**: 可执行清单
> **创建日期**: 2026-03-12
> **用途**: 逐项追踪设计差距，支持逐步验收

---

## 清单使用说明

- ✅ 已完成
- 🚧 进行中
- ⏸️ 暂缓/待定
- ❌ 未开始
- 🔴 阻塞项
- 🟡 警告项
- 🟢 已完成

---

## 1. 核心模型层 (P0 - 阻塞实施)

### 1.1 DerivedSpec 完整定义

| 编号 | 待补充项 | 状态 | 说明 | 阻塞点 |
|------|---------|------|------|--------|
| M-001 | `DerivedSpec` 根模型完整字段清单 | ❌ | id, version, role, profile, expression... | Phase 0 实施 |
| M-002 | `EntitySpec` 实体语义定义 | ❌ | join_keys, join_policy | 多实体 join |
| M-003 | `TimeSpec` 时间语义定义 | ❌ | event_time, availability_time, calendar, timezone | 多市场支持 |
| M-004 | `FeatureProfile` 完整字段 | ❌ | serving_enabled, training_enabled, parity_policy... | Feature 治理 |
| M-005 | `FactorProfile` 完整字段 | ❌ | normalization_policy, neutralization_policy... | Factor 治理 |
| M-006 | `role` 枚举最终定义 | 🚧 | feature, factor, signal, label (保留) | 统一语义 |
| M-007 | `materialization_profile` 枚举定义 | ✅ | SERIES, STATE, DERIVE, OFFLINE | 已定义 |
| M-008 | `DerivedSpec.spec_hash` 算法 | ❌ | 包含哪些字段？版本如何影响？ | 缓存键 |
| M-009 | `DerivedSpec.operator_versions` 字段 | ❌ | 记录依赖算子版本，用于失效检测 | 可复现性 |
| M-010 | `grain` 粒度语义 | ❌ | ticker, daily, minute | 多粒度支持 |
| M-011 | `aggregation_policy` 聚合策略 | ❌ | last, sum, mean | 下采样支持 |

#### EntitySpec 详细待定义

```python
# 待定义：packages/core/src/ditto_core/specs.py

@dataclass
class EntitySpec(BaseModel):
    """实体语义"""

    # Join 键
    join_keys: list[str] = field(default_factory=lambda: ["instrument_id"])

    # 多实体 join 场景
    # 例：["instrument_id", "exchange"] 或 ["instrument_id", "sector"]
    secondary_keys: list[str] = field(default_factory=list)

    # Join 策略
    join_policy: Literal["inner", "left", "outer"] = "inner"

    # 实体过滤（universe）
    universe_filter: str | None = None  # 如 "tradable", "index_constituent"
```

#### TimeSpec 详细待定义

```python
# 待定义：packages/core/src/ditto_core/specs.py

@dataclass
class TimeSpec(BaseModel):
    """时间语义"""

    # 事件时间列名
    event_time: str = "trade_date"

    # 数据可用时间（PIT 场景，可能不同于 event_time）
    availability_time: str | None = None  # 如 "announcement_date"

    # 交易日历
    calendar: str = "cn_trading"  # "cn_trading" / "us_trading" / "hk_trading"

    # 时区
    timezone: str = "Asia/Shanghai"

    # 业务时间对齐（如收盘时间）
    business_time_align: str | None = None  # 如 "15:00:00"
```

---

### 1.2 交易日历统一接口

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| M-020 | `TradingCalendar` Protocol 定义 | ❌ | is_trading_day, next/prev_trading_day, lookback |
| M-021 | CN 市场日历实现 | ❌ | 基于现有 metadata.trading_calendar |
| M-022 | US 市场日历预留 | ⏸️ | Phase 2 |
| M-023 | HK 市场日历预留 | ⏸️ | Phase 2 |
| M-024 | 日历数据源（内置 vs 外部） | ❌ | 决策：内置节假日表 vs 调用外部 API |

```python
# 待定义：packages/core/src/ditto_core/calendar.py

class TradingCalendar(Protocol):
    """交易日历协议"""

    @property
    def market(self) -> Literal["cn", "us", "hk"]: ...

    def is_trading_day(self, date: date) -> bool: ...

    def next_trading_day(self, date: date) -> date: ...

    def prev_trading_day(self, date: date) -> date: ...

    def lookback(self, date: date, n: int) -> date:
        """回溯 n 个交易日"""
        ...

    def trading_days_between(self, start: date, end: date) -> int:
        """两个日期间的交易日数"""
        ...
```

---

## 2. 查询架构层 (P0 - 阻塞实现)

### 2.1 DataHub 实现层

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| Q-001 | `DerivedQueryService` Protocol 定义 | ❌ | 统一查询入口 |
| Q-002 | `QueryMode` 枚举定义 | ❌ | SERVING, RESEARCH, MIXED_SOURCE |
| Q-003 | `QueryParams` 参数模型 | ❌ | derived_id, instrument_ids, date_range, as_of |
| Q-004 | `SourceRouter` 路由逻辑 | ❌ | 根据 QueryMode 选择数据源 |
| Q-005 | `VersionFilter` 版本过滤 | ❌ | primary/online/version 过滤 |
| Q-006 | `AsOfResolver` 时间旅行查询 | ❌ | as_of_date → version 映射 |
| Q-007 | 返回类型确认 | 🚧 | DataHub 返回 pl.DataFrame |

### 2.2 Port Facade 层

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| Q-010 | `ServingDerivedQueryFacade` 接口 | ❌ | 在线查询门面 |
| Q-011 | `ResearchDerivedQueryFacade` 接口 | ❌ | 研究查询门面 |
| Q-012 | `MixedSourceDerivedQueryFacade` 接口 | ❌ | 对拍/排障门面 |
| Q-013 | Facade → DataHub 接口边界 | ❌ | 职责划分 |
| Q-014 | 返回模型转换（DataFrame → dict/Response） | ❌ | 在 Facade 层 |
| Q-015 | 权限控制在哪层？ | ❌ | Port 层负责 |
| Q-016 | 默认策略在哪层？ | ❌ | Port 层负责 |

### 2.3 MixedSource 差异报告

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| Q-020 | `DiffReport` 结构定义 | ❌ | 差异报告模型 |
| Q-021 | 差异检测算法 | ❌ | 值差异、缺失差异 |
| Q-022 | 差异容忍阈值 | ❌ | 浮点误差容忍 |
| Q-023 | 跨源查询性能预估 | ❌ | 需要多长时间 |

```python
# 待定义：packages/datahub/src/ditto_datahub/services/derived/diff_report.py

@dataclass
class DiffReport:
    """差异报告"""

    derived_id: str
    query_time: datetime

    # 数据源对比
    sources_compared: list[str]  # ["parquet", "questdb", "kvrocks"]

    # 行数对比
    row_counts: dict[str, int]

    # 值差异
    value_diffs: list[ValueDiff]

    # 缺失行
    missing_rows: dict[str, list[dict]]  # source -> missing rows

    # 总结
    is_consistent: bool
    consistency_rate: float  # 0.0 - 1.0
```

---

## 3. 控制面协议 (P1 - 质量保障)

### 3.1 发布生命周期

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| C-001 | 发布状态机定义 | ❌ | draft → validated → materialized → certified → published → deprecated |
| C-002 | 状态转换条件 | ❌ | 每个转换的触发条件 |
| C-003 | `PublicationContract` 定义 | ❌ | status, version, is_primary, is_online... |
| C-004 | `publish()` 操作原子性 | ❌ | artifact → serving 同步 |
| C-005 | `rollback()` 契约 | ❌ | 回滚窗口、数据清理 |
| C-006 | `primary` 指针切换 | ❌ | 原子性保证 |
| C-007 | Feature/Factor 共享发布门禁 | ❌ | 共享框架，差异化阈值 |

### 3.2 版本管理

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| C-010 | Schema Evolution 规则 | ❌ | Breaking vs Additive vs Data-only |
| C-011 | Breaking Change 检测 | ❌ | 自动检测哪些变更必须升版本 |
| C-012 | 版本兼容性矩阵 | ❌ | 哪些版本可共存 |
| C-013 | 版本废弃策略 | ❌ | deprecated → archived 时间线 |

### 3.3 认证门禁

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| C-020 | `certify` 阶段是否单独建模 | ❌ | 是否需要独立状态 |
| C-021 | Feature 认证门禁 | ❌ | parity_gate, freshness_gate |
| C-022 | Factor 认证门禁 | ❌ | evaluation_gate, exposure_gate |
| C-023 | 门禁失败处理 | ❌ | 阻断 vs 告警 vs 继续但标记 |

---

## 4. 增量与失效协议 (P1 - 正确性保障)

### 4.1 失效传播

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| I-001 | `InvalidationEvent` 完整结构 | ❌ | trigger_source, affected_range, expansion_rule |
| I-002 | 传播深度限制 | ❌ | max_depth = 10 |
| I-003 | 传播模式 | ❌ | eager vs lazy |
| I-004 | 跨 role 传播 | ❌ | feature → factor 是否传播 |
| I-005 | 批量处理 | ❌ | batch_size = 100 |
| I-006 | 传播状态追踪 | ❌ | pending → processing → completed → failed |

### 4.2 Correction 协议

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| I-010 | Correction vs 故障恢复边界 | ❌ | 明确定义 |
| I-011 | Correction 触发方式 | ❌ | 手动 vs 自动 |
| I-012 | Correction 传播范围 | ❌ | 哪些下游受影响 |
| I-013 | Correction 幂等性 | ❌ | 重复执行是否安全 |

### 4.3 STATE 重建

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| I-020 | STATE 重建锚点 | ❌ | 从哪里开始重建 |
| I-021 | STATE 顺推协议 | ❌ | 如何从锚点顺推到当前 |
| I-022 | STATE 快照频率 | ❌ | 每日 vs 每周 vs 按需 |

### 4.4 SERIES 局部修复

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| I-030 | SERIES 局部修复策略 | ❌ | 替换 vs 追加 |
| I-031 | SERIES 去重机制 | ❌ | DEDUP 策略 |
| I-032 | SERIES 空洞填充 | ❌ | 缺失数据处理 |

---

## 5. 质量门禁 (P1 - 上线验收)

### 5.1 DQ 规则 - P1 必须

| 编号 | 规则 | 状态 | 阈值 | 说明 |
|------|------|------|------|------|
| D-001 | Schema 校验 | ❌ | 强制 | 输出列名/类型必须匹配 spec |
| D-002 | 空值率阈值 | ❌ | ≤ 5% | 列空值率检查 |
| D-003 | 数据新鲜度 | ❌ | ≤ T+1 | 延迟检查 |
| D-004 | Feature Parity | ❌ | ≥ 99.9% | 研究/生产一致性 |

### 5.2 DQ 规则 - P2 扩展

| 编号 | 规则 | 状态 | 阈值 | 说明 |
|------|------|------|------|------|
| D-010 | 分布漂移 (PSI) | ⏸️ | PSI ≤ 0.1 | 分布漂移检测 |
| D-011 | 极端值检测 | ⏸️ | 自动标记 | Winsorize |
| D-012 | 统计监控 | ⏸️ | 均值/方差/分位数 | 基础统计 |

### 5.3 性能基准 - P1 必须

| 编号 | 指标 | 状态 | 目标 | 说明 |
|------|------|------|------|------|
| P-001 | 单因子增量延迟 (P50) | ❌ | ≤ 5s | 1000 标的 × 1 日增量 |
| P-002 | 单因子增量延迟 (P99) | ❌ | ≤ 30s | 1000 标的 × 1 日增量 |
| P-003 | 100 因子日更吞吐 | ❌ | ≤ 10min | 全量因子日更完成时间 |
| P-004 | 基准测试脚本 | ❌ | - | scripts/benchmark_factor.py |
| P-005 | CI 性能门禁 | ❌ | - | 回退超过 20% 则失败 |

### 5.4 性能基准 - P2 扩展

| 编号 | 指标 | 状态 | 目标 | 说明 |
|------|------|------|------|------|
| P-010 | API 查询延迟 (P50) | ⏸️ | ≤ 10ms | |
| P-011 | API 查询延迟 (P99) | ⏸️ | ≤ 50ms | |
| P-012 | 并发写入压力测试 | ⏸️ | - | |
| P-013 | 内存峰值限制 | ⏸️ | - | |

### 5.5 算子数学正确性

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| D-020 | P0 算子黄金数据集 | ❌ | ts_mean, ts_std, ts_rank, cs_rank... |
| D-021 | TA-Lib 对齐测试 | ❌ | 与 TA-Lib 参考实现对齐 |
| D-022 | 边界情况测试 | ❌ | NULL 处理、窗口边界、空数据 |

---

## 6. 存储策略 (P2 - 运维优化)

### 6.1 热冷数据保留

| 编号 | 待决策项 | 状态 | 选项 | 建议 |
|------|---------|------|------|------|
| S-001 | 分钟数据进 Parquet | ❌ | 不保留 / 保留 30 日 | 保留 30 日用于对拍 |
| S-002 | QuestDB 分钟 TTL | ❌ | 5 日 / 120 日 | 5 日（热层最小化原则）|
| S-003 | QuestDB 日线 TTL | ❌ | 30 日 / 180 日 / 365 日 | 30 日 |
| S-004 | STATE 热序列 | ❌ | 不需要 / 可选 | 可选（性能敏感因子）|

### 6.2 状态存储

| 编号 | 待决策项 | 状态 | 说明 |
|------|---------|------|------|
| S-010 | Kvrocks key 拆分策略 | ❌ | 统一 namespace vs 按类型拆分 |
| S-011 | `derived:state:*` vs `state:feature:*` | ❌ | 命名统一 |
| S-012 | 状态快照 TTL | ❌ | 多久后自动清理 |

### 6.3 一致性校验

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| S-020 | 冷热数据一致性校验机制 | ❌ | 抽样对比 |
| S-021 | 一致性校验频率 | ❌ | 每日 vs 每周 |
| S-022 | 一致性告警 | ❌ | 发现不一致时的处理流程 |
| S-023 | CLI 命令 `ditto check consistency` | ❌ | 手动触发校验 |

---

## 7. 表达式引擎优化 (P1 - 性能与安全)

### 7.1 表达式缓存

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| E-001 | 内存缓存配置 | ❌ | max_entries, TTL |
| E-002 | 磁盘缓存支持 | ❌ | 可选持久化 |
| E-003 | 缓存失效触发条件 | ❌ | 算子版本变更、引擎升级 |
| E-004 | 缓存命中率监控 | ❌ | Prometheus 指标 |

### 7.2 表达式复杂度限制

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| E-010 | 最大字符长度 | ❌ | 建议 500 |
| E-011 | 最大嵌套深度 | ❌ | 建议 10 |
| E-012 | 最大 AST 节点数 | ❌ | 建议 100 |
| E-013 | 最大 lookback | ❌ | 建议 252 交易日 |
| E-014 | 最大执行时间 | ❌ | 建议 30s |
| E-015 | 最大内存占用 | ❌ | 建议 512MB |

### 7.3 算子版本管理

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| E-020 | 算子版本注册机制 | ❌ | 自动版本号 + checksum |
| E-021 | Spec 记录算子版本 | ❌ | `operator_versions` 字段 |
| E-022 | Breaking Change 自动检测 | ❌ | 触发因子重算 |
| E-023 | 算子废弃流程 | ❌ | deprecated → removed 时间线 |

### 7.4 自定义算子扩展

| 编号 | 待补充项 | 状态 | 说明 |
|------|---------|------|------|
| E-030 | `CustomOperator` Protocol | ⏸️ | Phase 2 |
| E-031 | 自定义算子注册 | ⏸️ | Phase 2 |
| E-032 | 自定义算子沙箱 | ⏸️ | Phase 2 |

---

## 8. 测试策略补充 (P1 - 质量保障)

### 8.1 算子黄金数据集

| 算子 | 状态 | 黄金数据来源 |
|------|------|-------------|
| ts_mean | ❌ | TA-Lib SMA |
| ts_std | ❌ | 手工计算 |
| ts_rank | ❌ | 边界情况验证 |
| ts_delta | ❌ | 手工计算 |
| ts_pct_change | ❌ | 手工计算 |
| cs_rank | ❌ | Pandas rank |
| cs_zscore | ❌ | Scipy zscore |
| correlation | ❌ | Pandas corr |
| covariance | ❌ | Pandas cov |

### 8.2 集成测试

| 编号 | 测试场景 | 状态 | 说明 |
|------|---------|------|------|
| T-001 | 全量 → 增量 结果一致性 | ❌ | 同一数据源，两种模式结果相同 |
| T-002 | Parquet → QuestDB 回补一致性 | ❌ | 回补后数据一致 |
| T-003 | Invalidation 级联传播正确性 | ❌ | 上游变更正确传播到下游 |
| T-004 | Rollback 数据完整性 | ❌ | 回滚后数据状态正确 |
| T-005 | 并发写入一致性 | ❌ | 多因子并行写入不冲突 |

---

## 9. 代码迁移项 (P1 - 平滑升级)

### 9.1 现有服务迁移

| 编号 | 待迁移项 | 状态 | 说明 |
|------|---------|------|------|
| G-001 | `FeatureService` → Facade | ❌ | 逐步退化为兼容门面 |
| G-002 | `FactorService` → Facade | ❌ | 逐步退化为兼容门面 |
| G-003 | DataHub `derived` 子域 | ❌ | 新增目录结构 |
| G-004 | Port `derived` provider | ❌ | registry/datahub/ 增加 derived |

### 9.2 测试迁移

| 编号 | 待迁移项 | 状态 | 说明 |
|------|---------|------|------|
| G-010 | 离线 reader mock → 新分层 | ❌ | 测试基础设施更新 |
| G-011 | 集成测试适配 | ❌ | 使用新接口 |
| G-012 | 基准测试适配 | ❌ | 使用新接口 |

---

## 10. 文档待更新项

| 编号 | 文档 | 状态 | 更新内容 |
|------|------|------|---------|
| DOC-001 | main-design.md | ❌ | 合并 DerivedSpec 定义 |
| DOC-002 | README.md | ❌ | 更新 ADR 索引 |
| DOC-003 | issues.md | ❌ | 同步本清单状态 |
| DOC-004 | reference/operator-reference.md | ❌ | 补充算子版本信息 |
| DOC-005 | reference/catalog-schema.md | ❌ | 补充 Entity/Time 字段 |

---

## 11. ADR 待创建/扩展清单

### 11.1 必须新建

| ADR | 标题 | 状态 | 依赖 | 阻塞点 |
|-----|------|------|------|--------|
| ADR-032 | Unified Derived Semantic Model | ❌ | 无 | Phase 0 实施 |
| ADR-033 | Derived Query Architecture and Layer Boundary | ❌ | ADR-032 | 查询层实现 |
| ADR-034 | Derived Publication Lifecycle and Version Contract | ❌ | ADR-032 | 控制面实现 |
| ADR-035 | Derived Rebuild, Invalidation, and Correction Protocol | ❌ | ADR-032,034 | 增量正确性 |
| ADR-036 | Derived Quality, Benchmark, and Certification Gates | ❌ | ADR-032,034 | 上线验收 |
| ADR-037 | Hot/Cold Retention and Minute Data Policy | ❌ | ADR-032,035 | 运维策略 |

### 11.2 需要扩展

| ADR | 扩展内容 | 状态 |
|-----|---------|------|
| ADR-007 | 算子版本管理 | ❌ |
| ADR-014 | 表达式复杂度限制、缓存失效策略 | ❌ |
| ADR-019 | 算子黄金数据集 | ❌ |
| ADR-022 | 失效传播级联策略 | ❌ |
| ADR-024 | Feature/Factor 统一生命周期 | ❌ |
| ADR-029 | 扩展到 feature + factor | ❌ |
| ADR-030 | 三类查询语义接口细化 | ❌ |
| ADR-031 | 扩展到 derived 视角 | ❌ |

---

## 12. 验收检查表

### Phase 0 验收（内核可跑通）

- [ ] DerivedSpec 支持 feature/factor/signal/label
- [ ] EntitySpec 支持多实体 join
- [ ] TimeSpec 支持多市场日历
- [ ] 能计算并写入首个 feature 和首个 factor
- [ ] 能记录 watermark 并完成一次 incremental
- [ ] Catalog 四张核心表（derived_spec/state/run/partition）

### Phase 1 验收（增量与并发）

- [ ] Invalidation 表与扩展逻辑
- [ ] requires_full_day 触发整日重算
- [ ] 表级/分区级锁策略
- [ ] 多因子并行运行稳定
- [ ] 增量结果与全量结果抽样一致

### Phase 2 验收（PIT 与闭环）

- [ ] 基本面修订触发区间回算
- [ ] feature_sets 宽表输出
- [ ] publish/latest 与回滚机制
- [ ] 研究回放与生产日更使用同一引擎代码路径
- [ ] 质量与可观测指标达标

---

## 变更日志

| 日期 | 变更 | 来源 |
|------|------|------|
| 2026-03-12 | 创建差距补齐清单 | 设计评审 |
