# Ditto V1 剩余交付计划 + V1.1 增强建议

> **创建**: 2026-04-17
> **状态**: Plan
> **前置**: V1 Sprint Phase 0-3 全部完成 + V1 Enhancement R1-R7 全部完成（含 R4 修正）
> **目标**: V1 收尾发布 + V1.1 增强路线图

---

## 一、V1 设计完成度修正

### 1.1 R4 信号推送 — 修正为已完成

设计文档标注"推迟至 V1.1"，但代码探索确认以下组件**全部就绪**：

| 组件 | 文件 | 状态 |
|------|------|------|
| DeliveryRouter | `packages/app/src/ditto_app/process/execution/delivery.py` (111 行) | 已实现 |
| AlertManager | `packages/infra/src/ditto_infra/services/notification/manager.py` | 已实现 |
| TelegramSender | `packages/infra/.../channels/telegram_sender.py` | 已实现 |
| EmailSender | `packages/infra/.../channels/email_sender.py` | 已实现 |
| WebhookSender | `packages/infra/.../channels/webhook_sender.py` | 已实现 |
| Jinja2 模板 | `templates/signal_trading_{telegram,email,webhook}.j2` | 已实现 |
| DI 注册 | `interfaces/registry/infra/signal_delivery.py` | 已实现 |
| 单元测试 | `app/tests/unit/process/execution/test_delivery_unit.py` | 已实现 |

**V1 Enhancement 实际完成率：100%（7/7）**

### 1.2 交易执行层 — 修正评估

代码探索发现交易执行层**远比表面评分显示的成熟**：

| 组件 | 状态 | 说明 |
|------|------|------|
| OrderType | 4 种已定义 | MARKET / LIMIT / STOP_MARKET / MARKET_ON_CLOSE |
| OrderStatus | 6 态状态机 | NEW→SUBMITTED→PARTIALLY_FILLED→FILLED/CANCELED/REJECTED/INVALID |
| AShareFillModel | LIMIT 单已支持 | 在 [low, high] 范围内以限价成交 |
| ExecutionPlanner | 仅生成 MARKET 单 | `_make_order()` 硬编码 `OrderType.MARKET`，但基础设施就绪 |
| Reality Model | 完整 | Fee/Fill/Slippage/Settlement/Market/Brokerage 6 子模块 |

**修正评分：交易执行从 3.0 调整为 4.0**（订单类型定义完整，仅 ExecutionPlanner 未启用 LIMIT）

### 1.3 风控系统 — 修正 MaxDrawdownRule 评估

MaxDrawdownRule **已有正确的 reset() 方法**（`_peak_nav = 0.0`），CompositePostTradeGuard 级联调用所有子规则 reset()。之前的"状态泄漏"评估不准确。

---

## 二、V1 剩余收尾工作

### 2.1 必须完成（P0 — V1 发布阻塞项）

#### P0-1: Kernel 测试补齐（测试覆盖 0.35 → 0.80+）

**原因：** Kernel 被 data/app/interfaces 三层消费，是系统稳定性的基石，当前仅 4/8 模块有测试。

| 缺失测试 | 优先级 | 测试用例估计 | 关键测试点 |
|----------|--------|-------------|-----------|
| `quality.py` | **高** | ~15 | DQResult.has_errors/has_warnings、L3CheckResult.has_error、ReconciliationResult.to_dict 条件序列化 |
| `math.py` | **高** | ~8 | pearson_correlation 正相关/负相关/零方差退化/n<=1 |
| `specs.py` | 中 | ~6 | DerivedSpec.effective_time_keys 显式 vs grain 推导、timezone 映射 |
| `research.py` | 低 | ~4 | ResearchSpineSpecRecord 纯值对象（可选） |

**新增文件：**
- `packages/kernel/tests/unit/test_quality.py`
- `packages/kernel/tests/unit/test_math.py`
- `packages/kernel/tests/unit/test_specs.py`

**工作量：** ~33 个测试用例，约 2-3 小时

---

#### P0-2: R4 信号推送端到端验证

**原因：** 代码已完整实现但缺少真实渠道的端到端验证。

| 任务 | 说明 |
|------|------|
| 配置通知渠道 | 在 `config/development/` 中配置 Telegram Bot Token / SMTP 密码 |
| 端到端集成测试 | 策略回测 → 生成 TradeIntent → DeliveryRouter → Telegram/Email 实际送达 |
| 回归测试 | 确认 DeliveryRouter 不影响回测主流程（fire-and-forget） |

