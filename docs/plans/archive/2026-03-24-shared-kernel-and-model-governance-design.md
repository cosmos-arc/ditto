# Shared Kernel 与模型同质化治理设计

**日期**：2026-03-24
**状态**：Approved
**关联**：[instrument-id-semantics-unification](2026-03-24-instrument-id-semantics-unification-implementation-plan.md)

---

## 1. 背景

### 1.1 问题

Ditto 的 DataHub 和 Core 两个包存在 6 个重叠领域概念（Trading、Portfolio、Strategy、Risk/Audit、Derived、Publication Safety），每个领域都是 DataHub 持有轻量 DTO、Core 持有富领域对象。这种 DTO/Domain Model 分裂本身是合理的分层模式，但当前存在三个治理缺陷：

1. **缺少显式转换契约** — 两层之间的映射隐式分散在 Port 层各处
2. **字段语义不一致** — 同名字段类型不同（`instrument_id: int` vs `instrument_id: str`）
3. **枚举/状态不同步** — DataHub 用 `str`，Core 用 `StrEnum`，无约束保证一致性

同时，`InstrumentId` 统一身份模型的归属位置需要明确，这是 instrument-id-semantics-unification 计划的前置决策。

### 1.2 目标

1. 确立跨层共享类型的显式归属位置
2. 建立"什么类型属于共享内核"的准入标准
3. 建立 DataHub DTO ↔ Core Domain Model 之间的映射治理规则
4. 为 InstrumentId 统一迁移提供架构基座

---

## 2. 决策记录

### 2.1 Shared Kernel 归属位置

**决策**：新建独立包 `ditto_kernel`，作为所有业务包的最底层依赖。

**备选方案与排除理由**：

| 方案 | 排除理由 |
|------|---------|
| `ditto_datahub.models.kernel` 子包 | 语义倒置 — 领域原语（`AssetClass`、`Exchange`）不应放在数据访问层；Core 获取领域类型需依赖数据层，逻辑上不自然 |
| 放入 `ditto_infra` | Infra 的定位是"zero-domain, zero-business-logic"的技术基础设施，领域类型原语不属于此 |
| 放入 `ditto_core` | DataHub 无法反向依赖 Core；且 Core 应是领域行为的载体，不应承担"共享类型库"的角色 |

**选择理由**：

1. **语义正确** — 领域原语（`InstrumentId`、`AssetClass`、`Exchange`）是领域概念，不是数据概念，独立包让依赖方向自然：Core 和 DataHub 平等依赖 Kernel
2. **依赖方向干净** — Core 和 DataHub 不再需要通过白名单互相依赖，消除 import-linter 的 `ignore_imports` 特殊规则
3. **与 DataHub Rich Data Service 定位互补** — Kernel 提供共享类型，DataHub 保留领域感知的数据服务逻辑，Core 保留业务决策逻辑，各司其职
4. **业界一致** — QuantConnect LEAN 的 `QuantConnect.Common`、Spring 的 `spring-data-commons` 均采用独立 artifact
5. **成本可控** — 零逻辑、零服务、零外部依赖的纯类型包，维护成本约等于一个 `__init__.py`

### 2.2 InstrumentRef 归属位置

**决策**：`InstrumentRef` 放在 Port 层（`ditto_port.models` 或 Port services 内部）。

**理由**：`InstrumentRef` 是 Port 层编排工具，负责在边界组装时携带完整身份信息。Core 层只接收 `InstrumentId`，不需要知道 `source_ticker`。不满足"跨层使用"的 kernel 准入标准。

### 2.3 模型同质化治理策略

**决策**：采用 **Strategy B — kernel 共享类型 + 显式映射**。

- DataHub DTO 和 Core Domain Model 各自独立定义结构
- 两层的共享字段类型（ID、枚举）统一从 `ditto_kernel` 导入
- Port 层提供显式的、可测试的映射函数
- 语义不一致的枚举（如 `OrderStatus`）不强制统一，各层保留自己的定义

---

## 3. Kernel 包设计

### 3.1 包结构

```
packages/kernel/
├── pyproject.toml
├── src/
│   └── ditto_kernel/
│       ├── __init__.py       # 统一导出所有 kernel 类型
│       ├── identity.py       # InstrumentId (NewType)
│       └── enums.py          # AssetClass, Exchange, InstrumentIdRange, OrderSide, RunStatus
└── tests/
    └── unit/
        ├── test_identity.py
        └── test_enums.py
```

