# 统一派生查询与物化架构设计决策（阶段性归档）

**状态**: 🚧 进行中
**创建日期**: 2026-03-11
**适用范围**: unified-feature-factor-engine / derived query / feature & factor 一体化
**文档目标**: 记录本轮已确认的设计决策、与当前仓库实现的对齐判断、以及后续仍需继续讨论的未决议题。

---

## 1. 背景

本轮讨论的目标不是重新发明一套全新架构，而是在以下基础上继续收敛：

- 已存在的 `docs/design/unified-feature-factor-engine/` 主设计与 ADR
- 2026-03-10 后修订的 QuestDB / 微批 / 在线边界方案
- 当前仓库 `packages/data/` 与 `apps/port/` 的真实实现方式

本轮讨论后，已经形成一个较清晰的方向：

> Ditto 的 unified-feature-factor-engine 长期应被定义为
> **统一语义 + 微批物化 + 冷热分层 + 在线访问边界控制** 的派生数据引擎。

这一定义明显区别于“纯流式状态引擎”或“单一存储统一执行器”。

---

## 2. 当前方案的事实基础（本轮对齐结果）

本轮讨论后，明确以下文档应作为**当前较新的事实基础**：

- `docs/design/unified-feature-factor-engine/revision-questdb-hot-layer.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-011-streaming-mode.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-028-questdb-hot-tables.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-029-intraday-postmarket-paths.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-030-online-data-access-boundary.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-031-state-snapshot-abi.md`

### 2.1 已确认的当前主线

1. **不是纯流式处理**
   盘中路径以**微批量处理模式**为主，而非逐事件流式算子图。

2. **QuestDB 不是状态引擎**
   QuestDB 的主职责是：
   - 热序列存储
   - 时间范围查询
   - 物化视图 / 聚合视图
   - 盘中热点因子热层

3. **Kvrocks 不是历史存储**
   Kvrocks 的主职责是：
   - latest snapshot
   - 状态快照
   - checkpoint / invalidation / lock
   - 队列与轻量状态

4. **Parquet 仍是长期真相层**
   研究、回测、历史回放、审计对拍、重算基准均以 Parquet 为基准。

5. **Polars 是统一语义与主计算引擎**
   QuestDB 只作为可下推后端与热层加速层，不是语义源头。

---

## 3. 本轮已确认的设计决策

## 3.1 总体定位

### 决策 D1：统一引擎的长期定位

**结论**：统一引擎应被定位为**派生数据物化与查询编排系统**，而不是单一“因子实时计算引擎”。

**含义**：

- 上层统一：表达式语义、版本、治理、物化契约
- 下层分层：研究、生产物化、在线服务
- 目标不是“所有路径都走一套执行器”，而是“统一语义 + 差异化物理执行”

### 决策 D2：不采用纯流式状态引擎路线

**结论**：不引入独立 ReactiveStateEngine / CrossSectionalEngine。

**理由**：

- 与当前修订后的 `ADR-011` 一致
- 微批更符合分钟级主战场
- 复用 Polars 统一语义更利于研究生产一致性

---

## 3.2 存储与执行边界

### 决策 D3：冷热分层职责固定

| 组件 | 定位 | 负责 | 不负责 |
|------|------|------|--------|
| `Parquet` | 唯一真相层 | 长期历史、研究、回放、重算基准 | 盘中低延迟服务 |
| `QuestDB` | 热序列 / MV / 范围查询层 | 热表、MV、时间窗口查询、热点分钟因子 | 状态快照、长期真相 |
| `Kvrocks` | latest / snapshot / coordination 层 | 最新值、状态快照、checkpoint、invalidation、lock | 长期历史、复杂聚合 |
| `SQLite` | catalog / run / lineage / publication 层 | 元数据、运行记录、发布状态、配置 | 热查询 |
| `Polars` | 统一语义与主计算引擎 | 编译后执行、复杂计算、最终裁决 | 作为持久化层 |
| `DuckDB` | ADHOC / 审计工具 | 联查、临时分析、对拍 | 常驻服务、在线查询主链路 |

