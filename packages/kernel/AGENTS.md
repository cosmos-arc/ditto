# Kernel Agent 指南

## 定位

共享内核 — 跨层共享的领域原语（类型 + Protocol + 薄实现）。零业务行为、零外部依赖、零 I/O。

## 核心模块

| 模块 | 职责 |
|------|------|
| instrument.py | AssetClass / Exchange / InstrumentIngestParams |
| order.py | OrderSide |
| market.py | CalendarId / GrainId / TimeSpec / MacroCategory |
| strategy.py | DerivedRole / DerivedSpec / RunStatus / DecisionFrame Protocol |
| identity.py | InstrumentId (NewType) |
| clock.py | Clock Protocol + SimulatedClock/RealtimeClock |
| events.py | DomainEvent + EventBus Protocol + SimpleEventBus |
| trading.py | A 股交易常量、FeeModel/InstrumentRuleProvider Protocol |
| quality.py | DQLevel / DQSeverity / DQIssue / DQResult |
| exceptions.py | DittoError 全局异常根 |

## 依赖规则

### 允许

- 所有包 → kernel ✅

### 禁止

- kernel → 任何其他 ditto 包 ❌
- kernel → 第三方库 ❌（仅标准库）

## 关键约束

- 值对象准入：跨 2+ 包使用 + 零业务行为 + 稳定性高 + 无外部依赖 + 纯值语义
- frozen dataclass 允许纯计算型 @property（无副作用、无 I/O）
- Barrel `__init__.py` ≤ 30 个符号，低频符号从叶模块导入
- 新增类型必须在 PR 描述中包含 2 行理由说明

## 详细规范

参见 [CLAUDE.md](CLAUDE.md)。
