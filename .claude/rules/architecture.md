---
paths:
  - ./**/*.py
---

# 架构设计规范

> 本文档是 Agent 架构速查卡。各包详细职责、放置规则和命名词典见
> [boundaries-and-abstraction-standards.md](../../docs/architecture/boundaries-and-abstraction-standards.md)。

## 分层架构原则

### 层级依赖规则

```
┌─────────────────────────────────────────────────────────────────┐
│                       apps (应用入口和 Composition Root)              │
│                              │                                  │
│                              ├──→ packages/application (应用编排平面)   │
│                              │         │                        │
│                              │         ├──→ packages/features (因子计算平面) │
│                              │         │                        │
│                              │         ├──→ packages/strategy (策略平面)   │
│                              │         │                        │
│                              │         ├──→ packages/portfolio (组合平面)  │
│                              │         │                        │
│                              │         ├──→ packages/risk (风控平面)       │
│                              │         │                        │
│                              │         ├──→ packages/execution (执行平面)  │
│                              │         │                        │
│                              │         ├──→ packages/backtest (回测平面)   │
│                              │         │                        │
│                              │         ├──→ packages/analysis (研究分析平面)│
│                              │         │                        │
│                              │         └──→ packages/data (数据服务平面)    │
│                              │                   │                │
│                              │                   └──→ ditto_kernel     │
│                              │                   └──> packages/platform │
│                              │                                  │
│                              └──> ditto_kernel                      │
│                              └──> packages/platform                   │
└─────────────────────────────────────────────────────────────────┘
              ↑                     ↑
              │                     │
     ditto_kernel ◄─────────────────┘
     (共享内核 — 领域原语，零逻辑,零外部依赖)
```