### 决策 D4：QuestDB + Polars 的最佳边界

**QuestDB 适合**：

- 热基础表
- 稳定重复的时间聚合
- `SAMPLE BY` / MV
- bounded time-range 查询

**Polars 保留**：

- 截面算子
- 复杂 PIT
- 多时间语义拼接
- 复杂 enrichment
- 最终结果裁决

### 决策 D5：Pushdown 升级为“分段执行计划”

不再只按“单算子能否下推”思考，而应按：

`QuestDB 预取 / 预聚合段 -> Polars 精算段 -> 写回段`

进行分段执行规划。

---

## 3.3 统一模型：feature 与 factor 同期支持

### 决策 D6：本期不是 factor-only，feature 也必须一等支持

**结论**：本期统一引擎范围明确包含：

- `feature`
- `factor`

而不是先只做 factor，再兼容 feature。

### 决策 D7：根抽象升级为 `Derived`

不再以 `FactorSpec / FeatureSpec` 作为系统根对象，而应引入统一底座：

- `DerivedSpec`
- `role`
- `materialization_profile`

### 决策 D8：采用 `role + materialization_profile` 双轴模型

#### role（语义轴）

本轮已确认当前至少需要：

- `feature`
- `factor`

长期预留：

- `signal`
- `label`

#### materialization_profile（物化轴）

四种 profile 共享给 feature 与 factor：

- `SERIES`
- `STATE`
- `DERIVE`
- `OFFLINE`

### 决策 D9：feature 与 factor 共享底座，但不共享评估语义

共享：

- 编译
- 物化
- backfill
- publish
- lineage
- query routing

分离：

- `FeatureProfile`
  - `serving_enabled`
  - `training_enabled`
  - `parity_policy`
  - `null_policy`
  - `consumer_group`
- `FactorProfile`
  - `normalization_policy`
  - `neutralization_policy`
  - `exposure_domain`
  - `evaluation_policy`

---

## 3.4 查询边界与服务形态

### 决策 D10：查询边界按场景分为三类

已确认三种查询语义：

- `Serving`
- `Research`
- `MixedSource`

其职责区分如下：

| 查询边界 | 目标 | 允许数据源 | 关键约束 |
|---------|------|-----------|----------|
| `Serving` | 盘中/在线主链路 | QuestDB + Kvrocks | 不默认读 Parquet |
| `Research` | 研究/回测/训练 | Parquet + catalog snapshot | 可复现、支持版本/时间旅行 |
| `MixedSource` | 对拍/核验/排障 | Parquet + QuestDB + Kvrocks + catalog/run metadata | 明确跨源，不进入在线主链路 |

### 决策 D11：`MixedSource` 命名确认

相比 `Audit`，当前更认可 `MixedSource` 语义。

**暂定名称**：

- `MixedSourceDerivedQueryService`

> 备注：如果最终该能力上提到应用层作为 facade，名称后缀可能进一步统一为 `Facade`。

### 决策 D12：场景化查询能力适合在 Port 做 facade

本轮已确认：

- **合适**将 `Serving / Research / MixedSource` 作为 `port` 层应用侧 facade
- **不合适**把底层数据源路由与查询实现整体搬到 `port`

因此推荐分层为：

#### DataHub 负责

- source routing
- version / publication / as_of / source_scope
- 读 QuestDB / Kvrocks / Parquet / SQLite
- 形成统一的 derived query 实现层

#### Port 负责

- 用例 facade
- 参数整形
- 权限控制
- 默认策略
- 返回模型转换
- 面向 API/CLI/jobs 的应用侧场景封装

---

## 3.5 与当前 DataHub 实现的整合判断

### 决策 D13：可以整合到现有 DataHub 服务体系，但不能硬塞进基础数据服务

#### 当前实现的特点

当前仓库中：

