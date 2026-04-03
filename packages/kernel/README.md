# ditto-kernel

**版本**: v0.1.0
**最后更新**: 2026-03-25
**状态**: ✅ 稳定

## 概要

共享内核层（Kernel Layer）是 Ditto 量化系统的最底层包，提供跨层共享的领域原语 — 枚举、NewType、值对象。零业务行为、零外部依赖、零 I/O。

## 架构定位

```
┌─────────────────────────────────────┐
│         apps/port                  │
│     (Application Layer)             │
├─────────────────────────────────────┤
│      packages/engine               │
│     (Domain Layer)                  │
├─────────────────────────────────────┤
│      packages/data                   │
│     (Data Service Layer)            │
├─────────────────────────────────────┤
│      packages/infra                │
│     (Infrastructure Layer)          │
├─────────────────────────────────────┤
│      packages/kernel (当前层)       │
│     (Shared Kernel)                 │
└─────────────────────────────────────┘
```

**依赖规则**: Kernel 零依赖其他 ditto 包，被所有业务包依赖。

## 模块结构

```
ditto_kernel/
├── __init__.py         # 统一导出（5 个公共符号）
├── identity.py         # 共享身份类型
└── enums.py            # 共享枚举类型
```

## 类型清单

| 类型 | 模块 | 说明 |
|------|------|------|
| `InstrumentId` | identity.py | 主键类型安全包装 `NewType("InstrumentId", int)` |
| `AssetClass` | enums.py | 资产类型：STOCK / ETF / INDEX / FUTURE / BOND / FUND |
| `Exchange` | enums.py | A 股交易所（MIC 简化版）：XSHE / XSHG / XBSE |
| `OrderSide` | enums.py | 订单方向：BUY / SELL |
| `RunStatus` | enums.py | 策略运行状态：PENDING / RUNNING / COMPLETED / FAILED |

## 准入标准

类型进入 Kernel 必须同时满足以下 5 条：

1. **跨层使用** — 至少被 2 个业务包直接导入
2. **零业务行为** — 纯值对象 / 枚举 / NewType，不含方法
3. **稳定性高** — 不会随某个子域的迭代频繁变更
4. **无外部依赖** — 只依赖 Python 标准库
5. **纯值语义** — 不含序列化、持久化关注点

## 使用方式

```python
# 从 kernel 顶层导入
from ditto_kernel import AssetClass, OrderSide, InstrumentId, Exchange, RunStatus

# 或从子模块导入
from ditto_kernel.enums import AssetClass, Exchange
from ditto_kernel.identity import InstrumentId

# StrEnum 直接支持字符串比较
assert AssetClass.STOCK == "stock"
assert OrderSide.BUY == "buy"

# NewType 提供编译期类型安全，运行时零开销
instrument_id: InstrumentId = InstrumentId(1_000_001)
```

## 测试

```bash
pixi run -e dev pytest packages/kernel/tests/
```

## 相关文档

- [共享内核设计文档](../../docs/plans/2026-03-24-shared-kernel-and-model-governance-design.md)
- [Kernel 包创建实施计划](../../docs/plans/2026-03-24-kernel-package-creation.md)
- [架构规范](../../.claude/rules/architecture.md)

## 变更记录

### v0.1.0 (2026-03-25)

- 创建 `ditto_kernel` 共享内核包
- 从 Data 迁入 `AssetClass`、`Exchange`、`OrderSide`、`RunStatus`
- 新建 `InstrumentId` NewType（预留）
- Core `OrderDirection` 统一为 kernel `OrderSide`
- Port `AssetClass` 删除重复定义，改为从 kernel 导入
- Import Linter 添加 `kernel-isolation` 合约
