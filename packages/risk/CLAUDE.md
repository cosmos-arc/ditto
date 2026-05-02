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

外部依赖：polars, orjson

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
├── constraints/          # 约束规则（待扩展）
├── exposure/             # 暴露度管理（待扩展）
├── drawdown/             # 回撤控制（待扩展）
├── models.py             # 风险模型
├── contracts.py          # 风控契约
├── errors.py             # 错误定义
└── events.py             # 领域事件
```

## 测试位置

```
packages/risk/tests/
├── unit/
│   ├── test_import_boundary_unit.py
│   └── test_risk_events_unit.py
```

## 典型导入示例

```python
# 风控检查
from ditto_risk.pre_trade import PreTradeChecker
from ditto_risk.post_trade import post_trade_audit

# 契约与模型
from ditto_risk.contracts import RiskConstraint
from ditto_risk.models import RiskReport

# 事件
from ditto_risk.events import RiskEvent
```

## 常用验证命令

```bash
pixi run -e dev pytest packages/risk/tests/unit -q
pixi run -e dev type packages/risk/src
pixi run -e dev arch-check
```
