# Kernel 层架构规范

## 定位

Kernel 层是 **Shared Kernel — 类型 + Protocol 抽象 + 薄实现**，提供跨层共享的领域原语和系统级抽象。

**核心原则**：
- 零业务行为、零外部依赖、零 I/O
- 值语义：枚举、NewType、值对象
- Protocol 抽象：跨层共享的接口契约
- 薄实现：系统级基础设施（如 SimulatedClock、SimpleEventBus）
- 位于依赖图最底层，被所有业务包依赖

### 值对象准入标准（5 条，全部满足才可进入）

| # | 标准 | 说明 |
|---|------|------|
| 1 | 跨层使用 | 至少被 2 个业务包直接导入 |
| 2 | 零业务行为 | 纯值对象 / 枚举 / NewType。frozen dataclass 允许纯计算型 `@property`（无副作用、无 I/O、仅基于自身字段） |
| 3 | 稳定性高 | 不会随某个子域的迭代频繁变更 |
| 4 | 无外部依赖 | 只依赖 Python 标准库 |
| 5 | 纯值语义 | 不含序列化、持久化关注点 |

### Protocol / 薄实现准入标准

适用于 Clock、EventBus 等 Protocol 及其薄实现类
（SimulatedClock、RealtimeClock、SimpleEventBus）。

1. **预期跨层使用**：至少被 2 个业务包消费
   - Phase 0 定义阶段允许"预期"（在 PR 描述中声明）
   - Phase 1 完成后验证实际消费关系
2. **零业务逻辑**：Protocol 定义纯接口签名；薄实现不含领域逻辑
3. **无外部依赖**：仅依赖 Python 标准库
4. **实现体 < 30 行**：每个薄实现类的方法体总计不超过 30 行
5. **无 I/O**：不进行文件读写、网络请求、数据库操作

**薄实现豁免**：SimulatedClock / RealtimeClock / SimpleEventBus 属于系统级基础设施，
不受"不含方法"限制，但必须满足上述 5 条。

### 增长控制

- 不设硬性数量上限
- 每个新增类型必须在 PR 描述中包含 **2 行理由说明**：
  1. 为什么这个类型属于 kernel 而非业务包
  2. 预期被哪些业务包消费

## 模块结构

```
ditto_kernel/
├── identity.py        # 共享身份类型（NewType）
├── enums.py           # 共享枚举类型（StrEnum）
├── clock.py           # Clock Protocol + 薄实现（SimulatedClock / RealtimeClock）
├── events.py          # DomainEvent + EventBus Protocol + SimpleEventBus
├── specs.py           # 衍生规格数据类（DerivedSpec / DerivedRole / TimeSpec 等，Phase 5 从 Engine 迁入）
├── research.py        # 研究数据集记录类型（frozen dataclass × 4）
├── quality.py         # 数据质量值对象（DQLevel / DQSeverity / DQIssue / DQResult / L3CheckResult / ReconciliationResult）
├── exceptions.py      # 共享异常层级（DataError / IdentifierError / NoIdentifierProvidedError / AmbiguousTickerError）
├── types.py           # 共享工具类型（InstrumentIngestParams）
└── math.py            # 共享数学工具（pearson_correlation 等纯计算函数）
```

## 当前类型清单

