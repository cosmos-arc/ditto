# 全库架构重构最终 Review（裁决稿）

**日期**: 2026-03-27
**评审对象**: [2026-03-26-full-architecture-refactoring-design](../plans/2026-03-26-full-architecture-refactoring-design.md)
**输入文档**:
- [2026-03-27-architecture-refactoring-design-review](./2026-03-27-architecture-refactoring-design-review.md)
- [2026-03-27-full-architecture-refactoring-review](../plans/2026-03-27-full-architecture-refactoring-review.md)
**状态**: 最终裁决，建议作为后续实施唯一评审基线
**目标**: 统一原设计与两份 review 的有效结论，形成可逐项落地的最终架构裁决

---

## 1. 最终结论

对 [2026-03-26-full-architecture-refactoring-design](../plans/2026-03-26-full-architecture-refactoring-design.md) 的最终裁决如下：

- **主方向采纳**
  - 按业务子域组织顶层结构，而不是继续围绕 `core / port / datahub` 修补
  - `application` 作为唯一跨域装配与流程编排层
  - `decisioning / trading / analytics` 只消费 prepared inputs
  - `sources` 与 `datahub` 分离，分别隔离外部世界与内部持久化
  - DataFrame 作为量化系统中的一等业务载体，但不取代领域行为对象

- **关键修正后采纳**
  - `metadata / marketdata` 不只拥有“查询语义”，还应拥有“查询契约与查询端口”
  - 摄取链必须补齐生产级契约，不能只停留在 `SourceSchema -> StoreSchema` 骨架
  - 实时/回测统一模型中，需补上内部事件契约，但**不**引入完整事件框架作为前置条件
  - `MarketSnapshot` 及相关执行输入契约必须覆盖市场模拟所需字段

- **明确不采纳**
  - 不采纳“rich kernel”路线
  - 不采纳“将 trading rules / fee schedule 的语义 owner 迁入 `trading` 域”
  - 不采纳“将通用质量结果对象提前放入 `kernel`”这一建议
  - 不采纳 Big Bang 式全库目录/包名先行迁移

一句话总结：

> Ditto 的最终目标架构，应当是“极小 kernel + 明确子域 owner + application 独占跨域装配 + sources/datahub 双边界隔离 + prepared-input-first 的行为域”。

---

## 2. 不可回退的北极星决策

以下内容建议直接视为后续重构的不可回退基线。

### 2.1 子域优先于技术层

顶层模块应以业务语义表达系统，而不是继续延续历史技术层命名。

目标形态：

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

### 2.2 `application` 是唯一跨域装配层

`application` 的职责必须被收紧为：

- 选择调用哪些子域能力
- 构建行为域输入契约
- 执行 command
- 推进 process
- 管理重试、补偿、checkpoint、状态推进

`interfaces` 只做输入适配与输出序列化，不承担业务编排。

### 2.3 行为域只消费 prepared inputs

以下约束建议升级为 lint 级铁律：

- `decisioning -X-> metadata / marketdata / sources / datahub`
- `trading -X-> metadata / marketdata / sources / datahub`
- `analytics -X-> metadata / marketdata / sources / datahub`

允许关系只有：

- 行为域依赖 `kernel`
- `application` 依赖行为域输入契约并负责构建它们

### 2.4 `sources` 与 `datahub` 必须拆开

二者虽都属基础设施，但边界完全不同：

- `sources`: 面向外部 provider、承担 ACL/connector/inbound adapter 角色
- `datahub`: 面向内部持久化、承担 repository/store/query implementation 角色

这是新架构中最重要的边界拆分之一。

### 2.5 DataFrame-first，但不是 DataFrame-everything

应坚持：

- `marketdata`、`analytics`、部分 `decisioning` 以 DataFrame 为一等模型
- 订单、账户、持仓、执行规则、风控状态、流程状态不应退化为无语义 DataFrame

---

## 3. 逐项裁决表

本节是本最终 review 的核心，用于后续逐条分析与落地。

| 议题 | 最终裁决 | 说明 |
|------|----------|------|
| 行为域不直接查数据 | 采纳 | 新设计最有价值的铁律，必须保留 |
| DataFrame 是一等业务载体 | 采纳 | 量化系统现实需要，但不得替代实体/值对象 |
| `application` 作为 Process 编排者 | 采纳 | 合理，且与现有 `port/services/*` 收敛趋势一致 |
| Input Contract 归属行为域 | 采纳 | 边界清晰，依赖方向正确 |
| `builders.py` 应保持纯装配 | 采纳 | 只能装配，不允许偷偷查询 |
| `sources` 从 `datahub` 独立 | 采纳 | ACL 与内部持久化边界必须分治 |
| `metadata / marketdata` 拥有查询语义 | 采纳，但需升级 | 需从“owner”升级为“契约 owner + 端口 owner” |
| `trading rules / fee schedule` 迁入 `trading` | 不采纳 | 消费方不等于真相 owner，仍应保留在 `metadata` 查询语义中 |
| `analytics` 可能过重 | 部分采纳 | 作为后续优化观察项，不作为当前前置拆分条件 |
| 缺少内部事件契约 | 采纳，但收窄范围 | 需要 domain event contract，不需要事件总线前置化 |
| `MarketSnapshot` 契约需要补全 | 采纳 | 必须显式覆盖市场模拟必需字段 |
| `kernel` 下沉极简 `CheckResult` | 暂不采纳 | 很容易继续膨胀 kernel，先避免过早共享 |
| `decisioning` 改名为 `strategy/alpha` | 延后评估 | 这是命名优化，不影响当前架构主线 |

