# 日频策略优先下的统一量化平台差距分析与 V1 设计

**日期**: 2026-03-19
**状态**: 已确认混合范式方向，StrategySpec 设计待深化
**定位**: 平台级分析与设计文档
**适用范围**:
- 终局按完整量化平台设计
- 当前实施优先日频研究、回测、调仓建议闭环
- 优先覆盖 ETF 轮动、趋势波段、部分选股与趋势波段策略
- 明确暂缓实时链路与实盘执行对接

---

## 1. 结论摘要

### 1.1 核心判断

Ditto 当前已经具备一个强内核，但尚未形成一个完整产品化平台。

- **强内核**: `unified-feature-factor-engine` 已基本形成平台内核 v1
- **弱上层**: 策略抽象、组合构建、调仓建议、API、Web 仍未接成闭环
- **正确方向**: 应继续坚持“统一平台”设计，而不是退化为若干孤立策略脚本
- **当前主线**: 实施上优先走“日频研究/回测/调仓建议闭环”，但架构上必须为完整平台留口

### 1.2 完成度判断

按“完整量化平台”视角拆分，当前完成度大致如下：

| 层次 | 当前完成度 | 判断 |
|------|-----------|------|
| 数据真相层 | 85-90% | 已接近可长期复用基础设施 |
| 统一特征/因子引擎 | 80-90% | 已具备平台内核特征 |
| 研究与评估层 | 65-75% | 能评估因子，但未形成研究工作流闭环 |
| 策略抽象层 | 20-30% | 文档多、真实实现少 |
| 组合/仓位/调仓建议层 | 15-25% | 关键能力尚未落地 |
| API 产品层 | 10-20% | 市场/元数据接口为主，策略接口几乎空白 |
| Web 工作台 | 0-10% | 当前只有 README，无真实页面实现 |
| 实时/实盘层 | Deferred | 当前不应作为主线阻塞项 |

### 1.3 当前最关键的系统性差距

当前最缺的不是再补一批底层表达式算子，而是补齐以下四层：

1. `策略定义层`
2. `信号 -> 目标仓位 -> 调仓计划` 决策层
3. `日频回测 + 组合约束 + 成本模型` 闭环
4. `API/Web 研究工作台`

一句话概括：

> **Ditto 已经先长出了很强的因子内核，但策略产品层和交互层还没有接上。**

---

## 2. 分析边界与设计原则

### 2.1 当前阶段边界

当前阶段的设计与实施边界应明确为：

- **必须服务**:
  - ETF 轮动策略
  - ETF 趋势波段策略
  - 股票选股与趋势波段策略
  - 日频研究、回测、调仓建议
  - API 与 Web 工作台
- **明确暂缓**:
  - 实时流式链路
  - 在线状态存储
  - 实盘执行对接
  - BrokerAdapter
  - 分钟级 `grain="1m"` 主路径

### 2.2 总体原则

1. **设计按完整平台统一**
   - 当前只做日频，不代表模型与边界只能服务日频
2. **实施按闭环优先**
   - 先把研究、回测、调仓建议跑通，再考虑执行
3. **对象先统一，再补能力**
   - 先统一核心对象，再建设 API/Web/后续链路
4. **不做半套实时**
   - Deferred 能力必须保留接口，不做低完成度实现
5. **策略不是脚本，而是一等对象**
   - 因子已有 `DerivedSpec`，策略也必须有统一语义模型

---

## 3. 现状核对与仓库证据

### 3.1 已明显落地的部分

以下能力已在当前仓库中形成真实代码与文档一致性：

- 统一表达式 DSL、Pratt Parser、AST、Analyzer、Codegen
- `DerivedSpec` 统一语义模型
- artifact-first 物化主链
- offline/serving 查询 facade
- Research Dataset / Spine Snapshot
- ETF 数据作为因子输入
- 因子评估、IC、分层收益、Fama-MacBeth、正交化
- Publication / Shadow / Certification / Cascade Invalidation

关键证据：

- `packages/core/src/ditto_core/engine/README.md`
- `apps/port/src/ditto_port/services/derived/runtime_input.py`
- `apps/port/src/ditto_port/services/derived/evaluation_facade.py`
- `apps/port/src/ditto_port/services/derived/factor_orthogonalization_service.py`
- `docs/design/unified-feature-factor-engine/main-design.md`
- `docs/plans/2026-03-18-unified-engine-convergence-plan.md`

### 3.2 已关闭或部分关闭的历史缺口

相较于 2026-03-18 的 readiness gap analysis，以下事项已经关闭或显著推进：

- ETF 输入命名空间与 ETF 复权查询
- 因子评估体系
- Universe 过滤能力中的 `min_list_days`
- Universe 集合运算
- `TradingSettings` 与 `Settings` 聚合
- `LateArrivalPolicy` 研究语义侧定义

说明：

- 这意味着不能再简单把 2026-03-18 文档中所有 gap 视作“当前现状”
- 需要区分“历史设计缺口”“已在代码实现”“对当前主线仍然阻塞”

### 3.3 仍明显空白的部分

以下部分从真实代码看仍明显未落地：

- `packages/core/src/ditto_core/strategy/__init__.py` 为空
- `packages/core/src/ditto_core/portfolio/__init__.py` 为空
- `packages/core/src/ditto_core/strategy/` 与 `portfolio/` 无真实实现文件
- `apps/port/src/ditto_port/api/routes/portfolio.py` 仅返回 `coming soon`
- `apps/web/src/` 当前仅存在 README，无真实页面代码

结论：

> **策略层、组合层、产品层目前仍主要停留在设计与规划态，而非可用态。**

---

## 4. 与业界最佳实践的对比判断

### 4.1 当前系统最接近的业界能力形态

从能力气质看，Ditto 当前更接近以下组合：

- `dbt/Feast` 风格的离线语义与物化治理
- `Alphalens/Qlib` 风格的研究与评估雏形
- 仍未达到机构常见的“研究工作台 + 组合决策 + 执行衔接”完整闭环

### 4.2 已对齐的最佳实践

以下部分与业界成熟体系方向一致：

- **统一语义模型**
  - 类似 dbt/Feast 的声明式定义与治理思路
- **离线真相层优先**
  - 与 Feast 的 offline-first 思路一致
- **发布安全与版本治理**
  - 类似 dbt 的环境、产物、变更治理
- **PIT 与研究快照**
  - 对量化研究是高价值设计，优于多数 notebook 风格项目