**工作量：** 约 1-2 小时

---

#### P0-3: V1 设计文档更新

**原因：** R4 状态标注不准确（实际已完成），需同步更新设计文档。

| 任务 | 文件 |
|------|------|
| R4 状态更新为"已完成" | `docs/plans/2026-04-11-v1-enhancement-design.md` |
| 交易执行层评分修正 | `docs/reviews/2026-04-07-industry-benchmark-gap-analysis.md` |
| MaxDrawdownRule 修正 | `docs/reviews/2026-04-07-architecture-deep-dive-and-industry-benchmark.md` |

**工作量：** 约 30 分钟

---

### 2.2 建议完成（P1 — 提升 V1 发布质量）

#### P1-1: ExecutionPlanner LIMIT 单启用

**原因：** OrderType.LIMIT / OrderStatus 状态机 / AShareFillModel LIMIT 逻辑均已定义，ExecutionPlanner 仅需修改 `_make_order()` 方法即可支持 LIMIT 单。这将交易执行评分从 4.0 提升到 5.5。

**修改范围：**
- `packages/engine/src/ditto_engine/execution/planner.py` — `_make_order()` 支持根据策略参数选择 MARKET/LIMIT
- `packages/engine/src/ditto_engine/alpha/specs.py` — StrategySpec 新增 `default_order_type` 字段
- 对应单元测试

**工作量：** ~100 行修改，约 2 小时

---

#### P1-2: PostTrade 风控通知集成

**原因：** PostTrade 扫描结果目前仅记录日志和 RiskLock，未通过 AlertManager 推送通知。集成后用户可在交易后实时收到风控告警。

**修改范围：**
- `packages/engine/src/ditto_engine/risk/post_trade.py` — 新增可选 `AlertManager` 注入
- `packages/engine/src/ditto_engine/backtest/steps/risk_scan.py` — RiskScanStep 传递风控事件

**工作量：** ~60 行修改，约 1 小时

---

#### P1-3: 回测报告 HTML 渲染（基础版）

**原因：** BacktestReport 数据模型非常完善（15 个字段），但可视化输出为零。引入 HTML 报告可将研究工具链评分从 5.5 提升到 6.5。

**分两步：**
- Step 1（V1）：纯 HTML 文本报告 — 关键指标表格（年化收益/夏普/最大回撤/胜率/盈亏比），无图表
- Step 2（V1.1）：添加 matplotlib 图表 — NAV 曲线、回撤图、月度收益热力图

**新增文件：**
- `packages/engine/src/ditto_engine/backtest/report_renderer.py` — HTML 报告生成器
- `packages/engine/src/ditto_engine/backtest/templates/report.html` — Jinja2 模板

**依赖：** 无新依赖（Jinja2 已在 infra 层使用）

**工作量：** Step 1 ~200 行，约 3 小时

---

#### P1-4: numpy 显式依赖声明

**原因：** analytics 层已使用 `import numpy`（factor_analysis.py, ic.py），但 pixi.toml 未显式声明。通过 polars 间接引入不可靠。

**修改：** `pixi.toml` 添加 `numpy >=2.0,<3`

**工作量：** 5 分钟

---

## 三、V1.1 增强建议（Phase 4-7 + 补充）

### 3.1 实施顺序建议

基于代码探索发现的准备度，**调整实施顺序**（区别于设计文档的 Phase 4→5→6→7）：

```
准备度排序:
  Phase 6 (Regime 扩展)  — 准备度: 高  → 最先实施
  Phase 7 (归因分析)     — 准备度: 中高 → 第二批
  Phase 4 (组合优化)     — 准备度: 中   → 第三批
  Phase 5 (参数优化)     — 准备度: 低   → 最后实施
```

---

### 3.2 Phase 6: Regime 扩展（建议最先实施）

**准备度分析：**

| 组件 | 状态 | 文件 |
|------|------|------|
| RegimeIndicator Protocol | 已就绪 | `engine/alpha/builtins/regime.py` |
| RegimeScoreEngine | 已就绪 | 同上，4 内置指标加权合成 |
| MacroService | 已就绪 | `data/services/macro_service.py`，双数据源 (Tushare/FRED) + PIT |
| 宏观存储 | 已就绪 | `data/storage/macro/` |

**需新增：**