| 类型 | 模块 | 格式 | 消费者 |
|------|------|------|--------|
| `InstrumentId` | identity.py | `NewType("InstrumentId", int)` | 预留（后续统一计划） |
| `AssetClass` | enums.py | `StrEnum`（6 成员） | Data, Interfaces |
| `Exchange` | enums.py | `StrEnum`（XSHE/XSHG/XBSE） | Data |
| `OrderSide` | enums.py | `StrEnum`（BUY/SELL） | Data, Engine |
| `RunStatus` | enums.py | `StrEnum`（PENDING/RUNNING/COMPLETED/FAILED） | Data |
| `RiskScope` | enums.py | `StrEnum`（INSTRUMENT/PORTFOLIO） | Engine |
| `MacroCategory` | enums.py | `StrEnum`（ECONOMIC/INTEREST_RATE/EXCHANGE_RATE/MONEY_SUPPLY/PRICES/EMPLOYMENT） | Data, App |
| `MacroFrequency` | enums.py | `StrEnum`（DAILY/MONTHLY/QUARTERLY） | Data, App |
| `DerivedRole` | specs.py | `StrEnum`（FEATURE/FACTOR/SIGNAL/LABEL） | Analytics, Engine |
| `DerivedSpec` | specs.py | frozen dataclass | Analytics, Engine |
| `MaterializationProfile` | specs.py | `StrEnum`（SERIES/STATE/DERIVE/OFFLINE） | Analytics, Engine |
| `TimeSpec` | specs.py | frozen dataclass | Analytics, Engine |
| `ExecutionPolicy` | specs.py | frozen dataclass（含默认值） | Analytics, Engine |
| `CalendarId` | specs.py | `Literal["cn_stock"]` | Analytics |
| `GrainId` | specs.py | `Literal["1d", "1m"]` | Analytics |
| `ResearchSpineSpecRecord` | research.py | frozen dataclass | Data, App |
| `ResearchDatasetSpecRecord` | research.py | frozen dataclass | Data, App |
| `ResearchSpineSnapshotRecord` | research.py | frozen dataclass | Data, App |
| `ResearchDatasetSnapshotRecord` | research.py | frozen dataclass | Data, App |
| `DQLevel` | quality.py | `Enum`（TECHNICAL/BUSINESS/STATISTICAL） | Data, App, Interfaces |
| `DQSeverity` | quality.py | `Enum`（ERROR/WARNING/ALERT） | Data, App, Interfaces |
| `DQIssue` | quality.py | frozen dataclass | Data, App, Interfaces |
| `DQResult` | quality.py | frozen dataclass（含纯计算型 `@property`） | Data, App, Interfaces |
| `L3CheckResult` | quality.py | frozen dataclass（L3 统计巡检结果） | App, Interfaces |
| `ReconciliationResult` | quality.py | frozen dataclass（数据源对账结果） | App, Interfaces |
| `DataError` | exceptions.py | `Exception`（基类） | Data, App, Interfaces |
| `IdentifierError` | exceptions.py | `DataError`（标识符异常基类） | Data, App |
| `NoIdentifierProvidedError` | exceptions.py | `IdentifierError` | App |
| `AmbiguousTickerError` | exceptions.py | `IdentifierError` | App |
| `InstrumentIngestParams` | types.py | frozen dataclass | Data, App |
| `pearson_correlation` | math.py | 纯函数 | Engine, App |

## 导入规范

```python
# ✅ 正确：从 kernel 顶层导入
from ditto_kernel import AssetClass, OrderSide, InstrumentId

# ✅ 正确：从子模块导入
from ditto_kernel.enums import AssetClass, Exchange
from ditto_kernel.identity import InstrumentId
from ditto_kernel.specs import DerivedSpec, DerivedRole, MaterializationProfile

# ❌ 禁止：kernel 导入任何其他 ditto 包
from ditto_data.models.enums import ...  # kernel 中禁止
```

## 依赖规则

```
┌─────────────────────────────────────────────┐
│  所有业务包都可以依赖 Kernel                  │
│  interfaces → kernel ✅                     │
│  app → kernel ✅                            │
│  engine → kernel ✅                         │
│  analytics → kernel ✅                      │
│  data → kernel ✅                           │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Kernel 禁止依赖其他层                       │
│  kernel → interfaces ❌                     │
│  kernel → app ❌                            │
│  kernel → engine ❌                         │
│  kernel → analytics ❌                      │
│  kernel → data ❌                           │
│  kernel → infra ❌                          │
└─────────────────────────────────────────────┘
```

## 红线

| 禁止 | 理由 |
|------|------|
| `import polars` / `import orjson` 等第三方库 | 零外部依赖 |
| pyproject.toml 声明运行时 dependencies | 零外部依赖 |
| 在枚举/值对象上添加方法 | 零业务行为 |
| 包含序列化、持久化逻辑 | 纯值语义 |
| 薄实现类超过 30 行方法体 | 控制复杂度 |
| Protocol / 薄实现包含 I/O | 零 I/O |

## 测试规范

### 测试文件位置

```
packages/kernel/
├── src/ditto_kernel/
└── tests/
    └── unit/           # 单元测试
        ├── test_clock.py
        ├── test_enums.py
        ├── test_events.py
        └── test_identity.py
```

### 运行测试

```bash
pixi run -e dev pytest packages/kernel/tests/
```

## 判断决策树

```
问题：这个类型应该放在 Kernel 吗？

1. 是纯类型（枚举/值对象/NewType）或 Protocol/薄实现？
   YES → 继续下一个问题
   NO → ❌ 不属于 Kernel

2. 至少被 2 个业务包消费（或预期被消费）？
   YES → 继续下一个问题
   NO → ❌ 放在使用最多的那个包里

3. 零业务逻辑、零 I/O？
   YES → 继续下一个问题
   NO → ❌ 放在对应的业务包里

4. 稳定性高，不会随子域迭代频繁变更？
   YES → 继续下一个问题
   NO → ❌ 放在对应的业务包里

5. 只依赖 Python 标准库？
   YES → ✅ 可以放入 Kernel
   NO → ❌ 放在对应的业务包里
```

## 相关文档

- 共享内核设计：[shared-kernel-and-model-governance-design](../../docs/plans/2026-03-24-shared-kernel-and-model-governance-design.md)
- Kernel 包创建计划：[kernel-package-creation](../../docs/plans/2026-03-24-kernel-package-creation.md)
