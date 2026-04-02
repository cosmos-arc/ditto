---
date: 2026-04-01
plan_type: refactor
status: active
origin: docs/plans/2026-03-31-hybrid-plane-v2-migration-plan.md
depth: deep
last_audit: 2026-04-01
---

# Phase 3: Analytics 收尾 + DataHub 域模型清理（3 Unit）

**目标**：收窄 datahub 职责边界，将散落的域模型迁移到正确的归属包，清理 deprecated 代码。
**前置**：Phase 2 已完成（4228 tests ✅, 11/11 arch-check ✅）
**验收**：每个 PR 后 `pixi run -e dev check` 全通过 + arch-check 全通过。

## 设计决策

1. **trading.py 整体删除** — Order/OrderStatus 已 deprecated，Trade 零业务消费者
2. **portfolio.py 整体删除** — Position/Portfolio 零业务消费者，engine.portfolio 有独立实现
3. **strategy.py 保持不动** — 存储记录模型留在 datahub 合理
4. **factors/features → analytics** — FactorMetadata/IndicatorMetadata 归属 analytics 域
5. **research → analytics** — Spine/Dataset Spec/Snapshot Record 归属 analytics 域
6. **允许 datahub → analytics** — 存储层引用领域类型合理，不禁止
7. **Strangler 模式** — 先建新路径 + re-export 兼容层，再逐步迁移消费者，最后删除旧路径

## 最终依赖图变化

```
变更前:
  analytics → engine.specs + engine.errors（单向）
  datahub → (无 analytics 依赖)

变更后:
  analytics → engine.specs + engine.errors（不变）
  datahub → analytics.models（新增：research records 的存储消费者）
  analytics 包内新增 models/ 子包
```

## PR 结构（3 个 PR）

---

### PR 3a: 清理 deprecated 模型（trading.py + portfolio.py）

**目标**：删除已废弃的域模型，收窄 datahub 职责边界。

#### Step 1: 删除 trading.py

| 操作 | 文件 | 说明 |
|------|------|------|
| DELETE | `packages/data/src/ditto_data/models/trading.py` | 整个文件（113 行） |
| DELETE | `packages/data/tests/unit/models/test_trading_models.py` | 专用测试文件 |

**消费者分析**（已确认）：
- `Order` / `OrderStatus` — 已 deprecated，指向 `ditto_engine.accounting.order_book`
- `Trade` — 零业务消费者，仅 test_trading_models.py 自测
- `models/__init__.py` — re-export `Order, OrderStatus, Trade`

#### Step 2: 删除 portfolio.py

| 操作 | 文件 | 说明 |
|------|------|------|
| DELETE | `packages/data/src/ditto_data/models/portfolio.py` | 整个文件（74 行） |

**消费者分析**（已确认）：
- `Position` / `Portfolio` — 零业务消费者
- `models/__init__.py` — re-export `Portfolio, Position`
- engine.portfolio 有独立、完整的 allocation/constraints/comparison 实现，不冲突

#### Step 3: 更新 models/__init__.py

从 `packages/data/src/ditto_data/models/__init__.py` 中移除：
- `from ditto_data.models.trading import Order, OrderStatus, Trade` 行
- `from ditto_data.models.portfolio import Portfolio, Position` 行
- `__all__` 中移除：`"Order"`, `"OrderStatus"`, `"Trade"`, `"Portfolio"`, `"Position"`

**验证**：`pixi run -e dev check` + `grep -rn "from ditto_data.models.trading\|from ditto_data.models.portfolio" packages/ apps/ tests/ --include="*.py"` 返回 0

---

### PR 3b: factors + features 迁入 ditto_analytics

**目标**：将因子/指标元数据类型迁入 analytics 域，建立 re-export 兼容层。

#### Step 1: 创建 analytics/models/ 子包

| 操作 | 文件 |
|------|------|
| CREATE | `packages/analytics/src/ditto_analytics/models/__init__.py` |
| CREATE | `packages/analytics/src/ditto_analytics/models/factors.py` |
| CREATE | `packages/analytics/src/ditto_analytics/models/features.py` |
| CREATE | `packages/analytics/tests/unit/models/__init__.py` |

#### Step 2: 迁移 factors.py

复制 `packages/data/src/ditto_data/models/factors.py` → `packages/analytics/src/ditto_analytics/models/factors.py`

**无需修改** — factors.py 零外部导入（仅 `dataclasses` + `typing`）。

#### Step 3: 迁移 features.py

