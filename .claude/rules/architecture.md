---
paths:
  - ./**/*.py
---

# 架构设计规范

## 分层架构原则

### 层级依赖规则

```
┌─────────────────────────────────────────────────────────────────┐
│                       apps (应用入口和 Composition Root)              │
│                              │                                  │
│                              ├──→ packages/application (应用编排层)     │
│                              │         │                        │
│                              │         ├──→ packages/features (因子计算层) │
│                              │         │                        │
│                              │         ├──→ packages/strategy (策略层)   │
│                              │         │                        │
│                              │         ├──→ packages/portfolio (组合层)  │
│                              │         │                        │
│                              │         ├──→ packages/risk (风控层)       │
│                              │         │                        │
│                              │         ├──→ packages/execution (执行层)  │
│                              │         │                        │
│                              │         ├──→ packages/backtest (回测层)   │
│                              │         │                        │
│                              │         ├──→ packages/analysis (研究分析层)│
│                              │         │                        │
│                              │         └──→ packages/data (数据服务层)    │
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

**各层定位**：

| 层 | 包 | 职责 | 类比 |
|----|-----|------|------|
| **共享内核** | `ditto_kernel` | 领域原语：枚举、值对象、NewType | DDD Shared Kernel |
| **因子计算层** | `ditto_features` | 因子表达式编译、物化计划、因子计算、评估 | Analysis Layer |
| **策略层** | `ditto_strategy` | 策略定义、Alpha Pipeline、信号生成 | Domain Service |
| **组合层** | `ditto_portfolio` | 持仓、目标组合、调仓、会计 | Domain Service |
| **风控层** | `ditto_risk` | 盘前/盘后风控、约束、暴露、审计 | Domain Service |
| **执行层** | `ditto_execution` | 订单、成交、OMS、券商网关、对账 | Domain Service |
| **回测层** | `ditto_backtest` | 回测运行时、模拟 broker、绩效 | Domain Service |
| **研究分析层** | `ditto_analysis` | 研究数据集 control-plane；产品分析命名空间保留/未来 | Analysis Layer |
| **数据服务层** | `ditto_data` | 市场事实数据：存储、数据源、质量 | DDD Rich Repository |
| **应用编排层** | `ditto_application` | CQRS 编排（commands/queries/processes/builders） | Application Layer |
| **应用入口层** | `ditto_apps` | HTTP API/CLI/Jobs/DI Composition Root | Application Boundary |
| **基础设施层** | `ditto_platform` | 技术设施:配置、日志、缓存、数据库连接池 | Technical Infrastructure |

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
from ditto_data.storage.bars_store import BarsStore  # ❌
store = BarsStore(...)  # ❌
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

## 层级职责边界

### 核心判断原则：业务决策 vs 数据服务

架构中最重要的区分不是"有没有领域知识"，而是"代码在做业务决策还是数据服务":

| 维度 | 业务决策（Capability） | 数据服务（Data） |
|------|-----------------|-------------------|
| 回答的问题 | **"该不该做"** | **"数据怎么查/怎么算"** |
| 典型行为 | 策略评估、交易决策、风险判断 | 复权计算、PIT 过滤、前向收益率、Universe 过滤 |
| DDD 类比 | Domain Service | Rich Repository |
| 可否包含领域知识 | 必须包含（这是它的职责） | 可以包含（服务于"提供领域合适的数据视图"） |
| 可否做 I/O | 不可以 | 可以（这是它的职责） |

### 包放置决策树

```
市场事实、PIT、数据质量、外部数据源？ → ditto_data
因子、指标、表达式、物化、因子评估？ → ditto_features
策略定义、策略版本、信号、alpha pipeline？ → ditto_strategy
持仓、目标组合、调仓、会计？ → ditto_portfolio
盘前/盘后风控、约束、暴露、审计？ → ditto_risk
订单、成交、OMS、券商网关、对账？ → ditto_execution
回测运行时、模拟 broker、绩效？ → ditto_backtest
研究数据集构建、导出、control-plane？ → ditto_analysis
command/query/process 编排？ → ditto_application
API/CLI/worker/web/DI composition root？ → ditto_apps
配置、日志、metrics、trace、存储连接、锁、缓存？ → ditto_platform
跨模块稳定值对象和错误根？ → ditto_kernel
```

### 各层职责详述

#### ditto_kernel（共享内核）

**做什么**：跨层共享的领域原语 — 枚举、值对象、NewType。

**准入标准**（5 条，全部满足才可进入）：
1. **跨层使用**：至少被 2 个业务包直接导入
2. **零业务行为**：纯值对象 / 枚举 / NewType，不含方法或 I/O
3. **稳定性高**：不会随某个子域的迭代频繁变更
4. **无外部依赖**：只依赖 Python 标准库
5. **纯值语义**：不含序列化、持久化关注点

**红线**：
- 不设硬性数量上限（每个新增类型须在 PR 中说明理由）
- 不允许 `import polars` / `import orjson` 等第三方库
- pyproject.toml 不声明运行时依赖

#### ditto_features（因子计算层）

**做什么**：因子表达式编译、物化计划、因子计算、评估指标。

**可以做的**：
- 表达式编译（词法 → AST → 代码生成 → 编译缓存）
- 因子计算（技术/基本面/Alpha 因子）
- 评估指标（IC、因子分析、组合分析、尾部风险）
- 物化计划与缓存

**不可以做的**：
- 依赖 strategy/portfolio/risk/execution/backtest/analysis
- 业务决策（交易决策、风险判断）
- I/O 操作（存储由 data 层提供）

#### ditto_strategy（策略层）

**做什么**：策略定义、Alpha Pipeline、信号生成。

**可以做的**：
- Alpha Pipeline（策略评估、信号生成、模板）
- 策略模型与版本管理
- 信号存储接口（Protocol）
- 纯领域算法

**不可以做的**：
- 依赖 ditto_execution（策略不直接执行交易）
- 数据查询和存储（这是 Data 的职责）
- I/O 操作

#### ditto_portfolio（组合层）

**做什么**：持仓管理、目标组合构建、调仓逻辑、会计核算。

**可以做的**：
- 组合优化与约束
- 持仓与会计核算
- 调仓算法

**不可以做的**：
- 依赖 ditto_execution（组合不直接执行）
- 数据查询和存储
- I/O 操作

#### ditto_risk（风控层）

**做什么**：盘前/盘后风控检查、约束计算、暴露分析。

**可以做的**：
- 风控规则引擎（PreTrade/PostTrade）
- 约束计算
- 暴露分析与审计

**不可以做的**：
- 依赖 ditto_execution（风控不直接执行）
- 依赖 ditto_backtest
- I/O 操作

#### ditto_execution（执行层）

**做什么**：订单管理、成交处理、OMS、券商网关适配。

**可以做的**：
- 订单生命周期管理
- 成交处理与对账
- 券商网关协议（Protocol）

**不可以做的**：
- 依赖 ditto_backtest（执行不依赖回测）
- 依赖 ditto_analysis
- 策略逻辑

#### ditto_backtest（回测层）

**做什么**：回测运行时、模拟 broker、绩效分析。

**可以做的**：
- 回测引擎与事件循环
- 模拟撮合
- 绩效计算

**不可以做的**：
- 导入真实券商网关
- I/O 操作（除回测结果持久化）

#### ditto_analysis（研究 control-plane 层 — 非生产路径）

**做什么**：研究数据集 control-plane 与 analysis-owned artifact I/O。

**可以做的**：
- 研究数据集构建元数据
- 研究 artifact 读取与导出
- analysis-owned storage wiring

**保留/未来**：
- 报告/诊断/实验/筛选产品命名空间当前不是 runtime API

**不可以做的**：
- 被生产包依赖
- 直接执行交易或策略

#### ditto_data（数据服务层 — Rich Data Service）

**做什么**：市场事实数据的统一查询、存储、数据源接入，以及**领域感知的数据编排**。

**可以做的**：
- 统一查询入口（`MarketService.get_bars()`, `MetadataService.get_trading_days()`）
- 数据转换（复权、PIT 过滤、基准对齐）
- 衍生数据计算（前向收益率、移动平均）
- 领域感知的过滤（流动性过滤、上市天数过滤、Universe 筛选）
- 数据编排（多源合并、缺失值处理、标识符解析）
- 数据质量策略（晚到数据检测、入库校验）
- DI Provider 注册（`ditto_data.di.get_data_providers`）

**不可以做的**：
- 业务决策（是否交易、风险敞口判断、策略信号生成）
- 策略评估（打分、排序、选择）
- 交易执行（下单、撮合、组合优化）
- 依赖 capability packages（strategy/portfolio/risk/execution/backtest）
- 工作流决策（何时重算、何时告警）

**设计依据**：Data 是 Rich Repository 模式的实现。Eric Evans 定义 Repository 为"mediates between the domain and data mapping layers, acting like an in-memory domain object collection" — 明确允许 Repository 包含查找逻辑和数据转换。

#### ditto_application（应用编排层 — CQRS）

**做什么**：Use Case 编排，协调 Capability Packages（领域计算）+ Data（数据服务）。

**核心职责**：
- 从 Data 获取数据 → 交给 Capability Package 做业务计算 → 结果写回 Data
- CQRS 分离： queries（只读）、processes（编排）、commands（写入）、builders（DI 构造）
- DTO ↔ Domain Model 的显式映射

**不可以做的**：
- 业务计算（应委托给 Capability Package）
- 数据查询编排（应委托给 Data Service）
- 直接访问 Store/Source（通过 Data DI）

#### ditto_apps（应用入口层）

**做什么**：HTTP API、CLI 命令、Prefect 任务调度、DI Composition Root。

**核心职责**：
- HTTP 路由（FastAPI）
- CLI 命令入口
- Prefect Flow/Task 编排
- DI 容器组装（Composition Root）
- **纯编排层，不包含业务逻辑**

**不可以做的**：
- 业务计算（应委托给 Application/Capability Package）
- 直接数据访问（应通过 Application 层或 registry DI）

---

## 判断决策树

```
问题：这个组件属于哪一层？