### 4.3 明显落后的最佳实践

当前与 Qlib / Alphalens / 机构研究平台相比，最关键的差距不在底层计算，而在以下四块：

1. **Strategy as Data**
   - 缺少策略的一等语义模型
2. **Experiment Management**
   - 缺少策略实验记录、参数版本、结果归档
3. **Portfolio Decision Layer**
   - 缺少从研究结果到目标仓位/调仓计划的标准化层
4. **Productized Research Surface**
   - 缺少研究 API 和可操作 Web 工作台

### 4.4 业界对标的设计启发

| 业界系统 | 可借鉴点 | 对 Ditto 的启发 |
|---------|---------|----------------|
| dbt | 声明式模型、测试、文档、状态感知构建 | 强化策略与研究产物的治理方式 |
| Feast | Offline/Online 分离、Registry、Materialization | 保持冷/热分离，但当前先只落离线主链 |
| Alphalens | 标准化 tear sheet | Web 与 API 侧统一因子/策略评估输出 |
| Qlib | 实验记录、任务编排、回测闭环 | 建立 `strategy_run` 与实验归档体系 |
| VectorBT | 向量化参数扫描 | V1 回测可优先采用向量化日频模式 |

---

## 5. 当前主线策略的能力需求拆解

### 5.1 ETF 轮动策略

ETF 轮动的核心不是复杂执行，而是：

- Universe 管理
- 横截面评分
- Regime Overlay
- 调仓日历
- 目标仓位分配
- 成本后收益评估
- 调仓建议输出

因此必须具备：

- ETF universe registry
- 多因子打分与排序
- TopN 选择器
- 权重分配器
- 月/周调仓规则
- 换手与成本评估
- 调仓计划输出

### 5.2 趋势波段策略

趋势波段策略与轮动策略共享大量基础设施，但额外更依赖：

- 趋势信号规则编排
- 进出场条件表达
- 止盈/止损/回撤控制
- 趋势过滤与 regime 联动
- 目标仓位的时间序列平滑

因此要求平台能表达：

- 策略规则组合
- 目标仓位动态缩放
- 风险预算联动
- 调仓原因可解释输出

### 5.3 股票选股与趋势波段

股票策略相较 ETF 会新增：

- Universe 过滤
- ST/停牌/退市过滤
- 新股过滤
- 流动性过滤
- 行业中性或风格约束
- 组合集中度控制

当前 Metadata 与 Market 基础设施已有一定支持，但还缺少被统一消费的策略层。

---

## 6. V1 必须补齐的功能

### 6.1 必须新增的核心语义对象

当前平台缺少一组能把研究、回测、调仓建议串起来的统一对象。建议补齐：

### 6.1.1 `StrategySpec`

职责：

- 定义一个策略是什么
- 绑定 universe、因子、评分、rebalance、约束、成本、基准、输出模式

建议字段：

- `strategy_id`
- `strategy_type`
- `asset_class`
- `universe_id`
- `factor_inputs`
- `score_formula`
- `rebalance_rule`
- `position_policy`
- `risk_constraints`
- `cost_model`
- `benchmark`
- `regime_overlay`
- `tags`

### 6.1.2 `StrategyRun`

职责：

- 表示一次研究/回测/调仓建议运行

建议字段：

- `run_id`
- `strategy_id`
- `spec_version`
- `start`
- `end`
- `asof`
- `parameters`
- `input_snapshot_refs`
- `status`
- `metrics_summary`
- `artifacts`

### 6.1.3 `SignalSnapshot`

职责：

- 表示某日策略对某标的的方向判断与强度

说明：

- V1 可以不把 `signal` 作为 unified derived engine 的激活 role
- 但策略域必须有自己的信号对象

### 6.1.4 `TargetPortfolio`

职责：

- 表示某个交易日希望持有的目标仓位

建议字段：

- `trade_date`
- `strategy_id`
- `positions`
- `cash_target`
- `gross_exposure`
- `net_exposure`
- `risk_budget_used`

### 6.1.5 `RebalancePlan`

职责：

- 连接“当前持仓”和“目标持仓”的调仓建议对象

建议字段：

- `plan_id`
- `trade_date`
- `current_positions`
- `target_positions`
- `buy_list`
- `sell_list`
- `estimated_turnover`
- `estimated_cost`
- `violations`
- `rationale`

---

### 6.2 必须建设的策略域能力

### P0: 策略抽象层

必须新增：

- `StrategySpec`
- `StrategyTemplate`
- `StrategyContext`
- `StrategyRunner`
- `ScoreEngine`
- `SelectionEngine`

建议首批模板：

- `etf_rotation`
- `etf_trend_swing`
- `stock_selection_trend`

注意：

- 模板不是 hardcode 页面逻辑
- 模板应是统一语义模型上的预配置

### P0: 组合与仓位层

必须新增：

- 权重分配器
- 目标仓位生成器
- 风险约束检查器
- 调仓计划生成器

首批支持能力：

- 等权
- score-weight
- volatility-scaling
- max weight
- min holdings
- cash floor
- turnover cap

### P0: 日频回测闭环

必须新增：

- 日频向量化回测主路径
- 调仓日历驱动
- 成本与滑点简化模型
- 净值、回撤、换手、成本、归因输出
- 每日持仓与调仓记录

V1 回测目标应聚焦：

- 研究可信
- 产物可归档
- 与调仓建议输出共享同一套策略对象

### P0: API 与 Web

后端必须新增：

- 策略列表/详情
- 创建策略运行
- 查询回测结果
- 查询目标持仓
- 查询调仓建议
- 查询策略评估报告

前端必须新增：

- 策略工作台首页
- 策略详情页
- 回测结果页
- 调仓建议页
- 因子/评分拆解页

---

### 6.3 必须建设的研究工作流能力

当前已有因子评估，但没有策略实验工作流。建议 V1 补齐：

- 实验参数管理
- baseline 对比
- benchmark 对比
- run 级指标快照
- 研究产物归档
- 关键报告标准化

建议首批报告对象：

- `FactorEvaluationReport`
- `StrategyBacktestReport`
- `RebalanceRecommendationReport`

---

## 7. 可以明确 Deferred 的能力

以下能力应明确保留接口，但不纳入当前主线交付：