- `MarketService` 已形成成熟模式：`Query DTO + Service + DataFrame`
- `FeatureService` / `FactorService` 目前仍是离线 Parquet + metadata 的轻包装
- `datahub` 当前整体仍偏同步风格

#### 推荐整合方式

1. **基础数据服务保持不变**
   - `MarketService`
   - `FundamentalService`
   - `CapitalService`
   - `MacroService`

2. **新增 derived 查询实现层**
   - `DerivedQueryService` 或 `services/derived/**`

3. **Port 层新增 facade**
   - `ServingDerivedQueryFacade`
   - `ResearchDerivedQueryFacade`
   - `MixedSourceDerivedQueryFacade`

4. **现有 `FeatureService` / `FactorService` 逐步退化为 facade 或兼容门面**

### 决策 D14：DataHub 边界上的返回类型优先保持 `pl.DataFrame`

当前 `datahub` service 风格已基本固定为：

- 输入使用 Query DTO
- 输出为 `pl.DataFrame`

因此本轮倾向：

- DataHub 查询实现层继续优先返回 `pl.DataFrame`
- Port facade 再做 DTO / dict / response model 转换

---

## 4. 当前文档中已发现但尚未统一的冲突口径

这些冲突**不改变大方向**，但会影响后续实现一致性，需在后续文档修订中统一。

### 4.1 `DERIVE` 的执行定位冲突

当前存在两种口径：

- 一处仍写成 `DERIVE -> DuckDB ADHOC`
- 较新的修订方案倾向 `DERIVE -> QuestDB 热基础数据 + Polars 现算`

**当前倾向**：以后者为准。

### 4.2 热层 TTL 口径冲突

当前存在两种口径：

- 主设计中的“分钟 5 日 / 日线 30 日”
- `ADR-028` 中 `120 / 180 / 365` 天类 TTL

**结论**：尚未最终统一，需要结合真实业务负载、成本与分钟数据是否长期保留进一步确认。

### 4.3 状态 key 抽象层级不一致

当前存在：

- 较泛化的 `derived:state:*`
- 更具体的 `state:feature:{factor_id}:{instrument_id}`

**结论**：需要后续统一 state namespace 与 derived namespace 的抽象边界。

### 4.4 分钟数据是否进入 Parquet 的口径仍需再钉死

有文档倾向：

- 分钟数据不在 Parquet 长期保留

但该结论对“研究生产一体”影响很大，仍需单独继续讨论并定案。

---

## 5. 本期建议落地范围（基于当前讨论）

本期建议聚焦到以下最小但完整的落地范围：

### 5.1 模型层

- 引入 `DerivedSpec`
- 引入 `role`
- 引入 `materialization_profile`
- Feature / Factor 同期纳入

### 5.2 查询层

- 明确三类查询语义：
  - `Serving`
  - `Research`
  - `MixedSource`
- Port 侧以 facade 形式承接场景差异
- DataHub 侧承接底层查询实现

### 5.3 目录与接口

- 不推翻现有基础数据服务
- 以新增 `derived` 子域的方式接入
- 现有 `FeatureService` / `FactorService` 允许保留为兼容 facade

### 5.4 文档层

- 需要统一 `main-design` 与新增 ADR 的冲突口径
- 需要把本轮结论沉淀到后续正式 ADR / 主设计修订中

---

## 6. 本轮尚未深入讨论、未完善的设计部分

以下内容已识别为后续必须继续讨论的议题。

## 6.1 统一语义模型仍未完全落定

- `DerivedSpec` 的完整字段清单
- `entity_keys / time_keys / grain / calendar / timezone`
- `FeatureProfile / FactorProfile` 的最终字段边界
- 是否本期就把 `signal / label` 进入统一 catalog 设计

## 6.2 查询实现层仍未完全细化

- DataHub 实现层到底是一组 service，还是一个 `DerivedQueryService + query_mode`
- Port facade 与 DataHub implementation 的精确接口关系
- `MixedSource` 的输出模型是否需要差异解释结构（diff report / trace report）

