# Ditto 统一派生查询引擎 - 待优化与差距补齐清单

> **状态**: 历史 backlog，仅供参考。
> **说明**: 本文档主要记录 2026-03-12 时点的优化拆分与状态估计，后续已有 ADR 落地和整改方案收敛。当前执行请优先参考：
> - [README.md](README.md)
> - [main-design.md](main-design.md)
> - [2026-03-13-unified-feature-factor-engine-remediation-design.md](../../plans/2026-03-13-unified-feature-factor-engine-remediation-design.md)

**状态**: 🚧 进行中
**创建日期**: 2026-03-12
**最后更新**: 2026-03-12
**文档目标**: 系统性记录设计分析报告中识别的所有待优化项、差距项和冲突口径，作为逐步解决的总览索引

---

## 0. 文档说明

### 0.1 使用方式

1. **本文档**：总览索引，记录所有待优化项的元信息和状态
2. **详细设计**：每个项目的详细设计落地到对应的 ADR 或主设计文档
3. **逐步讨论**：按优先级顺序逐一解决

### 0.2 状态定义

| 状态 | 含义 |
|------|------|
| 🔴 待设计 | 尚未开始设计讨论 |
| 🟡 讨论中 | 正在进行设计讨论 |
| 🟢 已决策 | 设计决策已完成，待实现 |
| ✅ 已实现 | 已完成实现并验证 |
| ⏸️ 暂缓 | 等待后续阶段处理 |

---

## 1. 优先级分级说明

### P0 - 阻塞实施（必须立即处理）

**定义**：阻塞 Phase 0 实施的缺口，不解决无法进入开发阶段

**影响范围**：核心模型、关键接口

**决策原则**：必须先完成设计决策，才能开始任何实现

### P1 - 架构决策（Phase 0 开始前）

**定义**：影响整体架构的关键决策，不解决会导致实现返工

**影响范围**：性能、可观测性、质量保障

**决策原则**：在 Phase 0 开始前完成决策，避免实现中反复修改

### P2 - 改进项（Phase 1/2 期间）

**定义**：功能完善和优化项，可以渐进式解决

**影响范围**：功能完整性、用户体验

**决策原则**：可以在实现过程中逐步补充

---

## 2. P0 - 阻塞项清单

### P0-1: DerivedSpec 完整字段模型

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **优先级** | P0 - 阻塞 |
| **当前问题** | `DerivedSpec` 缺少 `entity_keys`、`time_keys`、`grain`、`calendar`、`timezone` 等关键字段 |
| **影响范围** | 全局根抽象，影响 engine、catalog、query、publish、storage |
| **目标 ADR** | ADR-032: Unified Derived Semantic Model |
| **依赖** | 无 |

**当前状态**：
```python
@dataclass
class DerivedSpec(BaseModel):
    id: str
    version: int
    role: Literal["feature", "factor", "signal", "label"]
    materialization_profile: Literal["SERIES", "STATE", "DERIVE", "OFFLINE"]
    expression: str
    profile_config: FeatureProfile | FactorProfile
```

**缺失字段**：
- `entity_keys`: 实体键定义（如 `["instrument_id"]`）
- `time_keys`: 时间键定义（如 `["trade_date"]`）
- `grain`: 数据粒度（如 `"1d"`、`"1m"`）
- `calendar`: 交易日历标识（如 `"cn_stock"`、`"us_nasdaq"`）
- `timezone`: 时区定义（如 `"Asia/Shanghai"`）
- `owner`: 责任人/团队
- `created_at`/`updated_at`: 元数据时间戳

**待决策问题**：
1. `entity_keys` 是否需要支持复合键（如 instrument_id + exchange_code）？
2. `calendar` 是否本期只支持中国 A 股，还是预留下多市场扩展位？
3. `grain` 的枚举值范围？
4. 是否需要 `description` 字段？

**涉及文件**：
- 待新增: `packages/core/src/ditto_core/engine/specs.py`
- 待修改: `docs/design/unified-feature-factor-engine/main-design.md`
- 待新增: `docs/design/unified-feature-factor-engine/decisions/adr-032-unified-derived-semantic-model.md`

---