| 组件 | 工作量 | 说明 |
|------|--------|------|
| `InterestRateIndicator` | ~50 行 | LPR/MLF 方向 + M2 同比 |
| `InflationIndicator` | ~40 行 | CPI/PPI 剪刀差 |
| `LiquidityIndicator` | ~40 行 | M2/M1 剪刀差 + 社融 |
| `MacroDataProvider` Protocol | ~20 行 | 定义在 kernel（engine 不可直接依赖 data） |
| App 层桥接编排 | ~80 行 | MacroService → MacroDataProvider → RegimeIndicator |
| 单元测试 | ~100 行 | 各指标边界值 + 集成测试 |

**新增依赖：** 无

**总工作量：** ~330 行新代码

---

### 3.3 Phase 7: 归因分析增强（建议第二批）

**准备度分析：**

| 组件 | 状态 | 说明 |
|------|------|------|
| performance_attribution() | 已实现 | 多空分位归因，但 interaction=0（简化模型） |
| Fama-MacBeth 回归 | 已实现 | 两阶段截面回归 |
| 因子暴露分析 | 已实现 | 正交化 + R-squared |
| 归因单元测试 | 已有 | test_evaluation_attribution_unit.py |

**需新增：**

| 组件 | 工作量 | 说明 |
|------|--------|------|
| Brinson 分解 | ~150 行 | allocation + selection + interaction = active_return |
| 交易成本归因 | ~80 行 | commission + slippage + timing = total cost (bps) |
| AttributionReport | ~60 行 | 归因报告数据类 |
| 归因 API 端点 | ~50 行 | `GET /backtests/runs/{id}/attribution` |
| 测试 | ~120 行 | Brinson 数值正确性 + 成本分解 |

**新增依赖：** 无（numpy 已可用）

**总工作量：** ~460 行新代码

---

### 3.4 Phase 4: 组合优化（建议第三批）

**准备度分析：**

| 组件 | 状态 | 说明 |
|------|------|------|
| WeightAllocator Protocol | 已就绪 | `allocate(frame) -> frame` |
| Constraint Protocol | 已就绪 | MaxWeight/MinWeight/MaxPositions 3 种约束 |
| AllocationStage | 已就绪 | DecisionStage 适配器 |
| cvxpy/scipy | **缺失** | 需添加到 pixi.toml |

**需新增：**

| 组件 | 工作量 | 说明 |
|------|--------|------|
| PortfolioOptimizer Protocol | ~30 行 | solve()-style 接口（区别于 WeightAllocator） |
| MeanVarianceOptimizer | ~120 行 | CVXPY 二次规划 |
| RiskParityOptimizer | ~100 行 | SciPy 序贯二次规划 |
| SectorExposureConstraint | ~50 行 | 行业暴露约束 |
| TrackingErrorConstraint | ~40 行 | 跟踪误差约束 |
| OptimizationStage | ~60 行 | DecisionStage 适配器 |
| 测试 | ~150 行 | MVO/RP 数值正确性 + 无解退化 |

**新增依赖：** `cvxpy >=1.5,<2`、`scipy >=1.14,<2`

**总工作量：** ~550 行新代码 + 2 个新依赖

---

### 3.5 Phase 5: 参数优化（建议最后实施）

**准备度分析：**

| 组件 | 状态 | 说明 |
|------|------|------|
| optuna 依赖 | **缺失** | 需从零添加 |
| optimization 模块 | **缺失** | 需从零创建 |
| parameter_overrides | 已有 | 回测 Flow 已支持参数覆盖 |
| BacktestService | 已就绪 | 可复用执行单次回测 |

**需新增：**

| 组件 | 工作量 | 说明 |
|------|--------|------|
| ParamOptimizer Protocol | ~30 行 | 目标函数 + 搜索空间定义 |
| GridSearchOptimizer | ~80 行 | 网格搜索实现 |
| BayesianOptimizer | ~120 行 | Optuna TPE 封装 |
| OverfitDetector | ~100 行 | IS/OOS 衰减比 + Deflated Sharpe |
| WalkForwardOrchestrator | ~150 行 | App 层，IS/OOS 窗口划分 |
| run_parameter_sweep_flow | ~80 行 | Prefect Flow |
| OptimizationFactory | ~60 行 | Optuna storage/pruner DI 注入 |
| API 端点 | ~60 行 | `POST /optimization/studies` |
| 测试 | ~200 行 | 搜索正确性 + 过拟合检测 |