### 3.2 Kernel 准入标准

一个类型要进入 `ditto_kernel`，必须**同时满足**以下所有条件：

1. **跨层使用**：至少被 2 个包（DataHub + Core，或 DataHub + Port）直接导入
2. **零业务行为**：纯值对象 / 枚举 / NewType，不含方法或 I/O
3. **稳定性高**：不会随某个子域的迭代频繁变更
4. **无外部依赖**：只依赖 Python 标准库
5. **纯值语义**：不含任何 I/O、序列化、持久化关注点。如果类型需要 `asdict()`、`to_record()`、`from_row()` 等转换方法，应在 Core 或 DataHub 各自定义自己的版本

### 3.3 类型清单

#### `identity.py`

| 类型 | 定义 | 说明 |
|------|------|------|
| `InstrumentId` | `NewType("InstrumentId", int)` | Ditto 内部 canonical 主键，类型安全包装 |

#### `enums.py`

| 类型 | 迁移来源 | 迁入理由 |
|------|---------|---------|
| `AssetClass` (StrEnum) | `datahub/models/enums.py` | Core 策略层已使用资产分类概念 |
| `Exchange` (StrEnum) | `datahub/models/enums.py` | 跨层共享的交易所枚举 |
| `InstrumentIdRange` | `datahub/models/common.py` | ID 分配范围的跨层约束 |
| `OrderSide` (StrEnum) | `datahub/models/trading.py` | DataHub 和 Core 语义一致（`BUY/SELL`），统一名称消除 `OrderSide`/`OrderDirection` 歧义 |
| `RunStatus` (StrEnum) | `datahub/models/strategy_run.py` | DataHub 和 Core 值一致（`PENDING/RUNNING/COMPLETED/FAILED`），Core 侧从内联 `str` 升级为正式枚举 |

### 3.4 明确不迁入 kernel 的类型

| 类型 | 位置 | 不迁入理由 |
|------|------|-----------|
| `OrderStatus` | DataHub `trading.py` / Core `order_book.py` | 值集不同：Core 多 `NEW/SUBMITTED/INVALID`，拼写差异（`CANCELED` vs `CANCELLED`） |
| `RiskSeverity` / `RiskActionType` | Core `audit/records.py` | DataHub 刻意用 `str`（序列化灵活性），这是 DataHub DTO 的设计选择 |
| `SignalType` / `MarketState` | DataHub `strategy.py` | 两层结构不同，非语义等价 |
| `Dataset`, `Domain`, `Source` | DataHub `common.py` | DataHub 内部枚举，其他层不使用 |
| 所有 DTO / Record 类型 | DataHub `models/` | 层内模型，非跨层共享 |

### 3.5 依赖图

```
ditto_port (应用服务层)
  ├── ditto_core (领域层)
  ├── ditto_datahub (数据访问层)
  ├── ditto_kernel (共享内核)
  └── ditto_infra (基础设施层)

ditto_core      → ditto_kernel
ditto_datahub   → ditto_kernel
ditto_port      → ditto_core, ditto_datahub, ditto_kernel, ditto_infra
ditto_infra     → (无业务依赖)
ditto_kernel    → (无业务依赖)
```

**关键约束**：
- `ditto_kernel` 不依赖任何业务包（Core、DataHub、Port、Infra）
- `ditto_kernel` 不依赖任何第三方库（仅 stdlib）
- `ditto_core` 和 `ditto_datahub` 是同层关系，均可依赖 `ditto_kernel`，但彼此不依赖

### 3.6 import-linter 规则更新

```ini
[importlinter:contract:kernel-isolation]
name = Kernel must not depend on other layers
type = forbidden
source_modules =
    ditto_kernel.**
forbidden_modules =
    ditto_core.**
    ditto_datahub.**
    ditto_port.**
    ditto_infra.**

[importlinter:contract:core-datahub-boundary]
name = Core and DataHub must not depend on each other
type = forbidden
source_modules =
    ditto_core.**
    ditto_datahub.**
forbidden_modules =
    ditto_core.**
    ditto_datahub.**
# 允许两者都依赖 kernel
ignore_imports =
    ditto_core.** -> ditto_kernel.*
    ditto_datahub.** -> ditto_kernel.*
unmatched_ignore_imports_alerting = none
```