各包定位详见 [boundaries doc Section 3](../../docs/architecture/boundaries-and-abstraction-standards.md#31-各平面定位)。

**详细分层规范**：
- Kernel → [packages/kernel/CLAUDE.md](../../packages/kernel/CLAUDE.md)
- Platform → [packages/platform/CLAUDE.md](../../packages/platform/CLAUDE.md)
- Data → [packages/data/CLAUDE.md](../../packages/data/CLAUDE.md) | [pit.md](../../.claude/rules/pit.md)
- Features → [packages/features/CLAUDE.md](../../packages/features/CLAUDE.md)
- Strategy → [packages/strategy/CLAUDE.md](../../packages/strategy/CLAUDE.md)
- Portfolio → [packages/portfolio/CLAUDE.md](../../packages/portfolio/CLAUDE.md)
- Risk → [packages/risk/CLAUDE.md](../../packages/risk/CLAUDE.md)
- Execution → [packages/execution/CLAUDE.md](../../packages/execution/CLAUDE.md)
- Backtest → [packages/backtest/CLAUDE.md](../../packages/backtest/CLAUDE.md)
- Analysis → [packages/analysis/CLAUDE.md](../../packages/analysis/CLAUDE.md)
- Application → [packages/application/CLAUDE.md](../../packages/application/CLAUDE.md)
- Apps → [packages/apps/CLAUDE.md](../../packages/apps/CLAUDE.md)

### 依赖规则

```
ditto_apps → ditto_application → {ditto_data, ditto_features, ditto_strategy, ditto_portfolio, ditto_risk, ditto_execution, ditto_backtest, ditto_analysis} → ditto_kernel
ditto_apps → ditto_platform
platform 是横向技术基础设施

硬性约束:
- 生产包禁止依赖 ditto_analysis
- ditto_strategy 禁止依赖 ditto_execution
- ditto_execution 禁止依赖 ditto_backtest
- ditto_backtest 禁止导入真实券商网关
```

### v5 强制边界（CI 门禁）

以下规则由 `pixi run -e dev arch-check` 强制执行，违反即 CI 失败:

使用 **Import Linter** 进行架构约束检查,配置位于 [.importlinter](../../.importlinter)。

**检查类型：**
1. **分层架构** (`layers`): Apps → Application → {Capability Packages} → Data → Platform
2. **Kernel 隔离** (`forbidden`): Kernel 禁止依赖其他业务包
3. **Platform 隔离** (`forbidden`): Platform 禁止依赖其他层
4. **Data 边界** (`forbidden`): Data 禁止依赖 Capability/Application/Apps
5. **Features 边界** (`forbidden`): Features 禁止依赖 Strategy/Portfolio/Risk/Execution/Backtest/Analysis/Application/Apps
6. **Strategy 禁止执行** (`forbidden`): Strategy 禁止依赖 Execution
7. **Execution 禁止回测** (`forbidden`): Execution 禁止依赖 Backtest/Analysis
8. **生产包禁止分析** (`forbidden`): 生产包禁止导入 ditto_analysis
9. **Apps 边界** (`forbidden`): Apps 非 registry 禁止依赖 storage/runtime/services/models/errors/config
10. **循环依赖** (`acyclic_siblings`): 检测包之间的循环依赖
11. **R8 Application 互斥**: 6 条 CQRS 职责隔离规则

**运行检查:**
```bash
pixi run -e dev arch-check      # 完整检查
lint-imports --contract layered-architecture  # 单独检查分层
lint-imports --contract acyclic-packages       # 单独检查循环依赖
```

### 层级穿透（禁止）

**违反规则**：跳过中间层直接访问实现细节

| ❌ 禁止 | ✅ 正确 |
|--------|--------|
| apps → Store (直接访问存储) | apps → Application → Data Service → Store |
| apps → Source (直接访问数据源) | 仅 `apps/registry` 做 DI 装配，业务路径走 Application |

**正确的访问模式**:
```python
# ✅ 正确: Apps 通过 Application 层调用
from ditto_application.queries import MarketQueryFacade
bars = facade.get_bars(query)

# ✅ 正确: registry 负责 DI 装配（Composition Root）
from ditto_data.di import get_data_providers

# ❌ 错误: 直接访问 store（即使技术上可行）
from ditto_data.storage.market.stock.bars import StockBarsReader  # ❌
store = StockBarsReader(...)  # ❌
```

### 跨包 Re-export 禁止

**原则**：需要哪个包的类型，就从哪个包导入。跨包 re-export 隐藏真实依赖关系，使重构变得危险。

```python
# ❌ 禁止：ditto_data/models/__init__.py 中 re-export kernel 类型
from ditto_kernel.instrument import AssetClass, Exchange

# ❌ 禁止：消费者通过中间包间接导入
from ditto_data.models import AssetClass  # 看不出 AssetClass 来自 kernel

# ✅ 正确：消费者直接从来源包导入
from ditto_kernel.instrument import AssetClass
```

**适用范围**：所有 ditto 内部包之间的 re-export 均被禁止。包内子模块聚合见 [python.md](../python.md) Re-export 规范。

---

## 包放置与硬性禁令

### 包放置决策

新代码放置决策树详见 [boundaries doc Section 7](../../docs/architecture/boundaries-and-abstraction-standards.md#7-新代码放置决策树)。

### 硬性禁令摘要

| 包 | 禁止依赖 | 原因 |
|---|---|---|
| `kernel` | 所有其他业务包 | 零依赖共享内核 |
| `platform` | 所有业务包 | 通用技术能力，无业务知识 |
| `data` | features/strategy/portfolio/risk/execution/backtest/analysis/application/apps | 数据平面，不决策 |
| `features` | strategy/portfolio/risk/execution/backtest/analysis/application/apps | 因子计算平面 |
| `strategy` | data/features/portfolio/risk/execution/backtest | 策略不直接执行/不查数据 |
| `portfolio` | risk/execution/backtest/data/features | 组合不直接执行 |
| `risk` | execution/backtest/data/features/strategy | 风控不依赖执行 |
| `execution` | risk/strategy/backtest/data/features | 执行不依赖回测 |
| `backtest` | 真实券商网关 | 模拟与生产隔离 |
| 所有生产包 | `analysis` | 研究层隔离 |
| `apps`(非 registry) | storage/runtime/services/models/errors/config | 传输适配不直接访问存储 |

各包详细 can/cannot 规则详见 [boundaries doc Section 4](../../docs/architecture/boundaries-and-abstraction-standards.md#4-包级职责标准)。

---

## 核心判断原则

架构中最重要的区分不是"有没有领域知识"，而是"代码在做业务决策还是数据服务":

| 维度 | 业务决策（Capability） | 数据服务（Data） |
|------|-----------------|-------------------|
| 回答的问题 | **"该不该做"** | **"数据怎么查/怎么算"** |
| 典型行为 | 策略评估、交易决策、风险判断 | 复权计算、PIT 过滤、前向收益率、Universe 过滤 |
| DDD 类比 | Domain Service | Rich Repository |
| 可否包含领域知识 | 必须包含（这是它的职责） | 可以包含（服务于"提供领域合适的数据视图"） |
| 可否做 I/O | 不可以 | 可以（这是它的职责） |

---

## PLC0415 处理决策树

```
遇到 PLC0415
    │
    ├─ 使用 importlib？ → 检查是否真的循环（验证反向导入）
    │   ├─ 否 → 顶层导入
    │   └─ 是 → 重构架构（拆分职责）
    │
    ├─ Facade @cached_property？ → 顶层导入（延迟实例化已足够）
    │
    ├─ Pydantic computed_field？ → 在 pyproject.toml 添加 noqa
    │
    └─ 可选依赖？ → try/except + 顶层导入
```

---

## 导入规范（架构补充）

### 可选依赖处理

```python
# ✅ 正确
try:
    import keyring
except ImportError:
    keyring = None

# ❌ 错误
keyring = importlib.import_module("keyring")
```

---

## 延迟初始化

### 延迟导入 vs 延迟实例化

```python
# ❌ 不推荐（除非必要）
@cached_property
def pool(self):
    from foo import Pool  # PLC0415
    return Pool()

# ✅ 推荐
from foo import Pool

@cached_property
def pool(self):
    return Pool()  # 延迟 __init__，非延迟 import
```

**原理**：顶层导入（~1-10ms）+ 延迟实例化（~10-100ms）

---

## 工厂模式

### 简单工厂（解决 SRP 违反）

```python
# factory.py
def get_source(name: str) -> DataSource:
    sources: dict[str, type[DataSource]] = {
        "tushare": TushareSource,
    }
    return sources[name]
```

**何时使用**：根据字符串名称创建实例

---

## 案例：base.py 违反 SRP

**问题**：`get_source()` 使用 `importlib`，注释说"避免循环依赖"

**验证**：`grep -r "from.*base import" tushare/` → 无反向导入 → **不是循环依赖**

**解决**：
1. 拆分： `base.py`（接口）+ `factory.py`（工厂）
2. 顶层导入: `from tushare.source import TushareSource`

---

## 子领域分层规范

### 各子领域的完整定义

#### Quality（数据质量）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Data** | `packages/data/src/ditto_data/quality/` | 检查规则算法（OHLC、涨跌停、成交量异常） |
| **Data Service** | `packages/data/` | DQ 结果持久化、数据质量元数据管理 |
| **Application** | `packages/application/src/ditto_application/processes/` | 编排 dq 检查流程 |

**关键点**：
- ✅ dq 是量化业务规则（如 OHLC 一致性是金融知识），不是通用技术约束
- ✅ dq 配置文件（YAML）定义业务规则
- ❌ 不是"技术约束"而是"领域知识"

#### Factor（因子计算）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Features** | `packages/features/src/ditto_features/` | 因子表达式编译、物化计划、因子计算、评估 |
| **Data Service** | `packages/data/` | 因子数据查询、存储 |
| **Application** | `packages/application/src/ditto_application/queries/` | 编排计算流程 |

**关键点**：
- 表达式编译在 Features（知识密集分析计算）
- 前向收益率在 Application.queries（依赖 MarketService）
- 编排流程在 Application

#### Risk（风险管理）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Risk** | `packages/risk/src/ditto_risk/` | 风险检查（PreTrade/PostTrade）、约束、暴露 |
| **Application** | `packages/application/src/ditto_application/processes/` | 风险编排（注入到回测流程） |
| **Data Service** | `packages/data/` | 风险审计记录持久化 |

#### Alpha（Alpha 决策层）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Strategy** | `packages/strategy/src/ditto_strategy/alpha/` | Alpha Pipeline、信号生成、模板 |
| **Application** | `packages/application/src/ditto_application/processes/` | Alpha 运行编排、输入组装、结果持久化 |
| **Data Service** | `packages/data/` | Alpha 定义存储、运行记录存储、产物持久化 |

#### Execution（执行）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Execution** | `packages/execution/src/ditto_execution/` | 执行计划、撮合模型、交易规则 |
| **Application** | `packages/application/src/ditto_application/processes/` | 执行编排（注入到回测流程） |
| **Backtest** | `packages/backtest/src/ditto_backtest/` | 模拟撮合 |

---

## R8 Application 内部互斥矩阵

ditto_application 内部按 CQRS 职责划分为 4 个子模块，通过 importlinter R8 规则强制互斥：

```
ditto_application/
├── queries/     # 只读查询（零写入）
├── processes/   # Process Manager（有状态长流程，按能力域分 ingestion/materialization/execution/quality 子包）
├── commands/    # Command DTO + Handler（原子写操作）
├── builders/    # 运行时装配（DI 构造）
└── runtime/     # 运行时基础设施（空包，预留）
```

### 互斥规则

| 方向 | 规则 | 状态 |
|------|------|------|
| queries → processes | r8-queries-no-processes | ✅ |
| queries → builders | r8-queries-no-builders | ✅ |
| queries → commands | r8-queries-no-commands | ✅ |
| builders → queries | r8-builders-no-queries | ✅ |
| commands → queries | r8-commands-no-queries | ✅ |
| commands → builders | r8-commands-no-builders | ✅ |

### 允许的依赖

| 方向 | 说明 |
|------|------|
| processes → queries | 编排流程可调用查询 |
| commands → processes | Command Handler 委托底层 Service |
| processes → commands | Process Manager 注入 Command Handler |
| processes ↔ builders | 双向允许 |

**设计原则**：queries 只读、commands 纯写入、processes 编排、builders 装配，四者职责不交叉。
