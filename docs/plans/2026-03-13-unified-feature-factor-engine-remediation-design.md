# unified-feature-factor-engine 整改设计方案

**状态**: 🚧 执行中（2026-03-13，设计基线已审计、代码实现已启动）
**创建日期**: 2026-03-13
**适用范围**: unified-feature-factor-engine / derived query / feature & factor 一体化 / 设计治理收敛
**文档目标**: 在不推翻现有主干设计的前提下，明确统一引擎下一阶段应保留、补充、移除和重编排的内容，并给出与业界最佳实践对比后的优先级建议。

---

## 0. 当前执行状态（2026-03-13）

### 已完成

1. 文档真相源已完成首轮收敛：
   - README / 主设计 / 历史入口文档已明确主次关系
   - 历史 `issues / optimization / analysis` 文档已退出当前事实基础
2. 已新增并回写以下 ADR：
   - `ADR-040`: Hot/Cold Retention and State Namespace Policy
   - `ADR-041`: Research Dataset, Spine, and Availability-Time Contract
3. 已将 `main-design / ADR-028 / ADR-031 / ADR-032 / ADR-033 / reference/catalog-schema` 回写到 `ADR-040 / ADR-041` 的新口径。
4. 已完成设计基线审计：
   - 当前事实基础 = `README + main-design + ADR-032 ~ ADR-043 + remediation plan`
   - `issues / design-analysis / optimization-* / archive / revision-questdb-hot-layer` 均降级为历史参考，不再作为当前真相源
   - 结论：统一引擎的 **核心设计已完成并达到可实施态**，剩余未封板项均为显式暂缓或 Phase 2/3 扩展议题，不阻塞开发启动

### 本轮已完成

1. `ADR-042`: Shadow Publish 与 Dual-Read Diff 协议
2. `ADR-043`: Role/Profile Certification 与 Compatibility Manifest
3. 发布安全控制面第一批代码实现已落地：
   - `packages/core`: `CompatibilityManifest / ShadowDiffReport / CertificationReport` 等领域模型
   - `packages/datahub`: publication safety runtime records / stores / service
   - `apps/port`: RuntimeProvider 接入 publication safety service
4. 已形成发布安全最小实现计划：
   - [2026-03-13-derived-publication-safety-implementation-plan.md](2026-03-13-derived-publication-safety-implementation-plan.md)
5. 已形成统一引擎分阶段开发执行计划：
   - [2026-03-13-unified-feature-factor-engine-development-execution-plan.md](2026-03-13-unified-feature-factor-engine-development-execution-plan.md)

### 下一阶段待进入

1. 进入统一引擎分阶段开发执行：
   - Phase 1: derived catalog / metadata / run-state 基线
   - Phase 2: query facade / DataHub derived query implementation
   - Phase 3: materialization engine / artifact / invalidation 主链路
   - Phase 4: research dataset / publication orchestration / certification integration
2. 将已完成的 publication safety runtime 基座向上接入真正的 orchestration / dual-read compare / promote 流程
3. 按阶段推进实现与测试，不再继续扩 P0 设计范围

---

## 1. 背景

当前 `docs/design/unified-feature-factor-engine/` 已经形成较完整的主设计、ADR 集合和多轮补充分析文档。问题的重心已经不再是“架构主干是否成立”，而是：

1. **主干已基本成立，但文档状态未完全收敛**。
2. **治理面与控制面仍弱于计算面**。
3. **部分 gap 文档、优化文档和 ADR 的状态描述已经发生漂移**。
4. **研究/训练场景的检索契约仍弱于物化契约**。

因此，下一阶段的重点不应是“继续扩 DSL 或继续增加架构层次”，而应是：

- 固定单一真相源
- 补强高价值治理能力
- 删除或归档误导性文档
- 让设计直接可拆成后续 ADR 与实施计划

---

## 2. 总体判断

### 2.1 本方案不建议推翻重做

统一引擎的核心方向应继续保留：

