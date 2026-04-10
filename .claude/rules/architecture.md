---
paths:
  - ./**/*.py
---

# 架构设计规范

## 分层架构原则

### 层级依赖规则

```
┌─────────────────────────────────────────────────────────────────┐
│                       interfaces (应用边界层)                       │
│                              │                                  │
│                              ├──→ packages/app (应用编排层)          │
│                              │         │                        │
│                              │         ├──→ packages/analytics (分析层) │
│                              │         │         │                │
│                              │         │         └──→ ditto_kernel     │
│                              │         │                        │
│                              ├──→ packages/engine (领域层)         │
│                              │         │                        │
│                              │         └──→ ditto_kernel         │
│                              │                                  │
│                              ├──→ packages/data (数据服务层)        │
│                              │         │                        │
│                              │         └──> ditto_kernel         │
│                              │         └──> packages/infra         │
│                              │                                  │
│                              └──> ditto_kernel                      │
│                              └──> packages/infra                   │
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
| **领域层** | `ditto_engine` | 业务决策:引擎、策略、回测、风险、质量 | DDD Domain Service |
| **分析层** | `ditto_analytics` | 因子表达式编译、物化计划、因子计算、评估、研究 | Analysis Layer |
| **数据服务层** | `ditto_data` | 统一查询:存储、数据源、领域感知的数据编排 | DDD Rich Repository |
| **应用编排层** | `ditto_app` | Use Case 编排（CQRS: query/process/command/builders） | Application Layer |
| **应用边界层** | `ditto_interfaces` | HTTP API/CLI/Jobs/DI Composition Root | Application Boundary |
| **基础设施层** | `ditto_infra` | 技术设施:配置、日志、缓存、数据库连接池 | Technical Infrastructure |

**详细分层规范**：
- Kernel → [packages/kernel/CLAUDE.md](../../packages/kernel/CLAUDE.md)
- Infra → [packages/infra/CLAUDE.md](../../packages/infra/CLAUDE.md)
- Data → [packages/data/CLAUDE.md](../../packages/data/CLAUDE.md) | [pit.md](../../.claude/rules/pit.md)
- Engine → [packages/engine/CLAUDE.md](../../packages/engine/CLAUDE.md)
- Analytics → [packages/analytics/CLAUDE.md](../../packages/analytics/CLAUDE.md)
- App → [packages/app/CLAUDE.md](../../packages/app/CLAUDE.md)
- Interfaces → [interfaces/CLAUDE.md](../../interfaces/CLAUDE.md)

### 依赖规则

```
ditto_interfaces → ditto_app → ditto_engine → ditto_data → ditto_infra
ditto_interfaces → ditto_analytics → ditto_kernel
ditto_interfaces → ditto_data → ditto_kernel, ditto_infra
ditto_app → ditto_engine, ditto_data, ditto_analytics, ditto_kernel, ditto_infra
ditto_engine      → ditto_kernel                                            ✅
ditto_analytics   → ditto_kernel, ditto_data.errors, ditto_infra.foundation ✅
ditto_data        → ditto_kernel, ditto_infra                              ✅
ditto_kernel      → (无业务依赖)                                             ✅
ditto_infra       → (无业务依赖)                                             ✅
ditto_engine      → ditto_data (仅 errors/provider)                        ❌ (beyond)
ditto_data        → ditto_engine                                            ❌
ditto_data        → ditto_interfaces                                        ❌
ditto_infra       → 其他层                                                  ❌
```

### v5 强制边界（CI 门禁）

以下规则由 `pixi run -e dev arch-check` 强制执行，违反即 CI 失败:

使用 **Import Linter** 进行架构约束检查,配置位于 [.importlinter](../../.importlinter)。

共 24 条合约（0 broken, 0 warnings）。

**检查类型：**
1. **分层架构** (`layers`): Interfaces → App → Engine → Data → Infra
2. **Kernel 隔离** (`forbidden`): Kernel 禁止依赖其他业务包
3. **Infra 隔离** (`forbidden`): Infra 禁止依赖其他层
4. **Data 边界** (`forbidden`): Data 禁止依赖 Engine/Interfaces/App
5. **Analytics 隔离** (`forbidden`): Analytics 禁止依赖 Data（除 errors）/Engine/App
6. **Engine-Data 边界** (`forbidden`): Engine 和 Data 双向禁止互相依赖（均可依赖 Kernel）
7. **Interfaces 边界** (`forbidden`): Interfaces 非 registry 禁止依赖 storage/runtime/services/models/errors/config
8. **循环依赖** (`acyclic_siblings`): 检测包之间的循环依赖
9. **R8 App 互斥**: 6 条 CQRS 职责隔离规则

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
| interfaces → Store (直接访问存储) | interfaces → App Service → Data Service → Store |
| interfaces → Source (直接访问数据源) | 仅 `interfaces/registry` 做 DI 装配，业务路径走 App Service |
| data → engine (数据层依赖核心) | engine → kernel, data → kernel |
| engine → data (核心依赖数据，除 errors/provider) | App 编排 engine + data |

**正确的访问模式**:
```python
# ✅ 正确: Interfaces 通过 App 层调用
from ditto_app.query import MarketQueryFacade
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
from ditto_kernel.enums import AssetClass, Exchange

