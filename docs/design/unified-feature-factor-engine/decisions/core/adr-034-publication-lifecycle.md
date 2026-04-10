# ADR-034: Derived 发布生命周期协议

**状态**: 已决策（2026-03-12）

---

## 背景

因子/特征系统需要明确的发布生命周期管理，确保从开发到生产的可控性、可追溯性和可回滚性。

在最小状态机之外，发布安全还需要回答：

1. candidate 版本如何在不切换 primary 的情况下被验证
2. dual-read diff 如何进入发布判定
3. 最小 DQ 与更高等级认证如何衔接

本 ADR 作为生命周期主协议，吸收 [ADR-042](../research/adr-042-shadow-publish-dual-read-diff-protocol.md) 与 [ADR-043](../research/adr-043-role-profile-certification-compatibility-manifest.md) 的控制面关系。

---

## 状态机设计

### Phase 1 持久化状态

> **代码变更记录（2026-03-20）**：Phase 1 实现时简化了状态机，移除了 `REGISTERED` 状态（validate 检查合并到 materialize 入口），新增了 `ARCHIVED` 状态用于已下线且无可回滚价值的版本。详见 `DerivedVersionStatus`（`packages/analytics/src/ditto_analytics/materialization/models.py`）。

| 状态 | 含义 | 进入条件 |
|------|------|---------|
| **DRAFT** | spec 可编辑，未进入正式生命周期 | 创建时 |
| ~~**REGISTERED**~~ | ~~spec 已冻结入 catalog，可触发物化~~ | *已移除 — validate 检查合并到 materialize 入口* |
| **MATERIALIZED** | 至少存在一份通过基础运行检查的产物/水位 | materialize 成功 |
| **PUBLISHED** | 当前对查询/serving 生效的版本 | promote 操作 |
| **DEPRECATED** | 仍可保留查询或回滚价值，但不再推荐使用 | deprecate 操作 |
| **ARCHIVED** | 已下线且无可回滚价值，仅保留审计记录 | archive 操作 |

#### 设计变更说明

`REGISTERED` 状态在 ADR 原设计中用于"validate 通过后的冻结态"。Phase 1 实现中，validate 检查（表达式语法、复杂度限制）被合并为 materialize 的前置校验，不再作为独立持久化状态。这简化了状态机流转：`DRAFT → MATERIALIZED → PUBLISHED → DEPRECATED → ARCHIVED`。

### 门禁/事件（非持久化状态）

| 事件 | 触发点 | 职责 |
|------|--------|------|
| ~~**validate**~~ | ~~DRAFT → REGISTERED~~ | *已合并到 materialize 前置校验* |
| **shadow_publish** | MATERIALIZED 后 | 将 candidate 挂到 shadow 验证通道，不改 primary |
| **certify** | shadow / promote 前 | 汇总最小 DQ、shadow diff、compatibility manifest 与认证包 |

### 状态转换图

> **代码变更记录（2026-03-20）**：图示已更新为与 `DerivedVersionStatus` 一致。

```
DRAFT ──materialize──> MATERIALIZED ──promote──> PUBLISHED ──deprecate──> DEPRECATED ──archive──> ARCHIVED
                            │                        │
                            ├──shadow_publish──> shadow slot
                            │                        ↓
                            └──────────────────────────────────────> DEPRECATED
```

原始设计中 `DRAFT → REGISTERED → MATERIALIZED` 的两步流转被简化为 `DRAFT → MATERIALIZED` 单步，validate 检查在 materialize 入口完成。

### 辅助发布通道

`shadow_publish` 是辅助发布通道，不新增持久化生命周期状态：

1. candidate 版本在 shadow 期间仍保持 `MATERIALIZED`
2. 当前 primary 不受影响
3. shadow diff / certification 通过后，仍需显式 `promote()`

---

## 多版本并存策略

**决策**：复用 ADR-024 的 `online` + `primary` 指针模型

### 三维控制

