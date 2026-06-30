# 延后项修复完善计划

> 创建：2026-05-10
> 基线：延后项代码级任务完成分析（源码级核实）
> 分支：`remediation/cross-module-b1-b7`（继续）
> 策略：R1 先做（文档清理），R2 单独批次（重构需验证）

---

## 概述

延后项 43 个子任务完成度分析发现 2 处待修复项：

| ID | 问题 | 严重度 | 原因 |
|----|------|--------|------|
| R1 | kernel `AGENTS.md` / `README.md` 中 DecisionFrame 残留引用 | 中 | T2 计划未覆盖这两个文件 |
| R2 | `market_service.py` 537 LOC，查询执行函数未提取 | 低-中 | 实例方法与 `self._read_ports` 状态耦合，提取需重构 |

### 依赖关系

```
R1 (文档清理) ── 独立，无依赖
R2 (查询提取) ── 独立，无依赖
```

---

## R1：DecisionFrame 文档残留清理 `[S]`

### 源码现状

| 文件 | 残留行 | 内容 |
|------|--------|------|
| `kernel/AGENTS.md:14` | 1 处 | 策略模块清单含 `DecisionFrame Protocol` |
| `kernel/README.md:18` | 1 处 | 模块结构注释含 `DecisionFrame Protocol` |
| `kernel/README.md:57` | 1 处 | 类型清单表整行（`DecisionFrame \| strategy.py \| Protocol`） |
| `kernel/README.md:103` | 1 处 | 使用示例 `from ditto_kernel.strategy import ... DecisionFrame` |
| `kernel/README.md:136` | 1 处 | 变更记录 `DecisionFrame Protocol` |

### 任务清单

- [x] R1.1：清理 `AGENTS.md` 中 DecisionFrame 引用 `[S]`
  - 第 14 行 `strategy.py | DerivedRole / DerivedSpec / RunStatus / DecisionFrame Protocol` → 移除 `DecisionFrame Protocol`
  - 文件：`packages/kernel/AGENTS.md`
  - 验收：`rg "DecisionFrame" packages/kernel/AGENTS.md` → 0

- [x] R1.2：清理 `README.md` 中 DecisionFrame 引用 `[S]`
  - 第 18 行：模块结构注释移除 `DecisionFrame Protocol`
  - 第 57 行：删除类型清单整行
  - 第 103 行：移除 `DecisionFrame`（保留其他符号）
  - 第 136 行：变更记录中移除 `DecisionFrame`
  - 文件：`packages/kernel/README.md`
  - 验收：`rg "DecisionFrame" packages/kernel/README.md` → 0

- [x] R1.3：验证 `[S]`
  - `rg "DecisionFrame" packages/kernel/` → 仅应在 `CLAUDE.md` 等已正确不含 DecisionFrame 的文件中出现零结果
  - `pixi run -e dev check`

---

## R2：`market_service.py` 查询执行函数提取 `[M]`

### 源码现状

**当前文件结构**（537 LOC）：

```
market_service.py (537 LOC)
├── MarketService 类
│   ├── __init__(read_ports)                  # 12 行
│   ├── find_bars(query)                      # 3 行 — 委托
│   ├── list_bars(...参数...)                 # 40 行 — 便利方法
│   ├── _query_bars(query)                    # 74 行 — 核心查询编排
│   ├── get_constituents(...)                 # 10 行 — 委托
│   ├── _query_constituents(query)            # 39 行 — 成分股查询
│   ├── _load_bars_core(...)                  # 32 行 — 加载数据
│   ├── _get_bars_reader(asset_class)         # 27 行 — Reader 路由
│   ├── _resolve_instrument_ids_and_asset_class(query)  # 51 行 — ID 解析
│   ├── _parse_dates(query)                   # 26 行 — 日期解析
│   ├── get_stock_bars(start, end)            # 38 行 — 便利方法
│   ├── get_etf_bars(start, end, adj)         # 47 行 — 便利方法+复权
│   ├── get_adj_factors(start, end)           # 38 行 — 便利方法
│   └── get_stock_status(start, end)          # 40 行 — 便利方法
├── market_queries.py (104 LOC) — 仅类型定义
└── market_adjustment.py (151 LOC) — 已提取
```

**核心问题**：6 个私有方法（`_query_bars`/`_query_constituents`/`_load_bars_core`/`_get_bars_reader`/`_resolve_instrument_ids_and_asset_class`/`_parse_dates`）均为实例方法，使用 `self._read_ports` 状态。

### 技术方案

