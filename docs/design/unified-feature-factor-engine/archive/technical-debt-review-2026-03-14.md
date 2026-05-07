> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# Unified Feature/Factor Engine 技术债务记录

**Review 日期**: 2026-03-14（初版） / 2026-03-16（深度代码审查更新）
**Review 范围**: 架构设计、实现一致性、工程质量、**代码级语义正确性**
**状态**: 记录待处理

---

## 0. 核心问题（P0 - 阻塞性）

> 以下问题由深度代码审查发现，影响 control-plane 语义正确性，需优先处理。

### 0.1 生命周期状态语义漂移

| ID | 问题 | 严重程度 | 代码位置 |
|----|------|----------|----------|
| **C-LC-01** | `DerivedVersionStatus` 定义 `draft/active/deprecated/archived`，但 `publication.py` 直接写入 `"PUBLISHED"` 字符串 | **高** | `publication.py:235` |
| **C-LC-02** | SQLite 查询需同时兼容两套口径，失去唯一真相源地位 | **高** | `reader.py:249` |

**根因**：状态词汇分裂，未统一到 `DerivedVersionStatus` 枚举。

**修复建议**：
1. `DerivedVersionStatus` 添加 `PUBLISHED`/`DEPRECATED` 或
2. `publication.py` 改用 `active`/`deprecated` 枚举值

---

### 0.2 无事务边界

| ID | 问题 | 严重程度 | 代码位置 |
|----|------|----------|----------|
| **C-TX-01** | 每个 `write_*()` 方法立即 `commit()`，无事务包装 | **高** | `writer.py:44` |
| **C-TX-02** | `materialization.py` 多步骤（artifact 写入 + metadata 注册）无原子性 | **高** | `materialization.py:143, 508` |

**风险**：中途失败留下半完成状态，无法回滚，灾难恢复困难。

**修复建议**：
1. 引入 `UnitOfWork` 或事务上下文
2. 所有写操作在同一个事务内完成后再 commit

---

### 0.3 compile cache 逻辑错误

| ID | 问题 | 严重程度 | 代码位置 |
|----|------|----------|----------|
| **C-CC-01** | `get_or_compile()` 先编译再查缓存，缓存形同虚设 | **高** | `compile_cache.py:56` |
| **C-CC-02** | 没有 L2 read path（SQLite 查询） | 中 | `compile_cache.py` |

**代码证据**：
```python
# compile_cache.py:56-58
compiled = self._compiler.compile(spec)  # 先编译！
cache_key = compiled.compile_identity.cache_key
if not force_recompile and cache_key in self._memory_cache:  # 再查缓存
    return self._memory_cache[cache_key]
```

**修复建议**：先查缓存，miss 时再编译。

---

### 0.4 fallback alias 静默降级

| ID | 问题 | 严重程度 | 代码位置 |
|----|------|----------|----------|
| **C-FA-01** | 缺失依赖用任意可用列填充，导致"拿错列继续算" | **高** | `materialization.py:744` |

**代码证据**：
```python
# materialization.py:736-744
fallback_column = value_candidates[0] if value_candidates else None
for dependency in dependencies:
    if ... or fallback_column is None:
        continue
    prepared = prepared.with_columns(pl.col(fallback_column).alias(dependency))
```

**风险**：因子计算错误，且难以发现。

**修复建议**：缺失依赖应抛出显式异常，而非静默降级。

---

## 0.5 compute window 覆盖

| ID | 问题 | 严重程度 | 代码位置 |
|----|------|----------|----------|
| **C-CW-01** | 成功路径用 `request_start/end` 覆盖真实 `compute_start/end` | **中** | `materialization.py:357-358, 453-454` |

**影响**：审计追踪丢失 lookback/invalidation 回退信息。

**修复建议**：保留 `compute_start = plan.compute_start`（含 lookback）。

---

## 0.6 research 版本解析静默回退

| ID | 问题 | 严重程度 | 代码位置 |
|----|------|----------|----------|
| **C-RV-01** | `resolve_serving_version()` 无 primary online 时回退到 `active_version` | **高** | `artifact_reader.py:48` |
| **C-RV-02** | 可能静默绑定未发布版本到研究快照 | **高** | `research.py:115-117` |