| 维度 | 字段 | 职责 |
|------|------|------|
| **生命周期** | `status` | 状态机流转 |
| **可用性** | `online` | 是否对 serving/query 暴露 |
| **默认路由** | `primary` | 默认查询指向哪个版本 |

### 硬性约束

```python
# 规则 1: primary 唯一性
同一 (entity_type, entity_id) 族内，primary=true 只能有一个

# 规则 2: primary 前置条件
primary=true ⟹ online=true ∧ status=PUBLISHED
```

---

## PUBLISHED 状态精确定义

### 核心语义

**PUBLISHED = 已注册 + 已物化 + 已通过最小 DQ + 已通过发布级认证 + 已进入默认查询路由**

### 边界原则

| 原则 | 说明 |
|------|------|
| **MATERIALIZED ≠ PUBLISHED** | 有数据不等于可以对外成为默认版本 |
| **PUBLISHED 不是瞬时事件** | 不是"某次 run 成功"，而是"这个 version 被正式提升为默认版本"的控制面状态 |

### promote 操作前置条件

```python
def promote(version) -> PromotionResult:
    """MATERIALIZED → PUBLISHED：发布上线"""

    # 1. 状态检查
    require version.status == MATERIALIZED

    # 2. 最小 DQ 检查（参考 ADR-036）
    require latest_dq_report.has_errors == False

    # 3. compatibility manifest 完整
    require has_compatibility_manifest(version)

    # 4. 影子验证与认证（参考 ADR-042 / ADR-043）
    require latest_certification(stage="publish_ready").has_errors == False
    require shadow_diff_passed_or_equivalent_audit(version)

    # 5. 元数据完整性
    require has_artifact_metadata(version)  # artifact / partition / watermark / manifest

    # 6. 原子更新
    tx.begin()
    version.status = PUBLISHED
    set_primary(version)  # 同时更新 primary 指针
    tx.commit()
```

### DQ 门禁策略

| 门禁类型 | 阻断行为 | 说明 |
|---------|---------|------|
| **最小 DQ ERROR** | 一律阻断 | 结构性质量问题，见 ADR-036 |
| **shadow diff ERROR** | 阻断发布到 primary | 发布安全问题，见 ADR-042 |
| **publish_ready certification ERROR** | 一律阻断 | role/profile 级认证失败，见 ADR-043 |

### shadow_ready / publish_ready

| 认证阶段 | 用途 | 是否允许直接 promote |
|---------|------|----------------------|
| **shadow_ready** | 允许 candidate 进入 shadow 通道 | 否 |
| **publish_ready** | 允许 candidate promote 到 primary | 是 |

`shadow_ready` / `publish_ready` 是控制面 gate，不是新的持久化生命周期状态。

---

## 回滚/撤销机制

### 两类独立操作

| 操作 | 语义 | 前提条件 | 影响 |
|------|------|---------|------|
| **`deprecate(version)`** | 版本不再推荐使用 | version 当前为 PUBLISHED | 状态 → DEPRECATED，不删数据 |
| **`rollback_primary(target_version)`** | 切换默认查询指针 | target_version 已 PUBLISHED 且非 DEPRECATED | primary 指针移动，无需重新物化 |

### 约束规则

```python
# 规则 1: rollback_primary 是指针操作，不改状态
rollback_primary 只移动 primary 指针，不修改任何版本的 status

# 规则 2: DEPRECATED 不可成为 primary
status=DEPRECATED ⟹ 不能成为 primary=true

# 规则 3: 回滚目标必须是已发布版本
rollback_primary(target) ⟹ target.status == PUBLISHED
```

### 操作示例

```
场景: v2 有问题，需回滚到 v1

操作前:
  v1: status=PUBLISHED, online=true, primary=false
  v2: status=PUBLISHED, online=true, primary=true

执行: rollback_primary(v1)

操作后:
  v1: status=PUBLISHED, online=true, primary=true  ← 指针移动
  v2: status=PUBLISHED, online=true, primary=false ← 状态不变

可选后续: deprecate(v2)
  v2: status=DEPRECATED, online=false, primary=false
```

