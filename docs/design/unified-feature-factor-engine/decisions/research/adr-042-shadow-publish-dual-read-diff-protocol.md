# ADR-042: Shadow Publish 与 Dual-Read Diff 协议

**状态**: 已决策（2026-03-13）

---

## 背景

[ADR-034](../core/adr-034-publication-lifecycle.md) 已定义最小发布生命周期：`register -> materialize -> promote`。这条主线足以支持”能发布”，但还不足以支持”敢发布”，主要缺口包括：

1. **缺少上线前影子验证路径**
   当前候选版本只能在 `MATERIALIZED` 与 `PUBLISHED` 之间二选一，缺少“先接少量流量/审计流量验证”的正式步骤。

2. **缺少新旧版本双读对拍机制**
   对同一请求上下文，目前没有统一协议去同时读取 candidate 与 baseline，并生成结构化差异报告。

3. **最小 DQ 不能覆盖发布安全**
   Schema / null-rate / freshness 能阻断明显坏数据，但无法回答“新版本与当前 primary 是否行为一致、覆盖是否下降、延迟是否恶化”。

本 ADR 定义 shadow publish、dual-read compare、trace / diff report 与 promote 之间的正式关系。

---

## 决策记录

### D-1: Shadow publish 是辅助发布通道，不新增生命周期状态

**决策**：shadow publish 不引入新的持久化生命周期状态，candidate 版本在 shadow 期间仍保持 `MATERIALIZED`；shadow 只作为控制面上的辅助发布通道。

| 维度 | 决策 |
|------|------|
| **生命周期状态** | 仍使用 ADR-034 的 `DRAFT / REGISTERED / MATERIALIZED / PUBLISHED / DEPRECATED` |
| **shadow 语义** | `MATERIALIZED` 版本可被挂到 shadow serving slot，但不变成 primary |
| **primary 影响** | 当前 primary 完全不受影响 |
| **并发约束** | 同一 `(entity_type, entity_id)` 族内最多允许一个 active shadow candidate |

**决策理由**：

1. 避免把生命周期状态机扩成“状态爆炸”。
2. shadow 更像“候选版本的受控暴露方式”，而不是一个新的业务状态。
3. 保持 `promote()` 仍是唯一改变默认路由的原子操作。

---

### D-2: dual-read compare 必须在同一请求上下文下同时读取 candidate 与 baseline

双读对拍的最小比较单元是“同一请求上下文”：

- 相同 `derived_id`
- 相同 `entity_keys`
- 相同 `asof` / `sample_time`
- 相同 `runtime mode`
- 相同查询方法（`latest` / `series` / `compare_source slice`）

**baseline 选择规则**：

1. 默认 baseline = 当前 `primary` 版本。
2. 如果不存在 primary，可显式指定一个已发布版本作为 baseline。
3. `OFFLINE` profile 没有在线 shadow 路由时，允许退化为计划任务驱动的样本对拍。

**默认比较维度**：

| 维度 | SERIES | STATE | DERIVE | OFFLINE |
|------|--------|-------|--------|---------|
| **value parity** | 必需 | 必需 | 必需 | 抽样必需 |
| **coverage / miss ratio** | 必需 | 必需 | 必需 | 必需 |
| **freshness / stale ratio** | 必需 | 必需 | 可选 | 可选 |
| **latency regression** | 必需 | 必需 | 必需 | 非主项 |
| **fallback ratio** | - | - | 必需 | - |
| **cross-source consistency** | 可选 | 可选 | 必需 | 可选 |

---

### D-3: shadow compare 产出 `DiffReport` 与 `TraceReport` 两类结果

**聚合层**：`ShadowDiffReport`

用于 gate / certification / promote 判断，至少包含：

| 字段 | 说明 |
|------|------|
| `candidate_version` / `baseline_version` | 对拍双方 |
| `request_count` / `sample_count` | 对拍样本规模 |
| `schema_match` | 输出 schema 是否一致 |
| `value_diff_rate` | 值不一致比例 |
| `coverage_delta` | 覆盖率变化 |
| `freshness_delta` | 新鲜度变化 |
| `latency_p50_delta` / `latency_p95_delta` | 延迟变化 |
| `fallback_ratio_delta` | DERIVE profile fallback 变化 |
| `severity_summary` | ERROR / WARNING / INFO 汇总 |

**明细层**：`ShadowTraceReport`

用于排查与解释，至少保留：

