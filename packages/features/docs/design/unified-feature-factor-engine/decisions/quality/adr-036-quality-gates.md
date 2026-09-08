> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# ADR-036: DQ 门禁设计

**状态**: ✅ 已决策（2026-03-12）

---

## 背景

DQ（Data Quality）门禁是因子发布的质量保障机制，用于：
1. 确保发布的数据满足最低质量标准
2. 防止低质量数据流入下游系统
3. 提供可追溯的质量记录

当前问题：
- 无 Schema 校验门禁
- 无空值率阈值
- 无新鲜度检查
- 缺少结构化的门禁判定流程

本 ADR 定义 **最小 DQ 门禁** 设计，即“明显坏数据不能进入候选发布面”的基础层。

更高等级的发布安全认证、shadow diff 判定与 compatibility manifest 契约由 [ADR-042](../research/adr-042-shadow-publish-dual-read-diff-protocol.md) 与 [ADR-043](../research/adr-043-role-profile-certification-compatibility-manifest.md) 承担。

**关联 ADR**：
- 依赖 [ADR-010: Catalog Schema](../adr-010-catalog-schema.md)
- 关联 [ADR-034: 发布生命周期](../core/adr-034-publication-lifecycle.md)

---

## 决策记录

### D-1: 门禁执行阶段

采用**多阶段组合**模式，但阻断点在发布阶段。

| 阶段 | 职责 | 行为 |
|------|------|------|
| **register** | 静态规则（schema/编译） | 不通过即拒绝注册 |
| **materialize** | 运行期 DQ 计算与落库 | 采集，不阻断 |
| **publish/certify 输入** | 最小 DQ 输出 | 作为后续认证层输入，不单独完成全部发布判定 |

**决策理由**：
- P1-7 被定义为"最小发布门禁"，阻断点应是发布
- `null_rate` 和 `freshness` 没有运行结果无法计算
- 发布状态机 `register → materialize → certify → publish` 天然适合在 certify 阶段消费最小 DQ 结果
- 需要每次物化后沉淀质量指标，供发布时汇总

---

### D-2: 门禁类型

| 类型 | 检查项 | 阶段 | 说明 |
|------|--------|------|------|
| **Schema 门禁** | 输出列与定义一致 | register + materialize | 静态 + 运行期双重检查 |
| **空值率门禁** | `null_rate <= threshold` | materialize | 按 role 分层阈值 |
| **新鲜度门禁** | `watermark >= expected` | materialize | 按 `freshness_sla` 判定 |

---

### D-3: 空值率阈值（按 role 分层）

| role | 阈值 | 行为 | P1 落地 |
|------|------|------|---------|
| **feature** | ≤ 1% | ERROR | ✅ |
| **factor** | ≤ 5% | ERROR | ✅ |
| **signal** | 0% | ERROR | 预留 |
| **label** | - | 只告警 | 预留 |

**实现模式**：`role 默认阈值 + spec 可覆写`

```python
# 默认阈值预设
DEFAULT_NULL_RATE_LIMITS: dict[Role, float] = {
    "feature": 0.01,  # 1%
    "factor": 0.05,   # 5%
    "signal": 0.0,    # 0%
    "label": None,    # 不阻断
}


def get_effective_null_rate_limit(spec: DerivedSpec) -> float | None:
    """获取有效的空值率限制"""
    # Spec 级覆写优先
    if spec.null_rate_limit is not None:
        return spec.null_rate_limit
    # 否则使用 role 默认
    return DEFAULT_NULL_RATE_LIMITS.get(spec.role)
```

**关键边界**：
- `null_rate` 分母 = **eligible rows**（排除天然不可用区间）
- 不用"所有理论行"作为分母，否则 label 等角色会被误伤

---

### D-4: 新鲜度门禁

#### 语义定义

| 层级 | 定义 |
|------|------|
| **契约层** | `freshness_sla = "T+N"`（spec 可配置） |
| **P1 默认** | T+1（即 `watermark >= T-1`） |
| **判定方式** | 按 `spec.calendar` 交易日计算，不是自然日 |

#### 判定逻辑

```python
def check_freshness(
    spec: DerivedSpec,
    actual_watermark: date,
    check_date: date,
    calendar: TradingCalendar,
) -> FreshnessResult:
    """检查新鲜度"""
    # 解析 SLA：T+N -> N
    allowed_lag_days = parse_freshness_sla(spec.freshness_sla)  # "T+1" -> 1

    # 计算期望的 watermark（按交易日）
    expected_watermark = calendar.shift(check_date, -allowed_lag_days)

    passed = actual_watermark >= expected_watermark

    return FreshnessResult(
        passed=passed,
        allowed_lag_days=allowed_lag_days,
        expected_watermark=expected_watermark,
        actual_watermark=actual_watermark,
    )
```

#### P1 默认值

| role | 默认 SLA |
|------|---------|
| feature | T+1 |
| factor | T+1 |
| signal | T+1 |
| label | 预留 |

---

### D-5: 门禁失败处理

采用 **severity 驱动**的发布门禁。

| severity | 行为 | 产物处理 |
|----------|------|---------|
| **ERROR** | 阻断发布 | 保留用于排查，标记 `materialized but uncertified` |
| **WARNING** | 允许发布 | 必须留痕（run/partition/发布事件） |
| **INFO** | 仅记录 | 不影响发布 |

#### 失败处理流程

```
1. materialize 后立即跑 DQ，产出 DQReport

2. 如果有 ERROR：
   ├─ run 保留
   ├─ artifact 保留用于排查
   ├─ 状态标记为 materialized but uncertified
   └─ 不允许进入 published

3. 如果只有 WARNING/INFO：
   ├─ 可以进入后续认证/发布流程
   └─ 告警写入 run/partition 记录和发布事件
```