- `DerivedSpec + role + materialization_profile` 的统一语义模型
- `Pratt Parser -> Analyzer -> Codegen -> Polars` 的编译执行主线
- `Parquet + QuestDB + Kvrocks + SQLite` 的分层存储职责
- `Port Facade + DataHub Implementation` 的查询边界
- `publication lifecycle + DQ gate + operator versioning + compiled cache` 的控制面主线

换句话说，当前设计的问题主要不是“方向错”，而是“控制面不够厚、文档不够收敛、运维口径还不够硬”。

### 2.1.1 设计完成度审计结论

截至 2026-03-13，本设计应视为：

- **核心设计已完成**：`README + main-design + ADR-032 ~ ADR-043` 已能作为统一实现基线
- **可以直接进入开发**：不再需要新增 P0 级设计才能启动主线实现
- **仍存在显式延期项**：如 `1m` 全链路、复合键、多市场扩展、正式 SLO 数值、request-time derived features

这些延期项属于 **后续阶段功能范围**，而不是“当前设计未完成”。

### 2.2 当前最主要的系统性风险

当前最值得优先处理的，不是算子覆盖率，也不是 pushdown 细节，而是以下三类系统性风险：

1. **文档治理失真**
   部分文档仍将已完成 ADR 视为待创建，且存在 ADR 编号漂移。

2. **存储生命周期未彻底统一**
   TTL、分钟数据是否进入 Parquet、state namespace、artifact/serving 生命周期仍存在冲突口径。

3. **研究/训练可复现契约不足**
   当前对物化、发布、查询的设计比对研究数据集构建、point-in-time 左表契约、availability-time 语义更成熟，容易造成“能生产、难研究复现”的结构性短板。

---

## 3. 建议保留的设计主线

### 3.1 统一语义模型

应继续以 `DerivedSpec` 作为系统根抽象，并保留：

- `role`: `feature` / `factor`，长期预留 `signal` / `label`
- `materialization_profile`: `SERIES` / `STATE` / `DERIVE` / `OFFLINE`
- `calendar -> timezone` 推导关系
- `grain -> effective_time_keys` 推导关系

这里不建议回退到 `FeatureSpec / FactorSpec` 分立作为系统根对象，也不建议在当前阶段把复合键、多市场、分钟粒度全量落地为 MVP 必须项。

### 3.2 分层执行与在线边界

以下主线应继续保留，不建议软化：

- `Parquet` 作为长期历史与研究回放真相层
- 在线主链路默认不查 `Parquet`
- `QuestDB` 负责热时序与热查询
- `Kvrocks` 负责 latest / state / coordination
- `SQLite` 负责 catalog / run / publication / lineage
- `Polars` 负责统一语义与最终计算裁决

### 3.3 控制面主线

以下设计已经具备较高价值，应继续保留并进入实施主线：

- 发布状态机
- DQ 门禁
- 算子版本管理
- 编译缓存持久化
- 失效传播协议

这几项决定了统一引擎是否具备长期可维护性，比继续扩更多算子更重要。

---

## 4. 建议优先补充的高价值能力

## 4.1 P0：文档与 ADR 收敛

这一项应作为当前最高优先级整改工作。

### 必须完成的动作

1. 统一 README、主设计、ADR、gap 文档的当前状态。
2. 将过期 gap 文档归档或明确标注 `obsolete`。
3. 修正 ADR 编号漂移，避免后续实施计划继续引用错误编号。

### 当前明确存在的问题

- 有文档仍将 ADR-032 ~ ADR-036 视为待创建
- 部分文档将 `ADR-037` 视为“Retention Policy”，但仓库中现有 `ADR-037` 实际为“性能 SLO”
- `state namespace` 与 TTL 仍存在多口径

### 建议结果

- 保留 `ADR-032 ~ ADR-039` 现有编号
- 新增 `ADR-040: Hot/Cold Retention and State Namespace Policy`
- 由 `ADR-040` 统一以下议题：
  - 分钟数据是否进入 Parquet
  - QuestDB TTL
  - Kvrocks state key 命名
  - artifact 与 serving 的生命周期边界

