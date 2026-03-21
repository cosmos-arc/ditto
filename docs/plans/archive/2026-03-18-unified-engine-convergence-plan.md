# Unified Feature Factor Engine — Convergence Plan

> 日期：2026-03-18
> 分支：feature/unified-feature-factor-engine
> 状态：已完成

## 总判断

**架构方向正确，不需要方向性重构。需要一次"结构收敛"——在现有架构框架内把双轨协议合一、事务边界落地、seam 清理、层边界收口。**

### 评估基础

对照业界系统（dbt, Feast, Ray Data, TFX）验证后的核心结论：

| 设计决策 | 业界对标 | 评价 |
|---------|---------|------|
| Expression DSL → Pratt Parser → AST → Analyzer → Codegen | dbt (SQL→compiled), Feast (feature def→materialized) | 正确 |
| Parquet 单一真相源，Hot Layer 可重建 | Feast offline/online store 分离 | 正确 |
| Shadow → Certify → Promote 发布流程 | dbt dev→staging→prod，蓝绿发布 | 优秀 |
| Spine + Dataset Snapshot PIT 模型 | QuantLib PIT，因果推断标准 | 正确 |
| Invalidation Cascade → 选择性重算 | Airflow task dependency，Feast regeneration | 方向正确，实现有双轨问题 |
| 分层依赖 Core → DataHub → Port | Clean/Hexagonal Architecture | 正确 |

### 需要收敛的三类漂移

1. **协议双轨并存**（结构性，最高优先级）：新旧 Invalidation 协议同时存在
2. **层边界被实际运行路径侵蚀**（渐进式）：3 个 Port Service 直接绕过 DataHub
3. **语义模型半成品堆积**（技术债务）：定义了但未消费的类型、不一致的物理路径

## 不纳入范围（明确 defer）

| 项 | 理由 |
|----|------|
| Planner 日历回退 | 安全（多请求 ~30%），等日历服务集成 |
| Hot Layer 实现 | 依赖 QuestDB/Kvrocks 基础设施 |
| Shadow diff SLI 指标 (freshness/latency/fallback_ratio) | 等在线路径激活 |
| STATE profile 物理路径 | 依赖 Kvrocks |
| TimeSpec / ExecutionPolicy 行为迁移 | Phase seam，v2 再激活 |
| ARCHIVED 状态 / SIGNAL / LABEL 角色 | 保留定义，等实际需求出现 |
| grain='1m' / 复合键 | 保留 DerivedNotImplementedError 守卫 |

---

## P1：基础设施收口 ✅ 已完成

### P1-1：UoW 落地（Service 层注入）

**决策**：Option B — Service 层控制事务边界，Writer 暴露非 commit 的 execute 方法。

**改动**：

| 文件 | 改动 |
|------|------|
| `packages/datahub/src/ditto_datahub/stores/runtime/derived_sqlite/writer.py` | 每个 `write_*()` 新增 `_execute()` 变体（不 commit），原方法改为 enqueue + commit |
| `packages/datahub/src/ditto_datahub/stores/runtime/research_sqlite/writer.py` | 同上 |
| `packages/datahub/src/ditto_datahub/services/derived_catalog_service.py` | 关键编排方法注入 `UnitOfWork` |
| `packages/datahub/src/ditto_datahub/services/research_catalog_service.py` | 同上 |
| `apps/port/src/ditto_port/services/derived/materialization_orchestrator.py` | 通过 Service 调用，不直接调用 Writer |

**验收**：
- Writer 独立 commit 从 14 个降至 0
- 新增集成测试：模拟 write 中途崩溃，验证 UoW rollback 不留半完成状态
- 现有 66 个引擎单测全部通过

### P1-2：Record 类型守卫

**改动**：

| 文件 | 改动 |
|------|------|
| `derived_sqlite/writer.py` | `write_version()` 加 `DerivedVersionStatus(value)` 校验 |
| `derived_sqlite/writer.py` | `write_run()` 加 `DerivedRunStatus(value)` 校验 |
| `derived_sqlite/writer.py` | `mark_invalidation_status()` 加枚举校验 |

**验收**：写入非法 status 字符串时抛 ValueError。

### P1-3：ts_rank / ts_argmax / ts_argmin codegen 实现

**改动**：

| 文件 | 改动 |
|------|------|
| `packages/core/src/ditto_core/engine/expression/codegen.py` | `_WINDOW_KIND_BY_NAME` 新增 `rank`/`argmax`/`argmin` 映射；新增特殊处理分支 |

**参考实现**：
- `ts_rank(x, n)` → `pl.col(x).shift(1).rolling(n, closed="left").rank()`
- `ts_argmax(x, n)` → `pl.col(x).shift(1).rolling(n, closed="left").arg_max()`
- `ts_argmin(x, n)` → `pl.col(x).shift(1).rolling(n, closed="left").arg_min()`

**验收**：新增单测覆盖三个算子的 codegen 输出和计算正确性。

---

## P2：协议统一 ✅ 已完成

### P2-1：废弃旧 Invalidation 协议

**改动**：

| 文件 | 改动 |
|------|------|
| `apps/port/src/ditto_port/services/derived/cascade_protocol.py` | BFS 入口过滤 root ref（`market.*`），不产生 invalidation 记录 |
| `apps/port/src/ditto_port/registry/datahub/derived.py` | 替换 `derived_invalidation_orchestrator` Provider 为 `InvalidationCascadeOrchestrator` |
| `apps/port/src/ditto_port/registry/contexts/bundle.py` | `MaterializationBundle.invalidation_service` 类型更新 |
| `apps/port/src/ditto_port/jobs/flows/materialization.py` | `repair_from_invalidation_flow` 调用新协议 |
| `apps/port/src/ditto_port/services/derived/invalidation.py` | 删除旧协议代码 |
| `apps/port/src/ditto_port/services/derived/__init__.py` | 移除旧协议导出 |

