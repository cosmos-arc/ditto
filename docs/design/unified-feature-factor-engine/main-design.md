# Ditto Unified Derived Engine 完整设计文档

## 0. 文档状态

- **状态**: 当前真相源
- **最后更新**: 2026-03-18
- **适用范围**: `packages/core` + `packages/data` + `apps/port`
- **定位**: 这是 unified-feature-factor-engine 的唯一完整设计入口；阅读本文件应能理解当前架构、语义、边界、控制面与剩余延期项。

### 0.1 当前真相源

当前应以以下文档作为有效事实基础：

1. `docs/design/unified-feature-factor-engine/main-design.md`
2. `docs/design/unified-feature-factor-engine/README.md`
3. `docs/design/unified-feature-factor-engine/decisions/00-index.md`
4. `docs/plans/2026-03-18-unified-engine-convergence-plan.md`
5. `docs/plans/unified-feature-factor-engine-remaining-tasks.md`

如与历史评审、历史优化文档、已归档计划冲突，以上述文档与当前实现为准。

### 0.2 文档职责

- **本文件**: 统一主设计，回答“系统现在到底怎么设计”
- **README**: 阅读顺序、状态说明、归档导航
- **ADR**: 不可轻易更改的架构决策与专题细化
- **Plans**: 某一阶段的实施与收敛记录
- **Archive**: 已退出当前真相源的历史设计、评审、优化材料

---

## 1. 设计目标与非目标

### 1.1 目标

1. 统一 feature、factor 与其他派生实体的语义模型、查询、物化、发布与研究数据集链路。
2. 使用 `Expression DSL -> Pratt Parser -> Analyzer -> Codegen -> Polars` 建立统一计算主线。
3. 让全量、增量、修正重算、级联失效与发布安全共享同一套控制面。
4. 保持 Ditto 分层边界清晰：`Port -> Core -> DataHub -> Infra`。
5. 明确“当前已支持 / 预留 / 暂缓”的边界，避免把设计预留误读成已落地能力。

### 1.2 非目标

1. 不在当前阶段引入 Spark/Flink/K8s 等分布式计算框架。
2. 不引入 Iceberg/Delta/Hudi 等 lakehouse 表格式事务层。
3. 不在当前阶段完成 `grain="1m"` 全链路、复合键、多市场日历、多时区运行。
4. 不让在线查询默认回落到 Parquet 真相层。
5. 不把研究数据集构建混入 serving query 接口。

---

## 2. 当前支持矩阵

### 2.1 已落地能力

| 能力 | 当前状态 | 说明 |
|------|------|------|
| 根语义模型 | 已落地 | 统一使用 `DerivedSpec`，不再以 `FeatureSpec / FactorSpec` 作为系统根对象 |
| 表达式编译链路 | 已落地 | Pratt parser、语义分析、Polars codegen、编译诊断已成型 |
| 编译缓存 | 已落地 | `L1` 内存 + `L2` SQLite |
| 物化主链路 | 已落地 | compile -> plan -> input -> compute -> artifact -> catalog |
| 事务边界 | 已落地 | 多步写通过 UoW / Service 边界收口 |
| 查询门面 | 已落地 | `get_latest / get_series / compare_sources` |
| 发布生命周期 | 已落地 | `materialize / shadow_publish / certify / promote / rollback / deprecate` |
| 发布安全 | 已落地 | minimal DQ、compatibility manifest、shadow diff、certification pack |
| Research 数据集 | 已落地 | `SpineSpec / ResearchDatasetSpec / DatasetSnapshot` |
| 失效级联协议 | 已落地 | 旧协议已移除，仅保留 cascade protocol |
| 文档收敛 | 进行中 | 本次收敛将主入口统一到本文件与 README |

### 2.2 明确保留但未激活

