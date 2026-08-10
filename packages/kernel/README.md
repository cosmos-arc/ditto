# ditto-kernel

> 包级约束见 [AGENTS.md](AGENTS.md)；全局边界见 [架构快速参考](../../docs/architecture/agent-context-pack.md)。

**版本**: v0.3.1 | **日期**: 2026-05-10 | **状态**: 稳定

## 概要

共享内核层（Shared Kernel）— Ditto 依赖图的最底层。提供跨层共享的领域原语：枚举、NewType、值对象、Protocol 和薄实现。零业务行为、零外部依赖、零 I/O。

## 详细规范

- 目录结构详见 [AGENTS.md](AGENTS.md)
- 依赖规则详见 [AGENTS.md](AGENTS.md)
- 类型清单详见 [AGENTS.md](AGENTS.md)
- 架构规则和依赖约束详见 [AGENTS.md](AGENTS.md)
- 导入规范详见 [AGENTS.md](AGENTS.md)

## 三原则

| 原则 | 说明 |
|------|------|
| 零业务行为 | 纯类型 / Protocol / 薄实现，不含领域逻辑 |
| 零外部依赖 | 仅依赖 Python 标准库 |
| 零 I/O | 不进行文件、网络、数据库操作 |

## 测试

```bash
pixi run -e dev pytest packages/kernel/tests/
```

## 相关文档

- [Kernel 层规范](AGENTS.md)

## 变更记录

### v0.3.1 (2026-05-10)
- 迁移 `quality.py` → `ditto_data.quality.quality_types`（DQLevel / DQSeverity / DQIssue / DQResult）
- 迁移 `research.py` → `ditto_analysis.research.domain`（4 frozen dataclass）
- 迁移 `publication_safety.py` → `ditto_features.publication_safety_records`（6 frozen dataclass）

### v0.3.0 (2026-04-27)
- Phase 1 子域重组：`enums.py` / `specs.py` 拆分为 11 个子域文件
- 新增 `quality.py`（DQLevel / DQSeverity / DQIssue / DQResult）
- 新增 `research.py`（4 frozen dataclass）
- 新增 `exceptions.py`（5 异常类）
- 新增 `math.py`（pearson_correlation）
- 新增 `DerivedSpec` / `ExecutionPolicy` / `ImpactModel` / `RiskScope`（DerivedSpec 已在 v0.3.1 迁出）
- `RunStatus` 新增 `CANCELLED` 成员
- `DerivedRole` 更新为 `FEATURE/FACTOR/SIGNAL/LABEL`（已在 v0.3.1 迁出）
- `MaterializationProfile` 更新为 `SERIES/STATE/DERIVE/OFFLINE`（已在 v0.3.1 迁出）

### v0.2.0 (2026-04-04)
- 新增 clock.py（Clock Protocol + SimulatedClock + RealtimeClock）
- 新增 events.py（DomainEvent + EventBus Protocol + SimpleEventBus）
- 新增 specs.py（DerivedSpec / DerivedRole / MaterializationProfile / TimeSpec / ExecutionPolicy / CalendarId / GrainId）

### v0.1.0 (2026-03-25)
- 创建 ditto_kernel 包
- 从 Data 迁入 AssetClass、Exchange、OrderSide、RunStatus
- 新建 InstrumentId NewType
