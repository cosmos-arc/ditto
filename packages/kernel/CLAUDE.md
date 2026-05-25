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
| 5 | 纯值语义 | 不含 I/O、持久化关注点。允许结构转换方法（`to_json_dict`/`from_json_dict`）：仅做 dict ↔ dataclass 内存转换，不涉及文件/网络/数据库 |

### 允许的结构转换方法

frozen dataclass 可包含 `to_json_dict()` / `from_json_dict()` 类方法，前提：
- 仅做 dict ↔ dataclass 的内存结构转换
- 不涉及文件 I/O、网络请求、数据库操作

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

按业务子域组织（2026-04-18 Phase 1 重组），每个子域文件包含相关枚举、值对象、Protocol。

```
ditto_kernel/
├── instrument.py          # Instrument 子域 — AssetClass / Exchange / InstrumentIngestParams
├── order.py               # Order 子域 — OrderSide / OrderType
├── market.py              # Market 子域 — CalendarId / GrainId / TimeSpec / MacroCategory / MacroFrequency / GRAIN_TO_TIME_KEYS / CALENDAR_TO_TIMEZONE
├── strategy.py            # Strategy 子域 — ExecutionPolicy / ImpactModel / RiskScope / RunStatus
├── identity.py            # 共享身份类型（NewType）
├── clock.py               # Clock Protocol + 薄实现（SimulatedClock / RealtimeClock）
├── time_context.py        # TimeContext 值对象 — PIT 语义统一入口（decision_time / knowledge_date / trade_date）
├── synchronizer.py        # Synchronizer Protocol + TimeSlice 值对象 — 回测/实盘切换 seam
├── events.py              # DomainEvent + EventBus Protocol + SimpleEventBus + EventName catalog
├── tracing.py             # 可插拔追踪装饰器（traced / install_trace_handler / reset_trace_handler）
├── trading.py             # A 股交易领域常量、值对象与规则 Protocol（FeeModel / InstrumentRuleProvider / InstrumentRules / RulesGetter 等）
├── exceptions.py          # 共享异常层级（DittoError / DataError / IdentifierError / NoIdentifierProvidedError / AmbiguousTickerError）
└── math.py                # 共享数学工具（pearson_correlation 等纯计算函数）
```

### 子域间依赖

```
strategy → market（单向依赖，策略规格引用市场时间语义）
instrument / order / market / identity: 无子域间依赖
```

## 当前类型清单