- 实时 feature/signal online serving
- Kvrocks/QuestDB 热态状态存储
- 分钟级增量物化主路径
- 订单撮合模拟器细节深化
- BrokerAdapter
- 实盘下单回报与成交管理
- 实时风控联动
- 分布式执行与锁管理深化

原则：

> **Deferred 不是否定，而是明确“不进入当前主线实现”，只在接口边界上留口。**

---

## 8. 平台目标态设计建议

### 8.1 统一平台分层

建议将终局平台稳定为以下七层：

1. 数据真相层
2. 统一特征/因子引擎
3. 研究与评估层
4. 策略抽象层
5. 组合/仓位/调仓建议层
6. 执行适配层
7. API / Web / 观测层

其中当前实施优先顺序应为：

1. `2 -> 3 -> 4 -> 5 -> 6(留口不实现) -> 7`

### 8.2 V1 的统一主链

建议将当前主链标准化为：

```text
Market Truth / Metadata
  -> Derived Features / Factors
  -> StrategySpec + StrategyRunner
  -> SignalSnapshot
  -> TargetPortfolio
  -> RebalancePlan
  -> Backtest / Recommendation Report
  -> API / Web
```

关键点：

- **研究与调仓建议必须共用同一套策略对象**
- **回测不是单独模块，而是 StrategyRunner 的一种运行模式**
- **未来纸面执行/实盘执行只继续消费 `RebalancePlan`**

### 8.3 对 unified derived engine 的定位修正

统一因子引擎不应直接膨胀成整个策略平台，而应被定位为：

- **平台内核之一**
- **研究与决策的数据/计算基座**
- **不是策略编排、组合构建、执行控制的唯一承载者**

这点很关键。

否则会出现两种风险：

- 要么把 engine 塞成“大一统巨物”
- 要么上层策略逻辑各写各的，重新制造语义分裂

正确做法是：

- `engine` 负责统一语义、物化、评估、研究数据
- `strategy/portfolio` 负责策略与决策语义
- `port/api/web` 负责产品化暴露

---

## 9. 面向当前主线策略的优先级建议

### 9.1 第一优先级：ETF 轮动闭环

这是最适合作为平台第一条策略模板的原因：

- universe 更稳定
- 流动性更好
- 组合规模更小
- 调仓规则更清晰
- 更适合先完成 API/Web 产品化

第一条完整闭环建议：

- ETF universe
- 因子评分
- TopN 选择
- 权重生成
- 回测
- 调仓建议
- Web 展示

### 9.2 第二优先级：ETF 趋势波段模板

在 ETF 轮动闭环完成后，可以复用：

- 相同回测主链
- 相同组合对象
- 相同调仓建议对象

新增的主要是：

- 趋势规则模板
- 入场/减仓/退出规则
- 波动率或 drawdown 控制

### 9.3 第三优先级：股票选股趋势模板

在此之前再推进股票模板，性价比更高，因为届时：

- Universe 过滤链路已被验证
- API/Web 结构已成型
- 组合/仓位/调仓建议对象已稳定

股票模板主要是增加：

- universe 过滤器
- 选股排序器
- 行业/风格约束

---

## 10. API 与 Web 的 V1 目标态

### 10.1 API 侧

当前 API 最大问题不是不够多，而是没有围绕“策略工作流”建模。V1 应改为围绕以下资源设计：

- `/strategies`
- `/strategy-runs`
- `/backtests`
- `/portfolio-targets`
- `/rebalance-plans`
- `/factor-reports`

典型能力：

- 创建一次策略运行
- 获取某次回测结果
- 获取最近一次调仓建议
- 获取某次运行的因子/评分分解

### 10.2 Web 侧

当前 Web 侧还是空白，应优先建设研究工作台，而不是营销式 dashboard。

建议页面：

- `Strategy Lab`
  - 策略列表、参数配置、运行入口
- `Backtest Detail`
  - 净值曲线、回撤、换手、归因、基准对比
- `Rebalance Center`
  - 当前建议买卖、目标仓位、调仓原因
- `Factor Drilldown`
  - 因子评分、排名变化、策略解释

### 10.3 V1 UI 原则

- 先服务研究与决策，不追求炫技
- 页面围绕真实对象展开，而不是围绕概念命名
- 所有页面都应能追溯到 `strategy_run`

---

## 11. 建议实施路线

### Phase A: 平台语义补齐

- 定义 `StrategySpec`
- 定义 `StrategyRun`
- 定义 `SignalSnapshot`
- 定义 `TargetPortfolio`
- 定义 `RebalancePlan`

### Phase B: ETF 轮动闭环

- ETF 策略模板
- 日频回测主链
- 目标仓位与调仓建议
- API
- Web 页面

### Phase C: ETF 趋势波段

- 趋势策略模板
- 风险约束扩展
- 调仓解释增强

### Phase D: 股票选股趋势

- 股票 universe 过滤模板
- 排序器与约束器
- 组合侧风险暴露控制

### Phase E: Deferred 能力接口固化

- 执行适配接口
- 线上状态接口
- signal/order intent 契约

---

## 12. 后续建议逐章节深聊的专题

建议后续按以下顺序继续细化：

1. `StrategySpec` 设计 ✅ (§15 已完成范式调研与决策，待字段细化)
2. `TargetPortfolio / RebalancePlan` 对象设计
3. 日频回测引擎与运行模式
4. ETF 轮动模板设计
5. ETF 趋势波段模板设计
6. 股票选股趋势模板设计
7. API 资源模型
8. Web 工作台信息架构
9. Deferred 接口设计

---

## 13. 本文档的最终判断

### 13.1 应坚持什么

- 坚持统一平台设计
- 坚持语义统一、执行分层
- 坚持日频闭环优先

### 13.2 不应做什么

- 不应把当前主线分散到实时/实盘
- 不应让策略层继续停留在 README
- 不应让 API/Web 脱离统一对象模型各自生长

### 13.3 当前最重要的架构动作

> **在现有 unified derived engine 之上，补出 Strategy / Portfolio / Rebalance 三层统一语义，并围绕它们建设 API 与 Web。**

这一步完成后，Ditto 才会从“强大的因子内核”真正进入“平台化量化系统”的阶段。

---

## 14. 参考与证据

### 14.1 仓库内关键文档

- `docs/design/unified-feature-factor-engine/main-design.md`
- `docs/plans/2026-03-18-unified-engine-convergence-plan.md`
- `docs/plans/2026-03-18-daily-strategy-readiness-gap-analysis.md`
- `docs/plans/2026-03-19-p1p2-closure-plan.md`
- `docs/plans/2026-03-05-industry-benchmark-analysis.md`
- `docs/design/PRD.md`
- `docs/design/12_quant_architecture_alignment.md`