原有的 `core-datahub-boundary` 合并为双向禁止规则，不再需要 `ignore_imports` 对 `datahub.models.*` 和 `datahub.errors` 的例外。

---

## 4. Port 层映射治理规则

当 DataHub DTO 和 Core Domain Model 之间需要转换时，遵循以下规则：

### 4.1 职责分离

| 层 | 职责 | 禁止 |
|----|------|------|
| Port | 定义显式映射函数（DTO → Domain / Domain → DTO） | 不允许在 DataHub 或 Core 中写跨层转换逻辑 |
| DataHub | 持有 DTO，共享字段类型从 `ditto_kernel` 导入 | 不依赖 Core 模型 |
| Core | 持有 Domain Model，共享字段类型从 `ditto_kernel` 导入 | 不依赖 DataHub DTO |

### 4.2 映射函数要求

1. **必须显式定义** — 不允许隐式转换（如直接 `**kwargs` 展开）
2. **必须有单元测试** — 覆盖 `None` 字段、类型不匹配、枚举映射等边界情况
3. **共享字段从 kernel 导入类型** — 如 `instrument_id: InstrumentId`、`side: OrderSide`
4. **非共享枚举显式映射** — 如 `OrderStatus` 转换需要显式 case-by-case 映射

### 4.3 数据流示意

```
DataHub DTO ──[Port 映射函数]──→ Core Domain Model
     ↑                                ↑
     └── 共享字段类型来自 ditto_kernel ─┘
```

---

## 5. 对 Instrument ID 统一计划的影响

本设计是 [instrument-id-semantics-unification](2026-03-24-instrument-id-semantics-unification-implementation-plan.md) 的前置架构决策。具体影响：

1. **Phase 0 调整**：`InstrumentId` NewType 放入 `ditto_kernel.identity`（而非原计划的 `ditto_datahub.models.kernel`）
2. **Phase 0 扩展**：同步迁移 `AssetClass`、`Exchange`、`InstrumentIdRange`、`OrderSide`、`RunStatus` 到 `ditto_kernel.enums`
3. **Phase 2 调整**：Core 层 `instrument_id: str` → `instrument_id: InstrumentId` 时，直接从 `ditto_kernel` 导入
4. **InstrumentRef**：放在 Port 层，不进入 kernel
5. **Core 的 `OrderDirection`**：统一为 kernel 的 `OrderSide`，需要同步修改 Core 的引用
6. **DataHub `models/__init__.py`**：迁出的类型改为从 `ditto_kernel` re-export（保持向后兼容过渡期）

---

## 6. 后续演进

### 6.1 短期（本次 Instrument ID 统一）

- 创建 `packages/kernel/` 独立包
- 迁入 6 个共享类型
- 更新 DataHub 和 Core 的导入路径
- 更新 import-linter 规则
- 在 instrument-id-semantics-unification 计划中反映这些变更

### 6.2 中期（模型治理常态化 + 架构调整）

- 代码审查清单：新增涉及跨层概念的代码时，检查是否应放入 kernel
- 当发现新的跨层共享类型需求时，按准入标准评估是否迁入 kernel
- 将 Port 层混入的业务逻辑下沉到 Core（详见 §7 DataHub 定位决策）：
  - `StrategyInputAssembler` 中的硬编码默认动量信号
  - `DerivedPublicationFacade` 中的 shadow diff 计算逻辑
  - `DerivedMaterializationOrchestrator` 中的 CS amplification 逻辑
  - `IngestionCoordinator` 中的 `_infer_exchange_suffix()` 交易所后端推断
  - `MarketServiceDataFeed` 中的 `prev_close` 计算和 `amount` 回退

### 6.3 长期（kernel 治理红线）

- kernel 类型数量控制在 20 个以内
- 如果 kernel 开始出现需要 `import polars` 或 `import orjson` 的类型，说明准入标准被突破，需要重新审视
- kernel 的 pyproject.toml 不应声明任何运行时依赖

---

## 7. DataHub 定位决策：Rich Data Service Layer

### 7.1 问题

全库架构审计发现 DataHub 中存在"领域逻辑"，初步建议将其迁移到 Core。但进一步分析后认识到，"领域逻辑"需要区分为两种本质不同的概念：

