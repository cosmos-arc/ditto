# Re-Export 治理设计

> 状态：**已完成**
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

## 实施记录

### P0 — 跨包 Re-export 消除 ✅

| 文件 | 删除的跨包 re-export | 消费者迁移 |
|------|---------------------|-----------|
| `ditto_data/models/__init__.py` | `ditto_kernel.enums` (6), `ditto_kernel.types` (1) | 0 消费者（死 re-export） |
| `ditto_data/quality/__init__.py` | `ditto_kernel.quality` (4) | 0 消费者（死 re-export） |
| `ditto_analytics/materialization/__init__.py` | `ditto_kernel.specs` (3) | 4 个测试文件已迁移到 `ditto_kernel.specs` |
| `ditto_analytics/models/__init__.py` | `ditto_kernel.research` (4) | 0 消费者（死 re-export） |

**结果**：18 个跨包 re-export 符号已消除，14/18 无消费者（死代码），3 个测试消费者已迁移。

### P1 — 深层链截断 ✅（无需变更）

**审计结果**：所有 barrel 链深度已 ≤ 2 层，无需变更。

主要涉及区域：
- `ditto_data/sources/tushare/processors/mappings/` — 1 层 barrel，合规
- `ditto_data/sources/tushare/adapters/` — 1 层 barrel，合规
- `ditto_data/sources/schemas/` — 1 层 barrel，合规
- `ditto_data/storage/` 各子域 — 最大 2 层，合规

### P2 — 超大 Barrel 精简 ✅

| 文件 | 变更前 | 变更后 | 说明 |
|------|--------|--------|------|
| `ditto_app/process/__init__.py` | 52 符号 | `__all__ = []` | 0 消费者，直接清空 |
| `ditto_engine/execution/__init__.py` | 47 符号 | `__all__ = []` | 0 消费者，直接清空 |
| `ditto_data/models/__init__.py` | 70 符号 | 9 符号 | 移除 61 个未使用符号，保留 9 个活跃符号 |

**额外发现**：`execution/__init__.py` 存在跨子域 re-export（从 `accounting.order_book` 导入 7 个符号），已在 P4 中一并修复。

### P3 — Barrel + 内联定义分离 ✅

| 文件 | 内联定义 | 移至 | 消费者影响 |
|------|---------|------|-----------|
| `ditto_analytics/factors/__init__.py` | `ALL_FACTOR_SPECS` | `factor_specs.py` | 0（barrel re-export 不变） |
| `ditto_engine/execution/reality/__init__.py` | `BrokerageModel` | 删除（`BrokerageModel` 已在 `brokerage.py` 中定义，barrel 中的重复定义被删除） | 0（barrel re-export 不变） |
| `ditto_app/command/__init__.py` | `CommandHandler` Protocol | `_protocols.py` | 0（barrel re-export 不变） |
| `ditto_interfaces/registry/infra/__init__.py` | `get_infra_providers()` | `_factory.py` | 0（barrel re-export 不变） |
| `ditto_data/di/__init__.py` | `get_data_providers()` | `_factory.py` | 0（barrel re-export 不变） |
| `ditto_data/storage/market/__init__.py` | `AdjType` enum | 删除（孤立代码） | 0（所有消费者已使用 services 版本） |
| `ditto_interfaces/jobs/tasks/__init__.py` | `create_ingest_task_t1_adj` 等别名 | `_aliases.py` | 0（barrel re-export 不变） |

### P4 — 跨子域 Re-export 消除 ✅

| 文件 | 删除的跨子域 re-export | 消费者迁移 |
|------|---------------------|-----------|
| `ditto_engine/backtest/__init__.py` | 10 符号（`execution.reality`, `risk.post_trade`, `risk.pre_trade`） | 0 消费者（内部模块已直接引用） |
| `ditto_engine/execution/__init__.py` | 7 符号（`accounting.order_book`） | 0 消费者（死 barrel） |

## 不变项

以下现有模式保持不变：

- `__all__` 显式定义要求（已 100% 覆盖，继续保持）
- 显式符号导入（无 `from ... import *`，继续保持）
- 包根入口 barrel（如 `ditto_kernel/__init__.py` 36 符号，合理）
- `observability/__init__.py` 的 lazy `__getattr__`（解决循环依赖的合理用法）

## 量化成果

| 指标 | 变更前 | 变更后 |
|------|--------|--------|
| 跨包 re-export 符号 | 18 | 0 |
| 跨子域 re-export 符号 | 17 | 0 |
| 超大 barrel (>30 符号) | 3 | 0 |
| Barrel + 内联定义混合 | 7 | 0 |
| models barrel 符号数 | 70 | 9 |
| process barrel 符号数 | 52 | 0 |
| execution barrel 符号数 | 47 | 0 |

## 验证结果

```
basedpyright: 0 errors, 0 warnings, 0 notes
ruff lint: All checks passed
ruff fmt: 1125 files unchanged
tests: 4422 passed, 25 skipped, 0 failed
importlinter: 24 contracts, 0 broken
```

## 业界参考

| 模式 | 代表项目 | Ditto 对应 |
|------|---------|-----------|
| 极简显式 | FastAPI（~15 符号） | 包根入口目标 |
| 延迟 `__getattr__` | scikit-learn, Pydantic | 不采用（复杂度高，收益有限） |
| Anti-Barrel | TkDodo | 内部模块间不 re-export |