### 14.2 仓库内关键代码证据

- `packages/core/src/ditto_core/engine/README.md`
- `apps/port/src/ditto_port/services/derived/runtime_input.py`
- `apps/port/src/ditto_port/services/derived/evaluation_facade.py`
- `apps/port/src/ditto_port/services/derived/factor_orthogonalization_service.py`
- `packages/core/src/ditto_core/strategy/__init__.py`
- `packages/core/src/ditto_core/portfolio/__init__.py`
- `apps/port/src/ditto_port/api/routes/portfolio.py`

### 14.3 外部最佳实践参考

- Feast Documentation: https://docs.feast.dev/
- dbt Documentation: https://docs.getdbt.com/docs/introduction
- Alphalens Documentation: https://quantopian.github.io/alphalens/
- Qlib Recorder / Experiment Management: https://qlib.readthedocs.io/en/stable/component/recorder.html

---

## 15. StrategySpec 深入设计：业界调研与范式决策

**日期**: 2026-03-20
**状态**: 已确认混合范式方向，待逐阶段细化字段设计

### 15.1 业界 Alpha/策略建模范式对比

#### 15.1.1 三种范式

业界量化平台对策略/Alpha 的建模存在三种典型范式：

| 范式 | 核心思想 | 代表 | 优势 | 劣势 |
|------|---------|------|------|------|
| **纯表达式** | Alpha = 一条公式 + 配置 | WorldQuant BRAIN, Qlib, AlphaAgent | 可序列化、可缓存、可组合、版本控制友好 | 复杂逻辑（条件分支、状态机）难以表达 |
| **纯过程式** | Alpha = Python 类/函数 | QuantConnect Alpha Model | 完全自由、任意逻辑 | 不可序列化、难以复用、难以组合、调试困难 |
| **混合式** | 信号用表达式，编排用 Pipeline，风险用约束 | AQR, Man AHL, WorldQuant（上层组合） | 兼顾可复现性与灵活性 | 设计复杂度最高 |

#### 15.1.2 各平台详细对比

**WorldQuant BRAIN（纯表达式）**

- Alpha = FAST 语言公式 + 配置参数
- 评估方式：虚拟股票组合模拟 → Sharpe / Turnover / Fitness / Drawdown / Alpha Decay
- 多 Alpha 组合：协方差矩阵优化 → mega-alpha（4000+ alpha 组合）
- 行业中性化：`IndNeutralize(x, IndClass.sector)` 作为一等算子
- 延迟约定：delay-0（当日） / delay-1（前日）
- 核心洞察：Alpha 是短命资产，组合是抗衰减手段

**Qlib Alpha158/360（纯表达式 + ML Pipeline）**

- Alpha = `$close` 风格表达式字符串
- 158/360 个预定义因子表达式（KBAR、Volume、Price-Volume 交互）
- Factor Factory = `DataHandlerLP` + `QlibDataLoader`
- 多级缓存：MemCacheUnit → ExpressionCache → DatasetCache
- 表达式直接喂入 ML 模型（LightGBM 等）
- 标签表达式支持前视：`Ref($close, -2)/Ref($close, -1) - 1`

**QuantConnect Alpha Streams（纯过程式）**

- Alpha = Python 类，实现 `AlphaModel` 接口
- 输出 = `Insight` 对象流（Symbol, Period, Direction, Magnitude, Confidence, Weight）
- 五模块框架：Universe → Alpha → Portfolio Construction → Risk Management → Execution
- Alpha Streams 市场：Alpha 可交易、可授权、可评分
- 核心洞察：Insight 作为一等对象，携带丰富元数据（置信度、权重、来源）

**Numerai Signals（极简式）**

- Signal = `(ticker, prediction_value)` 对，值域 [0, 1]
- 强调信号原创性（与现有信号的 neutralization）
- Churn 阈值（15%）：换手过高不予奖励
- NMR 质押机制：用经济激励保证信号质量
- 核心洞察：不是预测收益，而是找原创信号

**AlphaAgent（2025，开源）**

- Alpha = AST（抽象语法树）
- 三重正则化：原创性（AST 相似度）、假设-因子对齐（LLM 评估）、复杂度控制
- 显式 Alpha Decay 跟踪（多 regime 下 IC 退化曲线）

**Man AHL / AQR（混合式）**

- 信号层：因子库（表达式/声明式）
- 编排层：Pipeline（声明式配置）
- 约束层：风险预算 / 风险模型（规则引擎）
- 研究/探索：Python 自由编码
- 成熟后沉淀：Python 原型 → 提炼为声明式组件

#### 15.1.3 Ditto 表达式引擎与 WQ101 的覆盖度

Ditto 当前已能表达 WQ101 中 ~90% 的 Alpha：

| WQ 算子 | Ditto 对应 | 状态 |
|---------|-----------|------|
| `delay(x,d)` / `delta(x,d)` | `ts_delay` / `ts_delta` | 已有 |
| `correlation(x,y,d)` / `covariance(x,y,d)` | `ts_corr` / `ts_cov` | 已有 |
| `ts_rank` / `ts_argmax` / `ts_argmin` | 完全对应 | 已有 |
| `ts_min` / `ts_max` / `sum` / `stddev` | 完全对应 | 已有 |
| `decay_linear` | `ts_decay_linear` | 已有 |
| `rank` / `scale` | `cs_rank` / `cs_scale` | 已有 |
| `IndNeutralize(x,g)` | `group_zscore` | 近似 |
| `signedpower(x,a)` | `power(x,a)` | 缺 sign 语义 |
| `product(x,d)` | — | 缺失 |
| `ts_skew` / `ts_kurt` / `ts_slope` | — | 缺失 |

### 15.2 范式决策：混合范式

**决策：Ditto 采用混合范式。**

理由：

1. **Ditto 已有强表达式内核**（Engine / FactorSpec / DerivedSpec），纯过程式会浪费这部分投入
2. **复杂策略需要 Python 灵活性**（条件分支、状态机、外部数据），纯表达式无法覆盖
3. **业界共识**：AQR / Man AHL / Qlib / WorldQuant 上层组合均采用混合路线
4. **可演进性**：Python 原型成熟后可沉淀为声明式组件