**代码证据**：
```python
# artifact_reader.py:48
version = primary_online or self._resolve_active_version(derived_id)
```

**修复建议**：无 primary online 时应显式报错或要求显式版本指定。

---

## 1. 设计层面问题

### 1.1 ADR 文档体系

| ID | 问题 | 严重程度 | 建议 |
|----|------|----------|------|
| D-ADR-01 | ADR 过度碎片化（43+ 文档），认知成本高 | 中 | 考虑按主题归组（如 `ADR-03x: 统一派生模型系列`） |
| D-ADR-02 | 部分 ADR 状态漂移（`⏸️ 暂缓` 无重启条件） | 低 | 添加触发条件或明确废弃 |
| D-ADR-03 | ADR 间交叉引用复杂，阅读路径不清晰 | 低 | 更新 README 导航结构 |

### 1.2 语义模型

| ID | 问题 | 严重程度 | 代码位置 |
|----|------|----------|----------|
| D-SPEC-01 | `CalendarId` 类型退化为 `str`，与 ADR-032 `Literal["cn_stock"]` 不一致 | 中 | `packages/core/src/ditto_core/engine/specs.py:8` |
| D-SPEC-02 | `GrainId` 类型退化为 `str`，与 ADR-032 `Literal["1d", "1m"]` 不一致 | 中 | `packages/core/src/ditto_core/engine/specs.py:9` |
| D-SPEC-03 | `DerivedSpec` 职责边界模糊，既承载计算语义又隐含执行策略 | 中 | `packages/core/src/ditto_core/engine/specs.py` |
| D-SPEC-04 | `availability_time` 缺席核心模型，ADR-041 定义但未在 `DerivedSpec` 体现 | 中 | 设计文档 vs 实现差距 |

### 1.3 热层/冷层架构

| ID | 问题 | 严重程度 | 说明 |
|----|------|----------|------|
| D-HEAT-01 | QuestDB 热层未实现 | 中 | 设计完整，实现为 Phase 3+ |
| D-HEAT-02 | Kvrocks 状态存储未实现 | 中 | 设计完整，实现为 Phase 3+ |
| D-HEAT-03 | `RuntimeMode` 空解析模式增加理解成本 | 低 | `query_facade.py:85` 解析后未消费 |
| D-HEAT-04 | artifact-first 策略缺少迁移计划 | 低 | 需明确热层实现时间表 |

---

## 2. 实现与设计差距

### 2.1 增量计算

| ID | 问题 | 严重程度 | 代码位置 |
|----|------|----------|----------|
| I-INCR-01 | `requires_full_day=True` 触发整日重算逻辑未完整消费 | 中 | `planner.py` 记录但消费端缺失 |
| I-INCR-02 | CS 因子全截面放大逻辑未实现 | 中 | ADR-006 承诺，无代码证据 |

### 2.2 Invalidation Cascade Protocol

| ID | 问题 | 严重程度 | 代码位置 |
|----|------|----------|----------|
| **I-CASC-01** | 当前只是一跳 repair 队列，非 ADR-035 cascade protocol | **中** | `invalidation.py:34-80` |
| I-CASC-02 | 无 BFS 分层、最大深度、stale/recomputing 状态 | 中 | ADR-035 定义缺失 |
| I-CASC-03 | 无 cycle guard、无微批合并 | 低 | ADR-035 定义缺失 |

**当前实现**：
```python
# invalidation.py:34-80
def enqueue(self, event: DerivedInvalidationEvent) -> str:
    # 只遍历直接依赖，无级联传播
    for dependency in self._catalog_service.list_dependencies_by_ref(...):
        records.append(...)
```

**ADR-035 承诺**：BFS 分层传播、状态机（stale → recomputing → healed）、cycle guard。

### 2.3 Research Spec Versioning