## 4.2 P0：Research Dataset / Spine 契约

当前统一引擎已经基本建立“如何定义派生数据”和“如何发布派生数据”，但仍缺少“如何生成研究/训练数据集”的系统根契约。

建议新增一组研究侧一等对象：

- `ResearchDatasetSpec`
- `SpineSpec`
- `DatasetSnapshot`

### 建议补充的核心语义

1. **左表/样本表契约**
   - entity keys
   - sample time
   - label horizon
   - point-in-time join policy

2. **数据集快照契约**
   - snapshot id
   - derived versions
   - source snapshot ids
   - generation time
   - reproducibility manifest

3. **研究/训练边界**
   - 训练集、回测集、对拍集的构建方式
   - 与在线 `Serving` 查询的默认隔离

### 价值判断

这是当前最值得新增的一类能力。它能直接补齐：

- point-in-time 正确数据集构建
- 研究/生产一致性
- label 无泄漏
- 回放可复现

## 4.3 P0：availability-time / known-at 语义

当前设计对 `trade_date`、`effective_from/effective_to` 已较清晰，但仍缺：

- 某条数据在系统中“何时可被合法看见”
- 基本面/修订/迟到数据在 join 中如何统一使用
- 盘中物化与研究回放如何共享该语义

建议将该能力补成独立契约，并优先进入研究数据集与查询路径设计。

建议新增字段或模型：

- `event_time`
- `availability_time`
- `known_at_policy`
- `late_arrival_policy`

## 4.4 P1：Shadow Publish + Dual-Read Diff

当前发布生命周期已具备 `register -> materialize -> publish` 主线，但仍缺少真正高安全性的上线前验证能力。

建议补充：

1. `shadow_publish`
2. `dual_read_compare`
3. `trace_report`
4. `diff_report`

### 目标

- 新版本先不切 primary
- 在线读流量或审计任务同时读取新旧版本
- 自动比较 latest / series / coverage / distribution 差异
- 通过后再 promote

### 价值

这类能力的价值高于继续扩一批新算子，因为它决定统一引擎是否“敢上线”。

## 4.5 P1：按 role / profile 分层的认证包

当前 DQ 主要围绕：

- schema
- null-rate
- freshness

这对最小上线门禁足够，但对长期平台化不够。

建议演进为 `role + profile` 分层认证包：

| 维度 | 建议新增门禁 |
|------|--------------|
| `feature` | parity、join coverage、freshness、serving readiness |
| `factor` | exposure stability、coverage、distribution drift、evaluation gate |
| `STATE` | rebuild lag、stale budget、snapshot consistency |
| `DERIVE` | query latency、fallback ratio、cross-source consistency |

## 4.6 P1：发布兼容清单（Compatibility Manifest）

当前 `operator_fingerprint` 和 `compiler_fingerprint` 主要用于缓存正确性，但仍建议把以下内容上升为发布兼容契约：

- `engine_codegen_version`
- `analysis_version`
- `polars_version`
- `expr_serialization_format`
- `operator_fingerprint`
- 全局编译开关

建议在 artifact metadata 与 publication record 中同时记录，避免后续出现“缓存正确，但回放不可解释”的问题。

## 4.7 P2：Request-Time Derived Feature

如果未来要服务盘中 API、策略触发、在线模型推理，这项能力价值很高；如果当前主战场仍以盘后批量物化为主，则可明确排到 P2。

建议只预留语义，不要现在把它拉进 MVP 实装。

---

## 5. 建议移除、归档或明确暂缓的内容

### 5.1 应归档或标记 obsolete 的文档

以下类型文档不应继续作为“当前状态入口”暴露：

- 仍将已完成 ADR 标记为待创建的 gap 文档
- 与当前 ADR 编号冲突的优化文档
- 早期 `issues.md` 形式的差距清单

这些文档仍可保留历史价值，但必须退出当前导航主线。

### 5.2 应明确暂缓而非继续扩大的能力

当前不建议纳入 MVP 主线的内容：