- 请求上下文
- candidate / baseline 返回值
- 差异分类
- 相关 manifest / version / watermark
- 采样时间

**原则**：

1. `DiffReport` 负责 gate，`TraceReport` 负责可解释性。
2. `TraceReport` 允许采样保留，不要求保存每一条成功一致记录。
3. `DiffReport` 必须引用当次 candidate / baseline 的 compatibility manifest。

---

### D-4: promote 到 primary 前，SERIES / STATE / DERIVE 默认要求 shadow diff 通过

| profile | 是否默认要求 shadow diff | 说明 |
|--------|-------------------------|------|
| **SERIES** | 是 | 直接影响 serving / series 查询 |
| **STATE** | 是 | 直接影响 latest snapshot 与盘中状态 |
| **DERIVE** | 是 | 需要验证 fallback / latency / cross-source 行为 |
| **OFFLINE** | 否 | 无在线 shadow 路由时可用样本审计替代 |

**promote 前置条件补充**：

1. 通过 ADR-036 的最小 DQ。
2. 存在最近一次有效 `ShadowDiffReport` 或等价审计报告。
3. `ShadowDiffReport` 不含阻断级 `ERROR`。
4. 通过 ADR-043 的 certification pack。

这意味着：

- `MATERIALIZED` 不再等于“随时可 promote”
- `PUBLISHED` 仍然只在显式 promote 时发生
- shadow 只是上线前验证，不改变 primary 指针

---

### D-5: shadow failure 不影响当前 primary，回滚仍复用现有 primary 指针模型

如果 shadow compare 失败：

1. candidate 版本保持 `MATERIALIZED`。
2. 当前 primary 保持不变。
3. shadow slot 可以被禁用、替换或重跑。
4. 失败报告与 trace 保留供排查。

如果 candidate 已 promote，回滚仍遵循 ADR-034：

- 通过 `rollback_primary(target_version)` 切回旧 primary
- 不要求重新物化旧版本

**关键边界**：

1. shadow failure 不是数据删除动作。
2. shadow pass 也不自动等于 promote，需要显式人工/流程决策。
3. 旧 primary 在新版本 promote 后仍是首选 rollback 目标。

---

## 决策汇总

| 决策点 | 决策 |
|-------|------|
| **shadow 定位** | 辅助发布通道，不新增生命周期状态 |
| **对拍上下文** | candidate / baseline 必须在同一请求上下文下双读 |
| **报告模型** | 同时产出 `DiffReport`（聚合）与 `TraceReport`（排查） |
| **promote 前置** | SERIES / STATE / DERIVE 默认要求 shadow diff 通过 |
| **失败语义** | candidate 保持 `MATERIALIZED`，primary 不受影响 |

---

## 与现有 ADR 的关系

| ADR | 关系 |
|-----|------|
| [ADR-034](../core/adr-034-publication-lifecycle.md) | 扩展其 promote 前置条件与发布安全路径 |
| [ADR-036](../quality/adr-036-quality-gates.md) | 最小 DQ 是 shadow / certification 的前置基础 |
| [ADR-037](../quality/adr-037-performance-slo.md) | dual-read compare 复用其 latency / regression 观测语义 |
| [ADR-040](../storage/adr-040-hot-cold-retention-state-namespace-policy.md) | DERIVE / STATE 的 shadow 行为受热层与冷层边界约束 |
| [ADR-043](adr-043-role-profile-certification-compatibility-manifest.md) | `DiffReport` 结果进入 certification pack 判断 |

---

## 实现清单

### 文档回写

| 文件路径 | 修改内容 |
|---------|---------|
| `docs/design/unified-feature-factor-engine/decisions/core/adr-034-publication-lifecycle.md` | 增补 shadow publish 与 promote 前置条件 |
| `docs/design/unified-feature-factor-engine/main-design.md` | 增加发布安全与 dual-read diff 段落 |

### 实现落点

| 模块 | 修改内容 |
|------|---------|
| `packages/core` | `ShadowDiffReport` / `ShadowTraceReport` / compare 规则模型 |
| `packages/data` | dual-read compare 执行器、shadow 报告持久化 |
| `packages/port` | shadow publish / compare / promote orchestration facade |

---

## 更新记录

### 2026-03-13
- 初始版本
- 定义 shadow publish 不新增生命周期状态
- 定义 dual-read compare 的上下文与报告模型
- 定义 SERIES / STATE / DERIVE promote 默认要求 shadow diff
- 固定 shadow failure 不影响当前 primary