### 15.3 混合范式架构

```
                    ┌─────────────────────────────────────┐
                    │        Risk Budget Layer            │  ← 约束层：规则引擎
                    │  vol_target, drawdown_limit, ...    │
                    └──────────┬──────────┬───────────────┘
                               │          │
              ┌────────────────▼──┐  ┌────▼──────────────┐
              │  Strategy Pod A   │  │  Strategy Pod B   │  ← 策略 = 独立 Pod
              │  ┌──────────────┐│  │  ┌──────────────┐ │
              │  │ Signal Layer ││  │  │ Signal Layer │ │  ← 信号层：表达式 or Python
              │  │ expression   ││  │  │ expression   │ │
              │  └──────┬───────┘│  │  └──────┬───────┘ │
              │  ┌──────▼───────┐│  │  ┌──────▼───────┐ │
              │  │ Score/Select ││  │  │ Score/Select │ │  ← 评分/选股：声明式 or Python
              │  └──────┬───────┘│  │  └──────┬───────┘ │
              │  ┌──────▼───────┐│  │  ┌──────▼───────┐ │
              │  │ Position Sizing│ │  │  │ Position Sizing│ │ ← 仓位：声明式 or Python
              │  └──────┬───────┘│  │  └──────┬───────┘ │
              └─────────┼────────┘  └─────────┼──────────┘
                        └────────┬────────────┘
                         Portfolio Layer              ← 组合层
```

**三层规律**：

- **信号层**：用表达式（可序列化、可缓存、可组合、可版本控制）
- **编排层**：用声明式 Spec（可复现、可参数化、可 A/B 测试）
- **约束层**：用规则引擎（可插拔、可叠加、可审计）

### 15.4 Protocol 分发设计：声明式与命令式统一

**核心设计**：StrategySpec 的每个 Pipeline 阶段都接受两种输入 — 声明式（Spec/字符串）或命令式（Python Callable）。Pipeline 内部通过 Protocol 分发，不关心具体实现方式。

```python
# ─── 信号层：表达式 or Python ───

# 方式 A：表达式（声明式）
momentum = FactorSpec(
    name="momentum_12m_skip1",
    expression="ts_pct_change(market.close, 252) / ts_pct_change(market.close, 21)",
    role=DerivedRole.SIGNAL,
)

# 方式 B：Python 函数（命令式 — 完全自由）
def regime_aware_momentum(ctx: SignalContext) -> pl.DataFrame:
    """根据市场状态切换动量窗口 — 表达式写不了这种逻辑"""
    regime = ctx.query("market_regime")
    bars = ctx.query("market.close")
    result = {}
    for instrument in ctx.universe:
        prices = bars.filter(instrument_id=instrument).sort("trade_date")
        if regime.current == "bull":
            window = 63
        elif regime.current == "bear":
            window = 252
        else:
            window = 126
        ret = prices.tail(window)
        if len(ret) < window:
            continue
        mom = ret["close"].iloc[-1] / ret["close"].iloc[0] - 1
        result[instrument] = mom
    return pl.DataFrame({"instrument_id": list(result.keys()),
                         "signal": list(result.values())})

# ─── 两种方式在同一个策略里混用 ───

strategy = StrategySpec(
    name="hybrid_etf_rotation",
    universe="csi_etf_broad",
    signals=[
        vol_adjusted,                     # FactorSpec — 表达式
        CallableSignal(regime_aware_momentum),  # Python 函数 — 自定义逻辑
    ],
    scorer=CallableScorer(my_custom_scoring),  # 或 "equal_weight"
    position_sizer=CallableSizer(adaptive_vol_target),  # 或 "equal_weight"
)
```

**Pipeline 内部调度**：

```python
class Stage(Protocol):
    def execute(self, ctx: Context, input: DataFrame) -> DataFrame: ...

def run_stage(stage: Stage, ctx, data):
    match stage:
        case FactorSpec():          return eval_expression(stage.expression, ctx)
        case CallableSignal(fn):    return fn(ctx)
        case str():                 return BUILTIN_DISPATCH[stage](ctx, data)
```

### 15.5 三种范式 Demo 对比

**同一策略：动量+波动率 ETF 轮动（月度换仓，选前3名，目标波动率 12%）**

#### 范式 A：纯表达式（WorldQuant 风格）

```python
etf_rotation_alpha = AlphaSpec(
    name="etf_momentum_vol_adjusted",
    universe="csi_etf_broad",
    expression="""
        momentum = ts_pct_change(market.close, 252) / ts_pct_change(market.close, 21)
        vol = ts_std(market.returns_1, 60) * sqrt(252)
        signal = momentum / vol
        cs_rank(signal)
    """,
    frequency="M",
    top_k=3,
    neutralization=None,
)
```

局限：换仓频率、选股数、目标波动率全是魔法参数；止损、波动率调仓等复杂逻辑无法表达。

#### 范式 B：纯过程式（QuantConnect 风格）

```python
class EtfRotationModel(AlphaModel):
    def __init__(self, lookback=252, skip=21, vol_window=60, top_k=3):
        self.lookback = lookback
        self.skip = skip
        self.vol_window = vol_window
        self.top_k = top_k
        self._last_rebalance = None

    def update(self, algorithm, data):
        today = algorithm.time.date()
        if not self._should_rebalance(today):
            return []
        bars = {}
        for symbol in algorithm.universe.selected:
            history = data.history(symbol, self.lookback + self.skip, "1d")
            if len(history) < self.lookback:
                continue
            close = history["close"]
            returns = close.pct_change()
            mom = close.iloc[-1] / close.iloc[-(self.lookback + self.skip)] - 1
            vol = returns.iloc[-self.vol_window:].std() * np.sqrt(252)
            bars[symbol] = {"momentum": mom, "vol": vol}
        scored = sorted(bars.items(),
                        key=lambda x: x[1]["momentum"] / x[1]["vol"],
                        reverse=True)
        selected = [s[0] for s in scored[:self.top_k]]
        weight = 1.0 / self.top_k
        return [Insight.price(s, timedelta(days=30), InsightDirection.UP,
                              weight=weight, source_model=self.__class__.__name__)
                for s in selected]
```

局限：业务逻辑绑死在类里，无法序列化/版本控制/复用信号；换策略就要重写整个类。

#### 范式 C：混合范式（推荐 — AQR / Man AHL 风格）

