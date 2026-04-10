# ADR-043: Role/Profile Certification 与 Compatibility Manifest

**状态**: 已决策（2026-03-13）

---

## 背景

[ADR-036](../quality/adr-036-quality-gates.md) 已定义最小 DQ 门禁，但它主要解决的是”明显坏数据不能发布”，仍然不足以支撑更高安全等级的发布与回放：

1. **不同 role / materialization_profile 需要不同验证重点**
   `feature`、`factor`、`STATE`、`DERIVE` 的风险形态并不相同，不能继续只靠 schema / null-rate / freshness。

2. **shadow compare 需要正式接入发布判定**
   [ADR-042](adr-042-shadow-publish-dual-read-diff-protocol.md) 已定义对拍协议，但还需要正式的 certification pack 把 diff、coverage、latency 等结果收敛进可执行 gate。

3. **回放与审计需要更强的环境可解释性**
   当前 `compiler_fingerprint` 更偏缓存正确性，而不是“这个版本为何能或不能与另一个版本直接比较/回放”的发布兼容契约。

本 ADR 将 certification pack 与 compatibility manifest 上升为正式控制面能力。

---

## 决策记录

### D-1: 在最小 DQ 之上增加 `CertificationPack`

**决策**：发布判定分为两层：

1. **最小 DQ 层**：沿用 ADR-036，解决“能否进入候选发布面”
2. **认证层**：通过 `CertificationPack` 解决“是否达到 shadow / publish 安全标准”

`CertificationPack` 至少包含：

| 字段 | 说明 |
|------|------|
| `pack_id` | 认证包 ID |
| `role` | `feature` / `factor` / `signal` / `label` |
| `materialization_profile` | `SERIES` / `STATE` / `DERIVE` / `OFFLINE` |
| `stage` | `shadow_ready` / `publish_ready` |
| `checks` | 认证项定义 |
| `result_summary` | ERROR / WARNING / INFO 汇总 |

**边界**：

1. `CertificationPack` 不替代 ADR-036，而是建立在其之上。
2. `shadow_ready` 与 `publish_ready` 可以复用部分检查项，但阈值与阻断等级允许不同。
3. P1 仍不提供通用 `force publish`。

---

### D-2: 认证项采用“role 基础包 + profile 增补包”

#### role 基础包

| role | 默认认证重点 |
|------|-------------|
| **feature** | parity、join coverage、freshness、serving readiness |
| **factor** | coverage、distribution stability、exposure stability、freshness |
| **signal** | 预留，偏 precision / decision safety |
| **label** | 预留，偏 leakage / horizon consistency |

#### profile 增补包

| profile | 默认增补认证项 |
|---------|---------------|
| **SERIES** | shadow parity、online latency、serving completeness |
| **STATE** | snapshot consistency、rebuild lag、stale budget |
| **DERIVE** | query latency、fallback ratio、cross-source consistency |
| **OFFLINE** | dataset reproducibility、snapshot manifest completeness |

**组合规则**：

1. 最终认证包 = `role 基础包 ∪ profile 增补包`。
2. 同一检查项若同时出现在两侧，以更严格阈值为准。
3. 未显式定义的 role / profile 组合，至少继承最小 DQ 与 manifest 完整性检查。

---

### D-3: certification stage 采用两级 gate

| stage | 默认用途 | 最低要求 |
|------|---------|---------|
| **shadow_ready** | 允许 candidate 进入 shadow 路由 | 最小 DQ 通过 + compatibility manifest 完整 + shadow 必需检查无 ERROR |
| **publish_ready** | 允许 candidate promote 到 primary | `shadow_ready` 通过 + publish 级检查无 ERROR + ADR-042 diff 通过 |

**处理原则**：

1. `ERROR` 阻断当前 stage。
2. `WARNING` 允许继续，但必须落库、可追溯，并纳入发布事件。
3. `INFO` 仅记录。

这意味着 `publish_ready` 是一个高于最小 DQ 的正式 gate，而不是“再跑一次同样的检查”。

---

### D-4: Compatibility Manifest 作为发布与回放的环境契约

每个版本化 artifact、shadow compare、dataset snapshot 都必须携带一份 `CompatibilityManifest`。

**必填字段**：