**关键点**：
- 失败不是"删除运行结果"
- 而是"允许计算完成，但不允许拿它当发布结果"
- 对排障和复现实用得多

---

### D-6: Override 策略

| 约束 | 决策 |
|------|------|
| **P1 通用 force publish** | ❌ 不提供 |
| **Schema ERROR override** | ❌ 永远不能 |
| **Null-rate ERROR override** | ❌ P1 默认不能 |
| **Freshness WARNING** | ✅ 本来就允许发布但留痕 |

**未来扩展（P2 可选）**：
- 受审计的人工 override
- 强制记录：`reason` + `operator` + `expires_at` + `ticket/reference`

---

### D-7: validation_policy 字段语义

仓库已有 `validation_policy` 字段，定义：

| 值 | 语义 |
|---|------|
| `strict` | 按上述规则执行 |
| `lenient` | 只影响 WARNING 处理方式（如是否要求显式确认），**不能绕过 ERROR** |

**关键约束**：`lenient` 不能把 ERROR 变没，否则门禁会被架空。

---

### D-8: 数据模型

#### DQReport

```python
from dataclasses import dataclass, field
from datetime import date
from typing import Literal


Severity = Literal["ERROR", "WARNING", "INFO"]


@dataclass
class DQCheckResult:
    """单个检查项结果"""
    check_name: str           # "schema_check" / "null_rate" / "freshness"
    severity: Severity
    passed: bool
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class DQReport:
    """DQ 检查报告"""
    spec_id: str
    spec_version: int
    run_id: str
    check_date: date

    # 检查结果
    results: list[DQCheckResult]

    # 汇总
    has_error: bool = False
    has_warning: bool = False

    # 元数据
    computed_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """序列化为 dict（用于存储）"""
        return {
            "spec_id": self.spec_id,
            "spec_version": self.spec_version,
            "run_id": self.run_id,
            "check_date": self.check_date.isoformat(),
            "results": [
                {
                    "check_name": r.check_name,
                    "severity": r.severity,
                    "passed": r.passed,
                    "message": r.message,
                    "details": r.details,
                }
                for r in self.results
            ],
            "has_error": self.has_error,
            "has_warning": self.has_warning,
            "computed_at": self.computed_at.isoformat(),
        }
```

---

### D-9: 本 ADR 只定义最小 DQ，不覆盖认证层

| 维度 | 本 ADR（最小 DQ） | ADR-043（认证层） |
|------|------------------|------------------|
| **目标** | 阻断明显坏数据 | 判断 candidate 是否达到 shadow/publish 安全标准 |
| **检查项** | schema / null-rate / freshness | parity / coverage / drift / latency / fallback / snapshot consistency |
| **输入** | 物化输出与 watermark | 最小 DQ + shadow diff + compatibility manifest |
| **stage** | `register` / `materialize` | `shadow_ready` / `publish_ready` |

**边界原则**：

1. 不把 distribution drift、shadow parity、fallback ratio 等发布安全检查重新塞回最小 DQ。
2. 最小 DQ 失败时，认证层无需继续。
3. 认证层通过也不能覆盖最小 DQ 的 `ERROR`。

---

## 决策汇总

| 决策点 | 决策 |
|-------|------|
| **执行阶段** | 多阶段组合：register（静态）→ materialize（采集）→ certify/publish 输入 |
| **门禁类型** | Schema + 空值率 + 新鲜度 |
| **空值率阈值** | 按 role 分层：feature 1% / factor 5% / signal 0% / label 只告警 |
| **新鲜度语义** | `freshness_sla = "T+N"`，P1 默认 T+1 |
| **失败处理** | ERROR 阻断但保留产物，WARNING 允许但留痕 |
| **Override** | P1 不提供通用 force publish |
| **职责边界** | 本 ADR 只定义最小 DQ；认证层见 ADR-043 |

---

## 与其他 ADR 的关系

| ADR | 关系 |
|-----|------|
| [ADR-010](../adr-010-catalog-schema.md) | 依赖：`validation_policy`、`freshness_sla` 字段 |
| [ADR-034](../core/adr-034-publication-lifecycle.md) | 被依赖：最小 DQ 是 certify / promote 的前置输入 |
| [ADR-042](../research/adr-042-shadow-publish-dual-read-diff-protocol.md) | 后续阶段消费最小 DQ 结果，进入 shadow compare |
| [ADR-043](../research/adr-043-role-profile-certification-compatibility-manifest.md) | 在最小 DQ 之上叠加更高等级认证 |

---

## 实现清单

### 新增文件

| 文件路径 | 用途 |
|---------|------|
| `packages/engine/src/ditto_engine/engine/gates/__init__.py` | 门禁模块入口 |
| `packages/engine/src/ditto_engine/engine/gates/checkers.py` | 检查器实现 |
| `packages/engine/src/ditto_engine/engine/gates/report.py` | DQReport 模型 |

### 修改文件

| 文件路径 | 修改内容 |
|---------|---------|
| `packages/engine/src/ditto_engine/engine/specs.py` | 增加 `null_rate_limit` 字段 |
| `packages/data/src/ditto_data/stores/catalog/schema.py` | 增加 DQ 相关字段 |

---

## 更新记录

### 2026-03-12
- 初始版本
- 定义三阶段门禁执行模型
- 定义按 role 分层的空值率阈值
- 定义 T+N 新鲜度语义
- 定义 severity 驱动的失败处理

### 2026-03-13
- 明确本 ADR 只定义最小 DQ，不覆盖 role/profile 认证层
- 与 ADR-042 / ADR-043 建立控制面分层关系