- 复合键全链路实现
- 多市场全链路实现
- `1m` grain 全链路实现
- 自定义算子开放平台
- 分布式计算调度
- lakehouse 事务层
- DSL 宏/模块系统

这些能力可以预留，但不应继续稀释当前治理与收敛工作的优先级。

---

## 6. ADR 重编排建议

### 6.1 保留现有 ADR 主线

以下 ADR 应继续保留为当前事实基础：

- `ADR-032`: 统一派生语义模型
- `ADR-033`: 派生查询架构与层边界
- `ADR-034`: 发布生命周期
- `ADR-035`: 失效传播级联协议
- `ADR-036`: DQ 门禁
- `ADR-037`: 性能 SLO
- `ADR-038`: 算子版本管理
- `ADR-039`: 表达式缓存持久化

### 6.2 新增 ADR 落地情况

#### ADR-040：Hot/Cold Retention and State Namespace Policy（已完成）

应回答：

- 分钟数据是否进入 Parquet
- QuestDB TTL 如何定义
- `derived:state:*` 与 `state:feature:*` 如何统一
- serving / artifact / snapshot / state 的生命周期边界如何分层

#### ADR-041：Research Dataset, Spine, and Availability-Time Contract（已完成）

应回答：

- `SpineSpec` 的定义
- dataset snapshot 的定义
- availability-time / known-at 如何建模
- 研究数据集如何与生产发布版本绑定

#### ADR-042：Shadow Publish and Dual-Read Diff Protocol（已完成）

应回答：

- shadow publish 是否引入新生命周期状态
- dual-read compare 如何定义 candidate / baseline 上下文
- diff report / trace report 如何建模
- promote 到 primary 前需要哪些 shadow 验证

#### ADR-043：Role/Profile Certification and Compatibility Manifest（已完成）

应回答：

- 如何从“最小 DQ”提升到 `role + profile` 分层认证
- `shadow_ready` / `publish_ready` 如何定义
- compatibility manifest 需要记录哪些环境与语义字段
- manifest 如何与 artifact / publication / dataset snapshot 绑定

### 6.3 需要回写的文档

新增 ADR 完成后，必须同步回写：

- `docs/design/unified-feature-factor-engine/main-design.md`
- `docs/design/unified-feature-factor-engine/README.md`
- 相关 gap / optimization 文档的状态说明

---

## 7. 与业界最佳实践的对比结论

### 7.1 Ditto 当前已经做得比较强的部分

与 Feast、Tecton、Hopsworks、Feathr 等主流方案相比，Ditto 当前设计在以下方面已经具备较强竞争力：

- 量化表达式 DSL 能力更强
- TS/CS 混合语义更强
- 对在线边界的约束更硬
- 对 operator version / compile cache / invalidation 的设计更细

这说明 Ditto 当前更像“面向量化场景的高表达力派生引擎”，而不是通用 feature store 的简单平移。

### 7.2 Ditto 明显弱于业界成熟方案的部分

与业界成熟实践相比，当前短板更集中在治理与数据集层：

- 缺少一等 `spine/entity dataframe` 契约
- 研究/训练数据集快照能力不够清晰
- availability-time / known-at 语义不够系统
- shadow publish / dual-read 验证不足
- discoverability / ownership / search / lineage 仍偏轻

### 7.3 最值得借鉴的实践方向

1. **Feast / Hopsworks / Feathr**
   - 一等数据集/样本表契约
   - point-in-time 数据集构建
   - registry / lineage / discoverability

2. **Tecton**
   - request-time / realtime feature 定义
   - freshness / monitoring / materialization 运行治理
   - 发布前后的平台级可观测性

3. **Materialize**
   - replacement / self-correcting 思维
   - 面向发布安全与系统自纠错的物化治理

---

## 8. 推荐实施顺序

### Phase A：先收敛文档真相源

1. 修正 ADR 编号漂移
2. 将过期 gap 文档归档或标记 obsolete
3. 更新 README 导航与状态说明

**状态**: ✅ 已完成