### P0-2: Port/DataHub 接口契约

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **优先级** | P0 - 阻塞 |
| **当前问题** | facade（Port 层）与 implementation（DataHub 层）的精确边界未定义 |
| **影响范围** | Port 层、DataHub 层、Import Linter 规则 |
| **目标 ADR** | ADR-033: Derived Query Architecture and Layer Boundary |
| **依赖** | P0-1 |

**决策总结**：
| 决策 | 结论 |
|------|------|
| D-1 Facade 模式 | 单一 `DerivedQueryFacade` + 按用例拆分方法（`get_latest`, `get_series`, `compare_sources`） |
| D-2 DataHub 返回类型 | 查询类统一 `pl.DataFrame`，状态/治理类返回标量或小型结构体 |
| D-3 Query DTO 归属 | 放在 DataHub 层 |
| D-4 同步/异步风格 | 统一同步风格 |

**涉及文件**：
- 已新增: `docs/design/unified-feature-factor-engine/decisions/adr-033-derived-query-architecture.md`
- 待新增: `apps/port/src/ditto_port/facades/derived/`
- 待新增: `packages/datahub/src/ditto_datahub/services/derived/`

---

## 3. P1 - 架构决策清单

### P1-1: 表达式缓存持久化策略

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **优先级** | P1 |
| **当前问题** | 只有内存缓存，缺少持久化，重启后需要重新编译 |
| **影响范围** | 性能、启动时间 |
| **目标 ADR** | [ADR-039: 表达式缓存持久化策略](decisions/adr-039-expression-cache-persistence.md) |
| **依赖** | P0-1 |
| **业界对标** | Qlib 两级缓存（内存 + 磁盘） |

**决策总结**：

| 决策点 | 决策 |
|-------|------|
| **缓存架构** | L1 内存（DataCache） + L2 SQLite |
| **缓存对象** | 编译产物 artifact（非 Python Expr） |
| **CSE 范围** | 仅 L1，不持久化 |
| **缓存键** | 双键模型：`compile_input_hash` + `compiler_fingerprint` |
| **算子指纹** | Phase 1: `op_name + op_version` |
| **失效策略** | 懒失效（fingerprint mismatch）+ 后台 GC |

**涉及文件**：
- 待新增: `packages/core/src/ditto_core/engine/cache/`

---

### P1-2: 算子版本管理

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **优先级** | P1 |
| **当前问题** | 算子变更无法追踪影响范围，可能导致历史数据不一致 |
| **影响范围** | 可复现性、缓存失效 |
| **目标 ADR** | [ADR-038: 算子版本管理](decisions/adr-038-operator-versioning.md) |
| **依赖** | P1-1 ✅ |
| **业界对标** | Qlib 算子版本、DolphinDB JIT 版本 |

**决策总结**：

| 决策点 | 决策 |
|-------|------|
| **版本号格式** | SemVer（严格三段式 `1.0.0`） |
| **升级规则** | 四分法：MAJOR / MINOR / PATCH / NO BUMP |
| **变更日志** | 结构化 `ChangeRecord`，append-only |
| **依赖提取** | Analyzer 阶段，产出 `operator_names` |
| **Spec 级存储** | `operator_versions` 快照 + `derived_spec_operator` 副表 |

**涉及文件**：
- 待修改: `packages/core/src/ditto_core/engine/ops/registry.py`
- 待修改: `packages/core/src/ditto_core/engine/specs.py`
- 待新增: `packages/core/src/ditto_core/engine/ops/versioning.py`

---

### P1-3: 表达式复杂度限制

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **优先级** | P1 |
| **当前问题** | 无复杂度检查，可能导致性能问题或资源耗尽 |
| **影响范围** | 性能、稳定性 |
| **目标 ADR** | [ADR-014: 表达式引擎核心设计](decisions/adr-014-expression-engine-core.md)（扩展） |
| **依赖** | 无 |
| **业界对标** | WorldQuant Brain：500 字符 / 10 层 |

**决策总结**：

| 类型 | 指标 | 阈值 | 行为 |
|------|------|------|------|
| **硬限制** | max_length | 500 | 编译期拒绝 |
| **硬限制** | max_depth | 10 | 编译期拒绝 |
| **硬限制** | max_nodes | 100 | 编译期拒绝 |
| **硬限制** | max_lookback | 252 | 编译期拒绝 |
| **软估计** | estimated_execution_time | - | 告警 |
| **软估计** | estimated_memory | - | 告警 |

