# Ditto 全库架构重构设计 Review

**日期**: 2026-03-27
**评审对象**: [2026-03-26-full-architecture-refactoring-design](./2026-03-26-full-architecture-refactoring-design.md)
**状态**: 建议采纳，附带关键修正
**范围**: 全库架构边界、模块职责、依赖规则、迁移顺序、文档治理

---

## 1. 执行摘要

对 [2026-03-26-full-architecture-refactoring-design](./2026-03-26-full-architecture-refactoring-design.md) 的总体判断如下：

- 大方向正确，应作为 Ditto 后续全库重构的主设计基线
- 不建议回退到 `core / port / datahub` 为中心的旧技术分层叙事
- 不建议沿用 2026-03-24/2026-03-25 文档中“rich kernel”扩张路线
- 应将“语义 owner”进一步收紧为“契约 owner + 端口 owner”
- 实施方式必须采用渐进式模块化单体迁移，而不是 Big Bang 全量搬家

一句话结论：

> 新设计的方向应被确认，但必须补上 `kernel` 哲学收敛、查询端口归属、摄取链生产级契约、迁移顺序细化这四个关键修正点。

---

## 2. 评审立场与业界对照

本次 review 采用以下业界基准判断 Ditto 的目标架构是否成立：

- DDD / Shared Kernel：共享内核必须保持极小，只承载跨上下文稳定一致的共享语义
- CQRS：查询模型与行为模型分离，读优化不应反向污染领域行为边界
- ACL：外部世界语义必须先翻译，再进入内部真相模型
- 量化系统实践：DataFrame 是合法的一等业务载体，但不应吞并订单、账户、风控、执行等行为对象

参考资料：

- Eric Evans, DDD Reference: https://www.domainlanguage.com/ddd/reference/
- Microsoft, CQRS Pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs
- Microsoft, Anti-Corruption Layer Pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer
- Matthias Noback, Does It Belong in the Application or Domain Layer?: https://matthiasnoback.nl/2021/02/does-it-belong-in-the-application-or-domain-layer/
- Martin Fowler, Anemic Domain Model: https://martinfowler.com/bliki/AnemicDomainModel.html
- QuantConnect, Algorithm Framework Overview: https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview

---

## 3. 应确认保留的核心决策

以下决策建议直接固化为 Ditto 后续重构的北极星原则。

### 3.1 子域优先于技术层

顶层模块按业务语义组织，而不是继续围绕 `core / port / datahub` 进行局部修补。

目标顶层结构建议保持为：

```text
apps/
  interfaces/

packages/
  kernel/
  application/
  metadata/
  marketdata/
  decisioning/
  trading/
  analytics/
  sources/
  datahub/
  infra/
```

这是正确方向，因为 Ditto 的复杂性主要来自：

- 数据语义复杂
- 跨域编排复杂
- 回测/实时/研究共模复杂

而不是传统 CRUD 式的“表到服务”复杂度。

### 3.2 `application` 独占跨域装配权

应明确确认：

- `application` 是唯一合法的跨域装配层
- 只有 `application` 可以同时协调 `metadata / marketdata / decisioning / trading / analytics / sources`
- `interfaces` 只做入口适配，不做业务编排

这与当前仓库中 [input_assembler.py](../../apps/port/src/ditto_port/services/strategy/input_assembler.py) 和 [backtest_service.py](../../apps/port/src/ditto_port/services/strategy/backtest_service.py) 已经呈现出的收敛方向一致。

### 3.3 行为域只消费 prepared inputs

以下铁律应保留并升级为 lint 级约束：

- `decisioning` 不直接查数据
- `trading` 不直接查数据
- `analytics` 不直接查数据
- 它们只消费由 `application` 预组装好的输入契约

这条规则是本次全库重构中价值最高的判断，应视为不可回退设计。

### 3.4 `sources` 与 `datahub` 必须拆开

这两个模块都属于基础设施，但服务于不同边界：

- `sources` 面向外部世界，承担 ACL/connector/inbound adapter 角色
- `datahub` 面向内部世界，承担 repository/store/query implementation 角色

它们不应长期被置于同一语义容器之下。

### 3.5 DataFrame-first，但不是 DataFrame-everything

以下场景可以且应当 DataFrame-first：

- `marketdata`
- `analytics`
- `decisioning` 中的决策 frame

以下场景仍应保持明确领域模型：

- 订单
- 账户
- 持仓
- 交易规则
- 风控上下文
- 执行状态推进

---

## 4. 必须修正的关键决策

