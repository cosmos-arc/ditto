# Execution 层架构规范

## 定位

Execution 是**交易执行平面**，负责：
- 订单管理与成交处理（OMS）
- 券商网关抽象（Broker Gateway）
- 执行现实模拟（费用、滑点、交收）
- 交易审计与对账
- 交易持久化（SQLite storage）

**核心原则**：
- 执行层是交易系统的最后一道门，不依赖回测或分析
- Broker Gateway 是与外部券商系统的唯一接口
- 执行现实模拟（reality/）封装了 A 股交易规则（T+1、涨跌停、费用等）
- 审计记录所有交易行为，不可篡改

## 允许依赖

```
ditto_execution → ditto_kernel ✅
ditto_execution → ditto_portfolio ✅
ditto_execution → ditto_risk ✅
ditto_execution → ditto_platform ✅
```

外部依赖：orjson

## 禁止依赖

```
ditto_execution → ditto_data ❌
ditto_execution → ditto_features ❌
ditto_execution → ditto_strategy ❌
ditto_execution → ditto_backtest ❌
ditto_execution → ditto_analysis ❌
ditto_execution → ditto_application ❌
ditto_execution → ditto_apps ❌
```

## 内部目录职责

```
ditto_execution/
├── broker/               # 券商网关抽象
│   ├── contracts.py      # BrokerGateway Protocol
│   └── gateways/         # 具体券商实现（待扩展）
├── orders/               # 订单管理
│   └── store.py          # 订单存储接口
├── fills/                # 成交处理
│   ├── store.py          # 成交存储接口
│   └── outcomes.py       # 成交结果
├── reality/              # 执行现实模拟
│   ├── brokerage.py      # 经纪商模拟
│   ├── fee.py            # 费用计算
│   ├── slippage.py       # 滑点模型
│   ├── fill.py           # 成交模拟
│   ├── settlement.py     # 交收规则（T+1）
│   ├── market.py         # 市场规则（涨跌停等）
│   └── constants.py      # A 股交易常量
├── audit/                # 交易审计
│   ├── models.py         # 审计模型
│   └── execution_audit_service.py  # 审计服务
├── storage/              # 持久化
│   ├── sqlite_client.py  # SQLite 客户端
│   ├── deps.py           # 依赖注入
│   └── sqlite/
│       ├── trade/        # 交易数据存储
│       │   └── service.py
│       └── legacy/       # 遗留存储（fill/signal/position reader/writer）
├── reconciliation/       # 对账（待扩展）
├── planner.py            # 执行计划器
├── trade_builder.py      # 交易构建器
├── targets.py            # 目标持仓计算
├── rules.py              # 执行规则
├── models.py             # 交易模型
├── contracts.py          # 执行契约
├── errors.py             # 错误定义
└── events.py             # 领域事件
```

## 测试位置

```
packages/execution/tests/
├── unit/
│   ├── test_order_events_unit.py
│   ├── broker/
│   │   └── test_contracts_unit.py
│   ├── execution_legacy/    # 遗留执行测试
│   │   ├── test_trade_builder_unit.py
│   │   ├── test_fill_model_unit.py
│   │   ├── test_fills_unit.py
│   │   ├── test_settlement_unit.py
│   │   ├── test_planner_unit.py
│   │   ├── test_brokerage_unit.py
│   │   ├── test_slippage_unit.py
│   │   ├── test_fee_model_unit.py
│   │   ├── test_rules_unit.py
│   │   └── test_brokerage_helpers_unit.py
│   ├── trade/
│   │   └── test_trade_service_unit.py
│   └── audit/
│       ├── test_audit_trade_fill_unit.py
│       └── test_execution_audit_service_unit.py
```

## 典型导入示例

```python
# 券商网关
from ditto_execution.broker.contracts import BrokerGateway

# 执行计划
from ditto_execution.planner import ExecutionPlanner
from ditto_execution.trade_builder import TradeBuilder

# 执行现实
from ditto_execution.reality.fee import calculate_commission
from ditto_execution.reality.slippage import SlippageModel

# 审计
from ditto_execution.audit.execution_audit_service import ExecutionAuditService
```

## 常用验证命令

```bash
pixi run -e dev pytest packages/execution/tests/unit -q
pixi run -e dev type packages/execution/src
pixi run -e dev arch-check
```