| | 业务决策（Business Decision） | 数据服务逻辑（Data Service Logic） |
|---|---|---|
| 本质 | "该不该做" | "数据怎么查/怎么算" |
| 例子 | 是否交易？风险敞口多少？策略信号是什么？ | 复权后 K 线、前向收益率、PIT 安全过滤、过滤后的 Universe |
| 归属 | Core | DataHub |
| DDD 类比 | Domain Service | Repository（Rich Repository） |

### 7.2 决策

**DataHub 定位为 Rich Data Service Layer（富数据服务层），而非简单的"哑 CRUD 层"。**

DataHub 可以包含领域感知的数据编排逻辑（如复权、PIT 过滤、前向收益率计算），因为这是 Repository 模式的正当职责 — "提供领域合适的数据视图"。DataHub 不应该包含业务决策逻辑（如策略评估、交易执行、组合优化），那是 Core 的职责。

### 7.3 边界规则

```
DataHub 可以做                          DataHub 不应该做
─────────────                          ─────────────────
✅ 统一查询入口                          ❌ 业务决策（该不该交易）
✅ 数据转换（复权、PIT 过滤）              ❌ 策略评估（信号计算、打分）
✅ 衍生数据计算（前向收益率）              ❌ 交易执行（下单、撮合）
✅ 领域感知的过滤（流动性、上市天数）        ❌ 组合优化（权重分配、约束求解）
✅ 数据编排（多源合并、缺失值处理）         ❌ 工作流决策（何时重算、何时告警）
```

### 7.4 具体模块归属

| 模块 | 分类 | 结论 | 理由 |
|------|------|------|------|
| `helpers/adjustment.py` | 数据转换 | **留在 DataHub** | 复权是"提供领域合适的数据视图"，属于 Repository 职责 |
| `helpers/pit/policy.py` | 数据约束 | **留在 DataHub** | PIT 安全是数据查询的完整性约束 |
| `services/forward_return_service.py` | 衍生数据计算 | **留在 DataHub** | 本质是物化视图/派生数据集计算 |
| `services/late_arrival.py` | 数据质量策略 | **留在 DataHub** | 数据入库时的完整性校验，属于数据服务职责 |
| `market_service._apply_adjustment()` | 数据编排 | **留在 DataHub** | 统一查询入口的数据编排，不是业务决策 |
| `market_service._resolve_instrument_ids()` | 数据编排 | **留在 DataHub** | 标识符解析是数据服务的基础能力 |

### 7.5 业界参考

- **Eric Evans**：Repository "mediates between the domain and data mapping layers, acting like an in-memory domain object collection" — 明确允许 Repository 包含查找逻辑和数据转换
- **QuantConnect LEAN**：`SecurityService` 在 Common 项目中直接提供 `GetRawData()` 等方法，内部包含交易日历过滤、时区处理等"领域感知"逻辑
- **Spring Data**：支持 `@Query` 注解在 Repository 接口中写领域特定的查询逻辑

---

## 附录 A：决策演进记录

### v1（原始设计）→ v2（独立 kernel）→ v3（本版，DataHub 定位修正）

| 变更 | v1 | v2 | v3 | 理由 |
|------|----|----|----|------|
| kernel 位置 | `ditto_datahub.models.kernel` 子包 | 独立 `ditto_kernel` 包 | 不变 | 领域原语不属于数据层 |
| 依赖方向 | 不变 | Kernel 作为底层被 Core 和 DataHub 平等依赖 | 不变 | 让依赖方向与语义层次一致 |
| import-linter | 白名单允许 `core → datahub.models.*` | 双向禁止 core↔datahub | 不变 | 消除特殊规则 |
| 准入标准 | 4 条 | 5 条（新增"纯值语义"） | 不变 | 防止 kernel 沦为 DTO 库 |
| DataHub 定位 | （未明确） | 建议迁移领域函数到 Core | **Rich Data Service Layer** | 区分"业务决策"与"数据服务逻辑"；复权/PIT/前向收益率属于 Repository 职责 |
| 中期迁移项 | — | 迁移 4 个 DataHub 模块到 Core | **撤销该迁移**；改为将 Port 层业务逻辑下沉到 Core | DataHub 的数据编排逻辑是正当的 Repository 职责 |
