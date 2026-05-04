# ditto-kernel

**版本**: v0.3.0 | **日期**: 2026-04-27 | **状态**: 稳定

## 概要

共享内核层（Shared Kernel）— Ditto 依赖图的最底层。提供跨层共享的领域原语：枚举、NewType、值对象、Protocol 和薄实现。零业务行为、零外部依赖、零 I/O。

## 模块结构

按业务子域组织（2026-04-18 Phase 1 重组），每个子域文件包含相关枚举、值对象、Protocol。

```
ditto_kernel/
├── instrument.py      # Instrument 子域 — AssetClass / Exchange / InstrumentIngestParams
├── order.py           # Order 子域 — OrderSide
├── market.py          # Market 子域 — CalendarId / GrainId / TimeSpec / MacroCategory / MacroFrequency / MacroDataProvider Protocol
├── strategy.py        # Strategy 子域 — DerivedRole / DerivedSpec / MaterializationProfile / ExecutionPolicy / ImpactModel / RiskScope / RunStatus / DecisionFrame Protocol
├── identity.py        # 共享身份类型（NewType）
├── clock.py           # Clock Protocol + 薄实现（SimulatedClock / RealtimeClock）
├── events.py          # DomainEvent + EventBus Protocol + SimpleEventBus
├── research.py        # 研究数据集记录类型（frozen dataclass x 4）
├── quality.py         # 数据质量值对象（DQLevel / DQSeverity / DQIssue / DQResult）
├── exceptions.py      # 共享异常层级（DittoError / DataError / IdentifierError / NoIdentifierProvidedError / AmbiguousTickerError）
└── math.py            # 共享数学工具（pearson_correlation 等纯计算函数）
```

### 子域间依赖

```
strategy → market（单向依赖，策略规格引用市场时间语义）
instrument / order / market / identity: 无子域间依赖
```

## 类型清单

| 类型 | 模块 | 格式 | 消费者 |
|------|------|------|--------|
| `AssetClass` | instrument.py | `StrEnum`（6 成员） | Data, Apps |
| `Exchange` | instrument.py | `StrEnum`（XSHE/XSHG/XBSE） | Data |
| `InstrumentIngestParams` | instrument.py | frozen dataclass（含纯计算型 `@property`） | Data, App |
| `OrderSide` | order.py | `StrEnum`（BUY/SELL） | Data, Execution |
| `CalendarId` | market.py | `Literal["cn_stock"]` | Analysis |
| `GrainId` | market.py | `Literal["1d", "1m"]` | Analysis |
| `TimeSpec` | market.py | frozen dataclass（含纯计算型 `@property`） | Analysis, Strategy |
| `MacroCategory` | market.py | `StrEnum`（6 成员） | Data, Apps |
| `MacroFrequency` | market.py | `StrEnum`（DAILY/MONTHLY/QUARTERLY） | Data, Apps |
| `MacroDataProvider` | market.py | `Protocol`（零依赖签名） | Data |
| `DerivedRole` | strategy.py | `StrEnum`（FEATURE/FACTOR/SIGNAL/LABEL） | Analysis, Strategy |
| `DerivedSpec` | strategy.py | frozen dataclass | Analysis, Strategy |
| `MaterializationProfile` | strategy.py | `StrEnum`（SERIES/STATE/DERIVE/OFFLINE） | Analysis, Strategy |
| `ExecutionPolicy` | strategy.py | frozen dataclass（含纯计算型 `@property`） | Analysis, Strategy |
| `ImpactModel` | strategy.py | `StrEnum`（NONE/VOLUME_SHARE） | Execution |
| `RiskScope` | strategy.py | `StrEnum`（INSTRUMENT/PORTFOLIO） | Risk, Data, Apps, Application |
| `RunStatus` | strategy.py | `StrEnum`（PENDING/RUNNING/COMPLETED/FAILED/CANCELLED） | Data |
| `DecisionFrame` | strategy.py | `Protocol`（零依赖签名，Sequence-based） | Strategy, Application |
| `InstrumentId` | identity.py | `NewType("InstrumentId", int)` | 预留（后续统一计划） |
| `ResearchSpineSpecRecord` | research.py | frozen dataclass | Data, App |
| `ResearchDatasetSpecRecord` | research.py | frozen dataclass | Data, App |
| `ResearchSpineSnapshotRecord` | research.py | frozen dataclass | Data, App |
| `ResearchDatasetSnapshotRecord` | research.py | frozen dataclass | Data, App |
| `DQLevel` | quality.py | `Enum`（TECHNICAL/BUSINESS/STATISTICAL） | Data, Apps, Application |
| `DQSeverity` | quality.py | `Enum`（ERROR/WARNING/ALERT） | Data, Apps, Application |
| `DQIssue` | quality.py | frozen dataclass（含纯计算型 `@property`） | Data, Apps, Application |
| `DQResult` | quality.py | frozen dataclass（含纯计算型 `@property`） | Data, Apps, Application |
| `DittoError` | exceptions.py | `Exception`（全局根） | 所有包 |
| `DataError` | exceptions.py | `DittoError`（数据域根） | Data, Apps, Application |
| `IdentifierError` | exceptions.py | `DataError`（标识符异常基类） | Data, App |
| `NoIdentifierProvidedError` | exceptions.py | `IdentifierError` | App |
| `AmbiguousTickerError` | exceptions.py | `IdentifierError` | App |
| `pearson_correlation` | math.py | 纯函数 | Engine, App |

