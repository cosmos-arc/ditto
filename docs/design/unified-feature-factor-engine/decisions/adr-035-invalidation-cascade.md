# ADR-035: 失效传播级联协议

**状态**: 已决策（2026-03-12）

---

## 背景

当因子 A 依赖因子 B，而因子 B 的数据失效（如上游修正、迟到数据）时，需要级联传播到因子 A，确保整个依赖链的数据一致性。

---

## 级联深度限制

### 决策

**D-1**: 实时失效级联采用固定最大深度 5 的 BFS 传播；批处理路径不受该限制，仍按完整 DAG 调度。

```python
REALTIME_CASCADE_MAX_DEPTH = 5
```

### 理由

- 现有因子体系的典型链路 2-3 跳，5 层足够宽松
- 深度限制保护实时传播引擎，不影响离线正确性
- 批处理路径靠 DAG 自然更新，不受深度限制

### 配套约束

| 约束 | 说明 |
|------|------|
| **循环依赖检测** | 在 register/publish 时基于 lineage 做 DAG 校验，发现环直接拒绝 |
| **超深链路告警** | 触发 `cascade_depth_exceeded` 告警，要求压平依赖或拆成中间物化层 |

---

## 级联传播模式

### 决策

**D-2**: 级联传播采用异步队列模式；失效事件 durable 入队后上游即可确认；下游按依赖深度分层消费，并在微批窗口内合并同目标事件；查询路径通过 stale 标记保证最终一致期间不误报 fresh。

### 协议约束

| 约束 | 说明 |
|------|------|
| **上游确认语义** | `ack` = 失效事件已持久化入队，不是"所有下游都已重算完成" |
| **传播顺序** | 按依赖深度 0→1→2... 分层处理，同层可并行 |
| **查询一致性** | 下游被判定受影响后进入 `stale` 状态，不能继续被当成 `fresh` 结果对外提供 |

### 查询可用性状态

```python
QUERY_STATUS = Literal["fresh", "stale", "pending_recompute", "recomputing"]

# 级联传播时的状态转换
fresh ──receive_invalidation──> stale ──start_recompute──> recomputing ──success──> fresh
                                                            │
                                                            └──failure──> stale
```

### 异步队列架构

```
                    ┌─────────────────────────┐
                    │  derived_invalidation   │
                    │  queue (durable)        │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Consumer (分层处理)   │
                    │  depth=0 → depth=1 →  │
                    │  depth=2 → ...        │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Micro-batch 合并      │
                    │  (同目标事件合并)      │
                    └───────────────────────┘
```

---

## 循环依赖检测

### 决策

**D-3**: 循环依赖检测采用两阶段策略——注册时静态 DAG 校验硬阻断，运行时轻量兜底。

### 检测策略

| 阶段 | 检测方式 | 行为 | 职责 |
|------|---------|------|------|
| **REGISTER** | 静态 DAG 校验（基于 lineage） | 发现环直接拒绝注册 | 主防线 |
| **运行时** | visited 去重 + max_depth 保护 | 命中后 fail 当前批次并告警 | 防御性兜底 |

### 注册时检测

```python
def validate(spec) -> ValidationResult:
    """DRAFT → REGISTERED 的静态检查"""
    # 1. 解析依赖
    dependencies = parse_dependencies(spec.expression)

    # 2. 构建临时 DAG 并检测环
    temp_dag = build_dag_with_new_node(spec.id, dependencies)
    if has_cycle(temp_dag):
        raise CycleDetectedError(f"Circular dependency detected: {spec.id}")

    return ValidationResult(success=True)
```

### 运行时兜底

```python
def propagate_invalidation(event, visited: set, depth: int) -> None:
    """级联传播时的防御性检查"""

    # 防御性检查 1: visited 去重（回边检测）
    if event.target_id in visited:
        log.warning(f"Cycle detected at runtime: {event.target_id}")
        emit_alert("runtime_cycle_detected", target=event.target_id)
        return

    # 防御性检查 2: max_depth 保护
    if depth > REALTIME_CASCADE_MAX_DEPTH:
        emit_alert("cascade_depth_exceeded", target=event.target_id)
        return

    visited.add(event.target_id)
    # 继续传播...
```

