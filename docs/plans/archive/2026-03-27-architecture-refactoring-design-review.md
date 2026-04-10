# 全库架构重构设计 Review

**日期**: 2026-03-27
**评审对象**: `docs/plans/2026-03-26-full-architecture-refactoring-design.md`
**评审视角**: 量化系统架构最佳实践（对标 QuantConnect LEAN、Zipline）
**总评**: 8.5/10 — 战略方向正确，核心设计决策经得起推敲，本文档列出增量修正建议

---

## 1. 整体评价

重构计划的核心判断——"当前系统的根本问题不是没有 DDD，而是技术层轴与业务域轴混杂"——是准确的。从 `core/datahub/port` 技术分层转向按业务子域组织模块，是成熟量化平台的共同选择。

六条北极星原则中，最关键的两条经得起严格审查：

1. **行为域不直接查数据** — 消除了行为对象不纯、编排对象也不纯的根本矛盾
2. **DataFrame 是一等业务载体，但不能冒充聚合根** — 这条在 DDD 教科书中找不到，但在量化系统中是生死攸关的判断

以下按模块和设计决策逐一评审，给出改进建议。

---

## 2. 模块划分

### 2.1 metadata vs marketdata 边界灰色地带

**问题**: 三类概念会卡在两个子域的裂缝里。

| 概念 | 归属争议 | 建议归属 |
|------|---------|---------|
| adj factor（复权因子） | 修改价格序列 vs instrument 固有属性 | `marketdata` — 它服务于价格序列的复权语义 |
| universe constituent | 静态元数据 vs 使用时总关联 marketdata | `metadata` — 本质是"一组 instrument 的列表"，查询语义归 metadata |
| trading rules / fee schedule | 参考数据 vs 交易行为规则 | `trading` — 它是"交易行为规则"，不是"参考数据" |

**建议**: 将 trading rules / fee schedule 归入 `trading` 域。理由：

- 它们的消费者是 `trading` 域（pre-trade risk、brokerage、execution）
- 按当前规则 `trading` 不能直接依赖 `metadata`，必须通过 `application` 注入
- 在高频回测循环中，每根 bar 一次的注入装配开销是不必要的间接层
- QuantConnect LEAN 的做法正是如此——`FeeModel`、`FillModel`、`SlippageModel` 都是 brokerage 模块的内部概念

### 2.2 `decisioning` 命名

量化业界没有 `decisioning` 这个词。LEAN 用 `Algorithm`，Zipline 用 `Strategy`，WorldQuant 用 `Alpha`。

这不影响架构正确性，但会影响系统的"可读性"这一北极星原则。建议评估是否用 `strategy` 或 `alpha` 替代，降低新贡献者的认知距离。

### 2.3 `analytics` 承载过重

当前包含 derived（因子物化）、research（研究数据集）、evaluation（评估统计）、simulation（仿真）四个子域，内聚性差异大：

- `derived` 和 `evaluation` 强相关（因子 → 评估）
- `research` 更接近 application 层的数据装配
- `simulation` 的职责已被 `application.Process` 承担（见第 3 节）

建议在实施时关注 `analytics` 内部是否需要进一步拆分，但不作为前置约束。

---

## 3. 依赖规则与 application 定位

### 3.1 application 作为 Process 编排者 — 合理

`application` 是整个系统的唯一跨域枢纽，所有跨域交互通过它协调。在量化系统中：

- 回测循环（bar-by-bar stepping）是 `RunBacktestProcess` 的流程编排
- 实时 session 是 `RunLiveSessionProcess` 的流程编排
- 摄取流程是 `RunIngestionProcess` 的流程编排

这些 Process 不发明任何业务规则，只按顺序调用"拉数据 → 做决策 → 执行 → 记录"。回测/实时的区别只在 Process 实现不同，共享同一套领域规则。`application` 作为 Process 编排者的定位完全正确。

### 3.2 回测引擎的结构性变化

当前 `core.backtest.engine.EngineLoop` 的 `step()` 方法本质上是流程编排，但物理位置放在了 `core` 里。迁移后：

| 当前位置 | 迁移目标 |
|---------|---------|
| `EngineLoop.step()` 循环 | `application.strategy.RunBacktestProcess` |
| 策略执行 | `decisioning` |
| 账户/订单管理 | `trading` |
| 统计归集 | `analytics` |

这不是"拆毁"回测引擎，而是把它的伪领域行为还原为真实身份——流程编排。

### 3.3 Query/Command/Process 角色约束

`*Query -X-> *Command / *Process` 和 `*Command -X-> *Query / *Process` 规则自洽。`shared/` 和 `builders.py` 打破了 Query/Command 之间不能共享逻辑的死结，依赖链为：

```
Process → Query（拿数据）→ shared/builder（装配）→ Command（执行）
```

建议明确 `builders.py` 的定位为**纯装配函数**——接受已查询好的数据作为参数，不做查询。

---

## 4. 模型分层体系

六层分类（Kernel Primitives、Behavior Input Contracts、Application DTO/Process State、Domain Models、Analytical Frames、Store Records）在理论上完备。

### 4.1 Input Contract 归属行为域 — 点睛之笔

