# ADR-040: Hot/Cold Retention 与 State Namespace 策略

**状态**: 已决策（2026-03-13）

---

## 背景

当前 unified-feature-factor-engine 在以下议题上仍存在多口径：

1. **QuestDB 热层 TTL**
   [ADR-028](adr-028-questdb-hot-tables.md) 仍使用 `120/180/365 天` 的长 TTL 示例，而整改方案已经收敛为“默认只保留够用 lookback”。

2. **分钟数据是否进入 Parquet**
   主设计与历史 gap 文档之间，对 `bar_1m` 是否保留、保留多久、保留哪些元数据仍有冲突。

3. **Kvrocks state key 命名冲突**
   [ADR-010](../adr-010-catalog-schema.md) 使用 `ditto:derived:state:{entity_type}:{entity_id}` 表达派生运行状态，[ADR-031](adr-031-state-snapshot-abi.md) 则使用 `state:feature:{factor_id}:{instrument_id}` 表达 per-instrument snapshot。

4. **artifact / serving / snapshot 生命周期边界不够清晰**
   当前设计已区分 Parquet、QuestDB、Kvrocks，但“哪些是权威层、哪些只是热投影、TTL 是否参与正确性”还未统一。

本 ADR 统一 Hot/Cold retention、state namespace 与 rebuild / GC 语义，作为后续实现与文档回写的唯一口径。

---

## 决策记录

### D-1: 统一存储层级与权威性边界

统一引擎中的相关数据分为五类：

| 数据类别 | 默认介质 | 是否权威 | 默认保留 | 说明 |
|---------|---------|---------|---------|------|
| **版本化发布产物** | Parquet + Catalog | 是 | 不由本 ADR 设自动 TTL | 由发布生命周期与显式 GC 管理 |
| **标准化冷回放窗口** | Parquet | 条件性权威 | 30 天 | 仅覆盖最小必要的 `bar_1m` 与 replay / audit 元数据 |
| **热 serving / query 投影** | QuestDB | 否 | 按热层 profile | 仅承担低延迟访问，不承担最终正确性 |
| **派生运行状态** | Kvrocks | 控制面 latest | 无 TTL | 保存 watermark / coverage / latest_run 等最新控制面信息 |
| **latest snapshot / checkpoint** | Kvrocks | 否 | snapshot 7 天 / checkpoint 7 天 | 可重建、可过期，TTL 只用于回收 |

**统一原则**：

1. **Parquet / 版本化 artifact 是长期正确性与回放的基线**。
2. **QuestDB / Kvrocks 的热数据默认都是可重建投影，不是长期权威副本**。
3. **TTL 只负责回收，不参与 invalidation 正确性判断**。

---

### D-2: Phase 1 默认热层 retention 采用“够用 lookback”

Phase 1 默认热层 retention 统一为表族级 profile，不再按单表零散定义。

| 表族 profile | 适用对象 | 默认 TTL | 说明 |
|-------------|---------|---------|------|
| **intraday_hot** | `bar_1m_hot`、分钟/秒级聚合视图、分钟级衍生热序列 | 5 天 | 仅覆盖盘中链路所需 lookback |
| **daily_hot** | 日线热序列、按日 serving projection | 30 天 | 支持最近一个月热查询 |
| **benchmark_hot** | 压测 / 对拍 / 临时长窗口 profile | 显式配置 | `120/180/365 天` 只允许作为 benchmark profile，不再视为默认值 |

**补充约束**：

1. `ADR-028` 中出现的 `120/180/365 天` 仅保留为 **benchmark / stress profile 示例**。
2. 新增热表时，必须先归入某个 profile，不能单独自定义默认 TTL。
3. 若业务确需更长热窗口，应通过环境 profile 或专用 workload 配置开启，而不是修改默认规范值。

---

### D-3: 标准化分钟数据进入 Parquet，但范围严格受限

**决策**：Phase 1 保留 **30 天标准化 `bar_1m`** 到 Parquet，并同时保留最小必要的 replay / audit 元数据；除此之外，不默认将更多高频热数据沉入冷层。

| 类别 | 是否默认进入 Parquet | 默认保留 | 说明 |
|------|----------------------|---------|------|
| **标准化 `bar_1m`** | 是 | 30 天 | 用于 replay / audit / rebuild |
| **replay / audit 元数据** | 是 | 30 天 | 例如 source snapshot id、ingest watermark、生成时间 |
| **原始逐笔成交** | 否 | - | 非本 ADR 默认范围 |
| **原始 LOB 高频明细** | 否 | - | 非本 ADR 默认范围 |
| **QuestDB 物化视图副本** | 否 | - | 仍视为热层投影 |
| **中间分钟级衍生临时结果** | 否 | - | 需要时走显式 artifact 或研究数据集快照 |

**恢复语义**：

1. 30 天窗口内，热层缺失优先由 Parquet `bar_1m` 回补。
2. 超出 30 天窗口的盘中数据恢复，不依赖热层 TTL，改由上游标准化源重放或重算。
3. “进入 Parquet”不等于“在线查询默认可读”；在线默认边界仍遵循 [ADR-030](adr-030-online-data-access-boundary.md)。

---

### D-4: 统一 state namespace 到 `ditto:derived:state:*`

State family 统一采用 `ditto:derived:state:*` 前缀，区分“控制面 latest 状态”和“per-instance latest snapshot”。