**关键约束**：
- ❌ 不提供普通白名单
- ❌ 不配置"是否拒绝"（避免环境漂移）
- ✅ 只配"阈值"（研发/生产可不同）

**涉及文件**：
- 待修改: `packages/core/src/ditto_core/engine/expression/analyzer.py`

---

### P1-4: 算子黄金数据集

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **优先级** | P1 |
| **当前问题** | 缺少数学正确性验证基准 |
| **影响范围** | 算子正确性 |
| **目标 ADR** | [ADR-019: 测试策略（黄金数据集扩展）](decisions/adr-019-testing-strategy.md) |
| **依赖** | 无 |
| **业界对标** | TA-Lib 验证基准 |

**决策总结**：

| 决策点 | 决策 |
|--------|------|
| **数据来源** | 混合方案：TA-Lib 参照生成 fixture + 手工样本覆盖边界/非 TS 算子；最终固化 fixture 进仓库 |
| **精度处理** | 语义优先 + 混合容差（numpy.assert_allclose）+ 按算子族少量覆写 |
| **覆盖目标** | 渐进式：Phase 1 覆盖 TS/CS 核心算子（7-9 个），每算子 3-5 个数学场景 |

**Phase 1 算子范围**：
- TS 核心：ts_mean, ts_std, ts_sum, ts_rank, ts_ref
- CS 核心：cs_rank, cs_zscore
- 递归指标：EMA / RSI（选 1-2 个）

**涉及文件**：
- 已修改: `docs/design/unified-feature-factor-engine/decisions/adr-019-testing-strategy.md`
- 待新增: `tests/golden/operators/`

---

### P1-5: 发布生命周期协议

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **优先级** | P1 |
| **当前问题** | `register → publish` 流程未细化 |
| **影响范围** | 控制面、质量保障 |
| **目标 ADR** | [ADR-034: Derived 发布生命周期协议](decisions/adr-034-publication-lifecycle.md) |
| **依赖** | P0-1 ✅ |
| **业界对标** | MLflow Stage 指针、Feast Feature View 版本化 |

**决策总结**：

| 决策点 | 决策 |
|--------|------|
| **状态机** | 5 状态：DRAFT → REGISTERED → MATERIALIZED → PUBLISHED → DEPRECATED；validate/certify 作为门禁事件 |
| **多版本策略** | 复用 ADR-024 的 `online` + `primary` 指针模型 |
| **回滚机制** | `deprecate` 标记废弃 + `rollback_primary` 指针切换，不改状态历史 |

**涉及文件**：
- 已新增: `docs/design/unified-feature-factor-engine/decisions/adr-034-publication-lifecycle.md`
- 待新增: `packages/datahub/src/ditto_datahub/services/derived/publication_service.py`

---

### P1-6: 失效传播级联协议

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **优先级** | P1 |
| **当前问题** | 跨因子依赖的级联传播未明确 |
| **影响范围** | 增量正确性 |
| **目标 ADR** | [ADR-035: 失效传播级联协议](decisions/adr-035-invalidation-cascade.md) |
| **依赖** | P0-1 ✅、P1-5 ✅ |
| **业界对标** | RisingWave MV 增量维护 |

**决策总结**：

| 决策点 | 决策 |
|--------|------|
| **级联深度** | 固定深度 5 作为实时级联护栏；批处理路径不受限 |
| **传播模式** | 异步队列 + 微批合并；上游确认=入队；下游分层消费；stale 标记保证查询一致性 |
| **循环检测** | 注册时 DAG 校验硬阻断 + 运行时 visited 去重兜底 |

**涉及文件**：
- 已新增: `docs/design/unified-feature-factor-engine/decisions/adr-035-invalidation-cascade.md`

---

### P1-7: DQ 门禁定义

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **优先级** | P1 |
| **当前问题** | 最小发布门禁未定义 |
| **影响范围** | 质量保障 |
| **目标 ADR** | [ADR-036: DQ 门禁设计](decisions/adr-036-quality-gates.md) |
| **依赖** | P0-1 ✅ |
| **业界对标** | Feast/Tecton DQ 检查 |

**决策总结**：