**风险点**：新旧协议 repair 接口签名可能不同，需要 adapter 或微调新协议入口。

**验收**：
- 旧协议代码从仓库删除
- MaterializationBundle 无旧协议引用
- 新协议 ~660 行单元测试全部通过
- 新增集成测试验证 DI 注入正确

---

## P3：层边界修复 ✅ 已完成

### P3-1：ResearchDatasetFacade 收回文件 I/O（最高优先级）

**目标**：消除 6 处直接文件 I/O，参照 `DerivedPublicationFacade` 模式。

**改动**：

| 步骤 | 层 | 文件 | 改动 |
|------|----|------|------|
| 1 | DataHub | 新增/扩展 Service | `read_research_parquet()` / `write_research_parquet()` / `read_research_metadata()` |
| 2 | DataHub | `research_catalog_service.py` | 新增 `get_spine_snapshot_data()` / `save_dataset_snapshot_data()` |
| 3 | Port | `research.py` | 替换所有 `pl.read_parquet()` / `.write_parquet()` / `.read_bytes()` / `.write_bytes()` / `.glob()` |

### P3-2：RuntimeDerivedInputProvider 收回 Store 访问

**改动**：

| 步骤 | 层 | 文件 | 改动 |
|------|----|------|------|
| 1 | DataHub | 确认 `MarketService` 已暴露 `get_bars()` / `get_adj_factors()` / `get_status()` | 如无，需要新增 Service 方法 |
| 2 | Port | `runtime_input.py` | Service 替代直接 Store import |

### P3-3：MaterializationOrchestrator 收回 Store 访问

**改动**：

| 步骤 | 层 | 文件 | 改动 |
|------|----|------|------|
| 1 | DataHub | Service 扩展 | 封装 `write_artifact()` / `write_durable_partitions()` / `write_metadata()` |
| 2 | Port | `materialization_orchestrator.py` | Service 调用替代直接 Writer 调用 |

**依赖**：P1-1（UoW 落地），Service 封装后 UoW 控制权自然上移。

### P3-4：UniverseProvider 注入修复

**改动**：

| 文件 | 改动 |
|------|------|
| `apps/port/src/ditto_port/registry/datahub/derived.py` | `derived_materialization_orchestrator` 构造时注入 `UniverseProvider` |

**验收**：`requires_full_day` 的 CS amplification 在应用路径真正生效。

---

## P4：生命周期与治理 ✅ 已完成

### P4-1：去掉 materialize 自动 shadow save

**改动**：

| 文件 | 改动 |
|------|------|
| `apps/port/src/ditto_port/services/derived/materialization_orchestrator.py` | 移除 `_save_shadow_slot()` 调用 |
| 对应单测 | 更新期望行为 |

**语义**：物化只产生 artifact，shadow 进入完全由 `shadow_publish_flow` 控制。

### P4-2：Research 版本绑定 PUBLISHED

**改动**：

| 文件 | 改动 |
|------|------|
| `packages/datahub/src/ditto_datahub/services/derived/artifact_reader.py` | `resolve_version()` 优先查询 `status='published'` 的版本 |
| `apps/port/src/ditto_port/services/derived/research.py` | 确认不直接读 `active_version` |
| `apps/port/src/ditto_port/services/derived/materialization_orchestrator.py` | `active_version` 只在 promote 时更新，materialize 不更新 |

**语义区分**：
- `active_version` = 当前在线服务的版本（PUBLISHED 后才更新）
- research 绑定 `active_version`（即 PUBLISHED 版本）

### P4-3：Profile 物理路径收敛

**改动**：

| 文件 | 改动 |
|------|------|
| `apps/port/src/ditto_port/services/derived/materialization_orchestrator.py` | 重构 profile 分支：`DERIVE` 有预处理（join upstream），之后所有 profile 共享后续路径 |

**保留**：`publication_rules.py` 的 certification 规则仍按 profile 差异化（差异在编排策略，不在物理路径）。

### P4-4：文档同步

| 文档 | 改动 |
|------|------|
| `packages/core/src/ditto_core/engine/README.md` | 完全重写，反映当前 unified derived engine 架构 |
| `docs/plans/unified-feature-factor-engine-remaining-tasks.md` | 更新 arch-check 0 broken，移除已完成项，加入收敛项 |
| `docs/design/unified-feature-factor-engine/archive/review-2026-03-15.md` | 标注为历史参考 |

---

## 验收标准

每个阶段完成后：

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # 0 broken
```

全部完成后系统应达到：

- [x] 单协议：只有 Cascade Invalidation
- [x] 事务安全：所有多步写通过 UoW 原子提交
- [x] 层边界清晰：Port 不直接访问 Store，不直接操作文件系统
- [x] 生命周期明确：物化和发布是显式分离的两个操作
- [x] 研究治理安全：research 只绑定 PUBLISHED 版本
- [x] 文档可信：README 和 remaining-tasks 反映代码现实

## 阶段依赖图

```
P1 基础设施收口 ──→ P2 协议统一
       │                    │
       └──────→ P3 层边界 ←─┘
                    │
                    ↓
              P4 生命周期与治理
                    │
                    ↓
              全量验证 + 合并
```

- P1 和 P2 可以并行（无直接依赖）
- P3 依赖 P1（UoW 落地后 Service 封装才完整）
- P4 依赖 P3（层边界修复后才能安全调整生命周期行为）