| 类型 | 模块 | 格式 | 消费者 |
|------|------|------|--------|
| `AssetClass` | instrument.py | `StrEnum`（6 成员） | Data, Apps |
| `Exchange` | instrument.py | `StrEnum`（XSHE/XSHG/XBSE） | Data |
| `InstrumentIngestParams` | instrument.py | frozen dataclass（含纯计算型 `@property`） | Data, App |
| `OrderSide` | order.py | `StrEnum`（BUY/SELL） | Data, Execution |
| `OrderType` | order.py | `StrEnum`（MARKET/LIMIT/STOP_MARKET/MARKET_ON_CLOSE） | Execution, Risk, Portfolio, Backtest |
| `CalendarId` | market.py | `Literal["cn_stock"]` | Analysis |
| `GrainId` | market.py | `Literal["1d", "1m"]` | Analysis |
| `GRAIN_TO_TIME_KEYS` | market.py | `dict[GrainId, tuple[str, ...]]` 常量 | Data, Analysis |
| `CALENDAR_TO_TIMEZONE` | market.py | `dict[CalendarId, str]` 常量 | Data |
| `TimeSpec` | market.py | frozen dataclass（含纯计算型 `@property`） | Analysis, Strategy |
| `MacroCategory` | market.py | `StrEnum`（6 成员） | Data, Apps |
| `MacroFrequency` | market.py | `StrEnum`（DAILY/MONTHLY/QUARTERLY） | Data, Apps |
| `ExecutionPolicy` | strategy.py | frozen dataclass（含纯计算型 `@property`） | Analysis, Strategy |
| `ImpactModel` | strategy.py | `StrEnum`（NONE/VOLUME_SHARE） | Execution, App |
| `RiskScope` | strategy.py | `StrEnum`（INSTRUMENT/PORTFOLIO） | Risk, Data, Apps, Application |
| `RunStatus` | strategy.py | `StrEnum`（PENDING/RUNNING/COMPLETED/FAILED/CANCELLED） | Data |
| `traced` / `install_trace_handler` / `reset_trace_handler` | tracing.py | 可插拔追踪装饰器 | Strategy, Execution, Backtest |
| `TimeContext` | time_context.py | frozen dataclass（含 `pit_cutoff` property） | Backtest, Application |
| `TimeSlice` | synchronizer.py | frozen dataclass | Backtest, Application |
| `Synchronizer` | synchronizer.py | `Protocol`（回测/实盘切换 seam） | Backtest, Application |
| `MarketSnapshot` | trading.py | frozen dataclass | Execution, Backtest |
| `InstrumentDefinition` | trading.py | frozen dataclass | Execution, Backtest |
| `TradingRuleSet` | trading.py | frozen dataclass | Execution, Backtest |
| `FeeSchedule` | trading.py | frozen dataclass | Execution, Backtest |
| `FeeModel` | trading.py | `Protocol`（费用计算契约） | Execution, Backtest |
| `InstrumentRuleProvider` | trading.py | `Protocol`（三层规则查询） | Execution, Backtest |
| `InstrumentRules` | trading.py | `type` 别名（`tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]`） | Execution, Backtest |
| `RulesGetter` | trading.py | `type` 别名（`Callable[[InstrumentId, str], InstrumentRules]`） | Execution, Backtest |
| `DEFAULT_SLIPPAGE_BPS` | trading.py | `float` 常量（1.0） | Execution, Backtest |
| `InstrumentId` | identity.py | `NewType("InstrumentId", int)` | 预留（后续统一计划） |
| `DittoError` | exceptions.py | `Exception`（全局根） | 所有包 |
| `DataError` | exceptions.py | `DittoError`（数据域根） | Data, Apps, Application |
| `IdentifierError` | exceptions.py | `DataError`（标识符异常基类） | Data, Apps |
| `NoIdentifierProvidedError` | exceptions.py | `IdentifierError` | Apps |
| `AmbiguousTickerError` | exceptions.py | `IdentifierError` | Apps |
| `pearson_correlation` | math.py | 纯函数 | Backtest, App |

## 导入规范

Barrel（`__init__.py`）仅保留高频跨层符号（≤30 个）。低频符号需从叶模块直接导入。

```python
# ✅ 正确：从 kernel 顶层导入（仅高频符号）
from ditto_kernel import AssetClass, OrderSide, InstrumentId, DittoError

# ✅ 正确：从子域模块导入（低频或子域内聚符号）
from ditto_kernel.instrument import AssetClass, Exchange, InstrumentIngestParams
from ditto_kernel.order import OrderSide
from ditto_kernel.market import CalendarId, GrainId, TimeSpec, MacroCategory, MacroFrequency
from ditto_kernel.strategy import ExecutionPolicy, ImpactModel, RiskScope, RunStatus
from ditto_kernel.identity import InstrumentId

# ❌ 禁止：kernel 导入任何其他 ditto 包
from ditto_data.models.enums import ...  # kernel 中禁止
```

### Barrel vs 叶模块导入（30 限制）

以下符号**不在** barrel `__all__` 中，必须从叶模块导入：

| 子域 | 需叶模块导入的符号 |
|------|-------------------|
| `market` | `CalendarId`, `GrainId` |

> `trading.py` 的领域特定 Protocol（FeeModel/FeeSchedule/InstrumentDefinition 等）因使用范围窄（仅 Execution/Backtest）不列入此表，直接从叶模块导入。`strategy.py` 的 `RunStatus` 同理。

## Barrel 公共 API 分级

Barrel `__all__` 包含 30 个符号，按稳定性分为两层：

### Stable — 核心类型（2+ 跨包消费者，接口稳定）