| ID | 问题 | 严重程度 | 代码位置 |
|----|------|----------|----------|
| I-RES-01 | `dataset_spec_version` 硬编码为 `1`，非动态版本 | 中 | `research.py:34` |
| I-RES-02 | `SpineSpec`/`ResearchDatasetSpec` 无 `version` 字段 | 中 | `research.py` Core 模型 |
| I-RES-03 | `DatasetSnapshot` 不是严格的 spec-versioned contract | 中 | ADR-041 语义 |

**代码证据**：
```python
# research.py:34
_DATASET_SPEC_VERSION = 1  # 硬编码
```

### 2.4 表达式引擎

| ID | 问题 | 严重程度 | 说明 |
|----|------|----------|------|
| I-EXPR-01 | DAG/CSE 优化未实现 | 低 | 设计标记为"可选"，不阻塞功能 |

---

## 3. 工程质量层面

### 3.1 职责划分

| ID | 问题 | 严重程度 | 代码位置 |
|----|------|----------|----------|
| Q-RESP-01 | `DerivedMaterializationService` 单文件 880+ 行，职责过重 | 高 | `apps/port/src/ditto_port/services/derived/materialization.py` |
| **Q-RESP-02** | Port 层直接操作文件系统，违反分层规范 | **中** | `materialization.py:488`/`research.py:184`/`publication.py:44` |
| Q-RESP-03 | `compile_cache.py` 位置存疑，可能应下沉到 DataHub | 低 | `apps/port/src/ditto_port/services/derived/compile_cache.py` |

**Q-RESP-02 详细位置**：
- `materialization.py:495-499` 直接创建目录、写 parquet
- `research.py:184+` 直接操作文件系统持久化 snapshot
- `publication.py:44+` 直接处理 artifact metadata 持久化

**违反规范**：CLAUDE.md 规定 Port 编排、DataHub 持久化。

**Q-RESP-01 拆分建议**：
1. `DerivedMaterializationOrchestrator`：流程编排
2. `DerivedArtifactWriter`：artifact 写入（下沉到 DataHub）
3. `DerivedRunFinalizer`：状态持久化（下沉到 DataHub）
4. `PublicationMetadataRegistrar`：发布元数据注册（下沉到 DataHub）

### 3.2 抽象设计

| ID | 问题 | 严重程度 | 代码位置 |
|----|------|----------|----------|
| Q-ABS-01 | `DerivedInputProvider` 参数过多（4 个），调用者负担重 | 低 | `materialization.py:59-71` |
| Q-ABS-02 | `InMemoryDerivedInputProvider` 忽略 3/4 参数 | 低 | `materialization.py:74-95` |

### 3.3 命名一致性问题

| ID | 问题 | 严重程度 | 建议 |
|----|------|----------|------|
| Q-NAME-01 | `DerivedMaterializationService` 位于 Port 层但命名像 Domain Service | 低 | 重命名为 `*Orchestrator` |
| Q-NAME-02 | 测试文件 `test_materialization_facade_unit.py` 名实不符 | 低 | 对齐被测类名 |

### 3.4 错误处理

| ID | 问题 | 严重程度 | 代码位置 |
|----|------|----------|----------|
| Q-ERR-01 | 异常类型混用，应定义统一 `DerivedError` 层次 | 中 | 多处使用 `KeyError`/`ValueError`/`NotImplementedError` |
| Q-ERR-02 | `RuntimeInputNotWiredError` 应作为领域异常而非 `NotImplementedError` | 低 | `materialization.py:113-115` |

---

## 4. 优先级排序（更新后）

### P0（阻塞性问题 - control-plane 语义正确性）

| 优先级 | ID | 问题 | 修复方案 |
|--------|-----|------|----------|
| 1 | C-LC-01/02 | 生命周期状态语义漂移 | 统一到 `DerivedVersionStatus` 枚举 |
| 2 | C-TX-01/02 | 无事务边界 | 引入 `UnitOfWork` 或事务上下文 |
| 3 | C-CC-01 | compile cache 逻辑错误 | 先查缓存再编译 |
| 4 | C-FA-01 | fallback alias 静默降级 | 缺失依赖抛显式异常 |

### P1（影响正确性/扩展性，建议下个迭代处理）