## 架构定位

```
apps → kernel ✅           application → kernel ✅
strategy/backtest → kernel ✅  analysis → kernel ✅
data → kernel ✅           platform → kernel ❌（importlinter 禁止）

kernel → any_other_ditto_package ❌
```

Kernel 零依赖其他 ditto 包，被所有业务包依赖。

## 三原则

| 原则 | 说明 |
|------|------|
| 零业务行为 | 纯类型 / Protocol / 薄实现，不含领域逻辑 |
| 零外部依赖 | 仅依赖 Python 标准库 |
| 零 I/O | 不进行文件、网络、数据库操作 |

## 使用方式

```python
# 从 barrel 导入（仅高频符号）
from ditto_kernel import AssetClass, OrderSide, InstrumentId, DittoError

# 从叶模块导入（低频或子域内聚符号）
from ditto_kernel.instrument import AssetClass, Exchange, InstrumentIngestParams
from ditto_kernel.strategy import DerivedSpec, DerivedRole, ExecutionPolicy, DecisionFrame
from ditto_kernel.identity import InstrumentId
from ditto_kernel.quality import DQIssue, DQLevel, DQResult, DQSeverity

# StrEnum 直接支持字符串比较
assert AssetClass.STOCK == "stock"

# NewType 编译期类型安全，运行时零开销
instrument_id: InstrumentId = InstrumentId(1_000_001)
```

## 测试

```bash
pixi run -e dev pytest packages/kernel/tests/
```

## 相关文档

- [Kernel 层规范](CLAUDE.md)

## 变更记录

### v0.3.0 (2026-04-27)
- Phase 1 子域重组：`enums.py` / `specs.py` 拆分为 11 个子域文件
- 新增 `quality.py`（DQLevel / DQSeverity / DQIssue / DQResult）
- 新增 `research.py`（4 frozen dataclass）
- 新增 `exceptions.py`（5 异常类）
- 新增 `math.py`（pearson_correlation）
- 新增 `DerivedSpec` / `ExecutionPolicy` / `ImpactModel` / `RiskScope` / `DecisionFrame` Protocol
- `RunStatus` 新增 `CANCELLED` 成员
- `DerivedRole` 更新为 `FEATURE/FACTOR/SIGNAL/LABEL`
- `MaterializationProfile` 更新为 `SERIES/STATE/DERIVE/OFFLINE`

### v0.2.0 (2026-04-04)
- 新增 clock.py（Clock Protocol + SimulatedClock + RealtimeClock）
- 新增 events.py（DomainEvent + EventBus Protocol + SimpleEventBus）
- 新增 specs.py（DerivedSpec / DerivedRole / MaterializationProfile / TimeSpec / ExecutionPolicy / CalendarId / GrainId）

### v0.1.0 (2026-03-25)
- 创建 ditto_kernel 包
- 从 Data 迁入 AssetClass、Exchange、OrderSide、RunStatus
- 新建 InstrumentId NewType