```python
# Layer 1: Signal（纯表达式）
momentum = FactorSpec(
    name="momentum_12m_skip1",
    expression="ts_pct_change(market.close, 252) / ts_pct_change(market.close, 21)",
    role=DerivedRole.SIGNAL,
)
vol_adjusted = FactorSpec(
    name="risk_adjusted_momentum",
    expression="momentum_12m_skip1 / (ts_std(market.returns_1, 60) * sqrt(252))",
    dependencies=[momentum.name],
    role=DerivedRole.SIGNAL,
)

# Layer 2: Pipeline（声明式编排）
strategy = StrategySpec(
    name="etf_momentum_rotation",
    universe="csi_etf_broad",
    signals=[vol_adjusted],
    scorer="equal_weight",
    selector=SelectorSpec(method="top_k", params={"k": 3, "min_count": 1}),
    position_sizer=PositionSizerSpec(
        method="equal_weight",
        params={"target_vol": 0.12},
    ),
    execution=ExecutionSpec(
        frequency="M",
        rebalance_rule="calendar",
    ),
    constraints=[
        ConstraintSpec(type="max_weight_per_instrument", value=0.40),
        ConstraintSpec(type="max_turnover", value=0.50),
        ConstraintSpec(type="max_drawdown", value=0.15, action="reduce_to_half"),
    ],
    evaluation=EvaluationSpec(
        metrics=["sharpe", "sortino", "max_drawdown", "turnover", "calmar"],
        benchmark="000300.SH",
    ),
)
```

#### 三范式对比矩阵

| 维度 | 纯表达式 | 纯过程式 | 混合范式 |
|------|---------|---------|---------|
| 信号可复用 | 可组合 | 绑死在类里 | 可组合 |
| 复杂逻辑 | 表达困难 | 灵活 | 可插拔 |
| 可序列化 | 完全可 | 不可 | 结构可 |
| 版本控制 | 表达式 diff | Git diff 代码 | 结构 diff |
| 调参 | 改参数 | 改代码/参数 | 改 spec |
| A/B 测试 | 天然支持 | 需要重写 | 天然支持 |
| 多策略组合 | 困难 | 困难 | Risk Budget 层统一 |
| 业界对标 | WorldQuant | QuantConnect | AQR, Man AHL |

### 15.6 业界 80/20 法则

| 机构 | 声明式部分 | Python/自由编码部分 |
|------|-----------|-------------------|
| AQR | 因子库（表达式） | 研究员用 Python 做新因子探索 |
| Man AHL | Pipelines（声明式） | 量化研究员用 Python 写新策略原型 |
| WorldQuant | FAST 表达式（核心） | 上层组合/风控用内部语言 |
| Qlib | 表达式因子 + 内置模型 | 自定义 Handler 用 Python |
| QuantConnect | 框架是声明式 | Alpha Model 全部 Python |

**统一规律**：80% 常规策略走声明式 Pipeline（快速、可复现、可组合），20% 创新策略用 Python 探索（自由、灵活），成熟后再提炼为声明式组件沉淀。

### 15.7 从调研推导的设计原则

1. **StrategySpec 是基座，不是牢笼**：每个阶段通过 Protocol 接受声明式或命令式输入
2. **信号层表达式优先**：Ditto 已有引擎，应最大化复用；表达式信号可缓存/组合/版本控制
3. **编排层声明式优先**：Pipeline 配置可复现、可参数扫描、可 A/B 测试
4. **Python 是一等公民**：CallableSignal / CallableScorer / CallableSizer 等逃生舱始终可用
5. **沉淀路径**：Python 原型 → 验证有效 → 提炼为 FactorSpec / 内置方法名 → 移入声明式层

### 15.8 Pipeline 各阶段字段设计

**完整 Pipeline**：

```
Universe → Signal → Score → Select → Size → Risk Check → Execute → Output
```

#### 15.8.1 Universe 阶段

Universe 决定"策略在哪些标的上运行"。

**业界对比**：

| 机构 | 做法 | 特点 |
|------|------|------|
| WorldQuant | 全市场 ~4000 股，信号自动为 0 | 简单粗暴 |
| Qlib | `D.instruments('csi300')` 字符串标识 | 简洁，预定义集合 |
| QuantConnect | `UniverseSelectionModel` 类，动态调整 | 灵活但重量级 |
| AQR | 静态规则 + 定期再平衡 | 规则化，可复现 |

**Ditto 场景差异**：

- ETF 轮动：静态列表或规则筛选（规模、流动性），变化少
- 股票选股：动态过滤链（ST/停牌/新股 → 流动性 → 行业），变化频繁

**设计**：Universe 分两层 — 基础集合 + 过滤规则。

```python
@dataclass
class UniverseFilter:
    """单个过滤规则，支持声明式和命令式"""
    name: str
    source: InlineExpression | CallableFilter

@dataclass
class UniverseSpec:
    """策略 Universe 定义"""
    base: str | UniverseRef              # 基础集合（"csi300", "csi_etf_broad"）
    filters: list[UniverseFilter]        # 额外过滤规则（叠加在 base 之上）
    rebalance: Frequency                 # Universe 本身的更新频率（可慢于策略换仓）
```

使用示例：

```python
universe = UniverseSpec(
    base="csi_etf_broad",
    filters=[
        UniverseFilter(name="min_size", source=InlineExpression("market.cap > 1e9")),
        UniverseFilter(name="liquidity", source=InlineExpression("ts_mean(market.volume, 20) > 1e6")),
        UniverseFilter(name="status", source=CallableFilter(exclude_st_and_suspended)),
    ],
    rebalance=Frequency("M"),  # 月度更新 Universe
)
```

#### 15.8.2 Signal 信号阶段

Signal 职责：**产出原始信号值，不做组合**。组合逻辑在下游 Score 阶段。

**三种信号来源**：

| 来源 | 形式 | 场景 |
|------|------|------|
| 引用已有 Factor | `FactorRef` | 复用引擎内已发布的因子 |
| 内联表达式 | `InlineExpression` | 策略专属的简单信号 |
| Python Callable | `CallableSignal` | 复杂逻辑（regime 切换等） |

```python
@dataclass
class SignalSpec:
    """单个信号定义"""
    name: str
    source: FactorRef | InlineExpression | CallableSignal
    dependencies: list[str] = field(default_factory=list)
```

使用示例：

