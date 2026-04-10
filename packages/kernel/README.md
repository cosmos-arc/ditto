# ditto-kernel

**版本**: v0.2.0 | **日期**: 2026-04-04 | **状态**: 稳定

## 概要

共享内核层（Shared Kernel）— Ditto 依赖图的最底层。提供跨层共享的领域原语：枚举、NewType、值对象、Protocol 和薄实现。零业务行为、零外部依赖、零 I/O。

## 模块结构

```
ditto_kernel/
├── __init__.py     # 统一导出 5 个公共符号
├── identity.py     # InstrumentId (NewType)
├── enums.py        # AssetClass, Exchange, OrderSide, RunStatus (StrEnum)
├── clock.py        # Clock Protocol + SimulatedClock + RealtimeClock
├── events.py       # DomainEvent + EventBus Protocol + SimpleEventBus
└── specs.py        # DerivedSpec, DerivedRole, MaterializationProfile, TimeSpec 等
```

## 类型清单

| 类型 | 模块 | 格式 |
|------|------|------|
| InstrumentId | identity.py | `NewType("InstrumentId", int)` |
| AssetClass | enums.py | StrEnum（6 成员） |
| Exchange | enums.py | StrEnum（XSHE / XSHG / XBSE） |
| OrderSide | enums.py | StrEnum（BUY / SELL） |
| RunStatus | enums.py | StrEnum（PENDING / RUNNING / COMPLETED / FAILED） |
| Clock | clock.py | Protocol |
| SimulatedClock | clock.py | 薄实现 |
| RealtimeClock | clock.py | 薄实现 |
| DomainEvent | events.py | Protocol |
| EventBus | events.py | Protocol |
| SimpleEventBus | events.py | 薄实现 |
| DerivedRole | specs.py | StrEnum（FACTOR / FEATURE / COMPOSITE） |
| DerivedSpec | specs.py | frozen dataclass |
| MaterializationProfile | specs.py | StrEnum（SERIES / STATE） |
| TimeSpec | specs.py | frozen dataclass |
| ExecutionPolicy | specs.py | frozen dataclass |
| CalendarId | specs.py | `Literal["cn_stock"]` |
| GrainId | specs.py | `Literal["1d", "1m"]` |

## 架构定位

```
interfaces → kernel ✅     app → kernel ✅
engine → kernel ✅         analytics → kernel ✅
data → kernel ✅           infra → kernel ✅（允许但当前未使用）

kernel → any_other_ditto_package ❌
```

Kernel 零依赖其他 ditto 包，被所有业务包依赖。

## 三原则

| 原则 | 说明 |
|------|------|
| 零业务行为 | 纯类型 / Protocol，不含领域逻辑 |
| 零外部依赖 | 仅依赖 Python 标准库 |
| 零 I/O | 不进行文件、网络、数据库操作 |

## 使用方式

```python
from ditto_kernel import AssetClass, InstrumentId
from ditto_kernel.specs import DerivedSpec, DerivedRole
from ditto_kernel.clock import Clock, SimulatedClock

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
- [共享内核设计](../../docs/plans/2026-03-24-shared-kernel-and-model-governance-design.md)

## 变更记录

### v0.2.0 (2026-04-04)
- 新增 clock.py（Clock Protocol + SimulatedClock + RealtimeClock）
- 新增 events.py（DomainEvent + EventBus Protocol + SimpleEventBus）
- 新增 specs.py（DerivedSpec / DerivedRole / MaterializationProfile / TimeSpec / ExecutionPolicy / CalendarId / GrainId）

### v0.1.0 (2026-03-25)
- 创建 ditto_kernel 包
- 从 Data 迁入 AssetClass、Exchange、OrderSide、RunStatus
- 新建 InstrumentId NewType