---

## API 设计（示意）

```python
# 发布服务接口
class PublicationService:
    def materialize(self, spec_id: str, version: int) -> MaterializationResult:
        """DRAFT → MATERIALIZED：验证并执行物化

        前置校验（原 validate 门禁已合并）：
        - 表达式语法与复杂度检查
        - 依赖完整性检查
        """
        ...

    def shadow_publish(self, spec_id: str, version: int) -> ShadowPublishResult:
        """将 MATERIALIZED 版本挂入 shadow 通道，不改变 primary。"""
        ...

    def certify(self, spec_id: str, version: int) -> CertificationResult:
        """汇总最小 DQ、shadow diff 与认证包，产出 shadow_ready/publish_ready 结果。"""
        ...

    def promote(self, spec_id: str, version: int) -> PromotionResult:
        """MATERIALIZED → PUBLISHED：发布上线

        前置条件：
        - version.status == MATERIALIZED
        - latest_dq_report.has_errors == False
        - compatibility manifest 完整
        - publish_ready certification 通过
        - shadow diff 通过或存在等价审计报告
        - has_artifact_metadata(version)

        原子操作：
        - version.status = PUBLISHED
        - primary -> version
        """
        ...

    def deprecate(self, spec_id: str, version: int) -> DeprecationResult:
        """PUBLISHED → DEPRECATED：标记废弃

        前置条件：
        - version.status == PUBLISHED

        操作：
        - version.status = DEPRECATED
        - version.online = False
        - 如果 version.primary == True，需要先 rollback_primary
        """
        ...

    def rollback_primary(self, spec_id: str, target_version: int) -> RollbackResult:
        """回滚 primary 指针到目标版本

        前置条件：
        - target_version.status == PUBLISHED
        - target_version.status ≠ DEPRECATED

        操作：
        - primary -> target_version（指针移动，不改状态）
        """
        ...
```

---

## 与现有 ADR 的关系

| ADR | 关系 |
|-----|------|
| **ADR-024: Factor Versioning** | 复用其 `online` + `primary` 指针模型 |
| **ADR-036: Quality Gates** | 注册/物化/发布各阶段的 DQ 门禁定义 |
| **ADR-042: Shadow Publish** | 扩展：影子发布与 dual-read diff 前置条件 |
| **ADR-043: Certification & Manifest** | 扩展：publish_ready 认证与兼容性契约 |
| **ADR-019: Testing Strategy** | 发布前的测试验收标准 |

---

## 反例：什么不适合放入本 ADR

- ❌ 物化执行细节（属于 ADR-006 增量计算）
- ❌ 具体存储格式（属于 ADR-016 Catalog 存储）
- ❌ 复杂流量切分/平台级金丝雀调度（Phase 2 再评估）
- ❌ 数据删除策略（属于数据生命周期管理）

---

## 决策记录

| 日期 | 决策 |
|------|------|
| 2026-03-12 | 确定状态机设计（5 状态 + 门禁事件） |
| 2026-03-12 | 确定复用 ADR-024 指针模型 |
| 2026-03-12 | 确定回滚机制（deprecate + rollback_primary） |
| 2026-03-12 | 确定 PUBLISHED 精确语义：已注册 + 已物化 + 通过最小 DQ + 原子更新 primary |
| 2026-03-13 | 吸收 ADR-042：shadow publish 不新增生命周期状态，promote 前默认要求 dual-read diff |
| 2026-03-13 | 吸收 ADR-043：promote 前增加 publish_ready 认证与 compatibility manifest 完整性检查 |
| 2026-03-20 | **变更**：Phase 1 实现移除 `REGISTERED` 状态，validate 合并到 materialize 入口；新增 `ARCHIVED` 状态。实际代码见 `DerivedVersionStatus`（`DRAFT → MATERIALIZED → PUBLISHED → DEPRECATED → ARCHIVED`） |