```python
strategy = StrategySpec(
    signals=[
        SignalSpec(name="momentum", source=FactorRef("momentum_12m_skip1")),
        SignalSpec(name="cheapness", source=InlineExpression("market.pe_ttm < cs_median(market.pe_ttm)")),
        SignalSpec(name="regime_signal", source=CallableSignal(regime_aware_momentum)),
    ],
    # ...
)
```

#### 15.8.3 Score 评分阶段

Score 职责：**将多个原始信号综合成一个最终得分**。Signal 产原始值，Score 做组合。

**业界常见做法**：

| 方法 | 说明 | 适用场景 |
|------|------|---------|
| `equal_weight` | 信号等权加总 | 无明确优劣关系 |
| `rank_then_combine` | 各自 rank 归一化后加总 | 信号量纲不同（WQ 最常用） |
| `ic_weighted` | 按历史 IC 加权 | 有历史 IC 数据 |

```python
@dataclass
class ScorerSpec:
    """评分器定义"""
    method: str | CallableScorer       # 内置方法名 or Python 自定义
    params: dict = field(default_factory=dict)
```

使用示例：

```python
# WQ 标准做法：先 rank 再组合
scorer = ScorerSpec(
    method="rank_then_combine",
    params={"signal_weights": {"momentum": 0.5, "cheapness": 0.3, "volatility": -0.2}},
)

# Python 自定义
scorer = ScorerSpec(method=CallableScorer(my_custom_scoring))

# 最简默认
scorer = ScorerSpec(method="equal_weight")
```

**`rank_then_combine` 说明**：先对每个信号做 `cs_rank()` 归一化到 [0,1]，然后加权求和。不受量纲影响，对异常值鲁棒，是 WQ101 和 AlphaAgent 最常用的模式。

**V1 内置方法**：`equal_weight` / `rank_then_combine` / `ic_weighted`

#### 15.8.4 Filter 过滤阶段

Filter 职责：**硬门槛过滤**，在 Score 之后、Select 之前。用于剔除不符合条件的标的（低得分、黑名单、暂停交易等）。

与 Select 分离的理由：Filter 是二元决策（通过/排除），Select 是排名决策（选谁/选几个），两者语义不同。

```python
@dataclass
class FilterSpec:
    """硬门槛过滤"""
    name: str
    source: InlineExpression | CallableFilter
```

使用示例：

```python
filters=[
    FilterSpec(name="min_score", source=InlineExpression("composite_score > 0.2")),
    FilterSpec(name="blacklist", source=CallableFilter(exclude_suspended_etf)),
],
```

#### 15.8.5 Select 选择阶段

Select 职责：**从 Filter 后的标的池中按规则选取**。

```python
@dataclass
class SelectorSpec:
    """标的选取"""
    method: str | CallableSelector
    params: dict = field(default_factory=dict)
```

V1 内置 Selector 方法：

| 方法 | 说明 | 场景 |
|------|------|------|
| `top_k` | 取得分最高的 k 个 | ETF 轮动（选前 3 名） |
| `bottom_k` | 取得分最低的 k 个 | 反向策略 |
| `threshold` | 得分超过/低于阈值的全选 | 宽度策略 |
| `long_short` | 做多 top_k + 做空 bottom_k | 多空策略 |

使用示例：

```python
selector=SelectorSpec(method="top_k", params={"k": 5, "min_count": 1}),
# min_count: 过滤后不足 k 个时至少选几个（避免空仓）
```

#### 15.8.6 WeightAllocator 权重分配阶段

WeightAllocator 职责：**标的间权重分配**。决定每个入选标的钱分多少。

与 RiskSizer 分离的理由：标的间分配和总仓位/波动率控制是两个独立维度，拆开后可独立演进。

```python
@dataclass
class WeightAllocatorSpec:
    """标的间权重分配"""
    method: str | CallableAllocator
    params: dict = field(default_factory=dict)
```

V1 内置方法：

| 方法 | 说明 |
|------|------|
| `equal_weight` | 等权（最常用默认值） |
| `score_weight` | 按得分比例加权 |
| `risk_parity` | 风险平价（各标的波动率贡献相等） |

#### 15.8.7 RiskSizer 风险缩放阶段

RiskSizer 职责：**总仓位 / 波动率缩放**。在 WeightAllocator 产出的初始权重基础上，根据风险指标做整体缩放。

```python
@dataclass
class RiskSizerSpec:
    """总仓位 / 波动率缩放"""
    method: str | CallableSizer
    params: dict = field(default_factory=dict)
```

V1 内置方法：

| 方法 | 说明 |
|------|------|
| `full_invest` | 满仓（默认） |
| `vol_target` | 目标波动率缩放（如年化 12%） |
| `drawdown_scaling` | 回撤越大仓位越轻 |

使用示例：

```python
strategy = StrategySpec(
    # ...
    weight_allocator=WeightAllocatorSpec(method="equal_weight"),
    risk_sizer=RiskSizerSpec(
        method="vol_target",
        params={"target_vol": 0.12, "lookback": 60, "max_leverage": 1.0},
    ),
)
```

#### 15.8.8 Risk Check 约束检查阶段

Risk Check 职责：**检查目标仓位是否违规，违规时执行预设动作**。

**设计决策：V1 采用后置检查而非硬优化约束。**

理由：ETF 轮动（3-5 个标的）不需要复杂优化器；后置检查逻辑清晰、可解释、可审计；后续需要时可加 `OptimizedPortfolioConstructor` 作为 V2。

```python
class ConstraintViolationAction(str, Enum):
    REJECT = "reject"           # 拒绝整个调仓计划
    REDUCE = "reduce"           # 按比例削减至合规
    WARNING = "warning"         # 仅记录，不拦截

@dataclass
class ConstraintSpec:
    """单条风险约束"""
    type: str                    # 约束类型
    params: dict                 # 约束参数
    action: ConstraintViolationAction = ConstraintViolationAction.REDUCE
```

V1 内置约束类型：

| 类型 | 说明 | 典型参数 |
|------|------|---------|
| `max_weight_per_instrument` | 单标的最大权重 | `value: 0.40` |
| `max_sector_exposure` | 单行业最大暴露 | `value: 0.30, group: "sector"` |
| `max_turnover` | 单次最大换手率 | `value: 0.50` |
| `max_drawdown` | 最大回撤触发 | `value: 0.15` |
| `min_holdings` | 最少持仓数量 | `value: 3` |
| `cash_floor` | 最低现金比例 | `value: 0.05` |