| 字段 | 说明 |
|------|------|
| `engine_codegen_version` | 代码生成器版本 |
| `analysis_version` | 静态分析规则版本 |
| `polars_version` | 执行引擎版本 |
| `expr_serialization_format` | 表达式序列化格式 |
| `operator_fingerprint` | 算子语义指纹聚合 |
| `global_compile_flags` | 全局编译开关 |
| `calendar_id` / `timezone` | 时间语义环境 |
| `time_semantics_version` | `event_time / availability_time / known_at` 语义版本 |

**推荐附加字段**：

- `python_version`
- `platform`
- `builder_version`
- `manifest_hash`

**关键原则**：

1. manifest 的首要目标是 **可解释与可回放**，不是缓存命中。
2. compare / certification 必须同时记录 candidate 与 baseline 的 manifest。
3. promote 不要求 candidate manifest 与 baseline 完全相同，但要求差异可见、字段完整、可审计。

---

### D-5: certification 必须显式消费 shadow diff 与 compatibility manifest

`CertificationPack` 的检查源至少来自三类输入：

1. **最小 DQ 报告**（ADR-036）
2. **ShadowDiffReport / TraceReport**（ADR-042）
3. **CompatibilityManifest**

因此默认判定流程为：

```
materialize
  -> minimal DQ
  -> compatibility manifest completeness check
  -> shadow publish / dual-read diff
  -> role/profile certification
  -> promote
```

**阻断样例**：

- manifest 缺字段
- feature 的 join coverage 明显下降
- factor 的分布漂移超过阈值
- STATE 的 rebuild lag 超预算
- DERIVE 的 fallback ratio / query latency 明显恶化

---

## 决策汇总

| 决策点 | 决策 |
|-------|------|
| **认证模型** | 在 ADR-036 之上新增 `CertificationPack` |
| **组合方式** | `role 基础包 + profile 增补包` |
| **认证阶段** | `shadow_ready` 与 `publish_ready` 两级 gate |
| **兼容契约** | 每个 artifact / compare / snapshot 都必须带 `CompatibilityManifest` |
| **输入来源** | certification 必须消费最小 DQ、shadow diff 与 manifest |

---

## 与现有 ADR 的关系

| ADR | 关系 |
|-----|------|
| [ADR-034](../core/adr-034-publication-lifecycle.md) | 扩展其 publish 前 gate，形成正式 certification 阶段 |
| [ADR-036](../quality/adr-036-quality-gates.md) | 继承最小 DQ，向更高安全等级扩展 |
| [ADR-039](../computation/adr-039-expression-cache-persistence.md) | 吸收其 `compiler_fingerprint` 思路，但上升为发布兼容契约 |
| [ADR-041](adr-041-research-dataset-spine-availability-contract.md) | `DatasetSnapshot` 必须携带 compatibility manifest |
| [ADR-042](adr-042-shadow-publish-dual-read-diff-protocol.md) | shadow diff 结果进入 certification pack |

---

## 实现清单

### 文档回写

| 文件路径 | 修改内容 |
|---------|---------|
| `docs/design/unified-feature-factor-engine/decisions/core/adr-034-publication-lifecycle.md` | 接入 `shadow_ready` / `publish_ready` 认证阶段 |
| `docs/design/unified-feature-factor-engine/decisions/quality/adr-036-quality-gates.md` | 明确”最小 DQ”与”认证层”分层 |
| `docs/design/unified-feature-factor-engine/decisions/computation/adr-039-expression-cache-persistence.md` | 区分缓存指纹与发布兼容 manifest |

### 实现落点

| 模块 | 修改内容 |
|------|---------|
| `packages/kernel` | `CertificationPack`、`CertificationReport`、`CompatibilityManifest` 模型 |
| `packages/data` | 认证结果与 manifest 持久化 |
| `packages/port` | publish orchestration 中接入认证阶段 |

---

## 更新记录

### 2026-03-13
- 初始版本
- 定义 `CertificationPack` 与两级认证 gate
- 定义 `role 基础包 + profile 增补包` 模型
- 定义 `CompatibilityManifest` 为发布与回放环境契约
- 固定 certification 必须消费最小 DQ、shadow diff 与 manifest