| 用途 | Key 模式 | 值格式 | TTL |
|------|---------|-------|-----|
| **派生运行状态** | `ditto:derived:state:{entity_type}:{entity_id}` | JSON | 无 TTL |
| **per-instance latest snapshot** | `ditto:derived:state:{entity_type}:{entity_id}:snapshot:{instance_key}` | HASH / BLOB | 默认 7 天 |
| **checkpoint** | `ditto:derived:checkpoint:{entity_type}:{entity_id}:{partition_key}` | JSON | 7 天 |

其中：

- `entity_type` 取值与 `DerivedSpec.role` / catalog entity 定义保持一致。
- `instance_key` 是按 `entity_keys` 规范编码后的实例主键；单键场景默认即 `instrument_id`。
- `HASH / BLOB` 双模式仍沿用 [ADR-031](adr-031-state-snapshot-abi.md) 的 ABI 设计，但 key 前缀与层级由本 ADR 统一。

**边界要求**：

1. `ditto:derived:state:{entity_type}:{entity_id}` 只保存“该 spec 当前最新控制面状态”，不再混入 per-instance 明细。
2. per-instance snapshot 必须显式落到 `snapshot:{instance_key}` 子空间。
3. 新实现不得再引入 `state:feature:*` 这类平行命名空间。

---

### D-5: 生命周期、GC 与 rebuild 语义分离

| 对象 | 生命周期主导者 | 是否允许 TTL 回收 | 回收后恢复路径 |
|------|---------------|------------------|---------------|
| **版本化发布产物** | Publication / explicit GC | 否 | 仅可通过显式 artifact GC 删除 |
| **QuestDB 热投影** | retention profile | 是 | 由 Parquet 冷层或上游重算恢复 |
| **Kvrocks 运行状态** | spec 生命周期 | 否 | 可由 catalog / run 记录重建 |
| **Kvrocks latest snapshot** | retention profile | 是 | 由当前发布版本 + 热数据重新生成 |
| **checkpoint / invalidation** | runtime 任务生命周期 | 是 | 由调度器重新派发或忽略历史临时状态 |

**硬性约束**：

1. **TTL 过期不等于版本失效**。版本是否可查询，只由 publication state 与 artifact 可用性决定。
2. **热投影可以先删，权威 artifact 不能隐式跟着删**。
3. **snapshot miss 必须走显式 rebuild / cold-start 路径**，不能被静默视作“业务值为空”。

---

## 决策汇总

| 决策点 | 决策 |
|-------|------|
| **热层默认 TTL** | `intraday_hot = 5 天`，`daily_hot = 30 天` |
| **长 TTL 定位** | `120/180/365 天` 仅作为 benchmark profile，不是默认规范 |
| **分钟冷回放窗口** | 保留 30 天标准化 `bar_1m` + replay / audit 元数据 |
| **state namespace** | 统一为 `ditto:derived:state:*`，区分 root state 与 `snapshot:{instance_key}` |
| **TTL 语义** | 仅负责回收，不承担 invalidation / 发布正确性 |
| **artifact / serving 边界** | artifact 权威且显式 GC；QuestDB / Kvrocks 热数据默认可重建 |

---

## 与现有 ADR 的关系

| ADR | 关系 |
|-----|------|
| [ADR-010](../adr-010-catalog-schema.md) | 继承其 `ditto:derived:state:{entity_type}:{entity_id}` 控制面 key，并补齐 snapshot 子空间 |
| [ADR-028](adr-028-questdb-hot-tables.md) | 覆盖其默认 TTL 口径；长 TTL 降级为 benchmark profile 示例 |
| [ADR-030](../adr-030-online-data-access-boundary.md) | 保持一致：在线默认不查 Parquet，冷层保留仅用于回放 / 重建 |
| [ADR-031](adr-031-state-snapshot-abi.md) | 继承其 HASH / BLOB ABI，替换 `state:feature:*` 命名规范 |
| [ADR-034](../core/adr-034-publication-lifecycle.md) | 明确发布产物与热 serving 投影的生命周期分离 |

---

## 实现清单

### 文档回写

| 文件路径 | 修改内容 |
|---------|---------|
| `docs/design/unified-feature-factor-engine/main-design.md` | 回写 hot/cold retention、分钟冷回放窗口、state namespace |
| `docs/design/unified-feature-factor-engine/decisions/storage/adr-028-questdb-hot-tables.md` | 将长 TTL 改写为 benchmark profile，补默认 profile 说明 |
| `docs/design/unified-feature-factor-engine/decisions/storage/adr-031-state-snapshot-abi.md` | 统一 key 命名到 `ditto:derived:state:*` |
| `docs/design/unified-feature-factor-engine/reference/catalog-schema.md` | 对齐 namespace 与生命周期矩阵 |

### 实现落点

| 模块 | 修改内容 |
|------|---------|
| `packages/core` | 增加 retention profile 配置模型 |
| `packages/datahub` | 统一 Kvrocks key builder 与 TTL policy |
| `packages/datahub` | 区分 artifact GC 与 hot projection cleanup |

---

## 更新记录

### 2026-03-13
- 初始版本
- 将热层默认 TTL 收敛为 `intraday_hot=5 天 / daily_hot=30 天`
- 明确 30 天标准化 `bar_1m` 冷回放窗口
- 统一 state namespace 到 `ditto:derived:state:*`
- 固定 TTL 不承担正确性、artifact 与 hot projection 生命周期分离