1. 是跨层共享的纯类型（枚举/值对象/NewType）？
   YES → ditto_kernel
   检查 5 条准入标准

2. 是市场事实数据、PIT、数据质量、外部数据源？
   YES → ditto_data

3. 是因子、指标、表达式编译、物化、因子评估？
   YES → ditto_features

4. 是策略定义、信号生成、Alpha Pipeline？
   YES → ditto_strategy

5. 是持仓、目标组合、调仓、会计？
   YES → ditto_portfolio

6. 是风控检查、约束、暴露分析？
   YES → ditto_risk

7. 是订单、成交、券商网关、对账？
   YES → ditto_execution

8. 是回测运行时、模拟 broker、绩效？
   YES → ditto_backtest

9. 是研究数据集构建、导出、control-plane？
   YES → ditto_analysis

10. 是应用编排或工作流协调？
    （CQRS: commands/queries/processes/builders）
    YES → ditto_application

11. 是应用入口（API/CLI/Jobs/DI 装配）？
    YES → ditto_apps

12. 是技术基础设施？
    （日志、配置、缓存、数据库连接池）
    YES → ditto_platform
```

---

## 单一职责原则（SRP）

### 禁止混合职责

| ❌ 违反 SRP | ✅ 正确 |
|------------|--------|
| Protocol + Factory 混在同一文件 | `base.py`（接口）+ `factory.py`（工厂） |
| 使用 `importlib` 绕过"循环依赖" | 顶层导入 + 字典映射 |

**识别信号**：注释解释"为什么用复杂方案" → 可能是架构问题

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

### 实施检查清单

在添加新组件时，使用以下问题判断其归属：

| 问题 | 回答 Yes → 归属 | 回答 No → 归属 |
|------|----------------|---------------|
| 是跨层共享的纯类型？ | ditto_kernel（检查准入标准） | 继续下一个问题 |
| 是市场事实数据？ | ditto_data | 继续下一个问题 |
| 是因子/表达式/评估？ | ditto_features | 继续下一个问题 |
| 是策略/信号/Alpha？ | ditto_strategy | 继续下一个问题 |
| 是持仓/调仓/会计？ | ditto_portfolio | 继续下一个问题 |
| 是风控/约束/暴露？ | ditto_risk | 继续下一个问题 |
| 是订单/成交/网关？ | ditto_execution | 继续下一个问题 |
| 是回测/模拟/绩效？ | ditto_backtest | 继续下一个问题 |
| 是研究数据集 control-plane？ | ditto_analysis | 继续下一个问题 |
| 是应用编排或工作流？ | ditto_application | 继续下一个问题 |
| 是应用入口（API/CLI/Jobs/DI）？ | ditto_apps | 继续下一个问题 |
| 是技术基础设施？ | ditto_platform | 重新审视设计 |

**禁止重复实现**：
- ❌ Application Layer 重复实现 Capability Package 已有的业务逻辑
- ❌ Capability Package 直接访问存储（应通过 Data Service）
- ❌ Data 包含业务决策逻辑（应委托给 Capability Package）
- ❌ 多个地方重复实现相同的业务规则

---

## R8 Application 内部互斥矩阵

ditto_application 内部按 CQRS 职责划分为 4 个子模块，通过 importlinter R8 规则强制互斥：

```
ditto_application/
├── queries/     # 只读查询（零写入）
├── processes/   # Process Manager（有状态长流程，按能力域分 ingestion/materialization/execution/quality 子包）
├── commands/    # Command DTO + Handler（原子写操作）
└── builders/    # 运行时装配（DI 构造）
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
