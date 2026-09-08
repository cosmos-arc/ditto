> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# ADR-041: Research Dataset、Spine 与 Availability-Time 契约

**状态**: 已决策（2026-03-13）

---

## 背景

当前 unified-feature-factor-engine 已经较完整地定义了：

- `DerivedSpec` 语义模型
- 物化 / 发布 / 查询控制面
- Online 与 Offline 的数据访问边界

但对“研究 / 训练数据集如何构建”仍缺少系统级根契约，具体表现为：

1. **缺少左表 / 样本表的一等对象**
   当前有 `DerivedSpec`，但没有与业界常见 `entity dataframe` / `spine` 对应的统一模型。

2. **`event_time` / `availability_time` 仍停留在语义提示层**
   [ADR-032](../core/adr-032-unified-derived-semantic-model.md) 已指出时间语义应与 `grain` 分离，但尚未定义训练数据集如何使用 `availability_time` / `known_at`。

3. **研究可复现性仍弱于物化可复现性**
   当前版本化、发布、artifact 已较清晰，但尚未把“某个训练数据集由哪些版本、哪些源快照、在什么 cutoff 下生成”固定成不可变快照。

本 ADR 将 `SpineSpec`、`ResearchDatasetSpec`、`DatasetSnapshot` 与 `availability_time / known_at` 统一为正式契约。

---

## 决策记录

### D-1: 将 `SpineSpec` / `ResearchDatasetSpec` / `DatasetSnapshot` 设为一等对象

研究数据集链路统一引入三个对象：

| 对象 | 职责 | 核心字段 |
|------|------|---------|
| **`SpineSpec`** | 定义左表 / 样本表契约 | `spine_id`、`entity_keys`、`sample_time_key`、`sample_grain`、`calendar`、`filters` |
| **`ResearchDatasetSpec`** | 定义数据集拼装规则 | `dataset_id`、`spine_ref`、`feature_refs`、`label_refs`、`join_policy`、`known_at_policy` |
| **`DatasetSnapshot`** | 定义一次不可变构建结果 | `snapshot_id`、`dataset_spec_version`、`spine_snapshot_id`、`resolved_inputs`、`output_path`、`manifest_hash` |

**对象职责边界**：

1. `SpineSpec` 只定义“保留哪些样本行”，不隐式携带 feature 版本。
2. `ResearchDatasetSpec` 只定义“如何基于某个 spine 拼出数据集”，允许引用 `feature` / `factor` / `label`。
3. `DatasetSnapshot` 是一次具体构建的不可变结果，必须解析为精确版本与精确源快照。

**示意模型**：

```python
class SpineSpec(BaseModel):
    spine_id: str
    entity_keys: list[str]
    sample_time_key: str
    sample_grain: Literal["1d", "1m"]
    calendar: str
    filters: dict[str, str | int | float | bool]


class ResearchDatasetSpec(BaseModel):
    dataset_id: str
    spine_ref: str
    feature_refs: list[str]
    label_refs: list[str] = []
    join_policy: Literal["left_preserving_pit"]
    known_at_policy: Literal["sample_time", "explicit_cutoff"]
    late_arrival_policy: Literal[
        "exclude_from_current_snapshot",
        "shift_to_next_snapshot",
        "require_rebuild",
    ] = "require_rebuild"


class DatasetSnapshot(BaseModel):
    snapshot_id: str
    dataset_id: str
    dataset_spec_version: int
    spine_snapshot_id: str
    resolved_inputs: list[dict[str, str | int]]
    output_path: str
    manifest_hash: str
```

---

### D-2: 研究链路必须显式建模 `event_time`、`availability_time` 与 `known_at`

研究数据集中的每个输入源都必须满足以下条件之一：

1. 原生提供 `event_time` 与 `availability_time`
2. 原生提供 `event_time`，并可明确推导 `availability_time`
3. 无独立 `availability_time` 时，显式声明 `availability_time == event_time`

**统一时间定义**：

| 字段 | 含义 |
|------|------|
| **`event_time`** | 业务事件真实发生时间 |
| **`availability_time`** | 数据在系统中可被合法使用的最早时间 |
| **`known_at`** | 构建某个样本行时允许读取数据的上界 |
| **`sample_time`** | spine 行的观察时点，通常来自 `sample_time_key` |

**默认规则**：

1. `known_at_policy = "sample_time"` 时，`known_at = sample_time`。
2. `known_at_policy = "explicit_cutoff"` 时，必须在 `DatasetSnapshot` 中记录具体 cutoff。
3. feature join 只能使用满足 `availability_time <= known_at` 的记录。
4. 若某条迟到数据会改变既有样本结果，Phase 1 默认 `late_arrival_policy = "require_rebuild"`，而不是静默修补旧 snapshot。

---

### D-3: 数据集构建默认采用 left-preserving PIT join

研究数据集构建默认 join 模式固定为 `left_preserving_pit`。

**含义**：

1. `SpineSpec` 决定输出行数上界。
2. feature / factor / label 的 join 不得因缺值而静默丢弃左表行。
3. 缺失值、join miss、coverage 降低必须体现在构建报告里。

**PIT join 规则**：

```
对每个 spine row:
1. 读取 entity_keys + sample_time
2. 计算 known_at
3. 在每个输入源中选择满足：
   - key 匹配
   - availability_time <= known_at
   - 时间上最接近 known_at 的最新记录
4. 保留左表行；未命中则记为 null / missing，并写入 coverage report
```

**原因**：

- 这与训练 / 回测场景的可复现性要求一致
- 避免 inner join 风格的数据集在不同版本下悄悄改变样本基数
- 与现有 DQ / coverage gate 设计天然兼容