### 4.1 P0：终结 `kernel` 哲学冲突

当前文档体系存在直接冲突：

- 新设计主张 `kernel` 必须极小
- 旧文档主张 `kernel` 承载 rich domain model

冲突文档包括：

- [2026-03-24-shared-kernel-and-model-governance-design](./2026-03-24-shared-kernel-and-model-governance-design.md)
- [2026-03-25-architecture-domain-refactoring-audit](./2026-03-25-architecture-domain-refactoring-audit.md)

本 review 的裁决是：

- 应以 2026-03-26 新设计为准
- `kernel` 仅保留极小共享语义原语
- `Order / Position / Account / OrderStatus / MarketSnapshot / ExecutionContext` 不进入 `kernel`
- rich domain model 应归属对应业务域，尤其是 `trading`

建议后续新增 superseding ADR，明确废止“rich kernel”路线。

### 4.2 P0：查询语义 owner 必须升级为“查询契约 owner + 端口 owner”

新设计正确指出：

- `metadata` 拥有 identity / calendar / universe / trading rules / metadata PIT 查询语义
- `marketdata` 拥有 bars / quotes / ticks / adj / asof 查询语义

但仅写“owner”还不够，必须继续明确：

- 查询接口定义在 `metadata / marketdata`
- 查询参数对象定义在 `metadata / marketdata`
- 稳定输出契约定义在 `metadata / marketdata`
- `datahub` 仅负责实现这些契约

否则所有权仍会漂移到实现层，继续让类似 [metadata_service.py](../../packages/data/src/ditto_data/services/metadata_service.py) 和 [market_service.py](../../packages/data/src/ditto_data/services/market_service.py) 成为事实 owner。

### 4.3 P1：迁移顺序必须从“先抽边界”改写，不能先全量改包名

当前高层迁移顺序方向正确，但仍偏抽象。

建议明确禁止以下方式：

- 先大规模改目录和包名
- 再回头修正依赖和职责

建议采用反向顺序：

1. 先明确约束和端口
2. 再抽 `application`
3. 再拆 `sources`
4. 再收缩 `datahub`
5. 最后才改顶层包结构与命名

这能最大化复用现有代码里的收敛趋势，避免大规模重命名把系统再次打散。

### 4.4 P1：摄取链必须补齐生产级契约

`SourceSchema -> application.ingestion -> StoreSchema` 是正确骨架，但还不够生产级。

正式实施前应显式补齐以下契约：

- idempotency 规则
- duplicate / correction policy
- event_time 与 business_date 的并存语义
- provenance / lineage 字段
- replay / reprocessing 语义

否则晚到、更正、补发、重放会继续把语义泄漏回 `datahub` 或 `sources` 私有实现中。

---

## 5. 最终推荐版目标架构

本 review 建议将最终架构收紧为如下形式。

### 5.1 顶层依赖结构

```text
interfaces -> application

application -> metadata ports
application -> marketdata ports
application -> decisioning
application -> trading
application -> analytics
application -> sources ports

datahub -> implements(metadata ports | marketdata ports | storage ports)
sources -> implements(source ports)

metadata -> kernel
marketdata -> kernel
decisioning -> kernel
trading -> kernel
analytics -> kernel
infra -> none
kernel -> none
```

### 5.2 核心角色

| 模块 | 最终角色 |
|------|----------|
| `kernel` | 极小共享语义原语 |
| `metadata` | reference/identity/trading-rules 语义 owner + query port owner |
| `marketdata` | 市场时序语义 owner + query port owner |
| `decisioning` | 目标持仓意图生成 |
| `trading` | 订单、成交、账户、执行与风险状态推进 |
| `analytics` | 研究数据集、评估、归因、仿真 |
| `application` | 输入装配、命令执行、长流程编排 |
| `sources` | 外部 provider ACL + normalized source frame 输出 |
| `datahub` | 内部持久化、读优化、存储实现 |
| `interfaces` | HTTP/CLI/jobs/streams 入口适配 |
| `infra` | 通用技术能力 |

### 5.3 端口归属原则

后续设计与实现应遵循：

- 谁拥有语义，谁拥有端口
- 谁实现存储，谁不拥有语义
- 谁负责流程，谁不拥有子域真相

因此：

- `metadata`、`marketdata` 应拥有查询端口
- `trading`、`analytics` 可拥有稳定写端口或存储契约
- `datahub` 只实现端口，不定义语义真相
- `application` 只组装和调用，不复制子域语义

---

## 6. 迁移实施建议