复制 `packages/data/src/ditto_data/models/features.py` → `packages/analytics/src/ditto_analytics/models/features.py`

**无需修改** — features.py 零外部导入（仅 `dataclasses` + `typing`）。

#### Step 4: 转换 datahub 原文件为 re-export shim

`packages/data/src/ditto_data/models/factors.py` 改为：
```python
from ditto_analytics.models.factors import *  # noqa: F401,F403
from ditto_analytics.models.factors import __all__  # noqa: F401
```

`packages/data/src/ditto_data/models/features.py` 改为：
```python
from ditto_analytics.models.features import *  # noqa: F401,F403
from ditto_analytics.models.features import __all__  # noqa: F401
```

#### Step 5: 更新包配置

| 文件 | 变更 |
|------|------|
| `packages/data/pyproject.toml` | deps 添加 `ditto-analytics`（re-export 兼容需要） |

#### Step 6: 更新 .importlinter

- 更新 `datahub-boundary`：forbidden 列表中**不需要**添加 `ditto_analytics.**`（因为我们允许 datahub → analytics）
- 无需新增 contract

**验证**：`pixi run -e dev check` 全通过（re-export 兼容，消费者零改动）

---

### PR 3c: research 迁入 ditto_analytics + 消费者迁移

**目标**：将 research 域类型迁入 analytics，更新所有消费者。

#### Step 1: 迁移 research.py

复制 `packages/data/src/ditto_data/models/research.py` → `packages/analytics/src/ditto_analytics/models/research.py`

**无需修改** — research.py 零外部导入（仅 `dataclasses`）。

#### Step 2: 更新 analytics/models/__init__.py

导出所有 research 模型：
```python
from ditto_analytics.models.research import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)
```

#### Step 3: 更新 research 消费者（9 文件）

所有 `from ditto_data.models.research import ...` → `from ditto_analytics.models.research import ...`：

| 文件 | 类型 |
|------|------|
| `packages/data/src/ditto_data/models/__init__.py` | re-export |
| `packages/data/src/ditto_data/services/research_catalog_service.py` | service |
| `packages/data/src/ditto_data/stores/runtime/research_sqlite/reader.py` | store |
| `packages/data/src/ditto_data/stores/runtime/research_sqlite/writer.py` | store |
| `packages/data/tests/unit/stores/runtime/research_sqlite/test_research_catalog_store_unit.py` | test |
| `apps/port/src/ditto_port/services/derived/research.py` | port service |
| `apps/port/tests/unit/services/derived/test_research_dataset_facade_unit.py` | port test |
| `apps/port/tests/integration/flows/test_research_dataset_integration.py` | e2e test |

#### Step 4: 删除 datahub 原文件 + 更新 __init__.py

| 操作 | 文件 |
|------|------|
| DELETE | `packages/data/src/ditto_data/models/research.py` |
| EDIT | `packages/data/src/ditto_data/models/__init__.py` — 移除 research import + __all__ 条目 |

#### Step 5: 更新 .importlinter

无需修改 — `datahub-boundary` 当前 forbidden `ditto_engine.**` 和 `ditto_port.**`，不包含 `ditto_analytics.**`。
`analytics-no-datahub-import` 仅约束 `analytics → datahub` 方向，不影响 `datahub → analytics`。

#### Step 6: 更新 datahub README

检查 `packages/data/README.md` 中是否有 research 相关引用需要更新。

**验证**：
- `pixi run -e dev check`
- `grep -rn "from ditto_data.models.research" packages/ apps/ tests/ --include="*.py"` 返回 0

---

## .importlinter 变更总结

| Contract | 变更 |
|----------|------|
| `analytics-no-datahub-import` | 不变 |
| `datahub-boundary` | 不变（不禁止 datahub → analytics） |
| 无新增 contract | datahub → analytics 是合法依赖方向 |

## 风险缓解

| 风险 | 缓解 |
|------|------|
| research.py 消费者遗漏 | grep 验证 + type check + test |
| re-export shim 遗留 | PR 3c 直接删除 shim，不保留 |
| datahub → analytics 循环 | analytics 已有 no-datahub-import 规则，datahub → analytics 单向安全 |
| 测试计数回归 | 每个 PR 后 `pixi run -e dev test` |

## 验证清单

每个 PR 完成后：
- [ ] `pixi run -e dev check` — lint + type + test 全通过
- [ ] `pixi run -e dev arch-check` — 11/11 contracts KEPT
- [ ] 对应 grep 验证返回 0
- [ ] 测试计数不下降