---

### D-4: `DatasetSnapshot` 必须是不可变、可追溯、精确版本绑定的

每次构建研究数据集都必须产出一个 `DatasetSnapshot` 清单，至少包含：

| 字段 | 说明 |
|------|------|
| `snapshot_id` | 数据集快照 ID |
| `dataset_id` / `dataset_spec_version` | 对应的数据集定义版本 |
| `spine_snapshot_id` | 左表快照 ID |
| `resolved_inputs` | 每个派生输入最终解析到的精确 `(entity_id, version, artifact_uri)` |
| `source_snapshot_ids` | 底层源数据快照 ID |
| `known_at_policy` / `effective_cutoff` | 当次构建采用的已知时间边界 |
| `row_count` / `schema_hash` | 构建结果摘要 |
| `output_path` / `manifest_hash` | 输出路径与 manifest 完整性校验 |
| `built_at` / `builder_version` | 构建时间与构建器版本 |

**硬性约束**：

1. `ResearchDatasetSpec` 可以写“跟随 primary”或“按别名引用”，但一旦进入 `DatasetSnapshot`，必须解析成精确版本。
2. 已生成的 `DatasetSnapshot` 不可原位修改；任何重跑都必须生成新的 `snapshot_id`。
3. `DatasetSnapshot` 是研究可复现性的权威入口，不允许仅靠运行日志恢复完整上下文。

---

### D-5: 研究数据集构建与在线 serving 默认隔离

研究数据集构建路径与在线查询路径需要共享统一语义，但默认隔离运行：

| 维度 | 研究数据集构建 | 在线 serving / query |
|------|---------------|----------------------|
| **输入层** | 可读取 Parquet 真相层 + 已发布 artifact | 默认只读 QuestDB / Kvrocks / serving projection |
| **入口契约** | 必须提供 `SpineSpec` / `ResearchDatasetSpec` | 由 query facade 或 serving API 驱动 |
| **时间语义** | 必须显式 `known_at` / `availability_time` | 以当前 latest / watermark 为主 |
| **输出** | 不可变 `DatasetSnapshot` | 当前值 / 查询结果，不形成研究快照 |

**边界要求**：

1. 研究数据集构建不能绕过 `SpineSpec` 直接“拉一批 features 再拼”。
2. `DerivedQueryFacade` 可以提供 PIT 提取能力，但不得隐藏 `known_at` / left-preserving join 语义。
3. 在线默认不承担“训练数据集保存”职责；保存训练集必须走 `DatasetSnapshot` 路径。

---

## 决策汇总

| 决策点 | 决策 |
|-------|------|
| **研究左表契约** | 引入 `SpineSpec` 作为一等对象 |
| **数据集定义** | 引入 `ResearchDatasetSpec`，显式管理 join / known_at / late arrival 策略 |
| **时间语义** | 每个输入源都必须显式建模 `event_time` 与 `availability_time` |
| **PIT join** | 默认 `left_preserving_pit`，不允许静默缩小样本基数 |
| **可复现性** | 每次构建都产出不可变 `DatasetSnapshot`，解析为精确版本与源快照 |
| **边界** | 研究数据集构建与在线 serving 共享语义但默认隔离 |

---

## 与现有 ADR 的关系

| ADR | 关系 |
|-----|------|
| [ADR-021](../quality/adr-021-pit-consistency.md) | 扩展其 PIT 一致性原则到研究数据集构建与左表契约 |
| [ADR-030](../adr-030-online-data-access-boundary.md) | 保持一致：在线默认不读 Parquet，但研究构建允许读取真相层 |
| [ADR-032](../core/adr-032-unified-derived-semantic-model.md) | 将其 `event_time / availability_time` 语义分离正式落到研究契约 |
| [ADR-033](../adr-033-derived-query-architecture.md) | 复用查询层能力，但要求研究链路显式提供 spine / known_at |
| [ADR-034](../core/adr-034-publication-lifecycle.md) | `DatasetSnapshot` 必须绑定已发布或显式指定的版本化 artifact |
| [ADR-036](../quality/adr-036-quality-gates.md) | 后续可基于 coverage / null / freshness 为数据集构建补认证包 |

---

## 实现清单

### 文档回写

| 文件路径 | 修改内容 |
|---------|---------|
| `packages/features/docs/design/unified-feature-factor-engine/main-design.md` | 增加 spine / research dataset / availability-time 章节 |
| `packages/features/docs/design/unified-feature-factor-engine/decisions/core/adr-032-unified-derived-semantic-model.md` | 回写 TimeSpec 与 dataset 契约之间的关系 |
| `packages/features/docs/design/unified-feature-factor-engine/decisions/adr-033-derived-query-architecture.md` | 区分 serving query 与 dataset build 的入口 |

### 实现落点

| 模块 | 修改内容 |
|------|---------|
| `packages/kernel` | 新增 `SpineSpec`、`ResearchDatasetSpec`、`DatasetSnapshot` 模型 |
| `packages/data` | 提供 left-preserving PIT join 与 dataset snapshot manifest 写入 |
| `packages/port` | 增加 research dataset build facade / API（如后续需要） |

---

## 更新记录

### 2026-03-13
- 初始版本
- 将 `SpineSpec`、`ResearchDatasetSpec`、`DatasetSnapshot` 定义为一等对象
- 明确 `event_time / availability_time / known_at` 的研究数据集语义
- 固定 `left_preserving_pit` 为默认研究 join 模式
- 固定数据集快照必须解析为精确版本与精确源快照
