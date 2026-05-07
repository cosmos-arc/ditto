# Portfolio 层架构规范

## 定位

Portfolio 是**组合构建与管理平面**，负责：
- 会计系统（账户、持仓、现金、购买力、订单簿）
- 调仓逻辑（权重分配、约束检查、组合对比）
- 持仓与目标组合管理

**核心原则**：
- 纯领域模型层，不依赖具体执行或风控实现
- 会计系统是投资组合的状态机，所有操作通过显式方法变更
- 调仓逻辑只做权重计算，不做交易决策

## 允许依赖

```
ditto_portfolio → ditto_kernel ✅
```

外部依赖：polars

## 禁止依赖

```
ditto_portfolio → ditto_data ❌
ditto_portfolio → ditto_features ❌
ditto_portfolio → ditto_strategy ❌
ditto_portfolio → ditto_risk ❌
ditto_portfolio → ditto_execution ❌
ditto_portfolio → ditto_backtest ❌
ditto_portfolio → ditto_analysis ❌
ditto_portfolio → ditto_application ❌
ditto_portfolio → ditto_apps ❌
```

## 内部目录职责

```
ditto_portfolio/
├── accounting/           # 会计系统
│   ├── account.py        # 账户（持有持仓、现金、订单簿）
│   ├── position.py       # 持仓模型
│   ├── cash.py           # 现金簿
│   ├── buying_power.py   # 购买力计算
│   ├── order_book.py     # 订单簿
│   └── fills.py          # 成交记录
├── rebalancing/          # 调仓逻辑
│   ├── allocation.py     # 权重分配器（等权等）
│   ├── constraints.py    # 约束检查
│   ├── comparison.py     # 组合对比（实际 vs 目标）
│   └── report_views.py   # 报告视图
├── positions/            # 持仓管理（待扩展）
├── target_portfolios/    # 目标组合（待扩展）
├── holdings/             # 持仓快照（待扩展）
├── observability/        # 可观测性
│   └── metrics.py        # 指标
├── contracts.py          # 组合领域契约
├── errors.py             # 错误定义
└── events.py             # 领域事件
```

## 测试位置

```
packages/portfolio/tests/
├── unit/
│   ├── test_import_unit.py
│   ├── test_position_events_unit.py
│   ├── rebalancing/
│   │   ├── test_allocation_unit.py
│   │   ├── test_constraints_unit.py
│   │   └── test_comparison_unit.py
│   └── accounting/
│       ├── test_account_unit.py
│       ├── test_position_unit.py
│       ├── test_cash_book_unit.py
│       ├── test_buying_power_unit.py
│       └── test_order_book_unit.py
```

## 典型导入示例

```python
# 会计系统
from ditto_portfolio.accounting.account import Account
from ditto_portfolio.accounting.position import Position

# 调仓
from ditto_portfolio.rebalancing.allocation import EqualWeightAllocator
from ditto_portfolio.rebalancing.constraints import check_constraints

# 事件
from ditto_portfolio.events import PortfolioEvent
```

## 常用验证命令

```bash
pixi run -e dev pytest packages/portfolio/tests/unit -q
pixi run -e dev type packages/portfolio/src
pixi run -e dev arch-check
```
