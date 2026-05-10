# Risk 层架构规范

## 定位

Risk 是**风险管理平面**，负责：
- 盘前风控检查（Pre-trade check）
- 盘后风控审计（Post-trade audit）
- 风险约束定义与验证
- 暴露度管理、回撤控制

**核心原则**：
- 风控是投资组合的安全网，不承担交易决策
- Pre-trade 检查阻止不合规交易，Post-trade 审计记录违规
- 约束规则可组合、可配置

## 允许依赖

```
ditto_risk → ditto_kernel ✅
ditto_risk → ditto_portfolio ✅
```

无外部依赖（kernel / portfolio 纯领域逻辑）

## 禁止依赖

```
ditto_risk → ditto_data ❌
ditto_risk → ditto_features ❌
ditto_risk → ditto_strategy ❌
ditto_risk → ditto_execution ❌
ditto_risk → ditto_backtest ❌
ditto_risk → ditto_analysis ❌
ditto_risk → ditto_application ❌
ditto_risk → ditto_apps ❌
```

## 内部目录职责

```
ditto_risk/
├── pre_trade.py          # 盘前风控检查
├── post_trade.py         # 盘后风控审计
├── _validation.py        # 校验工具
├── rules.py              # 风控规则类型
├── constraints/          # 约束规则
│   ├── checks.py         # 约束检查
│   └── context.py        # 约束上下文
├── exposure/             # 暴露度管理
│   ├── checks.py         # 暴露度检查
│   └── rules.py          # 暴露度规则
├── drawdown/             # 回撤控制
│   └── rules.py          # 回撤规则
├── observability/        # 可观测性
│   └── metrics.py        # 风控指标采集
├── models.py             # 风险模型
├── contracts.py          # 风控契约
├── errors.py             # 错误定义
└── events.py             # 领域事件
```

## 错误语义

Risk 的正常业务结果通过返回值表达，不通过异常表达：

- risk finding = return value，例如 `Decision`、`OrderCheckResult`、`RiskAction`。
- risk configuration failure = exception，例如无法构造有意义规则的非法配置。
- risk contract misuse = exception，例如调用方传入不满足公共契约的运行时上下文。

不要把正常的约束命中、暴露超限、回撤触发建模成异常。这些情况应返回明确的
风控决策或盘后动作，便于调用方组合、审计和持久化。

## 测试位置

```
packages/risk/tests/
└── unit/
    ├── test_buying_power_check_unit.py
    ├── test_composite_post_trade_guard_unit.py
    ├── test_composite_pre_trade_check_unit.py
    ├── test_concentration_limit_rule_unit.py
    ├── test_concentration_pre_check_unit.py
    ├── test_contracts_typed_unit.py
    ├── test_daily_turnover_pre_check_unit.py
    ├── test_import_risk_unit.py
    ├── test_lot_size_check_unit.py
    ├── test_market_anomaly_rule_unit.py
    ├── test_max_drawdown_rule_unit.py
    ├── test_models_unit.py
    ├── test_no_short_sell_check_unit.py
    ├── test_pre_trade_context_unit.py
    ├── test_price_validity_check_unit.py
    ├── test_risk_contracts_unit.py
    ├── test_risk_errors_unit.py
    ├── test_risk_events_unit.py
    ├── test_risk_import_boundary_unit.py
    ├── test_single_loss_limit_rule_unit.py
    ├── test_subdomain_facade_unit.py
    └── test_validation_unit.py
```

## 典型导入示例

```python
# 风控检查
from ditto_risk.pre_trade import CompositePreTradeCheck, BuyingPowerCheck, LotSizeCheck
from ditto_risk.post_trade import CompositePostTradeGuard, PostTradeRiskGuard, RiskAction

# 事件
from ditto_risk.events import RiskGuardDetails, RiskGuardTriggered
```

## 常用验证命令

```bash
pixi run -e dev pytest packages/risk/tests/unit -q
pixi run -e dev type packages/risk/src
pixi run -e dev arch-check
```

## 已知差距 / 计划工作

| ID | 差距 | 现状 | 目标 |
|----|------|------|------|
| RISK-P1-01 | **RiskGate 统一运行时契约** | Pre-trade / Post-trade 检查已实现，但回测与模拟盘各自内嵌风控门控逻辑，缺乏共享的 `RiskGate` 运行时契约 | 统一 `RiskGate` protocol，backtest 与 paper trading 共用同一门控抽象 |
| RISK-P1-02 | ~~有状态规则的无损恢复~~ **已修复 (B5)** | `DrawdownStateSnapshot` + `MaxDrawdownRule.snapshot()/restore()` 已实现，重放一致性已验证 | ✅ 完成 |
| RISK-P1-03 | ~~审计载荷类型化~~ **已修复 (B4)** | `RiskGuardDetails` typed dataclass 替代 `dict[str, Any]`，`event_type` 引用 `EventName` 常量 | ✅ 完成 |
| RISK-P2-01 | **审计血缘跨包断裂** | `RiskAction` 经本地映射转为 backtest `RiskScanRecord` 再到 execution audit，审计血缘分散在多个包中 | 建立跨包审计 lineage protocol，统一 trace id |