| 能力 | 当前状态 | 处理方式 |
|------|------|------|
| `grain="1m"` | 预留未实现 | 保留类型与守卫，未进入 v1 合同 |
| 复合键 `entity_keys` | 预留未实现 | 允许模型表达，校验阶段显式报错 |
| `SIGNAL / LABEL` role | 预留未启用 | 保留枚举，不作为当前交付范围 |
| `TimeSpec / ExecutionPolicy` 行为迁移 | 预留 seam | 保留字段与抽象，v2 再激活 |
| `STATE` 物理热路径 | 依赖基础设施 | 设计保留，未完成 Kvrocks 正式接线 |

### 2.3 暂缓项

| 项目 | 状态 | 重启条件 |
|------|------|---------|
| ADR-011 盘中微批量模式 | 暂缓 | QuestDB + Kvrocks 基础设施就绪 |
| ADR-023 灾备恢复 | 暂缓 | 上游断点续传与恢复脚本边界明确 |
| 多市场 / 多日历 | 暂缓 | 有真实跨市场需求时再扩类型系统与运行面 |
| Phase 6 Hardening | 延后 | 先处理剩余小型债务与运营化入口 |

---

## 3. 四条铁律

### 3.1 Parquet 是长期真相源

- Parquet / artifact 是历史重放、研究构建、回补与审计的最终依据。
- Hot layer 只负责在线加速，不承担长期持久化真相职责。
- 热层损坏后，应通过上游重放或 Parquet 重建，而不是反向把热层当真相源。

### 3.2 热层只保留必要 lookback

- 在线热层不是全量镜像，而是面向 serving 的最小必要窗口。
- TTL 只负责回收，不负责发布正确性、失效传播或版本治理。
- 在线默认不因热层 miss 自动降级到 Parquet；研究与审计路径必须显式进入离线语义。

### 3.3 状态与分析分离

- **控制面状态**: version、run、coverage、watermark、publication safety、research snapshot。
- **在线查询**: latest / serving projection。
- **研究构建**: artifact / Parquet + PIT + snapshot contract。
- 状态变更影响增量边界和默认路由，但不重写历史 artifact 真相。

### 3.4 统一语义、分层执行

- 上层统一使用 `DerivedSpec`、统一 DSL、统一 publication / research / query contract。
- 底层按 profile 和运行场景选择物理执行路径。
- 统一语义不意味着所有 profile 当前都已全量激活；未实现能力必须显式标记。

---

## 4. 架构总览

### 4.1 分层职责

#### Port

- 负责 facade、orchestration、flow、调度入口。
- 不直接访问底层 store，不直接做文件 I/O。
- 当前关键入口：
  - `apps/port/src/ditto_port/services/derived/query_facade.py`
  - `apps/port/src/ditto_port/services/derived/materialization_orchestrator.py`
  - `apps/port/src/ditto_port/services/derived/publication.py`
  - `apps/port/src/ditto_port/services/derived/research.py`

#### Core

- 负责语义模型、编译链路、执行规划、研究对象、发布安全领域模型。
- 保持纯计算、纯规则、低 I/O。
- 当前关键入口：
  - `packages/core/src/ditto_core/engine/specs.py`
  - `packages/core/src/ditto_core/engine/expression/*`
  - `packages/core/src/ditto_core/engine/materialization/*`
  - `packages/core/src/ditto_core/engine/research.py`
  - `packages/core/src/ditto_core/engine/publication_safety.py`

#### DataHub

- 负责 artifact 持久化、catalog、runtime metadata、research artifact、publication safety record。
- 封装文件 I/O、SQLite runtime、后续热层适配。
- 当前关键入口：
  - `packages/data/src/ditto_data/services/derived_catalog_service.py`
  - `packages/data/src/ditto_data/services/derived/artifact_reader.py`
  - `packages/data/src/ditto_data/services/derived/artifact_persistence_service.py`
  - `packages/data/src/ditto_data/services/research_artifact_service.py`

#### Infra

- 提供日志、锁、可观测性、测试辅助、底层通用原语。

### 4.2 端到端主链路

```text
DerivedSpec
  -> compile (lexer / parser / analyzer / codegen)
  -> plan (full / incremental / invalidation-aware)
  -> load input
  -> compute frame
  -> persist artifact + metadata + catalog
  -> minimal DQ / manifest / publication safety
  -> query / research / publish / compare / rollback
```