# ❌ 禁止：消费者通过中间包间接导入
from ditto_data.models import AssetClass  # 看不出 AssetClass 来自 kernel

# ✅ 正确：消费者直接从来源包导入
from ditto_kernel.enums import AssetClass
```

**适用范围**：所有 ditto 内部包之间的 re-export 均被禁止。包内子模块聚合见 [python.md](../python.md) Re-export 规范。

---

## 层级职责边界

### 核心判断原则：业务决策 vs 数据服务

架构中最重要的区分不是"有没有领域知识"，而是"代码在做业务决策还是数据服务":

| 维度 | 业务决策（Engine） | 数据服务（Data） |
|------|-----------------|-------------------|
| 回答的问题 | **"该不该做"** | **"数据怎么查/怎么算"** |
| 典型行为 | 策略评估、交易决策、风险判断 | 复权计算、PIT 过滤、前向收益率、Universe 过滤 |
| DDD 类比 | Domain Service | Rich Repository |
| 可否包含领域知识 | 必须包含（这是它的职责） | 可以包含（服务于"提供领域合适的数据视图"） |
| 可否做 I/O | 不可以 | 可以（这是它的职责） |

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
- kernel 类型数量控制在 20 个以内
- 不允许 `import polars` / `import orjson` 等第三方库
- pyproject.toml 不声明运行时依赖

#### ditto_engine（领域层）

**做什么**：业务决策和领域行为 — 引擎执行、策略评估、风险判断、组合优化。

**可以做的**：
- 纯领域算法（回测引擎、策略 Pipeline、质量检查）
- 业务规则（交易规则、风险约束、组合约束）
- 领域模型（富领域对象，带行为和状态机）
- Protocol 定义（供上层做依赖注入）

**不可以做的**：
- 数据查询和存储（这是 Data 的职责）
- I/O 操作（文件读写、网络请求）
- 应用编排（这是 App/Interfaces 的职责）

#### ditto_analytics（分析层）

**做什么**：因子表达式编译、物化计划、因子计算、评估指标、研究数据集。

**可以做的**：
- 表达式编译（词法 → AST → 代码生成 → 编译缓存）
- 因子计算（技术/基本面/Alpha 因子）
- 评估指标（IC、因子分析、组合分析、尾部风险）
- 研究数据集（领域模型）

**不可以做的**：
- 数据查询/存储（依赖 Data.errors 仅限错误类型）
- 业务决策（交易决策、风险判断）
- I/O 操作

#### ditto_data（数据服务层 — Rich Data Service）

**做什么**：统一的数据查询、存储、数据源接入，以及**领域感知的数据编排**。

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
- 工作流决策（何时重算、何时告警）

**设计依据**：Data 是 Rich Repository 模式的实现。Eric Evans 定义 Repository 为"mediates between the domain and data mapping layers, acting like an in-memory domain object collection" — 明确允许 Repository 包含查找逻辑和数据转换。

#### ditto_app（应用编排层 — CQRS）

**做什么**：Use Case 编排，协调 Engine（领域计算）+ Data（数据服务）。

**核心职责**：
- 从 Data 获取数据 → 交给 Engine 做业务计算 → 结果写回 Data
- CQRS 分离： query（只读）、process（编排）、command（写入）、builders（DI 构造）
- DTO ↔ Domain Model 的显式映射

**不可以做的**：
- 业务计算（应委托给 Engine）
- 数据查询编排（应委托给 Data Service）
- 直接访问 Store/Source（通过 Data DI）

#### ditto_interfaces（应用边界层）

**做什么**：HTTP API、CLI 命令、Prefect 任务调度、DI Composition Root。

**核心职责**：
- HTTP 路由（FastAPI）
- CLI 命令入口
- Prefect Flow/Task 编排
- DI 容器组装（Composition Root）
- **纯编排层，不包含业务逻辑**

**不可以做的**：
- 业务计算（应委托给 App/Engine）
- 直接数据访问（应通过 App 层或 registry DI）

---

## 判断决策树

```
问题：这个组件属于哪一层？

1. 是跨层共享的纯类型（枚举/值对象/NewType）？
   YES → ditto_kernel
   检查 5 条准入标准

2. 是业务决策或领域行为？
   （策略评估、交易决策、风险判断、引擎执行）
   YES → ditto_engine

3. 是数据查询、存储或领域感知的数据编排？
   （复权、PIT 过滤、前向收益率、Universe 过滤）
   YES → ditto_data

4. 是分析计算（表达式编译、因子计算、评估指标）？
   YES → ditto_analytics