---

## 4. 最关键的三项裁决

### 4.1 `kernel` 必须保持极小

这是本次最终 review 中最明确的一条。

应保留在 `kernel` 的类型必须同时满足：

1. 跨多个子域稳定复用
2. 低变更频率
3. 零流程逻辑
4. 不依赖具体层实现

因此：

- `InstrumentId`
- `AssetClass`
- `Exchange`
- `TradeDate`
- `Currency`

这类类型适合进入 `kernel`。

而以下类型**不应**进入 `kernel`：

- `Order`
- `Position`
- `Account`
- `OrderStatus`
- `MarketSnapshot`
- `ExecutionContext`

原因很简单：它们属于具体行为域边界，且变更频率、语义密度、上下文依赖都高于 shared kernel 可承受范围。

### 4.2 `metadata / marketdata` 不只是语义 owner，还应是端口 owner

新设计里对“owner”的判断是对的，但还不够落地。

最终裁决如下：

- `metadata` 应拥有：
  - identity 解析契约
  - instrument/reference data 查询契约
  - calendar / universe / trading rules / fee schedule 查询契约
  - metadata PIT 查询契约

- `marketdata` 应拥有：
  - bars / quotes / ticks / benchmark 查询契约
  - adj / asof / market PIT 查询契约

- `datahub` 的职责是：
  - 实现这些查询端口
  - 实现存储端口
  - 提供缓存/归档/读优化

因此后续正式落地时，必须明确：

- 查询接口定义在哪
- 查询参数对象定义在哪
- 稳定输出契约定义在哪
- `datahub` 如何实现它们

否则“语义 owner”会继续漂移到实现层。

### 4.3 `trading rules / fee schedule` 的最终归属

这是两份 review 分歧最大的地方，本最终稿明确裁决如下：

- **语义真相 owner**: `metadata`
- **行为消费方**: `trading`
- **装配责任**: `application`

理由：

1. `trading rules / fee schedule` 本质上是 reference/PIT 查询语义
2. 它们有明确的 `as_of_date`、版本、生效边界、查询真相属性
3. `trading` 需要消费它们，但“谁消费”不等于“谁拥有真相”
4. 将其迁入 `trading` 会把 reference truth 与 execution behavior 混在一起

应采纳的中间方案是：

- `metadata` 定义并拥有规则/费率的查询契约与真相模型
- `trading` 定义自己真正消费的运行时输入快照
- `application` 在回测/实时/实盘流程中预先查询并注入

性能问题通过缓存、会话级预组装、按日期快照复用解决，而不是通过错误迁移 owner 解决。

---

## 5. 从 Claude Code review 中采纳的有效补充

以下内容来自 [2026-03-27-architecture-refactoring-design-review](./2026-03-27-architecture-refactoring-design-review.md)，本最终稿明确采纳。

### 5.1 `builders.py` 必须是纯装配层

`builders.py` 的角色应被明确限定为：

- 接收已查询好的数据
- 进行本地转换与装配
- 构建 Input Contract / Read Model / Command Payload

禁止：

- 在 `builders.py` 中发起查询
- 在 `builders.py` 中写状态
- 把 `builders.py` 变成隐式 `Query`

### 5.2 Input Contract 必须执行 YAGNI

应增加设计约束：

- Input Contract 每个字段都必须可追溯到真实消费点
- 不允许预埋“未来也许会用”的字段
- 不允许把 Input Contract 演变成隐式共享大 schema

这条约束非常重要，否则 prepared-input-first 很容易退化成“超厚 DTO 中转站”。

### 5.3 `MarketSnapshot` 与执行输入契约必须补全

当前 [market.py](../../packages/core/src/ditto_core/execution/reality/market.py) 已经包含：

- `is_suspended`
- `limit_up`
- `limit_down`
- `avg_volume_20d`

这是正确方向，但最终设计稿仍应显式写清：

- 市场模拟到底要求哪些字段
- 哪些字段属于可选增强
- 哪些字段必须由 `application` 预组装提供

这会直接影响回测、实时模拟、成交模型、滑点模型和风控判定。

### 5.4 内部事件契约应补上，但不要框架先行

原设计已提到 `interfaces.streams` 可接收市场流、broker 回报、事件消息，因此“完全缺失事件流机制”这个说法不准确；但内部确实缺少正式的状态变更事件契约。

最终采纳建议：