### 4.3 当前数据流分叉

```text
source domains
  -> materialization orchestrator
     -> artifact truth layer
     -> catalog/runtime metadata
     -> publication safety records

artifact truth layer
  -> offline series query
  -> research dataset build
  -> shadow compare / audit

published primary version
  -> serving latest query
  -> default research version resolution
```

---

## 5. 统一语义模型

### 5.1 根对象：`DerivedSpec`

当前系统根对象是 `DerivedSpec`，而不是 `FeatureSpec / FactorSpec`。

核心字段包括：

- `id`
- `version`
- `role`
- `materialization_profile`
- `expression`
- `entity_keys`
- `grain`
- `time_keys`
- `calendar`
- `description`
- `time_spec`
- `operator_versions`
- `universe_id`

### 5.2 当前合同边界

| 维度 | 当前合同 |
|------|---------|
| `role` | 当前主路径只实际支持 `feature / factor` |
| `entity_keys` | 单键，仅 `instrument_id` |
| `grain` | 仅 `1d` |
| `calendar` | 仅 `cn_stock` |
| `timezone` | 由 `calendar` 推导，不单独外部输入 |
| `time_keys` | 为空时由 `grain` 推导 |

### 5.3 `TimeSpec` 与 `ExecutionPolicy`

当前保留但不把它们当作 fully-activated v1 contract：

- `TimeSpec` 用于承接 `event_time / availability_time` 语义 seam
- `ExecutionPolicy` 用于未来更细的 PIT / normalization 策略

它们的存在是为了避免未来再改根模型，但**不意味着当前已经开放所有相关行为**。

### 5.4 研究契约与单体 DerivedSpec 分层

以下对象不并入 `DerivedSpec`：

- `SpineSpec`
- `ResearchDatasetSpec`
- `DatasetSnapshot`

原因是它们属于“多输入数据集构建契约”，不是“单个派生定义契约”。

---

## 6. 生命周期与版本语义

### 6.1 持久化状态

当前版本状态机以实现与现行 contract 为准：

```text
DRAFT -> MATERIALIZED -> PUBLISHED -> DEPRECATED -> ARCHIVED
```

### 6.2 重要澄清

1. `REGISTERED` 在设计历史上曾作为“validate 之后可物化”的术语出现，但当前不作为持久化状态枚举。
2. `MATERIALIZED != PUBLISHED`。
3. `active_version` 的设计语义是“当前在线服务默认版本”；它应只在发布后更新，而不是每次 materialize 后更新。
4. `primary=true` 必须同时满足 `online=true` 与 `status=PUBLISHED`。

### 6.3 发布动作

- `materialize`: 产生 artifact 与运行元数据
- `shadow_publish`: 把 candidate 送入 shadow 验证通道，不切 primary
- `certify`: 汇总 minimal DQ、shadow diff、compatibility manifest 与 certification pack
- `promote`: 原子切换为 `PUBLISHED` primary
- `rollback_primary`: 只移动 primary 指针
- `deprecate`: 版本退出推荐路径，但保留历史与回滚价值

---

## 7. 表达式与执行模型

### 7.1 编译管线

```text
Expression
  -> Lexer
  -> Pratt Parser
  -> AST
  -> Semantic Analyzer
  -> Polars Codegen
  -> pl.Expr
```

### 7.2 Analyzer 负责的核心推导

- 依赖提取
- 作用域判定（TS / CS / MIXED）
- `lookback`
- `requires_full_day`
- 排序要求

### 7.3 TS / CS 语义

- TS 算子扩大回看窗口
- CS 算子不扩大 lookback，但会传播 `requires_full_day=True`
- 嵌套规则通过编译期分析传播到执行规划

### 7.4 增量与失效重算

执行规划统一使用：

- `request_start / request_end`
- `watermark`
- `lookback`
- `earliest_pending_invalidation`