"接口定义在客户端"原则（Go 的 `io.Reader` 定义在 `io` 包而非 `os` 包）。行为域定义自己需要什么，`application` 负责满足。依赖方向始终是 `application → 行为域`，不会形成反向依赖。

### 4.2 Input Contract 膨胀风险

需警惕退化模式：Input Contract 逐渐膨胀成"厚输入模型"，成为 application 和行为域之间的隐式共享 schema。

**建议约束**: Input Contract 的字段必须能追溯到行为域内部的**实际消费点**。不允许"可能以后会用到"的字段存在。这是 YAGNI 在接口层面的体现。

---

## 5. sources 与摄取链

这是整份计划中设计最成熟的部分。评价 9.5/10。

- `sources` 从 `datahub` 独立 — 正确，二者面向不同边界
- `SourceSchema` vs `StoreSchema` 两阶段模型 — 严密
- `source_ticker → instrument_id` 统一化归 `metadata` + `application.ingestion` 编排 — 职责清晰
- `SourceSchema` 不包含 `instrument_id` — 守住了外部/内部世界的边界

### 5.1 datahub 写入路由

`application.ingestion` 显式选择目标 store writer，分区策略封装在 datahub 存储实现内部：

```
application.ingestion → datahub.etf_bar_store.write(normalized_frame)
                                        ↑ 分区策略封装在 store 内部
```

---

## 6. 质量与风险拆分

拆分逻辑正确（metadata.quality / analytics.evaluation / trading.risk），但需注意共享基座。

当前 `core.quality` 的引擎（`QualityEngine`、`QualitySpec`、`QualityReport`、checker 注册机制）是通用框架。拆分后三个域都需要类似的检查/评估能力。复制违反 DRY，下沉到 `kernel` 违反极小原则。

**建议**: `kernel` 提供极简的 `CheckResult` 值对象（passed/failed + severity + message），各域自行实现 checker 注册机制。只需要共享结果类型，不需要共享框架。

实际提取成本很低——当前 `core.quality.report.Severity` 和 `QualityReport` 的核心就是这种值对象。

---

## 7. 结构性遗漏

### 7.1 事件流机制缺失

实时场景（市场数据推送、brokerage 回报、风控告警）需要事件驱动能力。计划未提及事件总线、domain event、消息机制。

LEAN 用 `IBrokerageMessageHandler` 和 `ISecurityInitializer` 处理此类问题；回测中用同步事件队列模拟实时。

**建议**: 至少在 `trading` 域内定义 domain event 契约（`OrderFilled`、`PositionChanged` 等），让回测和实盘共享同一套状态变更语义。不一定要引入完整事件框架，但需要事件契约。

### 7.2 回测市场模拟的数据契约

回测需要模拟市场行为：撮合、滑点、涨跌停判断、停牌处理。当前在 `core.execution.reality` 中，迁移后归 `trading` 域。但 `trading` 域不直接查数据——涨跌停判断需要"当日涨跌停价格"。

**要求**: `trading` 域的 `MarketSnapshot` 输入契约必须显式包含市场模拟所需的全部数据字段（涨跌停价、停牌状态、集合竞价信息等）。`application` 在预组装时负责填充。这不是新约束，而是对现有 `MarketSnapshot` 契约的精度要求。

---

## 8. 评分汇总

| 维度 | 评分 | 说明 |
|------|------|------|
| 问题诊断 | 9/10 | 精准识别技术层/业务域混杂、四类模型混用、行为域与查询装配混杂 |
| 模块划分 | 8/10 | metadata/marketdata 边界有灰色地带，analytics 承载略重 |
| 依赖规则 | 8.5/10 | 星型拓扑在量化场景下合理，application 作为 Process 编排者定位准确 |
| 模型体系 | 9/10 | 六层分类完备，Input Contract 归属行为域是点睛之笔 |
| 摄取链设计 | 9.5/10 | SourceSchema/StoreSchema 两阶段模型、sources 独立、identity 归属清晰 |
| 遗漏项 | 7/10 | 缺事件流机制、缺市场模拟的数据契约 |

**总评: 8.5/10** — 架构方向正确，核心设计决策经得起推敲。本文档提出的改进点均为增量修正，不涉及结构性推翻。

---

## 附录：改进建议清单

| # | 建议 | 优先级 | 影响 |
|---|------|--------|------|
| 1 | trading rules / fee schedule 归入 `trading` 域 | P1 | 消除每 bar 注入开销，对齐 LEAN 做法 |
| 2 | `trading` 域定义 domain event 契约 | P1 | 实时/回测共享状态变更语义 |
| 3 | `MarketSnapshot` 契约精确包含市场模拟所需字段 | P1 | 确保 `trading` 域可独立完成市场模拟 |
| 4 | Input Contract 字段需可追溯到行为域消费点（YAGNI） | P2 | 防止厚输入模型退化 |
| 5 | kernel 提供极简 `CheckResult` 值对象 | P2 | 质量拆分后的共享基座 |
| 6 | 评估 `decisioning` 命名替换为 `strategy` 或 `alpha` | P3 | 可读性优化 |
| 7 | 关注 `analytics` 内部是否需要进一步拆分 | P3 | 内聚性优化 |
