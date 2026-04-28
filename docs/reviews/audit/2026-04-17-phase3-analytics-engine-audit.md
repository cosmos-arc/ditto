# Phase 3: Analytics + Engine 审计报告

> **日期**: 2026-04-17
> **范围**: packages/analytics (49 文件, 8,204 行) + packages/engine (74 文件, 12,085 行)
> **架构检查**: 24 条契约全部通过

---

## Analytics 审计发现

### P1（3 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| A-P1-1 | `obv_ma20` 缺少对 `obv` 的 dependency 声明 | `factors/technical.py:194-202` | 语义错误：依赖 obv 但未声明 |
| A-P1-2 | expression ↔ materialization 循环语义依赖 | `expression/analyzer.py:19` + `materialization/contracts.py:8` | analyzer 依赖 contracts，contracts 依赖 kernel specs，形成隐式循环 |
| A-P1-3 | importlinter 未配置 analytics 依赖方向检查 | 项目级配置 | 虽然 importlinter 存在但 analytics 包的规则未独立配置 |

### P2（7 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| A-P2-1 | expression.analyzer 依赖 materialization.contracts | `expression/analyzer.py:19` | 反向依赖，Analysis 类型应定义在 expression/ 内 |
| A-P2-2 | lookback 窗口参数位置在 analyzer/codegen 间隐式耦合 | `analyzer.py:285` + `codegen.py:424` | 未从 registry 驱动，修改易不同步 |
| A-P2-3 | alpha.py 与 momentum.py 分类重叠 | `factors/alpha.py` + `factors/momentum.py` | 同类因子分布在不同模块 |
| A-P2-4 | alpha.py 包含 value/quality/volatility/liquidity 因子 | `factors/alpha.py:29-65` | 与专门分类模块语义交叉 |
| A-P2-5 | earnings_growth 在 fundamental.py 而非 growth.py | `factors/fundamental.py:52-57` | 分类归属不一致 |
| A-P2-6 | research/domain.py 包含数据处理逻辑 | `research/domain.py:154-227` | DataFrame 变换更适合 Engine 层 |
| A-P2-7 | validate.py 使用 bare Exception 捕获 | `factors/validate.py:38,54` | 可能掩盖非预期错误 |

### P3（4 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| A-P3-1 | technical.py 中 volatility_n 与 volatility.py 重叠 | `factors/technical.py:107-115` | 分类逻辑不清晰 |
| A-P3-2 | expression.compiler 依赖 validation | `expression/compiler.py:34` | 增加耦合 |
| A-P3-3 | evaluator.py 中英文注释混用 | `evaluation/evaluator.py` 多处 | 其他模块用英文 |
| A-P3-4 | contracts.py 引入 pl.Expr 运行时依赖 | `materialization/contracts.py:71` | materialization 直接依赖 Polars 运行时 |

### Analytics 四维评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **架构** | 8/10 | 编译器管线设计精良，但有 expression↔materialization 循环语义依赖 |
| **抽象** | 8/10 | 因子声明与评估分离清晰，Protocol 使用恰当，因子分类有重叠 |
| **依赖** | 9/10 | 仅依赖 kernel + data.errors，importlinter 规则未配置 |
| **实践** | 9/10 | 类型标注完整，诊断系统优秀（Rust 风格），编译缓存 L1+L2 |

---

## Engine 审计发现

### P0 — 无违规（所有 P0 均为正面评价）

**积极发现**：Pipeline + Stage 严格对标 LEAN、accounting 零 I/O、execution 完全解耦、DataProvider Protocol 唯一窗口、importlinter 全部通过、DDD 值对象建模极高。

### P1（2 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| E-P1-1 | 多处 `Any`/`object` 类型弱化 | `risk/post_trade.py:39`, `portfolio/allocation.py:212`, `portfolio/constraints.py:247` | 降低类型安全性 |
| E-P1-2 | `AssertionError` 误用 | `execution/brokerage.py:360` | 应使用 ValueError 或自定义异常 |

### P2（5 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| E-P2-1 | `Order.created_at` 默认硬编码 `datetime(2026,1,1)` | `accounting/order_book.py:89,119` | 未传参时审计记录不准确 |
| E-P2-2 | `OrderCanceled`/`PositionChanged` 事件未发布 | `events.py:40-56` | 预留但未使用，事件覆盖不完整 |
| E-P2-3 | `_execute_delayed_signal` 吞掉所有异常 | `backtest/engine.py:429-431` | 可能导致问题难以排查 |
| E-P2-4 | `_SliceView` Protocol 使用 `Any` 类型 | `risk/post_trade.py:39` | 失去类型安全 |
| E-P2-5 | `AssertionError` 运行时校验 | `execution/brokerage.py:360` | 同 E-P1-2 |

### P3（6 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| E-P3-1 | StrategySpec benchmark 白名单硬编码 | `alpha/specs.py:176-188` | 扩展需改源码 |
| E-P3-2 | EngineResult 使用可变 dataclass | `backtest/engine.py:79-106` | 与项目 frozen 风格不一致 |
| E-P3-3 | statistics.py 812 行过大 | `backtest/statistics.py` | 可拆分 |
| E-P3-4 | execution/__init__.py 空 re-export | `execution/__init__.py` | 缺少公共 API |
| E-P3-5 | total_trades 类型 int 与 MetricsDelta 其他 float 不一致 | `portfolio/comparison.py:146` | 类型不一致 |
| E-P3-6 | AllocationStage/ConstraintStage context 为 object | `portfolio/allocation.py:212` | 降低类型安全 |

### Engine 四维评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **架构** | 10/10 | Pipeline+Stage 对标 LEAN，Step Chain 7 步清晰，execution 完全解耦 |
| **抽象** | 10/10 | DDD 值对象建模极高，Protocol 使用恰当，订单生命周期完整 |
| **依赖** | 10/10 | 仅依赖 kernel + data.provider Protocol，24 条 importlinter 全部通过 |
| **实践** | 9/10 | frozen dataclass 一致性好，仅少量 Any/object 类型弱化 |

---

## 业界对标总结

### Analytics

| 维度 | Ditto | 业界最佳 | 差距 |
|------|-------|---------|------|
| **表达式引擎** | 6 阶段编译器 + L1/L2 缓存 | Qlib AST + LRU + 磁盘缓存 | **领先** — 编译期 PIT 安全内置 |
| **因子体系** | 111 个因子，11 分类 | Zipline Factor/Filter/Classifier | 缺 DAG 依赖分析 |
| **诊断系统** | Rust 风格结构化错误码 | rustc | **领先** — 量化框架中罕见 |
| **因子分类** | 11 模块但有交叉 | Qlib 单层注册表 | P2 级分类重叠 |

### Engine

| 维度 | Ditto | 业界最佳 | 差距 |
|------|-------|---------|------|
| **Pipeline 架构** | 8 Stage Step Chain | LEAN 5 层 Framework | **领先** — 更细粒度 |
| **Accounting 纯度** | 零 I/O frozen 值对象 | NautilusTrader Rust core | 对标 |
| **Execution 解耦** | Protocol 完全隔离 | NautilusTrader Component FSM | 对标 |
| **风控模型** | 6 PreTrade + 4 PostTrade | LEAN Risk + Execution | **领先** — 预/后分离 |
| **多策略并发** | 单策略 | LEAN/NautilusTrader 多策略 | **P1 级差距** |
| **backtest-live parity** | 仅回测 | NautilusTrader 核心设计目标 | **P1 级差距** |