对 CS 因子，单个标的变化可以放大为整日全截面重算；这条语义必须在 planner 和应用路径同时生效。

### 7.5 编译缓存

- `L1`: 进程内命中，避免重复编译
- `L2`: SQLite 持久化缓存，避免重复 tokenize / parse / analyze

缓存属于性能优化层，不改变语义判定结果。

---

## 8. 物化架构

### 8.1 物化统一入口

Port 层通过 `DerivedMaterializationOrchestrator` 执行统一物化。

当前主流程：

1. 读取 spec/version
2. 编译表达式
3. 规划执行窗口
4. 通过 input provider 取数
5. 生成 `value` 列并做必要扩面
6. 写 artifact / metadata / run / partition / state
7. 生成 minimal DQ 与 publication safety 记录

### 8.2 Profile 语义

当前 profile 仍保留四类：

- `SERIES`
- `STATE`
- `DERIVE`
- `OFFLINE`

但实现成熟度并不相同：

- `DERIVE` 已用于上游 join 与派生计算路径
- `STATE` 的完整热态物理落点仍依赖后续基础设施
- `OFFLINE` 更偏研究/离线消费

### 8.3 事务边界

当前设计要求：

- Port 负责编排
- DataHub Service 负责 durable write 与 catalog mutation
- 多步写必须在 UoW / 事务边界内提交

这部分已经在 2026-03-18 convergence 中明确收口，不能再回退到“Port 直接调 writer + 每步独立 commit”的旧模式。

---

## 9. 存储与控制面

### 9.1 Artifact-first

当前主路径采用 artifact-first：

- durable artifact 是离线真相层
- catalog 记录 spec/version/run/partition/state/publication safety
- serving / hot projection 是后续读优化层

### 9.2 Artifact 路径

当前 canonical artifact 语义为：

```text
derived/artifacts/{profile}/{derived_id}/v{version}/...
```

具体文件布局由 DataHub persistence service 负责，外层文档不再把路径细节硬编码到 Port 逻辑。

### 9.3 控制面记录

当前控制面至少包含：

- spec
- version
- run
- partition
- state
- dependency
- checkpoint
- publication safety records
- research snapshot records

### 9.4 热层与状态命名空间

`ADR-040` 是 retention / state namespace 的唯一设计口径。当前应坚持：

- Hot layer 与 control-plane state 分开
- `ditto:derived:state:*` 统一命名空间
- TTL 不影响发布正确性

---

## 10. 查询架构

### 10.1 单一 facade

Port 层查询入口为 `DerivedQueryFacade`：

- `get_latest()`
- `get_series()`
- `compare_sources()`

### 10.2 用例分工

| 方法 | 场景 | 默认语义 |
|------|------|---------|
| `get_latest` | serving | 优先 serving / hot path |
| `get_series` | offline / research-friendly slice | 走 offline contract |
| `compare_sources` | audit / release safety | 对比 serving 与 offline |

### 10.3 重要边界

1. Research dataset build 不并入 query facade。
2. `RuntimeMode` 是内部 seam，不应成为外部 request contract 的主参数。
3. 在线 miss 是否 fallback，属于运行策略；研究构建必须显式走 dataset contract。

---

## 11. Research 数据集设计

### 11.1 一等对象

Research 链路使用三个对象：

- `SpineSpec`
- `ResearchDatasetSpec`
- `DatasetSnapshot`

### 11.2 时间语义

研究构建必须显式区分：

- `event_time`
- `availability_time`
- `known_at`
- `sample_time`

### 11.3 默认 join 策略

默认使用 `left_preserving_pit`：

1. spine 决定输出样本基数
2. feature / factor / label join 不得静默丢左表行
3. 未命中应体现在 coverage / build report 中

### 11.4 版本绑定原则

研究构建默认应绑定：

- `primary`
- `online`
- `published`

显式 `version_override` 可以覆盖默认版本解析，但不能把“默认 research 绑定未发布版本”当作正常路径。

### 11.5 Snapshot 合同

每次研究构建都必须固化：