**新增依赖：** `optuna >=4.0,<5`

**总工作量：** ~880 行新代码

---

### 3.6 V1.1 补充建议（设计文档未覆盖但评分影响大）

#### S1: 回测报告可视化增强

**评分影响：** 研究工具链 +1.0（5.5→6.5）

- NAV 曲线图（matplotlib）
- 回撤水下图
- 月度收益热力图
- 因子 IC 时序图

**工作量：** ~300 行，约 4 小时

---

#### S2: 风控参数动态配置

**评分影响：** 风控系统 +0.5（6.5→7.0）

- RiskConfig dataclass 替代硬编码阈值
- 通过 API 暴露风控参数配置
- 策略级风控参数覆盖

**工作量：** ~150 行，约 2 小时

---

#### S3: 多策略运行基础接口

**评分影响：** 策略引擎 +0.5（8.5→9.0）

- StrategyInstance 运行实例类型
- StrategyRegistry 注册中心 Protocol
- 为 V2 多策略协调打下基础（不实现协调逻辑）

**工作量：** ~200 行，约 3 小时

---

## 四、V1 剩余交付时间线

```
Week 1 (V1 收尾):
  Day 1-2: P0-1 Kernel 测试补齐（quality.py + math.py + specs.py）
  Day 2:   P0-2 R4 端到端验证
  Day 2:   P0-3 设计文档更新
  Day 3:   P1-4 numpy 显式依赖
  Day 3-4: P1-1 ExecutionPlanner LIMIT 单启用
  Day 4:   P1-2 PostTrade 风控通知集成
  Day 4-5: P1-3 HTML 报告基础版
  Day 5:   pixi run -e dev check + arch-check 全通过

V1 发布门禁:
  [ ] Kernel 测试覆盖 ≥ 80%
  [ ] R4 端到端验证通过（至少 Telegram 通道）
  [ ] LIMIT 单回测测试通过
  [ ] HTML 报告生成正确
  [ ] pixi run -e dev check + arch-check 全通过
```

---

## 五、修正后的评分卡

### V1 收尾后预期评分

| 维度 | 当前 | V1 收尾后 | 提升 | 来源 |
|------|------|-----------|------|------|
| 架构分层 | 8.5 | **8.5** | - | 已领先 |
| 数据基础设施 | 8.0 | **8.0** | - | 已领先 |
| 因子引擎 | 9.0 | **9.0** | - | 已领先 |
| 策略引擎 | 8.5 | **9.0** | +0.5 | S3 多策略基础接口 |
| 回测引擎 | 8.0 | **8.5** | +0.5 | HTML 报告 + LIMIT 单 |
| 交易执行 | 4.0 | **5.5** | +1.5 | LIMIT 单启用 + 状态机已有 |
| 风控系统 | 6.5 | **7.0** | +0.5 | 通知集成 + 参数配置 |
| 生产运维 | 4.0 | **5.5** | +1.5 | R4 已完成 + 风控通知 |
| 研究工具链 | 5.5 | **6.5** | +1.0 | HTML 报告 + 可视化 |
| API/产品化 | 6.5 | **7.5** | +1.0 | 归因 API + HTML 报告 |

**加权综合分：V1 收尾后 7.55（从 7.15 提升 0.4 分）**

### V1.1 完成后预期评分

| 维度 | V1 收尾后 | V1.1 后 | 提升 | 来源 |
|------|-----------|---------|------|------|
| 策略引擎 | 9.0 | **9.0** | - | - |
| 回测引擎 | 8.5 | **9.0** | +0.5 | 归因分析 |
| 交易执行 | 5.5 | **5.5** | - | - |
| 风控系统 | 7.0 | **7.5** | +0.5 | Regime 扩展 |
| 研究工具链 | 6.5 | **8.0** | +1.5 | 参数优化 + 组合优化 + 可视化 |

**V1.1 综合分：8.05（逼近 V2 目标 8.45）**

---

## 六、关键文件索引

### V1 收尾修改文件

| 文件 | 修改类型 | P 级 |
|------|----------|------|
| `packages/kernel/tests/unit/test_quality.py` | 新增 | P0 |
| `packages/kernel/tests/unit/test_math.py` | 新增 | P0 |
| `packages/kernel/tests/unit/test_specs.py` | 新增 | P0 |
| `packages/engine/src/ditto_engine/execution/planner.py` | 修改 | P1 |
| `packages/engine/src/ditto_engine/risk/post_trade.py` | 修改 | P1 |
| `packages/engine/src/ditto_engine/backtest/report_renderer.py` | 新增 | P1 |
| `pixi.toml` | 修改 | P1 |