## 6.3 DataHub 风格一致性仍未定案

- 新 derived 查询实现是否保持同步风格
- 是否允许 `Serving` 查询走异步接口
- DataHub 层是否一律返回 `pl.DataFrame`
- Port facade 是否负责 dict / API model 转换

## 6.4 物化与发布控制面仍未细化到底

- `register -> validate -> materialize -> publish` 的详细协议
- publication 与 version / primary / online 的关系
- feature 与 factor 的发布门禁是否完全共享
- `certify` 阶段是否需要单独建模

## 6.5 DQ / Benchmark / Publish Gate 仍未细化阈值

- `feature` 的 parity gate
- `factor` 的评估 gate
- `SERIES / STATE / DERIVE / OFFLINE` 的 profile-specific gate
- benchmark 指标、阈值、环境差异

## 6.6 回补 / 更正 / invalidation 仍需协议化

- correction 与故障恢复的边界
- invalidation event 的完整结构
- `STATE` 类重建锚点与顺推协议
- `SERIES` 类局部修复策略

## 6.7 存储策略仍有关键未决项

- 分钟数据是否进入 Parquet
- QuestDB 热层 TTL 最终口径
- `STATE` 是否需要可选 QuestDB 上下文序列
- Kvrocks snapshot 与 latest 的 key/model 拆分程度

## 6.8 当前代码迁移路径仍未细化

- `FeatureService` / `FactorService` 如何平滑迁移为 facade
- 新的 `derived` provider 如何落到 `apps/port/registry/datahub/`
- tests 如何从当前离线 reader mock 迁移到新分层

---

## 7. 建议的后续讨论顺序

为了减少反复重写文档和实现，建议下一轮按以下顺序继续：

1. **先钉死 `DerivedSpec` / `role profile` / `materialization_profile` 的字段模型**
2. **再钉死 DataHub implementation 与 Port facade 的边界**
3. **再细化三类 query facade 的接口与返回模型**
4. **再补 publish / version / gate / invalidation 协议**
5. **最后统一 TTL、分钟数据保留、状态 key 等运维与存储参数**

---

## 8. 后续需要修订或新增的文档（建议）

### 8.1 需要修订

- `docs/design/unified-feature-factor-engine/main-design.md`
- `docs/design/unified-feature-factor-engine/README.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-029-intraday-postmarket-paths.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-030-online-data-access-boundary.md`

### 8.2 可能需要新增 / 扩展 ADR

- `DerivedSpec / role + materialization_profile` 建模 ADR
- `DataHub derived query implementation + Port facade` 边界 ADR
- `feature + factor` 同期纳入 unified engine 的 scope ADR

---

## 8.3 后续 ADR Backlog 拆分（建议）

本节把后续工作拆成三类：

1. **必须新建 ADR**：跨层、长期、不可逆的关键决策
2. **扩展既有 ADR**：已有 ADR 已覆盖主问题，只需补充新结论
3. **非 ADR 工作项**：更适合落到主设计、实施计划或代码迁移任务

### A. 必须新建 ADR

#### ADR-032：Unified Derived Semantic Model

**目标**：定义统一的 `DerivedSpec` 根模型与 `role + materialization_profile` 双轴抽象。
**优先级**：P0
**依赖**：无
**主要回答的问题**：

- `DerivedSpec` 的完整字段是什么
- `feature` 与 `factor` 如何在同一底座下一等支持
- `FeatureProfile` 与 `FactorProfile` 的边界如何划分
- `signal` / `label` 是本期纳入，还是只做保留位

**输出范围**：

- `DerivedSpec`
- `role`
- `materialization_profile`
- `FeatureProfile`
- `FactorProfile`

**为什么必须单独 ADR**：

- 这是全局根抽象
- 会影响 engine、catalog、query、publish、storage、测试模型
- 一旦进入实现，返工成本极高

