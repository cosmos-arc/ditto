# 日频策略优先下的统一量化平台差距分析与 V1 设计

**日期**: 2026-03-19
**状态**: 已确认方向，待分章节细化
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

1. `StrategySpec` 设计
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