---

## 失效事件结构

> **代码变更记录（2026-03-20）**：Phase 1 实现中，失效事件结构经过重新设计，聚焦于数据源变更描述（source domain/dataset/date），而非 ADR 原始设计的因子级追踪（event_id/source_version/priority/depth）。实际代码见 `DerivedInvalidationEvent`（`packages/core/src/ditto_kernel/engine/materialization/contracts.py`）。

### 原始设计（概念层）

```python
@dataclass
class InvalidationEvent:
    """失效事件 — 原始 ADR 概念设计"""
    event_id: str              # 唯一标识
    source_id: str             # 失效源头（因子 ID）
    source_version: int        # 源头版本
    affected_partitions: list[str]  # 受影响的分区
    reason: str                # 失效原因（correction / late_arrival / ...）
    priority: int              # 优先级（0=最高）
    created_at: datetime       # 创建时间
    depth: int                 # 传播深度
```

### 实际实现（Phase 1）

```python
@dataclass(frozen=True)
class DerivedInvalidationEvent:
    """Source change event that fans out into downstream repair work."""
    source_domain: str              # 变更来源领域（如 market、fundamental）
    source_dataset: str             # 变更来源数据集（如 daily_bar）
    change_date: str                # 变更日期
    affected_start: str             # 受影响范围起始
    affected_end: str               # 受影响范围结束
    source_snapshot_id: str | None  # 来源快照 ID
    root_dependency_ref: str        # 根依赖引用（用于依赖链解析）
```

#### 设计差异说明

| 原始设计字段 | 实际实现 | 说明 |
|-------------|---------|------|
| `event_id` | （隐式由存储层生成） | 不作为事件数据字段 |
| `source_id` | `source_domain` + `source_dataset` | 改为二维定位（领域 + 数据集） |
| `source_version` | `source_snapshot_id` | 改用快照引用 |
| `affected_partitions` | `affected_start` + `affected_end` | 改为连续日期范围 |
| `reason` | （隐式由变更来源推断） | correction / late_arrival 等由上游事件类型决定 |
| `priority` | 由 `InvalidationCascadeOrchestrator` 内部排序 | 同深度按 `DerivedRole` 优先级排序 |
| `created_at` | （由存储层自动管理） | 不作为事件数据字段 |
| `depth` | （由传播器运行时计算） | 不作为事件数据字段 |
| — | `root_dependency_ref` | 新增：用于依赖链解析的根引用 |
| — | `change_date` | 新增：精确变更日期 |

---

## 与现有 ADR 的关系

| ADR | 关系 |
|-----|------|
| **ADR-006: 增量计算** | 单因子的 invalidation 机制 |
| **ADR-010: Catalog Schema** | `derived_dependency` 表作为 lineage 输入 |
| **ADR-022: Correction Handling** | 修正数据的处理策略 |
| **ADR-034: Publication Lifecycle** | validate 阶段的静态检查入口 |

---

## 反例：什么不适合放入本 ADR

- ❌ 具体重算逻辑（属于 ADR-006 增量计算）
- ❌ 队列持久化细节（属于基础设施层）
- ❌ 调度器实现细节（属于执行层）

---

## 决策记录

| 日期 | 决策 |
|------|------|
| 2026-03-12 | D-1: 确定级联深度限制（实时 5 层，批处理不限） |
| 2026-03-12 | D-2: 确定异步队列传播模式 + stale 标记 |
| 2026-03-12 | D-3: 确定循环依赖检测策略（注册时硬阻断 + 运行时兜底） |
| 2026-03-20 | **变更**：Phase 1 实现的 `DerivedInvalidationEvent` 结构与原始 ADR 概念设计有显著差异（见"失效事件结构"章节），聚焦于数据源变更描述而非因子级追踪 |