#### ADR-033：Derived Query Architecture and Layer Boundary

**目标**：定义 `DataHub implementation + Port facade` 的查询分层。
**优先级**：P0
**依赖**：ADR-032
**主要回答的问题**：

- `Serving / Research / MixedSource` 是服务实现还是 facade
- `datahub` 与 `port` 各自负责什么
- DataHub 是否统一返回 `pl.DataFrame`
- Query DTO、source routing、publication filtering 放在哪一层
- 同步/异步风格如何统一

**输出范围**：

- `ServingDerivedQueryFacade`
- `ResearchDerivedQueryFacade`
- `MixedSourceDerivedQueryFacade`
- DataHub derived query implementation 的职责边界

**为什么必须单独 ADR**：

- 涉及 Port / DataHub 边界
- 直接受 Import Linter 约束
- 会决定 API/CLI/jobs 如何接入

#### ADR-034：Derived Publication Lifecycle and Version Contract

**目标**：统一 feature/factor 的发布、认证、版本和可见性模型。
**优先级**：P1
**依赖**：ADR-032
**主要回答的问题**：

- `register -> validate -> materialize -> certify -> publish` 是否成立
- `status / online / primary / published_at / rollback_from` 如何协同
- 哪些变更必须升版本
- publication state 与 materialization state 如何分离

**输出范围**：

- unified publication state machine
- version / primary / online contract
- certify gate 与 publish gate

**为什么必须单独 ADR**：

- 这是控制面核心协议
- 影响 catalog、调度、查询默认行为与回滚策略

#### ADR-035：Derived Rebuild, Invalidation, and Correction Protocol

**目标**：把 backfill / invalidation / correction / state rebuild 统一成正式协议。
**优先级**：P1
**依赖**：ADR-032、ADR-034
**主要回答的问题**：

- `append / correction / spec_change` 三类触发的统一事件模型
- `STATE` 的重建锚点与顺推机制
- correction 与系统故障恢复如何区分
- `SERIES / STATE / DERIVE / OFFLINE` 在重物化上的差异

**输出范围**：

- invalidation event schema
- rebuild policy
- correction propagation contract

**为什么必须单独 ADR**：

- 影响增量正确性
- 是研究生产一致性和可恢复性的关键

#### ADR-036：Derived Quality, Benchmark, and Certification Gates

**目标**：定义按 `role + profile` 分层的质量门禁与性能门禁。
**优先级**：P1
**依赖**：ADR-032、ADR-034
**主要回答的问题**：

- `feature` 的 parity / freshness / null gate
- `factor` 的 evaluation / exposure / quality gate
- `SERIES / STATE / DERIVE / OFFLINE` 的 benchmark gate
- certification 是否单独建模

**输出范围**：

- contract gate
- quality gate
- benchmark gate
- certification contract

**为什么必须单独 ADR**：

- 直接决定是否能安全上线
- 没有这一层，publish 就没有可执行门槛

#### ADR-037：Hot/Cold Retention and Minute Data Policy

**目标**：钉死分钟数据保留策略、QuestDB TTL、Kvrocks 状态保留范围。
**优先级**：P2
**依赖**：ADR-032、ADR-035
**主要回答的问题**：

- 分钟数据是否进入 Parquet
- QuestDB 热层 TTL 最终按什么口径
- `STATE` 是否需要可选上下文热序列
- `derived:state:*` 与 `state:feature:*` namespace 如何统一

**输出范围**：

- retention policy
- TTL policy
- state namespace policy

**为什么必须单独 ADR**：

- 存储成本、研究可复现性、恢复策略都受此影响
- 但它相对更后置，可以在模型/边界收敛后再决策

### B. 扩展既有 ADR（不建议再单开）

#### 扩展 ADR-029：盘中/盘后路径

**建议补充内容**：

- `materialization_profile` 从 factor-only 扩展到 feature + factor
- 四类 profile 不再只被视作“因子服务模式”，而是统一物化契约
- `DERIVE` 路径统一到“QuestDB 热基础数据 + Polars 现算”

