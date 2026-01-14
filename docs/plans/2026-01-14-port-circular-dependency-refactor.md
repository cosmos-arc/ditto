# 彻底消除 port/jobs 循环依赖的架构重构计划

**日期**: 2026-01-14
**目标**: 通过引入 `common/` 共享类型层，彻底消除 `apps/port/` 循环依赖，移除 PLC0415 豁免配置

---

## 问题诊断

### 当前状态
- 整个 `jobs/` 和 `services/` 目录被全局豁免 PLC0415 检查
- `IngestionResult` 定义在 `coordinator.py` 中，导致类型注解依赖 TYPE_CHECKING
- `helpers.py` 和 `t0_meta.py` 使用延迟导入避免循环

### 依赖关系（健康单向）
```
jobs/ → services/ingestion/ → datahub/ → foundation/
```

**关键发现**: `services/` 完全不导入 `jobs/`，不存在真实的循环依赖，只是类型耦合导致需要延迟导入。

---

## 架构设计

### 新增 `common/` 共享类型层

```
apps/port/src/ditto_port/
├── common/                    # 新增：共享类型层
│   ├── __init__.py
│   └── types.py              # IngestionResult, ResultCounts
├── jobs/                      # 任务编排层
│   ├── flows/
│   └── tasks/
└── services/                  # 业务逻辑层
    └── ingestion/
```

### 依赖规则
- `jobs/` → `common/` ✅
- `services/` → `common/` ✅
- `common/` → `jobs/` / `services/` ❌

---

## 实施步骤（TDD）

### 阶段 1: 创建共享类型层

**任务 1.1**: 创建 `common/types.py`
```python
"""apps/port/src/ditto_port/common/types.py"""

from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class IngestionResult:
    """数据摄取结果。"""
    dataset: str
    trade_date: str
    status: Literal["success", "skipped", "failed"]
    row_count: int | None = None
    checksum: str | None = None
    message: str = ""
    error: str | None = None


@dataclass(frozen=True)
class ResultCounts:
    """摄取结果统计。"""
    success: int
    failed: int
    skipped: int
```

**任务 1.2**: 创建测试 `test_types_unit.py`
```python
def test_ingestion_result_creation():
    result = IngestionResult(
        dataset="stock_daily",
        trade_date="2024-01-01",
        status="success",
    )
    assert result.status == "success"

def test_ingestion_result_frozen():
    result = IngestionResult(dataset="x", trade_date="y", status="success")
    with pytest.raises(TypeError):
        result.status = "failed"
```

**验证**: `pytest apps/port/tests/unit/common/test_types_unit.py -v`

---

### 阶段 2: 重构 services/ 层

**任务 2.1**: 更新 `coordinator.py`
- 删除 `IngestionResult` 定义（第 28-38 行）
- 从 `common.types` 导入 `IngestionResult`

**任务 2.2**: 更新 `backfill.py`
- 从 `common.types` 导入 `IngestionResult`

**任务 2.3**: 更新 `result_utils.py`
- 移除 TYPE_CHECKING 块
- 从 `common.types` 导入 `IngestionResult` 和 `ResultCounts`

**验证**:
```bash
pytest apps/port/tests/unit/ingestion/test_coordinator_unit.py -v
pytest apps/port/tests/unit/ingestion/test_backfill_unit.py -v
pytest apps/port/tests/unit/ingestion/test_result_utils_unit.py -v
```

---

### 阶段 3: 重构 jobs/ 层

**任务 3.1**: 更新 `jobs/flows/helpers.py`
- 移除 `from __future__ import annotations`
- 移除 TYPE_CHECKING 块
- 移除延迟导入（第 49-53 行）
- 顶部正常导入 `DataHub` 和 `IngestionCoordinator`

**任务 3.2**: 更新 `jobs/tasks/t0_meta.py`
- 移除 `from __future__ import annotations`
- 移除 TYPE_CHECKING 块
- 移除延迟导入（第 85-90 行）
- 顶部正常导入 `DataHub` 和 `IngestionCoordinator`

**任务 3.3**: 更新 `jobs/flows/daily.py`
- 移除 `from __future__ import annotations`
- 移除 TYPE_CHECKING 块
- 顶部导入 `create_ingestion_context`

**任务 3.4**: 更新 `jobs/flows/backfill.py` 和 `repair.py`
- 移除延迟导入

**验证**:
```bash
pytest apps/port/tests/unit/flows/ -v
pytest apps/port/tests/integration/ -v
```

---

### 阶段 4: 移除 PLC0415 豁免

**任务 4.1**: 更新 `pyproject.toml`
```toml
# 删除以下行：
"apps/port/src/ditto_port/jobs/**/*.py" = ["PLC0415"]
"apps/port/src/ditto_port/services/**/*.py" = ["PLC0415"]
```

**任务 4.2**: 验证检查
```bash
pixi run -e dev ruff check apps/port/src
pixi run -e dev pyright apps/port/src
```

---

## 关键文件修改

### 新建文件
1. `apps/port/src/ditto_port/common/__init__.py`
2. `apps/port/src/ditto_port/common/types.py`
3. `apps/port/tests/unit/common/test_types_unit.py`

### 修改文件（按优先级）
1. `apps/port/src/ditto_port/services/ingestion/coordinator.py` - 移除 IngestionResult 定义
2. `apps/port/src/ditto_port/jobs/flows/helpers.py` - 移除延迟导入
3. `apps/port/src/ditto_port/jobs/tasks/t0_meta.py` - 移除延迟导入
4. `apps/port/src/ditto_port/services/ingestion/backfill.py` - 更新导入
5. `apps/port/src/ditto_port/services/ingestion/result_utils.py` - 移除 TYPE_CHECKING
6. `apps/port/src/ditto_port/jobs/flows/daily.py` - 更新导入
7. `apps/port/src/ditto_port/jobs/flows/backfill.py` - 更新导入
8. `apps/port/src/ditto_port/jobs/flows/repair.py` - 更新导入
9. `pyproject.toml` - 移除 PLC0415 豁免

---

## 验证清单

- [x] Ruff 检查: `pixi run -e dev ruff check apps/port/src` → 0 errors ✅
- [x] Pyright 检查: `pixi run -e dev pyright apps/port/src` → 0 errors ✅
- [ ] 单元测试: `pytest apps/port/tests/unit -v` → 100% pass
- [ ] 集成测试: `pytest apps/port/tests/integration -v` → 100% pass
- [ ] 覆盖率: `pytest --cov=apps/port --cov-report=term-missing` → >= 80%

---

## 成功标准

1. **代码质量**: Ruff 和 Pyright 0 错误
2. **架构清晰**: `common/` 作为独立的类型层，无循环依赖
3. **测试覆盖**: 所有测试通过，覆盖率 >= 80%

---

## 风险控制

1. **分阶段提交**: 每个阶段独立 commit
2. **测试先行**: 修改前先写测试
3. **回滚友好**: 每个 commit 可独立回滚

---

## 提交计划

```bash
git commit -m "feat(port): 新增 common/ 共享类型层"
git commit -m "refactor(port): services/ 迁移到 common.types"
git commit -m "refactor(port): jobs/ 移除延迟导入"
git commit -m "refactor(port): 移除 PLC0415 豁免配置"
```