| 决策点 | 决策 |
|-------|------|
| **执行阶段** | 多阶段：register（静态）→ materialize（采集）→ publish（阻断） |
| **门禁类型** | Schema + 空值率 + 新鲜度 |
| **空值率阈值** | 按 role 分层：feature 1% / factor 5% / signal 0% / label 只告警 |
| **新鲜度语义** | `freshness_sla = "T+N"`，P1 默认 T+1 |
| **失败处理** | ERROR 阻断但保留产物，WARNING 允许但留痕 |
| **Override** | P1 不提供通用 force publish |

**涉及文件**：
- 待新增: `packages/core/src/ditto_core/engine/gates/`

---

### P1-8: 性能 SLO 定义

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **优先级** | P1 |
| **当前问题** | 无性能基准 |
| **影响范围** | 性能监控、容量规划 |
| **目标 ADR** | [ADR-037: 性能 SLO 定义](decisions/adr-037-performance-slo.md) |
| **依赖** | 无 |
| **业界对标** | RisingWave MV 性能指标 |

**决策总结**：

| 决策点 | 决策 |
|--------|------|
| **SLO 策略** | Phase 1 定义测量框架 + SLI + CI 回归预算（相对阈值），Phase 2 收敛为正式 SLO |
| **SLI 指标** | P0：端到端物化延迟 + 级联传播延迟；P1：吞吐；资源作为诊断指标 |
| **CI 门禁** | 退化 > 15% 告警，退化 > 25% 阻断 |

**涉及文件**：
- 已新增: `docs/design/unified-feature-factor-engine/decisions/adr-037-performance-slo.md`
- 待新增: `tests/benchmarks/`

---

## 4. P2 - 改进项清单

### P2-1: 多市场日历框架

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **优先级** | P2 |
| **当前问题** | 只支持中国 A 股交易日历 |
| **影响范围** | 多市场支持 |
| **目标 ADR** | ADR-040（新建）或 ADR-006（扩展） |
| **依赖** | P0-1 ✅ |

**决策总结**：

| 决策点 | 决策 |
|--------|------|
| **Phase 1 范围** | 框架 + CN 实现；DerivedSpec.calendar 对外仍只允许 `cn_stock` |
| **对外契约** | US/HK 只预留接口位，不交付具体市场规则 |
| **最小 Protocol** | 4 个原语：`calendar_id`、`is_trading_day`、`shift`、`trading_days_between` |
| **便捷方法** | 放在 `BaseTradingCalendar`：`next_trading_day`、`prev_trading_day`、`lookback`（委托到 `shift`） |
| **分钟级 session** | Phase 1 不进接口（1m 仍为预留） |

**接口形态**：
```python
class TradingCalendar(Protocol):
    @property
    def calendar_id(self) -> CalendarId: ...
    def is_trading_day(self, day: date) -> bool: ...
    def shift(self, day: date, offset: int) -> date: ...
    def trading_days_between(self, start: date, end: date) -> list[date]: ...

class BaseTradingCalendar(ABC):
    def next_trading_day(self, day: date) -> date:
        return self.shift(day, 1)
    def prev_trading_day(self, day: date) -> date:
        return self.shift(day, -1)
    def lookback(self, day: date, n: int) -> date:
        return self.shift(day, -n)
```

---

### P2-2: Rolling State 缓存

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **优先级** | P2（建议提升至 P1 性能优化项） |
| **当前问题** | 增量计算每次需要重新预热窗口 |
| **影响范围** | 增量性能 |
| **目标 ADR** | ADR-041（新建） |
| **依赖** | P1-1 ✅ |

**决策总结**：

| 决策点 | 决策 |
|--------|------|
| **Phase 1 范围** | 最小可用：单因子 + 单标的 + Tier 1/2 TS 算子 |
| **算子覆盖** | ts_mean、ts_sum、ts_std、ts_count、ts_ema |
| **存储** | 复用 Kvrocks，不复用 state snapshot 键空间 |
| **缓存键** | `derived:rolling:{entity_type}:{entity_id}:{version}:{instrument_id}:{state_slot_id}` |
| **state_slot_id** | `sha256(canonical_subexpr + operator_version + window_params)` |
| **失效机制** | keyspace 隔离 + read-time 懒失效 + event-driven overlap + continuity guard；TTL 仅回收 |

**失效触发**：