#### 扩展 ADR-030：在线访问边界

**建议补充内容**：

- `Serving / Research / MixedSource` 三类查询边界
- online 主链路默认不允许跨级回退到 Parquet
- Port facade / DataHub implementation 的接口隔离方式

#### 扩展 ADR-031：State Snapshot ABI

**建议补充内容**：

- `STATE` 从 factor-only 扩展到 derived 视角
- 说明 snapshot ABI 与 `role`、`profile` 的关系
- 明确 state namespace 统一策略

#### 扩展 ADR-024：版本管理

**建议补充内容**：

- 不再只覆盖 factor
- 升级为 derived publication/version contract 的既有历史依据
- 但最终正式协议应由 ADR-034 主导

### C. 非 ADR 工作项（不建议上升到 ADR）

以下内容重要，但更适合落到主设计文档、实施计划或迁移计划：

#### 文档统一

- 回写 `main-design.md`
- 统一 `DERIVE`、TTL、state namespace 等冲突口径
- 更新 `README.md` ADR 索引

#### 代码迁移计划

- `FeatureService` / `FactorService` 如何平滑退化为 facade
- DataHub `derived` 子域目录如何落地
- Port registry 如何增加 `derived` provider / facade provider
- tests 如何逐层迁移

#### 实施计划

- 任务拆分
- TDD 路径
- 文件清单
- 验证顺序

这些更适合进入 implementation plan，而不是 ADR。

### D. 推荐编写顺序

建议按以下顺序推进：

1. `ADR-032 Unified Derived Semantic Model`
2. `ADR-033 Derived Query Architecture and Layer Boundary`
3. `ADR-034 Derived Publication Lifecycle and Version Contract`
4. `ADR-035 Derived Rebuild, Invalidation, and Correction Protocol`
5. `ADR-036 Derived Quality, Benchmark, and Certification Gates`
6. `ADR-037 Hot/Cold Retention and Minute Data Policy`

### E. 推荐分阶段产出

#### Phase 1：先锁住根抽象与查询分层

- ADR-032
- ADR-033

#### Phase 2：锁住控制面协议

- ADR-034
- ADR-035
- ADR-036

#### Phase 3：锁住运维与存储策略

- ADR-037
- 回写 ADR-029 / ADR-030 / ADR-031

### F. 验收标准（ADR 层面）

一个 ADR 可以认为“可进入实现”，至少应满足：

- 明确回答“为什么这样设计，而不是另一个方案”
- 明确受影响层级：Core / DataHub / Port / Infra
- 明确新旧路径如何兼容或迁移
- 明确至少一个反例：什么不应该放进这个 ADR
- 明确和既有 ADR 的关系：替代、扩展或引用

---

## 9. 本轮阶段性结论

本轮最重要的结果不是“又多了几个 service 名字”，而是把以下几件事收拢了：

1. **引擎定位收拢**
   从“流式状态引擎想象”收拢到
   `统一语义 + 微批物化 + 冷热分层 + 在线边界`。

2. **作用域收拢**
   明确本期必须支持 `feature + factor`，而不是 factor-only。

3. **模型收拢**
   明确应走 `Derived + role + materialization_profile` 路线。

4. **查询边界收拢**
   明确按 `Serving / Research / MixedSource` 三类场景分层。

5. **分层收拢**
   明确场景化 facade 适合放到 `port`，底层查询实现仍归 `datahub`。

---

## 10. 更新记录

### 2026-03-11

- 归档本轮关于 unified-feature-factor-engine / derived query 的阶段性设计决策
- 记录 feature + factor 同期支持、query 三分、Port facade / DataHub implementation 分层等已确认方向
- 汇总仍未讨论完善的剩余议题，供下一轮继续收敛
- 新增后续 ADR backlog 拆分，区分必须新建 ADR、扩展既有 ADR 与非 ADR 工作项