### 6.1 Phase 0：冻结目标边界

先冻结，而不是先搬目录。

交付物：

- 统一后的顶层依赖矩阵
- `kernel` 准入标准最终版
- `application` 内部 `Query / Command / Process` 约束
- `metadata / marketdata / sources / datahub` 的 owner 说明

### 6.2 Phase 1：从现有 `port` 中提炼 `application`

现有 [apps/port/src/ditto_port/services](../../apps/port/src/ditto_port/services) 中已经存在大量 application 形态代码，应优先抽象为：

- `application.strategy`
- `application.ingestion`
- `application.analytics`
- `application.sources`

此阶段重点不是改名，而是固定边界。

### 6.3 Phase 2：分离 `interfaces`

将现有 `port` 拆为：

- `interfaces`：HTTP/CLI/jobs/streams/bootstrap
- `application`：真正的编排层

这是落地新设计的第一条真实结构缝合线。

### 6.4 Phase 3：将 `sources` 从 `datahub` 中独立

独立后形成清晰摄取链：

```text
provider raw payload
-> sources normalized frame
-> application.ingestion identity unify / dq / route / duplicate handling
-> datahub persistence
```

### 6.5 Phase 4：建立 `metadata / marketdata` 端口并收缩 `datahub`

本阶段关键动作：

- 将查询契约迁入 `metadata / marketdata`
- 将 `datahub` 的 service 调整为实现层或适配层
- 逐步消除“实现层拥有查询语义”的遗留结构

### 6.6 Phase 5：最后再做包级重命名和目录切换

只有在前述边界稳定后，才建议：

- 新建 `packages/metadata`
- 新建 `packages/marketdata`
- 新建 `packages/application`
- 将遗留 `core / port / datahub` 的语义映射迁入新结构

这是最稳妥、也最符合长期可维护性的迁移方式。

---

## 7. 约束固化建议

### 7.1 importlinter

建议新增或重写以下约束：

- `interfaces -> application` 唯一上游入口约束
- `decisioning / trading / analytics -X-> metadata / marketdata / sources / datahub`
- `datahub -X-> 行为域实现`
- `sources -X-> datahub`
- `application` 内部 `Query / Command / Process` 依赖约束

### 7.2 文档治理

应同步更新或新增：

- 根 `AGENTS.md`
- [.importlinter](../../.importlinter)
- `packages/kernel/CLAUDE.md`
- `packages/metadata/CLAUDE.md`
- `packages/marketdata/CLAUDE.md`
- `packages/decisioning/CLAUDE.md`
- `packages/trading/CLAUDE.md`
- `packages/analytics/CLAUDE.md`
- `packages/sources/CLAUDE.md`
- `packages/data/CLAUDE.md`
- `apps/interfaces/CLAUDE.md`

### 7.3 superseded 标记

建议后续对以下文档追加 superseded 或 partial-superseded 标记：

- [2026-03-24-shared-kernel-and-model-governance-design](./2026-03-24-shared-kernel-and-model-governance-design.md)
- [2026-03-25-architecture-domain-refactoring-audit](./2026-03-25-architecture-domain-refactoring-audit.md)

原因不是它们完全错误，而是它们在 `kernel` 边界与模块 owner 上已与新设计冲突。

---

## 8. 最终裁决

本 review 的最终裁决如下：

- 采纳 2026-03-26 新设计作为 Ditto 全库重构的主设计基线
- 明确否决 rich kernel 扩张路线
- 明确要求 `metadata / marketdata` 从语义 owner 升格为端口 owner
- 明确要求 `sources` 与 `datahub` 分治外部世界与内部世界
- 明确要求 `decisioning / trading / analytics` 只消费 prepared inputs
- 明确要求以渐进式模块化单体迁移替代 Big Bang 重构

最重要的最终判断是：

> Ditto 的长期优雅架构，不是“更干净的 core”，而是“清晰的子域边界 + 极小 kernel + 由 application 独占跨域装配 + 由 sources/datahub 分别隔离外部世界与内部持久化”。

---

## 9. 后续建议

建议按以下顺序继续：

1. 基于本 review 产出 superseding ADR，先终结 `kernel` 哲学冲突
2. 基于新设计与本 review 产出详细实施计划
3. 先做边界抽取，再做目录迁移
4. 每完成一个 phase，就同步更新 `.importlinter` 与对应 `CLAUDE.md`

推荐下一份文档：

- `docs/plans/2026-03-27-full-architecture-refactoring-implementation-plan.md`