- 在 `trading` 域定义最小 domain event contract
- 例如：
  - `OrderSubmitted`
  - `OrderFilled`
  - `OrderCanceled`
  - `PositionChanged`
  - `RiskGuardTriggered`

- 这些契约服务于：
  - 回测与实盘共享状态变更语义
  - 审计、通知、下游投影的统一消费

明确不做：

- 不把消息总线/事件框架作为当前架构重构的前置条件
- 不把系统提前推向事件驱动架构

---

## 6. 不采纳或延后采纳的建议

### 6.1 不采纳：`trading rules / fee schedule` 迁入 `trading`

已在第 4.3 节明确裁决，不再重复。

### 6.2 暂不采纳：`kernel` 下沉 `CheckResult`

虽然“只共享极简结果对象”听起来无害，但现阶段不应贸然下沉到 `kernel`。

原因：

- `passed/failed + severity + message` 在不同域未必真能长期同语义复用
- 这类类型很容易继续膨胀出 code/category/context/source 等字段
- 一旦进入 `kernel`，回退成本高

建议顺序是：

1. 各域先独立演化
2. 等至少 2-3 个域出现稳定同构
3. 再判断是否值得下沉

### 6.3 部分采纳：`analytics` 可能过重

这条提醒有价值，但不应在当前阶段变成强前置约束。

最终裁决：

- 当前先保留 `analytics = derived + research + evaluation + simulation`
- 后续观察以下两类裂缝是否真实出现：
  - `research` 是否更像 application 读模型构建器
  - `simulation` 是否只是 process 编排外壳，而缺乏独立领域语义

只有当裂缝在实现中稳定出现，才进行二次拆分。

### 6.4 延后评估：`decisioning` 命名是否改为 `strategy` 或 `alpha`

这是一个有价值的命名问题，但不属于当前主路径阻塞项。

最终裁决：

- 架构先落地
- 命名后统一评估
- 若后续引入 `strategy` 作为更贴近团队认知的名称，可单独作为命名治理任务处理

---

## 7. 最终目标架构

本最终稿建议的目标形态如下。

### 7.1 顶层依赖

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

### 7.2 模块角色

| 模块 | 最终角色 |
|------|----------|
| `kernel` | 极小共享语义原语 |
| `metadata` | reference/identity/PIT 真相 owner + query port owner |
| `marketdata` | 市场时序/PIT/adj 真相 owner + query port owner |
| `decisioning` | 目标持仓意图生成 |
| `trading` | 订单、成交、账户、执行、风险状态推进 |
| `analytics` | 研究数据集、评估、归因、仿真语义 |
| `application` | 输入装配、命令执行、长流程编排 |
| `sources` | 外部 provider ACL + normalized source frame 输出 |
| `datahub` | 内部持久化、读优化、存储实现 |
| `interfaces` | HTTP/CLI/jobs/streams/bootstrap 入口适配 |
| `infra` | 配置、日志、锁、连接、任务底座等技术能力 |

---

## 8. 先解决什么：P0 / P1 / P2

### P0：实施前必须先收敛

1. 明确 supersede rich-kernel 路线
2. 明确 `metadata / marketdata` 的查询契约与端口 owner 身份
3. 明确 `trading rules / fee schedule` 的最终 owner 与消费模式
4. 明确 `application` 内部 `Query / Command / Process / builders` 规则

### P1：进入实施时优先落地

1. 从现有 `port/services/*` 提炼 `application`
2. 从现有 `port` 中拆出 `interfaces`
3. 将 `sources` 从 `datahub` 中独立
4. 补上最小 domain event contract
5. 完整定义 `MarketSnapshot` / `ExecutionContext` 等交易输入契约
6. 补齐摄取链的幂等、更正、重放、lineage 契约

### P2：体系稳定后再优化

1. 评估 `analytics` 是否需要二次拆分
2. 评估 `decisioning` 命名是否调整
3. 评估跨域共享质量结果对象是否真的值得抽象

---

## 9. 后续工作方式

从本文件开始，建议后续按以下顺序推进：

1. 先对第 8 节的 P0 议题逐项做设计裁决
2. 每解决一个 P0，再补对应 ADR / 规范文档
3. P0 全部落定后，再写正式实施计划
4. 实施时坚持“先抽边界，再改目录，再迁命名”的顺序

因此，本文件后续应作为：

- 逐项问题分析清单
- 后续 implementation plan 的上位约束
- 文档 supersede/partial-supersede 的依据

---

## 10. 最终裁决摘要

本最终 review 的最终裁决可以压缩为 8 句话：

1. 采纳新设计的大方向。
2. 否决 rich kernel。
3. 保留 prepared-input-first。
4. 保留 `sources` / `datahub` 分治。
5. `metadata / marketdata` 必须升级为端口 owner。
6. `trading rules / fee schedule` 保留在 `metadata` 真相侧，由 `trading` 消费。
7. 采纳最小 domain event contract 与更完整的交易输入契约。
8. 用渐进式模块化单体迁移替代 Big Bang 重构。