### V1.1 新增文件

| 文件 | Phase |
|------|-------|
| `packages/engine/src/ditto_engine/alpha/builtins/regime/indicators/macro.py` | Phase 6 |
| `packages/kernel/src/ditto_kernel/protocols.py`（MacroDataProvider） | Phase 6 |
| `packages/analytics/src/ditto_analytics/attribution/brinson.py` | Phase 7 |
| `packages/analytics/src/ditto_analytics/attribution/cost_attribution.py` | Phase 7 |
| `packages/engine/src/ditto_engine/portfolio/optimizers/mvo.py` | Phase 4 |
| `packages/engine/src/ditto_engine/portfolio/optimizers/risk_parity.py` | Phase 4 |
| `packages/engine/src/ditto_engine/optimization/bayesian_search.py` | Phase 5 |
| `packages/engine/src/ditto_engine/optimization/overfit_detector.py` | Phase 5 |

---

## 七、验证方式

### V1 收尾验证

1. `pixi run -e dev check` — lint + type + test 全通过
2. `pixi run -e dev arch-check` — 架构约束通过
3. Kernel 测试覆盖率 ≥ 80%（`pixi run -e dev test --cov packages/kernel`）
4. R4 端到端：策略回测 → Telegram 通知实际送达
5. LIMIT 单回测：使用 LIMIT 策略运行完整回测，验证 AShareFillModel LIMIT 成交逻辑
6. HTML 报告：生成并人工检查报告内容完整性

### V1.1 验证（每 Phase）

1. Phase 6: 宏观 Regime 正确识别经济周期，综合信号影响仓位
2. Phase 7: Brinson 分解数值正确（allocation + selection + interaction = active_return）
3. Phase 4: MVO 对 3+ 标的产生产效权重（sum=1, all≥0）
4. Phase 5: 网格搜索对 2x3 参数网格返回 6 个 trial

---

## 八、业界对标评分总表

> 评分基准：10 分制，对标 LEAN（10）、NautilusTrader（9.5）、Qlib（8）、VectorBT（7.5）

### 当前各模块评分

| 维度 | 得分 | 等级 | 核心优势 | 核心短板 |
|------|------|------|----------|----------|
| **架构分层** | 8.5 | A | importlinter 强制、CQRS 四象限 | Kernel 测试偏低 |
| **数据基础设施** | 8.0 | A- | L1-L4 质量、PIT 编译器级 | 无流式 API |
| **因子引擎** | 9.0 | A | 自研编译器、Fama-MacBeth+正交化 | 无自动挖掘 |
| **策略引擎** | 8.5 | A- | 8 Stage Pipeline、4 模板 | 单策略运行 |
| **回测引擎** | 8.0 | B+ | A 股规则最精确、TradingStep Chain | 无回测/实盘统一核心 |
| **交易执行** | 4.0 | D+ | A 股规则完整、状态机已有 | Planner 仅 MARKET |
| **风控系统** | 6.5 | B- | 10 PreTrade + 4 PostTrade | 无持续监控 |
| **生产运维** | 4.0 | D+ | 三渠道通知、8 Prefect Flow | 无实时监控 |
| **研究工具链** | 5.5 | C+ | 表达式+评估器 | 无可视化/参数优化 |
| **API/产品化** | 6.5 | B | 50+ 端点、Pydantic 类型安全 | 无 WebSocket/权限 |

### Ditto 独特护城河

| 优势 | 超越对象 | 说明 |
|------|----------|------|
| 因子表达式编译器 | Qlib/LEAN | 自研 DSL→Polars，零运行时解释 |
| PIT 安全保证 | 全部竞品 | 编译器级 shift(1) + 冻结管理 |
| 因子评估深度 | Qlib/LEAN | Grinold-Kahn IR + Fama-MacBeth + 正交化 + Regime IC |
| 数据质量引擎 | 全部竞品 | L1-L4 四级检查（开源最全面） |
| A 股规则精度 | 全部竞品 | T+1/100+1/涨跌停/费率全部模型化 |
| 架构治理 | 全部竞品 | importlinter 机器强制依赖方向 |
