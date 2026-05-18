# ADR: EventName catalog vs DomainEvent.event_type 类型安全

> 日期：2026-05-18
> 状态：Accepted
> 范围：`ditto_kernel.events.DomainEvent` + `ditto_kernel.events.EventName`

## 背景

`ditto_kernel/events.py` 中定义了事件系统的核心类型：

- **`EventName`**：`StrEnum`，包含 8 个成员（`ORDER_SUBMITTED`、`ORDER_FILLED`、`ORDER_CANCELED`、`ORDER_REJECTED`、`RISK_GUARD_TRIGGERED`、`POSITION_CHANGED`、`ACCOUNT_UPDATED`、`STRATEGY_SIGNAL_GENERATED`），作为事件名称的权威目录。
- **`DomainEvent`**：`frozen=True` 的 dataclass，`event_type` 字段类型为 `str`。

当前状况：

```python
class EventName(StrEnum):
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    # ... 共 8 个成员

@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    event_type: str          # 类型为 str，非 EventName
    timestamp: datetime
    payload: dict[str, Any] = field(default_factory=dict)
```

所有内部消费者均使用 `EventName.*` 常量赋值 `event_type`，但类型标注为 `str` 而非 `EventName`。

核心问题：是否应将 `event_type` 的类型从 `str` 收窄为 `EventName`，以获得静态类型安全？

## 决策

保持 `event_type: str`，不收窄为 `EventName`。理由如下：

### 1. 传输边界兼容性

事件系统存在序列化/反序列化边界。外部存储（SQLite、Parquet）和网络传输层需要处理纯字符串格式的 `event_type`。如果类型收窄为 `EventName`，反序列化时需要额外的枚举转换逻辑，增加传输层复杂度。

### 2. 外部系统兼容

当前和未来的外部系统（券商网关、监控平台、审计系统）产生和消费的 `event_type` 均为纯字符串。`str` 类型标注保持前向兼容，无需在外部接口层做类型适配。

### 3. EventName 作为权威目录

`EventName` 的定位是**已知事件类型的权威目录**，而非 `event_type` 的类型约束。它提供：

- 事件名称的集中定义和发现入口
- 消费者引用的类型安全常量（`EventName.ORDER_FILLED`）
- IDE 自动补全和静态分析支持

### 4. 子类约定

所有 `DomainEvent` 子类**必须**在其 `event_type` 默认值中引用 `EventName` 常量，禁止硬编码字符串：

```python
# ✅ 正确：引用 EventName 常量
@dataclass(frozen=True, kw_only=True)
class OrderFilledEvent(DomainEvent):
    event_type: str = EventName.ORDER_FILLED
    order_id: str = ""

# ❌ 禁止：硬编码字符串
class OrderFilledEvent(DomainEvent):
    event_type: str = "order_filled"  # 禁止
```

### 5. Docstring 引用

`DomainEvent` 的 docstring 明确引用 `EventName` 作为事件类型的目录来源：

```python
class DomainEvent:
    """
    领域事件.

    Attributes:
        event_type: 事件类型标识（如 EventName.ORDER_FILLED）
    """
```

## 类型安全缓解措施

`str` 类型引入的静态类型安全缺口通过以下约定缓解：

| 措施 | 机制 | 检查时机 |
|------|------|----------|
| 子类默认值约定 | `event_type` 默认值必须引用 `EventName.*` | Code Review |
| Docstring 引用 | `DomainEvent` 文档指向 `EventName` 作为目录 | 持续 |
| EventName 单一来源 | 所有事件类型字符串统一定义在 `EventName` | 编译期（IDE 补全） |
| EventBus 订阅一致性 | `subscribe(event_type: str, ...)` 接受 `EventName`（`StrEnum` 是 `str` 子类） | 运行时 |

## 后果

### 正面

- 事件传输层（序列化、存储、网络）保持简单，无需枚举转换
- 外部系统兼容性不受影响
- `EventName` 仍提供集中定义、IDE 补全和代码导航能力
- 新事件类型只需在 `EventName` 中添加成员，无需修改 `DomainEvent` 类型定义

### 负面

- 静态类型检查器（basedpyright）无法捕获 `event_type` 中的非 `EventName` 字符串
- 代码中可能出现拼写错误的事件类型字符串，需通过 Code Review 和测试覆盖保证正确性
- `EventName` 的权威性依赖团队约定而非编译器强制

### 接受的权衡

传输兼容性 > 静态类型安全。事件系统的核心职责是跨边界传输，`str` 类型确保传输层零摩擦。类型安全通过约定和测试保证，而非通过类型标注强制。

## 参考

- `packages/kernel/src/ditto_kernel/events.py` — 当前实现
- `packages/kernel/CLAUDE.md` — DomainEvent 兼容策略
- `docs/architecture/adr-runtime-spine.md` — Runtime Spine ADR（事件系统设计相关讨论）