输出：合规的目标仓位 + 违规记录（Violation 列表，用于可解释性）。

#### 15.8.9 Execute 执行阶段

Execute 职责：**决定换仓触发时机，生成交易指令，估算成本**。

**V1 范围**：触发时机 + 交易指令生成 + 成本估算合并在一起。V2 引入实盘时拆出独立 OrderBuilder。

```python
@dataclass
class ExecutionSpec:
    """执行层配置"""
    trigger: TriggerSpec
    cost_model: CostModelSpec
    batch: bool = False              # V1: 一次性执行

@dataclass
class TriggerSpec:
    """换仓触发规则"""
    method: str | CallableTrigger
    params: dict = field(default_factory=dict)

@dataclass
class CostModelSpec:
    """成本模型"""
    commission_rate: float = 0.0003   # 佣金率（万三）
    slippage_bps: float = 5.0         # 滑点（5bp）
    impact_model: str = "linear"      # 冲击模型：linear / square_root / none
```

V1 内置触发规则：

| 方法 | 说明 | 场景 |
|------|------|------|
| `calendar` | 按日历周期（月/周/季） | ETF 轮动，最常见 |
| `signal_change_pct` | 信号变化超过阈值时触发 | 减少无效换仓 |
| `volatility_trigger` | 波动率突破阈值时触发 | 风控驱动紧急调仓 |
| `composite` | 组合多个触发条件 | 月度定期 + 信号大变额外触发 |

使用示例：

```python
execution = ExecutionSpec(
    trigger=TriggerSpec(
        method="composite",
        params={
            "rules": [
                {"method": "calendar", "frequency": "M"},
                {"method": "signal_change_pct", "threshold": 0.3},
            ],
            "logic": "any",
        },
    ),
    cost_model=CostModelSpec(commission_rate=0.0003, slippage_bps=5.0),
)
```

#### 15.8.10 Output 输出阶段

Output 职责：**将 Pipeline 结果固化为一等对象**。

Pipeline 流转与输出对象的对应关系：

```
Pipeline 阶段                              输出对象
─────────────────                         ────────
Universe → Signal → Score → Filter →       SignalSnapshot
  Select →                                 （每个标的的 composite_score + 各信号分量）
  WeightAllocator → RiskSizer →            TargetPortfolio
  Risk Check →                             （合规的目标仓位 + 风险预算消耗 + 违规记录）
  Execute →                                RebalancePlan
                                           （当前 vs 目标 diff + 买卖列表 + 成本估算 + 触发原因）
```

**SignalSnapshot**：保存全部信号分量（composite_score + 各信号原始值），支持因子贡献归因分析。

**TargetPortfolio**：关联策略 spec 版本 + 风险预算消耗 + 违规记录。

**RebalancePlan** 完整字段：

```python
@dataclass
class RebalancePlan:
    plan_id: str
    trade_date: str
    strategy_id: str
    strategy_spec_version: str

    # 持仓 diff
    current_positions: dict[str, float]    # instrument_id → 当前权重
    target_positions: dict[str, float]     # instrument_id → 目标权重
    trades: list[Trade]                    # 交易指令列表

    # 成本估算
    estimated_turnover: float
    estimated_cost: float

    # 风控
    violations: list[Violation]            # 约束违规记录

    # 可解释性
    trigger_reason: str                    # 为什么触发这次调仓
    signal_snapshot_ref: str               # 关联的信号快照
```

#### 15.8.11 Pipeline 完整总览

```
Universe → Signal → Score → Filter → Select → WeightAllocator → RiskSizer → Risk Check → Execute → Output
    │         │       │       │        │            │              │          │         │        │
    │         │       │       │        │            │              │          │         │        ├─ RebalancePlan
    │         │       │       │        │            │              │          │         │        ├─ TargetPortfolio
    │         │       │       │        │            │              │          │         │        └─ SignalSnapshot
    │         │       │       │        │            │              │          │         └─ CostModel
    │         │       │       │        │            │              │          │         └─ TriggerSpec
    │         │       │       │        │            │              │          └─ ConstraintSpec[]
    │         │       │       │        │            │              └─ RiskSizerSpec
    │         │       │       │        │            └─ WeightAllocatorSpec
    │         │       │       │        └─ SelectorSpec
    │         │       │       └─ FilterSpec[]
    │         │       └─ ScorerSpec
    │         └─ SignalSpec[]
    └─ UniverseSpec
```

每个阶段均支持声明式（Spec / 内置方法名）和命令式（Callable）两种输入，通过 Protocol 统一分发。

### 15.9 剩余待讨论专题总览

#### A. StrategySpec Pipeline ✅ 全部完成

#### B. 跨阶段横切关注点（下一步）

| 专题 | 核心问题 | 优先级 |
|------|---------|--------|
| **Protocol / Callable 接口** | 每个 Pipeline 阶段的 Protocol 正式定义、Context 注入方式、类型约束 | 高 |
| **StrategyContext** | 运行时上下文：可查询什么数据、如何注入外部状态（regime/持仓）、生命周期 | 高 |
| **Risk Budget 层** | 多策略资金分配、策略间相关性处理、动态权重调整（AQR mega-alpha 思路） | 中 |
| **缺失算子补全** | ts_product / ts_skew / ts_kurt / ts_slope / signedpower 对 WQ101 的覆盖度 | 低 |

#### C. 核心语义对象细化

| 对象 | 当前状态 | 核心问题 |
|------|---------|---------|
| **StrategyRun** | §6.1.2 有初版字段 | 实验参数管理、baseline 对比、产物归档的完整设计 |
| **SignalSnapshot** | §6.1.3 有初版字段 | 信号历史存储、版本关联、衰减追踪 |
| **TargetPortfolio** | §6.1.4 有初版字段 | 仓位快照与策略 spec 版本的关联、风险预算消耗记录 |
| **RebalancePlan** | §6.1.5 有初版字段 | 调仓建议的 diff 计算、成本估算精度、rationale 可解释性 |

#### D. 回测引擎（单独讨论，不在本次范围）

#### E. 策略模板设计（单独讨论，不在本次范围）

#### F. 产品化层（单独讨论，不在本次范围）

#### G. Deferred 接口（单独讨论，不在本次范围）

#### 建议讨论顺序

```
A (Pipeline 剩余) → B (横切) → C (对象细化)
```

D / E / F / G 另开专题讨论。