- `dataset_spec_version`
- `spine_spec_version`
- `resolved_inputs`
- `source_snapshot_ids`
- `known_at_policy`
- `effective_cutoff`
- `builder_version`
- `manifest_hash`

这保证研究可复现性不再依赖日志猜测。

---

## 12. 失效传播、质量门禁与发布安全

### 12.1 单协议失效传播

当前只保留 cascade invalidation protocol：

- BFS 分层传播
- stale / recomputing 状态语义
- depth guard
- cycle guard

任何旧 repair-only 协议都不应再作为现行设计描述。

### 12.2 质量门禁

`ADR-036` 定义 DQ gate，当前最小闭环是：

- schema / 主键基本完整性
- row count
- value 可计算性
- minimal DQ summary 持久化

更高层认证由 publication certification pack 消费，而不是让 DQ 文档独自承担全部发布判定。

### 12.3 发布安全链路

发布安全当前由以下证据面组成：

- minimal DQ summary
- compatibility manifest
- shadow diff / sample audit
- role/profile certification pack

`publish_ready` 与 `shadow_ready` 是 gate，不是新的持久化状态。

---

## 13. 可观测性与性能

### 13.1 性能口径

`ADR-037` 当前只承诺：

- SLI 维度
- benchmark harness
- CI regression budget

不承诺正式容量与生产 SLO 数值。

### 13.2 观测分层

- compile / materialize / query / shadow_compare workload
- watermark / coverage / freshness
- publication safety evidence
- 运行级失败与降级日志

### 13.3 当前延后项

Phase 6 仍保留以下后续工作：

- benchmark 治理
- runtime SLI 落库
- housekeeping
- release hardening

---

## 14. Deferred 与重启条件

### 14.1 明确 defer

| 项目 | 当前处理 |
|------|---------|
| `grain="1m"` | 保留守卫，不进入 v1 |
| 复合键 | 保留守卫，不进入 v1 |
| 多市场 / 多时区 | 类型系统不开放任意字符串 |
| 完整 hot layer | 等 QuestDB / Kvrocks 真正接通 |
| Planner 日历回退 | 等日历服务集成 |
| DR 恢复脚本闭环 | 等上游能力边界明确 |

### 14.2 重启条件

| ADR | 重启条件 |
|-----|---------|
| ADR-011 | QuestDB + Kvrocks 基础设施就绪 |
| ADR-023 | 上游断点续传与恢复要求确认 |

---

## 15. ADR 使用方式

### 15.1 必读 ADR

以下 ADR 直接定义当前系统骨架：

- ADR-032 统一派生语义模型
- ADR-033 派生查询架构
- ADR-034 发布生命周期
- ADR-035 失效传播级联协议
- ADR-036 DQ 门禁
- ADR-040 Hot/Cold retention 与 state namespace
- ADR-041 Research Dataset / Spine / Availability-Time
- ADR-042 Shadow Publish / Dual-Read Diff
- ADR-043 Certification / Compatibility Manifest

### 15.2 作为专题细化或参考的 ADR

以下内容更接近专题规格、实施附录或参考手册：

- 算子目录
- catalog schema
- testing strategy
- deployment ops
- QuestDB 热表 DDL
- state snapshot ABI
- expression cache persistence

它们仍然保留在 ADR 目录中，但阅读顺序应以本文件与 `00-index.md` 为主，不应要求新读者顺序吞下全部 ADR。

---

## 16. 当前结论

统一引擎当前已经跨过“架构是否成立”的阶段，进入“真相源收敛、剩余延期项显式化、运营与 hardening 收尾”的阶段。

当前最重要的设计约束是：

1. 用 `DerivedSpec` 统一语义，不再回退到 feature/factor 双根模型。
2. 用 artifact-first + control-plane 收口正确性，不再让 Port 直接持久化。
3. 用 `PUBLISHED`、primary、online 统一默认服务与研究版本解析。
4. 用单一主设计入口 + ADR 索引 + archive 分层，避免文档体系继续碎片化。