| 来源模块 | 符号 |
|----------|------|
| `trading.py` | `DEFAULT_COMMISSION_RATE`, `DEFAULT_LOT_SIZE`, `DEFAULT_MIN_COMMISSION` |
| `exceptions.py` | `AmbiguousTickerError`, `DittoError`, `IdentifierError`, `NoIdentifierProvidedError` |
| `instrument.py` | `AssetClass`, `Exchange`, `InstrumentIngestParams` |
| `market.py` | `MacroCategory`, `MacroFrequency`, `TimeSpec` |
| `order.py` | `OrderSide`, `OrderType` |
| `identity.py` | `InstrumentId` |
| `clock.py` | `Clock`, `RealtimeClock`, `SimulatedClock` |
| `synchronizer.py` | `Synchronizer`, `TimeSlice` |
| `time_context.py` | `TimeContext` |

### Candidate — 候选类型（1-2 包消费，接口可能演进）

| 来源模块 | 符号 | 备注 |
|----------|------|------|
| `strategy.py` | `ExecutionPolicy`, `ImpactModel`, `RiskScope` | |
| `events.py` | `DomainEvent`, `EventBus`, `EventName`, `SimpleEventBus` | |
| `tracing.py` | `traced` | |

> **注意**：`DittoError` 作为跨包异常基类放在 kernel 是合理的——它是异常层级的根。
> 但 `strategy.py` 中的部分类型具有策略领域特有语义，虽然当前通过 barrel 共享以方便消费者，
> 随着策略领域的演进，这些类型可能需要重新评估是否应转为叶模块直导。

## DomainEvent 兼容策略

`DomainEvent.payload: dict[str, Any]` 保留用于 transport 兼容（序列化/反序列化边界）。

**新事件子类的规则**：
1. 通过专属 typed 字段承载业务数据，不依赖 `payload` 字段
2. `event_type` 必须引用 `EventName` 常量，禁止硬编码字符串
3. `payload` 保持默认空字典（继承自基类）

**EventName catalog 规则**：
- 所有领域事件的 `event_type` 值统一定义在 `EventName` 类中
- 消费者通过 `from ditto_kernel.events import EventName` 引用常量
- 新增事件必须同步更新 `EventName`

## 依赖规则

```
┌─────────────────────────────────────────────┐
│  所有业务包都可以依赖 Kernel                  │
│  apps → kernel ✅                           │
│  application → kernel ✅                    │
│  strategy/portfolio/risk/execution/backtest → kernel ✅ │
│  analysis → kernel ✅                       │
│  data → kernel ✅                           │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Kernel 禁止依赖其他层                       │
│  kernel → apps ❌                           │
│  kernel → application ❌                    │
│  kernel → strategy ❌                       │
│  kernel → portfolio ❌                      │
│  kernel → risk ❌                           │
│  kernel → execution ❌                      │
│  kernel → backtest ❌                       │
│  kernel → analysis ❌                       │
│  kernel → data ❌                           │
│  kernel → platform ❌                        │
└─────────────────────────────────────────────┘
```

## 红线

| 禁止 | 理由 |
|------|------|
| `import polars` / `import orjson` 等第三方库 | 零外部依赖 |
| pyproject.toml 声明运行时 dependencies | 零外部依赖 |
| 在枚举上添加方法 | 零业务行为 |
| frozen dataclass 上添加有副作用/有 I/O 的方法 | 零业务行为 |
| 包含序列化、持久化逻辑 | 纯值语义 |
| 薄实现类超过 30 行方法体 | 控制复杂度 |
| Protocol / 薄实现包含 I/O | 零 I/O |

### 允许的例外

| 允许 | 条件 | 示例 |
|------|------|------|
| frozen dataclass `@property` | 纯计算：无副作用、无 I/O、仅基于自身字段 | `InstrumentIngestParams.has_identifier` |
| Protocol 定义 | 零依赖签名，使用 `Sequence` 等标准库类型 | `MacroDataProvider` |

## 测试规范

### 测试文件位置

```
packages/kernel/
├── src/ditto_kernel/
└── tests/
    └── unit/           # 单元测试
        ├── test_clock.py
        ├── test_events.py
        ├── test_identity.py
        ├── test_subdomain_properties.py  # 子域 @property 纯计算测试
        └── test_*.py                     # 其他单元测试
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