5. 是应用编排或工作流协调？
   （组合 Engine +Data、DTO 映射、CQRS）
   YES → ditto_app

6. 是应用入口（API/CLI/Jobs/DI 装配）？
   YES → ditto_interfaces

7. 是技术基础设施？
   （日志、配置、缓存、数据库连接池）
   YES → ditto_infra
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
| **Domain** | `packages/data/src/ditto_data/quality/` | 检查规则算法（OHLC、涨跌停、成交量异常） |
| **Data Service** | `packages/data/` | DQ 结果持久化、数据质量元数据管理 |
| **Application** | `packages/app/src/ditto_app/process/` | 编排 dq 检查流程 |

**关键点**：
- ✅ dq 是量化业务规则（如 OHLC 一致性是金融知识），不是通用技术约束
- ✅ dq 配置文件（YAML）定义业务规则
- ❌ 不是"技术约束"而是"领域知识"

#### Factor（因子计算）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Domain** | `packages/engine/src/ditto_engine/alpha/` | 因子表达式编译、物化计划 |
| **Analysis** | `packages/analytics/` | 因子表达式编译、评估指标、研究数据集 |
| **Data Service** | `packages/data/` | 因子数据查询、存储 |
| **Application** | `packages/app/src/ditto_app/query/` | 编排计算流程 |

**关键点**：
- 表达式编译在 Analytics（知识密集分析计算）
- 前向收益率在 App.query（依赖 MarketService）
- 编排流程在 App

#### Risk（风险管理）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Domain** | `packages/engine/src/ditto_engine/backtest/` | 风险检查（PreTrade/PostTrade） |
| **Application** | `packages/app/src/ditto_app/process/` | 风险编排（注入到回测流程） |
| **Data Service** | `packages/data/` | 风险审计记录持久化 |

#### Alpha（Alpha 决策层，原 Strategy）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Domain** | `packages/engine/src/ditto_engine/alpha/` | Alpha Pipeline、信号生成、模板 |
| **Application** | `packages/app/src/ditto_app/process/` | Alpha 运行编排、输入组装、结果持久化 |
| **Data Service** | `packages/data/` | Alpha 定义存储、运行记录存储、产物持久化 |

#### Execution（执行）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Domain** | `packages/engine/src/ditto_engine/execution/` | 执行计划、撮合模型、交易规则 |
| **Application** | `packages/app/src/ditto_app/process/` | 执行编排（注入到回测流程） |
| **Data Service** | `packages/data/` | 执行审计记录持久化 |

### 实施检查清单

在添加新组件时，使用以下问题判断其归属：

| 问题 | 回答 Yes → 归属 | 回答 No → 归属 |
|------|----------------|---------------|
| 是跨层共享的纯类型？ | ditto_kernel（检查准入标准） | 继续下一个问题 |
| 是业务决策或领域行为？ | ditto_engine | 继续下一个问题 |
| 是分析计算（编译、因子、评估）？ | ditto_analytics | 继续下一个问题 |
| 是数据查询、存储或数据编排？ | ditto_data | 继续下一个问题 |
| 是应用编排或工作流？ | ditto_app | 继续下一个问题 |
| 是应用入口（API/CLI/Jobs/DI）？ | ditto_interfaces | 继续下一个问题 |
| 是技术基础设施？ | ditto_infra | 重新审视设计 |

**禁止重复实现**：
- ❌ Application Layer 重复实现 Domain Layer 已有的业务逻辑
- ❌ Domain Layer 直接访问存储（应通过 Data Service）
- ❌ Data 包含业务决策逻辑（应委托给 Engine）
- ❌ 多个地方重复实现相同的业务规则

---

## R8 App 内部互斥矩阵

ditto_app 内部按 CQRS 职责划分为 4 个子模块，通过 importlinter R8 规则强制互斥：

```
ditto_app/
├── query/       # 只读查询（零写入）
├── process/     # Process Manager（有状态长流程，按能力域分 ingestion/materialization/execution/quality 子包）
├── command/     # Command DTO + Handler（原子写操作）
└── builders/    # 运行时装配（DI 构造）
```

### 互斥规则

| 方向 | 规则 | 状态 |
|------|------|------|
| query → process | r8-query-no-process | ✅ |
| query → builders | r8-query-no-builders | ✅ |
| query → command | r8-query-no-command | ✅ |
| builders → query | r8-builders-no-query | ✅ |
| command → query | r8-command-no-query | ✅ |
| command → builders | r8-command-no-builders | ✅ |

### 允许的依赖

| 方向 | 说明 |
|------|------|
| process → query | 编排流程可调用查询 |
| command → process | Command Handler 委托底层 Service |
| process → command | Process Manager 注入 Command Handler |
| process ↔ builders | 双向允许 |

**设计原则**：query 只读、command 纯写入、process 编排、builders 装配，四者职责不交叉。