| 类型 | 触发 | 机制 |
|------|------|------|
| 主触发 | spec version 变化 | 新 keyspace，旧 key 自然 miss |
| 主触发 | operator version / fingerprint 变化 | 读时比对 metadata，懒失效 |
| 主触发 | 上游 correction 命中窗口 | Invalidation 事件 overlap 检测 |
| 主触发 | watermark 不连续 / gap | continuity guard |
| 补充 | state_schema_version 变化 | ABI 演进信号 |
| 补充 | manual force/backfill/rebuild | 运维入口 |
| 回收 | TTL | 仅回收，不承担正确性 |

**关键约束**：TTL 不是正确性失效触发器，只是回收机制

---

### P2-3: 热冷数据一致性校验

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **优先级** | P2（建议优先于 P2-4/P2-5） |
| **当前问题** | QuestDB vs Parquet 数据一致性无验证 |
| **影响范围** | 数据质量 |
| **目标 ADR** | ADR-042（新建） |
| **依赖** | 无 |

**决策总结**：

| 决策点 | 决策 |
|--------|------|
| **Phase 1 范围** | 最小校验能力：只检测不修复 |
| **校验范围** | 最近 N 天热数据，N 与热层 TTL 对齐 |
| **触发频率** | 每日定时（盘后/凌晨）+ 手动触发（回补/修正/恢复后） |
| **抽样粒度** | 分区级（trade_date）为主；异常后按 instrument_id 下钻 |
| **比对策略** | 轻量摘要基础 + 异常时自动补充 diff sample |
| **checksum 口径** | 规范化后哈希（主键排序 → 关键列 → 浮点规范化 → xxhash64） |
| **告警分级** | Warning / Critical 分层 |
| **处理动作** | 差异报告 + 告警 + 指标 + 显式命令，不做自动修复 |

**比对字段**：

| 阶段 | 比对内容 |
|------|---------|
| 正常校验 | row_count + min/max ts + checksum |
| 摘要不一致 | 抽样主键 + 值级 diff（缺失行、重复行、值不一致） |

**checksum 规范化规则**：
1. 按 `instrument_id + trade_date + bar_time` 稳定排序
2. 只选业务关键列（OHLCV、因子值、trade_date/bar_time）
3. 浮点统一规范化（固定精度 round，统一 NaN/null）
4. 对规范化行做 xxhash64，再聚合成分区 checksum

**告警分级**：

| 级别 | 触发条件 |
|------|---------|
| Warning | 历史分区不一致、行数差异小、checksum 不一致但主链路未受影响 |
| Critical | 最近交易日热分区不一致、行数差异大、连续多次失败、命中 serving 热点 |

**处理动作**：
- 生成差异报告
- 发 AlertManager 告警
- 记录一致性检查结果指标
- 提供显式 `rebuild`/`replay`/`check` 命令
- 不做自动修复

---

### P2-4: 自定义算子扩展

| 属性 | 值 |
|------|------|
| **状态** | ⏸️ 暂缓 |
| **优先级** | P2 |
| **当前问题** | 用户无法自定义算子 |
| **影响范围** | 可扩展性 |
| **依赖** | 无 |

**建议方案**：
1. 用户算子注册机制
2. 沙箱执行环境
3. 版本管理

---

### P2-5: Lineage 可视化

| 属性 | 值 |
|------|------|
| **状态** | ⏸️ 暂缓 |
| **优先级** | P2 |
| **当前问题** | 因子依赖关系无可视化 |
| **影响范围** | 可观测性 |
| **依赖** | 无 |

**建议方案**：
1. Grafana 面板
2. Marquez 集成
3. 自定义可视化

---

## 5. 冲突口径统一清单

### C-1: DERIVE 执行定位

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **口径 A** | DuckDB ADHOC |
| **口径 B** | QuestDB + Polars 现算 |
| **决策** | 采用口径 B |
| **理由** | 复用热层数据，减少数据移动 |

**需修改文件**：
- `docs/design/unified-feature-factor-engine/main-design.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-029-intraday-postmarket-paths.md`

---

### C-2: 热层 TTL

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策（临时） |
| **口径 A** | 分钟 5 日 / 日线 30 日 |
| **口径 B** | 120/180/365 天 |
| **决策** | 可配置策略；Phase 1 默认 分钟 5 日 / 日线 30 日；长 TTL 作为压测候选 profile |