将私有方法改为**模块级独立函数**，接受 `read_ports: MarketReaders` 参数。`MarketService` 方法变为薄委托。

**提取后目标结构**：

```
market_queries.py (~340 LOC) — 类型 + 查询执行
├── AdjType / MarketBarsQuery / MarketConstituentsQuery（现有）
├── query_bars(query, read_ports)           # 从 _query_bars 提取
├── query_constituents(query, read_ports)   # 从 _query_constituents 提取
├── load_bars_core(..., read_ports)         # 从 _load_bars_core 提取
├── get_bars_reader(asset_class, read_ports) # 从 _get_bars_reader 提取
├── resolve_ids_and_class(query, read_ports) # 从 _resolve_instrument_ids_and_asset_class 提取
└── parse_dates(query)                       # 从 _parse_dates 提取（纯函数，无需 read_ports）

market_service.py (~200 LOC) — facade + 便利方法
├── MarketService 类
│   ├── __init__(read_ports)
│   ├── find_bars(query)         → 委托 query_bars
│   ├── list_bars(...)           → 构造 query + 委托 query_bars
│   ├── get_constituents(...)    → 委托 query_constituents
│   ├── get_stock_bars(...)      → 直接读 reader（保留）
│   ├── get_etf_bars(...)        → 直接读 reader + 复权（保留）
│   ├── get_adj_factors(...)     → 直接读 reader（保留）
│   └── get_stock_status(...)    → 直接读 reader（保留）
└── re-export AdjType / MarketBarsQuery / MarketConstituentsQuery

market_adjustment.py (151 LOC) — 不变
```

### 任务清单

- [x] R2.1：提取纯函数 `parse_dates` 到 `market_queries.py` `[S]`
  - 将 `_parse_dates` 方法移到 `market_queries.py` 作为 `parse_dates(query)` 纯函数
  - 添加到 `market_queries.py` 的 `__all__`
  - `MarketService._query_bars` 改为调用 `parse_dates(query)`
  - 文件：`market_queries.py`, `market_service.py`
  - 验收：`market_service.py` 不再包含 `_parse_dates`

- [x] R2.2：提取 Reader 路由函数到 `market_queries.py` `[S]`
  - `_get_bars_reader(asset_class, read_ports: MarketReaders)` → `get_bars_reader(asset_class, read_ports)`
  - `_load_bars_core(instrument_ids, start, end, asset_class, read_ports: MarketReaders)` → `load_bars_core(...)`
  - `_resolve_instrument_ids_and_asset_class(query, read_ports: MarketReaders)` → `resolve_ids_and_class(query, read_ports)`
  - 添加到 `__all__`
  - 文件：`market_queries.py`, `market_service.py`

- [x] R2.3：提取核心查询函数到 `market_queries.py` `[S]`
  - `_query_bars(query, read_ports)` → `query_bars(query, read_ports)`
  - `_query_constituents(query, read_ports)` → `query_constituents(query, read_ports)`
  - 内部调用改为使用 `market_queries.py` 中的同模块函数
  - 添加到 `__all__`
  - 文件：`market_queries.py`, `market_service.py`

- [x] R2.4：MarketService 方法改为薄委托 `[S]`
  - `find_bars` → `return query_bars(query, self._read_ports)`
  - `list_bars` → 构造 `MarketBarsQuery` + `return query_bars(query, self._read_ports)`
  - `get_constituents` → `return query_constituents(query, self._read_ports)`
  - 删除所有已提取的私有方法
  - 文件：`market_service.py`

- [x] R2.5：更新测试 + 验证 `[S]`
  - 搜索 `market_service` 测试文件中是否直接测试了已提取的私有方法
  - 如有，更新为测试 `market_queries.py` 中的公开函数
  - 文件：`packages/data/tests/`
  - 验收：
    - `market_queries.py` ~340 LOC
    - `market_service.py` ~200 LOC
    - `pixi run -e dev check`

---

## 验收总清单

每个任务完成后：

- [ ] `pixi run -e dev lint` — 零错误
- [ ] `pixi run -e dev fmt` — 格式一致
- [ ] `pixi run -e dev type` — 零 type error
- [ ] `pixi run -e dev test` — 全部通过
- [ ] `pixi run -e dev arch-check` — 36/36 contracts kept

---

## 任务统计

| 任务 | 复杂度 | 子任务数 | 涉及包 |
|------|--------|---------|--------|
| R1 DecisionFrame 文档清理 | S | 3 | kernel |
| R2 market_service 查询提取 | M | 5 | data |
| **合计** | — | **8** | 2 包 |
