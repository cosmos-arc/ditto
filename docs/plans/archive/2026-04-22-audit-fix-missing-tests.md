# 审计缺失项修复计划

## 概述
- Sprint: feat/v1-sprint | Phase: 审计修复收尾
- 创建: 2026-04-22
- 状态: **已完成** (2026-04-22)
- 来源: `2026-04-17-full-audit-fix-plan.md` 全方位审查发现的 5 项缺失

## 技术方案

5 项缺失均为 **测试补齐 + 1 项小规格修复**，无架构变更，无新依赖。

---

## 任务清单

### Task 1: obv FactorSpec 定义补充 `[S]`

obv_ma20 声明依赖 `("obv",)` 但 `obv` 自身无 FactorSpec，导致依赖链断裂。

- 验收: `_obv_specs` 字典包含 `obv` 条目；`TECHNICALS["obv"]` 可访问；obv_ma20 的 dependencies 可解析
- 文件:
  - `packages/analytics/src/ditto_analytics/factors/technical.py` — 添加 obv FactorSpec
  - `packages/analytics/tests/unit/factors/test_technical_specs_unit.py` — 添加 obv 规格验证测试

**设计要点**:
- `obv` 是 On-Balance Volume，`computation_type="python"`
- `dependencies` 应为 `("market.close", "market.volume")`
- `expression=""` （python 计算，无表达式）

---

### Task 2: LIMIT 单 planner 测试补齐 `[S]`

`SimpleExecutionPlanner` 支持 `default_order_type=OrderType.LIMIT`，但测试仅覆盖 MARKET。

- 验收: 至少 3 个测试覆盖 LIMIT 场景
- 文件:
  - `packages/engine/tests/unit/execution/test_planner_unit.py` — 添加 LIMIT 测试

**测试用例**:
1. `default_order_type=OrderType.LIMIT` 时 `_make_order()` 生成 LIMIT 订单
2. 显式传入 `order_type=OrderType.MARKET` 覆盖 default
3. `_make_order()` 传入 `price` 参数时 LIMIT 订单携带价格
4. 无 `price` 的 LIMIT 订单行为（当前设计回退到 default，确认行为）

---

### Task 3: PostTrade callback 测试补齐 `[S]`

`CompositePostTradeGuard.scan()` 支持 callbacks 参数触发通知，但无测试验证。

- 验收: 至少 3 个测试覆盖 callback 触发逻辑
- 文件:
  - `packages/engine/tests/unit/backtest/test_post_trade_unit.py` — 在 `TestCompositePostTradeGuard` 中添加

**测试用例**:
1. 传入 callback，`scan()` 后回调被调用且接收到正确的 `list[RiskAction]`
2. 多个 callbacks 均按注册顺序被调用
3. 无 actions 时回调仍被调用（接收空列表）
4. 回调抛异常不影响其他回调执行（可选，视实现决定）

**关键类型**:
- `CompositePostTradeGuard.__init__(rules, callbacks: tuple[Callable[[list[RiskAction]], None], ...])`
- `scan()` 在收集 actions 后遍历 `_callbacks` 调用
- `RiskAction` 是 frozen dataclass（action_type, instrument_id, severity 等字段）

---

### Task 4: BacktestReportRenderer 单元测试 `[S]`

`BacktestReportRenderer.render()` 生成 HTML 报告，无任何测试覆盖。

- 验收: 至少 4 个测试覆盖渲染逻辑
- 文件:
  - `packages/engine/tests/unit/backtest/test_report_renderer_unit.py` — 新建

**测试用例**:
1. `render()` 返回合法 HTML（包含 `<!DOCTYPE html>`、关键 CSS class）
2. 所有模板变量被正确替换（输出中无 `$` 未替换残留）
3. `_fmt()` 正确格式化正/负值（`+1.23` / `-1.23`）
4. 零值和边界值格式化（0.0、极大值、极小值）
5. `render()` 输出包含 run_id、日期范围、alpha 指标、trade 统计

**关键类型**:
- `BacktestReport` frozen dataclass（run_id, period, initial_cash, final_nav, alpha_stats, aggregated_trade_stats）
- `AlphaStats`（annualized_return, sharpe_ratio, max_drawdown 等）
- `AggregatedTradeStats`（total_trades, win_rate, profit_factor 等）
- 使用 `string.Template` 内联模板（非 Jinja2）

---

### Task 5: R4 信号推送端到端测试 `[M]`

`DeliveryRouter` 从 intents 构建通知上下文 → `AlertManager.send_alert()` → Jinja2 模板渲染，无端到端验证。

- 验收: 集成测试覆盖 context 构建 + 模板渲染的完整链路
- 文件:
  - `packages/app/tests/integration/process/execution/test_delivery_integration.py` — 新建

**测试用例**:
1. `_build_context()` 输出与 3 个模板（telegram/email/webhook）的变量完全匹配
2. `deliver()` 调用 AlertManager 时 context 包含所有必需字段
3. 模板渲染输出无 Jinja2 `UndefinedError`（所有变量已提供）
4. Markdown 渲染输出格式正确（buy/sell actions、信号日期、策略 ID）

**关键文件**:
- `packages/app/src/ditto_app/process/execution/delivery.py` — DeliveryRouter
- `packages/infra/src/ditto_infra/services/notification/templates/signal_trading_telegram.j2`
- `packages/infra/src/ditto_infra/services/notification/templates/signal_trading_email.j2`
- `packages/infra/src/ditto_infra/services/notification/templates/signal_trading_webhook.j2`
- `packages/app/src/ditto_app/process/execution/delivery.py:44-71` — `_build_context()` 方法

**注意**: 需 mock `AlertManager`（不触发真实通知），但验证 `_build_context()` 输出和模板变量一致性。如果模板渲染依赖 `NotificationRenderer` 基础设施，需检查 `packages/app/tests/unit/process/execution/test_delivery_unit.py` 现有 conftest 是否可复用。

---

## 执行顺序

```
Task 1 [S] ──┐
Task 2 [S] ──┤
Task 3 [S] ──┼──→ 并行执行（无依赖）
Task 4 [S] ──┘
Task 5 [M] ──────→ 独立执行
```

Task 1-4 互相独立可并行，Task 5 独立。

## 验证

```bash
# 每个 Task 完成后
pixi run -e dev test --unit --fast

# 全部完成后
pixi run -e dev check
```