**决策约束**：
- 配置粒度只到"数据类别/表族/环境 profile"，不细到每张表
- 120/180/365 天仅作为 benchmark profile，不是默认规范值
- 这是 provisional decision，压测完成或 Phase 2 时必须复审定案

**需修改文件**：
- `docs/design/unified-feature-factor-engine/main-design.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-028-questdb-hot-tables.md`

---

### C-3: 状态 Key 命名

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **口径 A** | `derived:state:*` |
| **口径 B** | `state:feature:{id}` |
| **决策** | 统一为口径 A |
| **理由** | 更通用，支持 role 扩展 |

**需修改文件**：
- `docs/design/unified-feature-factor-engine/decisions/adr-031-state-snapshot-abi.md`

---

### C-4: 分钟数据进 Parquet

| 属性 | 值 |
|------|------|
| **状态** | 🟢 已决策 |
| **口径 A** | 不保留 |
| **口径 B** | 保留 30 日 |
| **决策** | 保留 30 日标准化分钟 bar，限最小必要范围 |

**决策约束**：
- **必保留**：标准化 bar_1m + replay/audit 元数据
- **默认不保留**：原始逐笔、LOB 高频明细、分钟级中间物化视图
- **恢复语义**：30 日内优先从 Parquet 回补；超窗后依赖上游重放

**需修改文件**：
- `docs/design/unified-feature-factor-engine/main-design.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-023-disaster-recovery.md`

---

## 6. 待修改/待删除/待新增文件汇总

### 6.1 待新增文件

| 文件路径 | 用途 | 关联项目 |
|---------|------|---------|
| `docs/design/unified-feature-factor-engine/decisions/adr-032-unified-derived-semantic-model.md` | DerivedSpec 完整模型 | P0-1 |
| `docs/design/unified-feature-factor-engine/decisions/adr-033-derived-query-architecture.md` | Port/DataHub 边界 | P0-2 |
| `docs/design/unified-feature-factor-engine/decisions/adr-034-publication-lifecycle.md` | 发布生命周期 | P1-5 |
| `docs/design/unified-feature-factor-engine/decisions/adr-035-invalidation-cascade.md` | 失效级联协议 | P1-6 |
| `docs/design/unified-feature-factor-engine/decisions/adr-036-quality-gates.md` | DQ 门禁 | P1-7 |
| `docs/design/unified-feature-factor-engine/decisions/adr-037-performance-slo.md` | 性能 SLO | P1-8 |
| `docs/design/unified-feature-factor-engine/decisions/adr-038-operator-versioning.md` | 算子版本管理 | P1-2 |
| `docs/design/unified-feature-factor-engine/decisions/adr-039-expression-cache-persistence.md` | 表达式缓存持久化 | P1-1 |
| `packages/core/src/ditto_core/engine/specs.py` | DerivedSpec 模型 | P0-1 |
| `packages/core/src/ditto_core/engine/cache/` | 表达式缓存 | P1-1 |
| `packages/core/src/ditto_core/engine/gates/` | 质量门禁 | P1-7 |
| `packages/datahub/src/ditto_datahub/services/derived/` | Derived 查询实现 | P0-2 |
| `apps/port/src/ditto_port/facades/derived/` | Derived 查询 Facade | P0-2 |
| `tests/golden/operators/` | 黄金数据集 | P1-4 |
| `tests/benchmarks/` | 性能基准 | P1-8 |

### 6.2 待修改文件

| 文件路径 | 修改内容 | 关联项目 |
|---------|---------|---------|
| `docs/design/unified-feature-factor-engine/main-design.md` | 统一冲突口径、补充字段 | C-1, C-2, C-4 |
| `docs/design/unified-feature-factor-engine/decisions/adr-014-expression-engine-core.md` | 复杂度限制 | P1-3 |
| `docs/design/unified-feature-factor-engine/decisions/adr-019-testing-strategy.md` | 黄金数据集 | P1-4 |
| `docs/design/unified-feature-factor-engine/decisions/adr-024-factor-versioning.md` | 扩展到 Derived | P1-5 |
| `docs/design/unified-feature-factor-engine/decisions/adr-006-incremental-computation.md` | 级联传播 | P1-6 |
| `docs/design/unified-feature-factor-engine/decisions/adr-028-questdb-hot-tables.md` | TTL 统一 | C-2 |
| `docs/design/unified-feature-factor-engine/decisions/adr-029-intraday-postmarket-paths.md` | DERIVE 定位 | C-1 |
| `docs/design/unified-feature-factor-engine/decisions/adr-030-online-data-access-boundary.md` | 查询边界细化 | P0-2 |
| `docs/design/unified-feature-factor-engine/decisions/adr-031-state-snapshot-abi.md` | State namespace | C-3 |
| `docs/design/unified-feature-factor-engine/README.md` | ADR 索引更新 | 全部 |

