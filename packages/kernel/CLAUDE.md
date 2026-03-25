# Kernel 层架构规范

## 定位

Kernel 层是 **Shared Kernel（共享内核）**，提供跨层共享的领域原语。

**核心原则**：
- 零业务行为、零外部依赖、零 I/O
- 纯值语义：枚举、NewType、值对象
- 位于依赖图最底层，被所有业务包依赖

## 准入标准（5 条，全部满足才可进入）

| # | 标准 | 说明 |
|---|------|------|
| 1 | 跨层使用 | 至少被 2 个业务包直接导入 |
| 2 | 零业务行为 | 纯值对象 / 枚举 / NewType，不含方法 |
| 3 | 稳定性高 | 不会随某个子域的迭代频繁变更 |
| 4 | 无外部依赖 | 只依赖 Python 标准库 |
| 5 | 纯值语义 | 不含序列化、持久化关注点 |

## 模块结构

```
ditto_kernel/
├── identity.py        # 共享身份类型（NewType）
└── enums.py           # 共享枚举类型（StrEnum）
```

## 当前类型清单

| 类型 | 模块 | 格式 | 消费者 |
|------|------|------|--------|
| `InstrumentId` | identity.py | `NewType("InstrumentId", int)` | 预留（后续统一计划） |
| `AssetClass` | enums.py | `StrEnum`（6 成员） | DataHub, Port |
| `Exchange` | enums.py | `StrEnum`（XSHE/XSHG/XBSE） | DataHub |
| `OrderSide` | enums.py | `StrEnum`（BUY/SELL） | DataHub, Core |
| `RunStatus` | enums.py | `StrEnum`（PENDING/RUNNING/COMPLETED/FAILED） | DataHub |

## 导入规范

```python
# ✅ 正确：从 kernel 顶层导入
from ditto_kernel import AssetClass, OrderSide, InstrumentId

# ✅ 正确：从子模块导入
from ditto_kernel.enums import AssetClass, Exchange
from ditto_kernel.identity import InstrumentId

# ❌ 禁止：kernel 导入任何其他 ditto 包
from ditto_datahub.models.enums import ...  # kernel 中禁止
```

## 依赖规则

```
┌─────────────────────────────────────────────┐
│  所有业务包都可以依赖 Kernel                  │
│  port → kernel ✅                            │
│  core → kernel ✅                            │
│  datahub → kernel ✅                         │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Kernel 禁止依赖其他层                       │
│  kernel → port ❌                           │
│  kernel → datahub ❌                        │
│  kernel → core ❌                           │
│  kernel → infra ❌                          │
└─────────────────────────────────────────────┘
```

## 红线

| 禁止 | 理由 |
|------|------|
| `import polars` / `import orjson` 等第三方库 | 零外部依赖 |
| pyproject.toml 声明运行时 dependencies | 零外部依赖 |
| kernel 类型数量超过 20 个 | 控制范围，避免变成万能包 |
| 在枚举/值对象上添加方法 | 零业务行为 |
| 包含序列化、持久化逻辑 | 纯值语义 |

## 测试规范

### 测试文件位置

```
packages/kernel/
├── src/ditto_kernel/
└── tests/
    └── unit/           # 单元测试
        ├── test_identity.py
        └── test_enums.py
```

### 运行测试

```bash
pixi run -e dev pytest packages/kernel/tests/
```

## 判断决策树

```
问题：这个类型应该放在 Kernel 吗？

1. 是纯类型（枚举/值对象/NewType）？
   YES → 继续下一个问题
   NO → ❌ 不属于 Kernel

2. 至少被 2 个业务包直接导入？
   YES → 继续下一个问题
   NO → ❌ 放在使用最多的那个包里

3. 不含方法或 I/O？
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