| 优先级 | ID | 问题 | 修复方案 |
|--------|-----|------|----------|
| 1 | C-RV-01/02 | research 版本解析静默回退 | 无 primary online 时显式报错 |
| 2 | C-CW-01 | compute window 覆盖 | 保留真实 `compute_start/end` |
| 3 | Q-RESP-01 | Service 单文件过大 | 拆分为 4 个协作对象 |
| 4 | Q-RESP-02 | Port 层文件操作下沉 | 移入 DataHub Writer |

### P2（影响可维护性，建议季度内处理）

| 优先级 | ID | 问题 |
|--------|-----|------|
| 1 | D-SPEC-01/02 | `CalendarId/GrainId` 类型约束恢复 |
| 2 | I-CASC-01/02 | Invalidation cascade protocol 实现 |
| 3 | I-RES-01/02 | Research spec versioning 完善 |
| 4 | Q-ERR-01 | 统一异常类型体系 |
| 5 | I-INCR-02 | CS 因子全截面放大逻辑 |

### P3（改善性，有时间再处理）

| 优先级 | ID | 问题 |
|--------|-----|------|
| 1 | Q-ABS-01 | Input Provider 参数封装 |
| 2 | D-HEAT-03 | `RuntimeMode` 空解析模式清理 |
| 3 | Q-NAME-01/02 | 命名对齐 |
| 4 | I-EXPR-01 | DAG/CSE 优化 |
| 5 | D-ADR-01 | ADR 归组整理 |

---

## 5. Review 统计

### 初版 Review（2026-03-14）

| 维度 | 评分 | 说明 |
|------|------|------|
| **设计完整度** | 8/10 | ADR 体系完整，但碎片化 |
| **设计实现一致性** | 6/10 | 核心链路一致，热层/CS 放大有差距 |
| **工程质量** | 7/10 | 分层清晰，但部分文件过大、异常处理不一致 |
| **可维护性** | 7/10 | 文档丰富但认知成本高 |

### 深度代码审查后（2026-03-16）

| 维度 | 评分 | 变化 | 说明 |
|------|------|------|------|
| **语义正确性** | 5/10 | 新增 | Control-plane 状态分裂、事务边界缺失、静默降级 |
| **设计实现一致性** | 5/10 | ↓1 | 发现更多设计与实现差距（cascade、versioning） |
| **工程质量** | 6/10 | ↓1 | 分层边界塌陷、compile cache 逻辑错误 |
| **可维护性** | 7/10 | - | 无变化 |

### 问题统计

| 分类 | P0 | P1 | P2 | P3 | 合计 |
|------|----|----|----|----|------|
| 核心问题 (C-*) | 4 | 2 | - | - | 6 |
| 设计层面 (D-*) | - | - | 2 | 2 | 4 |
| 实现差距 (I-*) | - | - | 5 | 1 | 6 |
| 工程质量 (Q-*) | - | 2 | 1 | 4 | 7 |
| **合计** | **4** | **4** | **8** | **7** | **23** |

---

## 6. 相关文档

- [main-design.md](main-design.md)
- [README.md](README.md)
- [ADR-032 ~ ADR-043](decisions/)
- [整改设计方案](../../plans/2026-03-13-unified-feature-factor-engine-remediation-design.md)
- [Review 记录 2026-03-15](review-2026-03-15.md)

---

## 7. 建议的修复顺序

基于用户确认的 Plan：

```
Phase 1: P0 收敛
├── 统一 lifecycle vocabulary
├── 补 transaction boundary
├── 修 compile cache
├── 移除 fallback alias
└── 修 compute window / research 版本解析

Phase 2: 结构重构
├── artifact persistence 下沉到 DataHub
├── research snapshot store 下沉到 DataHub
├── publication evidence store 下沉到 DataHub
└── Port 只保留 facade/orchestration

Phase 3: 语义补全
├── research spec versioning
├── invalidation cascade protocol (BFS + 状态机)
└── CS 因子全截面放大

Phase 4: 横向扩展（在 control-plane 稳定后）
├── hot layer (QuestDB/Kvrocks)
├── retention policy
├── DR strategy
└── housekeeping
```