### 6.3 待删除文件

| 文件路径 | 原因 | 替代方案 |
|---------|------|---------|
| 暂无 | - | - |

---

## 7. 推荐讨论顺序

### 第一轮：根抽象与接口契约（P0）

1. **P0-1: DerivedSpec 完整字段**
   - 确定全局根模型
   - 所有问题的基础

2. **P0-2: Port/DataHub 接口契约**
   - 确定分层边界
   - 影响所有实现

### 第二轮：性能与质量（P1）

3. **P1-1: 表达式缓存策略**
4. **P1-3: 复杂度限制**
5. **P1-7: DQ 门禁**
6. **P1-8: 性能 SLO**

### 第三轮：控制面协议（P1）

7. **P1-5: 发布生命周期**
8. **P1-2: 算子版本管理**
9. **P1-6: 失效传播级联**

### 第四轮：测试与验证（P1）

10. **P1-4: 黄金数据集**

### 第五轮：冲突口径统一

11. **C-2: 热层 TTL**（需负载测试数据）
12. **C-4: 分钟数据保留**（需成本评估）

---

## 8. 验收标准

### ADR 验收标准

每个 ADR 必须满足：
- [ ] 明确回答"为什么这样设计，而不是另一个方案"
- [ ] 明确受影响层级：Core / DataHub / Port / Infra
- [ ] 明确新旧路径如何兼容或迁移
- [ ] 明确至少一个反例：什么不应该放进这个 ADR
- [ ] 明确和既有 ADR 的关系：替代、扩展或引用

### 实施验收标准

整体设计验收：
- [ ] 所有 P0 项目状态为 🟢 已决策
- [ ] 冲突口径全部统一
- [ ] ADR 索引更新完成
- [ ] main-design.md 更新完成

---

## 9. 更新记录

### 2026-03-12

- 创建文档，记录分析报告中的所有待优化项
- 按 P0/P1/P2 分级
- 汇总冲突口径
- 整理待修改/待新增文件清单
- **P1-1 决策完成**：表达式缓存持久化策略 → [ADR-039](decisions/adr-039-expression-cache-persistence.md)
- **P1-2 决策完成**：算子版本管理 → [ADR-038](decisions/adr-038-operator-versioning.md)
- **P1-3 决策完成**：表达式复杂度限制 → [ADR-014](decisions/adr-014-expression-engine-core.md)（扩展）
- **P1-4 决策完成**：算子黄金数据集 → [ADR-019](decisions/adr-019-testing-strategy.md)（扩展）
- **P1-5 决策完成**：发布生命周期协议 → [ADR-034](decisions/adr-034-publication-lifecycle.md)
- **P1-6 决策完成**：失效传播级联协议 → [ADR-035](decisions/adr-035-invalidation-cascade.md)
- **P1-7 决策完成**：DQ 门禁设计 → [ADR-036](decisions/adr-036-quality-gates.md)
- **P1-8 决策完成**：性能 SLO 定义 → [ADR-037](decisions/adr-037-performance-slo.md)
- **C-2 临时决策**：热层 TTL → 可配置，默认 分钟 5 日 / 日线 30 日（压测后复审）
- **C-4 决策完成**：分钟数据进 Parquet → 保留 30 日标准化 bar_1m，限最小必要范围

### 2026-03-13

- **P2-1 决策完成**：多市场日历框架 → 框架 + CN 实现，US/HK 预留接口
- **P2-2 决策完成**：Rolling State 缓存 → 最小可用，复用 Kvrocks，混合失效机制
- **P2-3 决策完成**：热冷数据一致性校验 → 只检测不修复，分区级抽样 + 告警分级
