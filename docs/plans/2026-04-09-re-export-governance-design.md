# Re-Export 治理设计

> 状态：待实施
> 日期：2026-04-09
> 背景：项目 ~75 个 `__init__.py` 做 re-export，~975 个 `__all__` 条目，依赖关系被隐藏，维护成本高

## 决策摘要

采用**分层治理**策略：保留有价值的聚合入口，消除依赖隐藏，限制链深度，降低维护成本。

## 核心痛点

1. **依赖关系被隐藏** — 跨包 re-export 让人看不出真实依赖，重构时容易踩坑
2. **维护负担** — 每加一个符号就要更新多处 `__init__.py` + `__all__`，变更成本高

## 分层规则

### 第 1 层 — 包根入口（保留，精简）

每个包的根 `__init__.py` 是唯一允许做聚合 re-export 的地方。

- 只 re-export **外部消费者需要直接使用的符号**
- 内部实现细节不导出
- 每个 barrel 控制在 **≤ 30 符号**，超过则分拆为子域入口

### 第 2 层 — 子包聚合（有条件保留）

子包 `__init__.py` 允许做聚合，但有限制：

**允许**：
- 内聚子域聚合（如 `storage.capital` 聚合 Reader/Writer 对）
- 对称 API（如 `evaluation/metrics/__init__.py` 聚合所有指标函数）
- 符号数 ≤ 15

**禁止**：
- 跨子域聚合（如 `backtest/__init__.py` 从 sibling `execution.reality` 拉符号）
- "万能桶"（只为方便堆砌）

### 第 3 层+ — 禁止聚合

最大链深度 **2 层**（包根 → 子包）。第 3 层起的 `__init__.py` 不再做聚合，保持空或仅含 `__all__ = []`。

## 绝对禁止项

### 1. 跨包 Re-export

任何包不得从另一个 ditto 包 re-export 符号。消费者需要哪个包的类型，就从哪个包导入。

```python
# ❌ ditto_data/models/__init__.py
from ditto_kernel.enums import AssetClass, Exchange

# ✅ 消费者代码
from ditto_kernel.enums import AssetClass, Exchange
```

### 2. Barrel + 内联定义混合

`__init__.py` 中不应混合 re-export 和新符号定义。新符号定义放到独立模块。

### 3. Lazy `__getattr__` 仅用于延迟加载

仅用于避免启动时的循环依赖（如 `observability/__init__.py` 现有用法），不得用于隐藏跨包依赖。

## 具体变更清单

### P0 — 跨包 Re-export 消除（4 处）

| 文件 | 删除的跨包 re-export | 消费者改为 |
|------|---------------------|-----------|
| `ditto_data/models/__init__.py` | `ditto_kernel.enums`, `ditto_kernel.types` | 直接从 `ditto_kernel.enums` / `ditto_kernel.types` 导入 |
| `ditto_data/quality/__init__.py` | `ditto_kernel.quality` | 直接从 `ditto_kernel.quality` 导入 |
| `ditto_analytics/materialization/__init__.py` | `ditto_kernel.specs` | 直接从 `ditto_kernel.specs` 导入 |
| `ditto_analytics/models/__init__.py` | `ditto_kernel.research` | 直接从 `ditto_kernel.research` 导入 |

### P1 — 深层链截断（~15 处）

链深度从最大 4 层缩减到 2 层。第 3 层起的 barrel `__init__.py` 改为空或 `__all__ = []`，消费者改为直接引用叶模块。

主要涉及：
- `ditto_data/sources/tushare/processors/mappings/` → 消费者直接引用 `mappings.basic`、`mappings.capital` 等
- `ditto_data/sources/tushare/adapters/` → 消费者直接引用 `adapters.market`、`adapters.capital` 等
- `ditto_data/sources/schemas/` → 消费者直接引用 `schemas.market`、`schemas.capital` 等
- `ditto_data/storage/` 下各 leaf 子域（`capital/margin/`、`fundamental/financial/` 等）

### P2 — 超大 Barrel 拆分（3 处）

| 文件 | 当前符号数 | 拆分方向 |
|------|-----------|---------|
| `ditto_app/process/__init__.py` | 52 | 拆为 `process.ingestion`、`process.strategy`、`process.research` 等子域入口 |
| `ditto_engine/execution/__init__.py` | 41 | 拆为 `execution.planner`、`execution.brokerage`、`execution.accounting` 等子域入口 |
| `ditto_data/models/__init__.py` | ~60 | 拆为 `models.market`、`models.capital`、`models.fundamental` 等子域入口 |

### P3 — Barrel + 内联定义分离（~7 处）

| 文件 | 内联定义 | 移至 |
|------|---------|------|
| `ditto_analytics/factors/__init__.py` | `ALL_FACTOR_SPECS` | `_registry.py` |
| `ditto_engine/execution/reality/__init__.py` | `BrokerageModel` | `_model.py` |
| `ditto_app/command/__init__.py` | `CommandHandler` Protocol | `_protocols.py` |
| `ditto_interfaces/registry/infra/__init__.py` | `get_infra_providers()` | `_factory.py` |
| `ditto_data/di/__init__.py` | `get_data_providers()` | `_factory.py` |
| `ditto_data/storage/market/__init__.py` | `AdjType` enum | `_types.py` |
| `ditto_interfaces/jobs/tasks/__init__.py` | `create_ingest_task_t1_adj` 等别名 | `_aliases.py` |

### P4 — 跨子域 Re-export 消除（1 处）

| 文件 | 问题 | 修正 |
|------|------|------|
| `ditto_engine/backtest/__init__.py` | 从 sibling `execution.reality`、`risk.post_trade`、`risk.pre_trade` 拉符号 | 消费者直接引用原模块 |

## 不变项

以下现有模式保持不变：

- `__all__` 显式定义要求（已 100% 覆盖，继续保持）
- 显式符号导入（无 `from ... import *`，继续保持）
- 包根入口 barrel（如 `ditto_kernel/__init__.py` 36 符号，合理）
- `observability/__init__.py` 的 lazy `__getattr__`（解决循环依赖的合理用法）

## 实施建议

- **优先级顺序**：P0 → P1 → P2 → P3 → P4
- **每步独立可验证**：完成后运行 `pixi run -e dev check` 确保无回归
- **消费者迁移**：每个 P 的变更需要同步更新所有消费者代码的 import 路径
- **importlinter**：可考虑新增规则约束跨包 re-export

## 业界参考

| 模式 | 代表项目 | Ditto 对应 |
|------|---------|-----------|
| 极简显式 | FastAPI（~15 符号） | 包根入口目标 |
| 延迟 `__getattr__` | scikit-learn, Pydantic | 不采用（复杂度高，收益有限） |
| Anti-Barrel | TkDodo | 内部模块间不 re-export |
