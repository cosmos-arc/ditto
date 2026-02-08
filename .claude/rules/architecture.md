---
paths: ./**/*.py
---

# 架构设计规范

## 分层架构原则

### 层级依赖规则

```
┌─────────────────────────────────────────────────────────┐
│                    apps/port (应用层)                    │
│                         │                                │
│                         ├──→ packages/datahub (数据层)   │
│                         │         │                      │
│                         │         └──→ packages/foundation │
│                         │                                │
│                         └──→ packages/core (核心层)      │
│                                   │                      │
│                                   └──→ packages/foundation │
└─────────────────────────────────────────────────────────┘
```

**依赖规则**：
- **应用层** (port) → 数据层 (datahub) ✅
- **应用层** (port) → 核心层 (core) ✅
- **应用层** (port) → **横切层 (foundation)** ✅ **（允许）**
- **数据层** (datahub) → 横切层 (foundation) ✅
- **核心层** (core) → 横切层 (foundation) ✅
- **数据层** (datahub) → 应用层 (port) ❌ 反向依赖
- **横切层** (foundation) → 其他层 ❌ 零依赖

### v5 强制边界（CI 门禁）

以下规则由 `pixi run -e dev arch-check` 强制执行，违反即 CI 失败：

1. `packages/foundation/src/**` 禁止依赖 `ditto_core` / `ditto_datahub` / `ditto_port`
2. `packages/datahub/src/**` 禁止依赖 `ditto_core` / `ditto_port`
3. `packages/core/src/**` 仅允许依赖 `ditto_datahub.models`，禁止依赖 DataHub 实现模块
4. `apps/port/src/ditto_port/**`（非 `registry`）禁止直接导入：
   - `ditto_datahub.stores.*`
   - `ditto_datahub.sources.*`
   - `ditto_datahub.runtime.*`
5. `apps/port/src/ditto_port/registry/**` 可以导入 stores/sources 进行 DI 装配，但禁止在
   Provider 中直接调用它们的业务方法（只允许注入与构造）

### 横切层 (Foundation)

**定义**：提供跨所有层的基础设施服务，可被任何层访问

**包含模块**：
- `config` - 配置管理（Settings、路径管理）
- `observability` - 可观测性（日志、追踪、指标）
- `util` - 通用工具（校验和、日期处理）
- `cache` - 通用缓存（DataCache）
- `concurrency` - 并发控制（FileLockManager）
- `db` - 数据库连接管理（SQLitePool）
- `version` - 版本管理（Checksum、版本标识）

**正确使用**：
```python
# ✅ 所有层都可以直接使用 foundation
from ditto_foundation.observability import get_logger
from ditto_foundation.config import get_settings
from ditto_foundation.util.checksum import file_checksum
```

### 层级穿透（禁止）

**违反规则**：跳过中间层直接访问实现细节

| ❌ 禁止 | ✅ 正确 |
|--------|--------|
| port → Store (直接访问存储) | port → DataHub Service → Store |
| port → Source (直接访问数据源) | 仅 `port/registry` 做 DI 装配，业务路径走 Service |
| datahub → core (数据层依赖核心) | core → datahub (核心依赖数据) |

**v5 更新（2026-02-08）**：
- ✅ Port 层业务代码统一调用 DataHub Service
- ✅ `apps/port/src/ditto_port/registry/**` 可导入 stores/sources 仅用于 DI 构造
- ❌ Port 运行路径禁止直接调用 Store/Source 业务方法

**正确的访问模式**：
```python
# ✅ 正确：Port 通过 DataHub Service 调用
bars = hub.market.get_bars(query)
calendar = hub.metadata.get_trading_days(start, end)

# ✅ 正确：registry 仅负责 DI 装配
def provide_sqlite_client(pool: SQLitePool) -> SQLiteClient:
    return SQLiteClient(pool)

# ❌ 错误：直接访问 store（即使技术上可行）
from ditto_datahub.stores.bars_store import BarsStore  # ❌
store = BarsStore(...)  # ❌
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
1. 拆分：`base.py`（接口）+ `factory.py`（工厂）
2. 顶层导入：`from tushare.source import TushareSource`

---

## 子领域分层规范

### 核心原则

| 层级 | 职责 | 典型组件 | 判断标准 |
|------|------|----------|----------|
| **Domain Layer** | 业务逻辑、领域知识 | 引擎、算法、规则 | 是否是业务逻辑/规则？ |
| **Application Layer** | 用例编排、事务边界 | 服务、协调器 | 是否是用例编排？ |
| **Infrastructure Layer** | 数据访问、持久化 | Store、Service、Source | 是否是数据访问？ |

### 判断决策树

```
问题：这个组件属于哪一层？