### Phase B：先补最短板，而不是继续扩引擎内核

1. 新建 `ADR-040`
2. 新建 `ADR-041`
3. 将 retention / state namespace / research dataset / availability-time 统一纳入主设计

**状态**: ✅ 已完成

### Phase C：补发布安全与认证治理

1. 新建 `ADR-042`
2. 新建 `ADR-043`
3. 将 shadow publish / dual-read diff / certification / compatibility manifest 纳入控制面主线

**状态**: ✅ ADR 已完成，后续待回写与实施拆解

### Phase D：再进入实施计划

在上述发布安全与认证 ADR 完成后，再编写 implementation plan，拆到：

- catalog/schema
- facade/service
- publication
- dataset snapshot
- verification / benchmark / diff

---

## 9. 验收标准

以下条件满足后，可认为统一引擎设计已从“多轮讨论态”进入“可实施态”：

- [x] README、主设计、ADR 的状态与编号已收敛到当前事实基础
- [x] 不再存在把已决策 ADR 视为待创建的当前文档入口
- [x] `ADR-040` 完成并统一 TTL、分钟数据保留、state namespace
- [x] `ADR-041` 完成并定义 `SpineSpec`、`DatasetSnapshot`、availability-time 语义
- [x] 发布门禁已通过 `ADR-043` 正式提升为“role/profile 分层认证”
- [x] 已通过 `ADR-042` 形成 shadow publish / diff report 的正式设计
- [x] 已形成 [2026-03-13-derived-publication-safety-implementation-plan.md](2026-03-13-derived-publication-safety-implementation-plan.md)
- [ ] 回写 `ADR-034 / ADR-036 / ADR-039`，使控制面 ADR 完全对齐

---

## 10. 本文档的最终建议

统一引擎下一阶段的正确方向，不是继续“往执行器里加更多东西”，而是把它补成一个真正可上线、可研究、可回放、可治理的派生数据系统。

因此，本轮的主建议可以压缩为四句话：

1. **保留现有架构主干，不推翻重做。**
2. **优先修正文档与 ADR 治理失真。**
3. **优先补 research dataset / availability-time / retention policy 三个高价值缺口。**
4. **把发布安全与认证能力提升到与表达式能力同等级。**

---

## 参考资料

### 项目内文档

- `docs/design/unified-feature-factor-engine/main-design.md`
- `docs/design/unified-feature-factor-engine/README.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-032-unified-derived-semantic-model.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-033-derived-query-architecture.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-034-publication-lifecycle.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-035-invalidation-cascade.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-036-quality-gates.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-037-performance-slo.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-038-operator-versioning.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-039-expression-cache-persistence.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-040-hot-cold-retention-state-namespace-policy.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-041-research-dataset-spine-availability-contract.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-042-shadow-publish-dual-read-diff-protocol.md`
- `docs/design/unified-feature-factor-engine/decisions/adr-043-role-profile-certification-compatibility-manifest.md`

### 外部最佳实践参考

- Feast Concepts: https://docs.feast.dev/getting-started/concepts/point-in-time-joins
- Feast Feature View: https://docs.feast.dev/getting-started/concepts/feature-view
- Feast Dataset: https://docs.feast.dev/v0.23-branch/getting-started/concepts/dataset
- Tecton Realtime Feature View: https://docs.tecton.ai/docs/beta/defining-features/feature-views/realtime-feature-view
- Tecton Monitoring: https://docs.tecton.ai/docs/1.0/monitoring
- Hopsworks Feature Store Concepts: https://docs.hopsworks.ai/3.2/concepts/fs/
- Hopsworks Spine Group: https://docs.hopsworks.ai/latest/concepts/fs/feature_group/spine_group/
- Hopsworks Data Validation: https://docs.hopsworks.ai/3.0/user_guides/fs/feature_group/data_validation/
- Feathr Repository: https://github.com/feathr-ai/feathr
- Materialize Blog, Self-Correcting Materialized Views: https://materialize.com/blog/self-correcting-materialized-views/