1. 是否是业务逻辑/规则？
   YES → Domain Layer (packages/core/)

2. 是否是用例编排（协调多个服务）？
   YES → Application Layer (apps/port/services/)

3. 是否是数据访问（存储、查询）？
   YES → Infrastructure Layer (packages/datahub/)
```

### 各子领域的完整定义

#### Quality（数据质量）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Domain** | `packages/core/src/ditto_core/quality/` | 检查规则算法（OHLC、涨跌停、成交量异常） |
| **Application** | `apps/port/src/ditto_port/services/ingestion/` | 编排 dq 检查流程 |
| **Infrastructure** | `packages/datahub/src/ditto_datahub/domains/**` | 保存检查结果、隔离失败数据与服务封装 |

**关键点**：
- ✅ dq 是量化业务规则（如 OHLC 一致性是金融知识），不是通用技术约束
- ✅ dq 配置文件（YAML）定义业务规则
- ❌ 不是"技术约束"，而是"领域知识"

#### Factor（因子计算）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Domain** | `packages/core/src/ditto_core/factor/` | 因子计算算法（RS、动量、波动率） |
| **Application** | `apps/port/src/ditto_port/services/factor/` | 编排计算流程（获取数据、计算、清洗、保存） |
| **Infrastructure** | `packages/datahub/src/ditto_datahub/stores/factors/` | 因子数据持久化 |

**关键点**：
- 计算逻辑在 Core（纯函数、无状态）
- 编排流程在 Application（获取数据、调用计算、保存结果）
- 存储在 DataHub（parquet 文件）

#### ML（机器学习）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Domain** | `packages/core/src/ditto_core/ml/` | ML 算法实现（训练、预测、评估） |
|  | `core/ml/models/` | ML 模型定义（RandomForest、XGBoost） |
|  | `core/ml/metrics/` | 评估指标（Sharpe、IC Rank） |
| **Application** | `apps/port/src/ditto_port/services/ml/` | 编排训练流程（特征工程、训练、验证、部署） |
| **Infrastructure** | `packages/datahub/src/ditto_datahub/stores/models/` | 模型持久化（pickle、joblib） |

**关键点**：
- `ml/models` 是算法实现（Domain Layer），不是数据模型（如 ORM）
- 训练/预测是业务逻辑（Domain Layer）
- 特征工程编排是应用层（Application Layer）

#### Risk（风险管理）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Domain** | `packages/core/src/ditto_core/risk/` | 风险模型（回撤检测、风险度量） |
| **Application** | `apps/port/src/ditto_port/services/risk/` | 风险监控、告警编排 |
| **Infrastructure** | `packages/datahub/src/ditto_datahub/stores/risk_metrics/` | 风险指标存储 |

#### Strategy（策略）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Domain** | `packages/core/src/ditto_core/strategy/` | 策略逻辑、信号生成 |
|  | `core/strategy/base.py` | 策略抽象基类 |
| **Application** | `apps/port/src/ditto_port/services/trading/` | 交易执行编排 |
| **Infrastructure** | `packages/datahub/src/ditto_datahub/stores/orders/` | 订单存储 |

#### Signal（信号）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Domain** | `packages/core/src/ditto_core/strategy/signal/` | 信号生成逻辑 |
| **Application** | `apps/port/src/ditto_port/services/signal/` | 信号管理编排 |
| **Infrastructure** | `packages/datahub/src/ditto_datahub/stores/signals/` | 信号存储 |

#### Execution（执行）

| 层级 | 路径 | 职责 |
|------|------|------|
| **Domain** | `packages/core/src/ditto_core/strategy/execution/` | 执行逻辑（订单拆分、路由） |
| **Application** | `apps/port/src/ditto_port/services/execution/` | 执行编排 |
| **Infrastructure** | `packages/datahub/src/ditto_datahub/stores/trades/` | 成交存储 |

### 统一的依赖关系

```
Application Layer (apps/port/services/)
    │
    ├── quality.QualityEngine.check()
    ├── factor.FactorEngine.calc()
    ├── ml.MLEngine.train()
    ├── risk.RiskEngine.check()
    ├── strategy.Strategy.generate_signals()
    └── execution.ExecutionEngine.execute_orders()
    │
    ↓ 依赖
Domain Layer (packages/core/)
    │
    └── 依赖
Infrastructure Layer (packages/datahub/)
    │
    └── 依赖
Foundation Layer (packages/foundation/)
```

**依赖规则**：
- ✅ Application → Domain
- ✅ Application → Infrastructure
- ✅ Domain → Infrastructure
- ✅ Infrastructure → Foundation
- ❌ Infrastructure → Domain（禁止反向依赖）
- ❌ Foundation → 其他层（零依赖）

### 配置文件位置

| 组件 | 配置类型 | 位置 | 说明 |
|------|---------|------|------|
| **quality** | 业务规则 | `data_root/config/dq/*.yaml` | L1/L2/L3 检查规则 |
| **factor** | 因子定义 | `data_root/config/factors/*.yaml` | 因子公式、参数 |
| **ml** | 模型配置 | `data_root/config/ml/*.yaml` | 算法选择、超参数 |
| **risk** | 风险参数 | `data_root/config/risk/*.yaml` | 风险阈值、参数 |

**原则**：配置与代码分离，运行时动态加载。

### 实施检查清单

在添加新组件时，使用以下问题判断其归属：

| 问题 | 回答 Yes → 归属 | 回答 No → 归属 |
|------|----------------|---------------|
| 是否直接访问存储文件/数据库？ | DataHub Store | 使用 DataHub Service |
| 是否包含业务规则/算法逻辑？ | Domain Layer | 不应在此层 |
| 是流程编排/任务协调？ | Application Layer | 不应在此层 |
| 是否依赖外部数据源（API/爬虫）？ | DataHub Source | 不应在此层 |

**禁止重复实现**：
- ❌ Application Layer 重复实现 Domain Layer 已有的业务逻辑
- ❌ Domain Layer 直接访问存储（应通过 Infrastructure）
- ❌ 多个地方重复实现相同的业务规则

### Runtime 与 Foundation 边界

**核心原则**：

| 维度 | Foundation | Runtime |
|------|-----------|---------|
| **领域知识** | 零领域概念 | 可包含领域概念 |
| **外部依赖** | 标准库 + 基础设施库 | 可依赖领域相关库 |
| **复用性** | 可独立提取为包 | 与 datahub 耦合 |
| **依赖内部模型** | 不依赖 datahub.models | 可依赖 datahub.models |

**开发者决策树**：

```
这是技术组件还是业务逻辑？
├── 技术组件 → 是否依赖领域模型？
│   ├── 是 → runtime/
│   └── 否 → foundation/
└── 业务逻辑 → domains/** (services/stores/models)

这是代码模块还是项目脚本？
├── Python 代码模块 → runtime/ 或 foundation/
└── SQL/Shell 脚本 → scripts/
```

**判断示例**：

| 问题 | Foundation | Runtime | Scripts |
|------|-----------|---------|---------|
| 缓存实现需要知道"证券"吗？ | ✅ DataCache | ❌ | ❌ |
| 文件锁需要知道"交易日"吗？ | ✅ FileLockManager | ❌ | ❌ |
| Instrument ID 分配需要知道"股票/ETF"吗？ | ❌ | ✅ InstrumentIdAllocator | ❌ |
| SQL 引擎需要知道"复权"吗？ | ❌ | ✅ SqlEngine | ❌ |
| 这是 Python 代码还是 SQL 脚本？ | ❌ | ❌ | ✅ schema.sql |
