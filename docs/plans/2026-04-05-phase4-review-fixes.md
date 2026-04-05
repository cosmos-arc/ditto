# Phase 4 代码审查修复计划

> **状态: COMPLETED** (2026-04-05)
>
> Phase 1-7 全部完成。最终验证：basedpyright 0 errors，4781 tests passed，22 arch contracts kept。

## 概述
- **来源**: 6 维度并行代码审查（架构/PIT/规约/可维护/质量/文档/测试）
- **范围**: `refactor/phase4-app-layer-extraction` 分支 (e9661da..cc3c44f)
- **问题**: 3 Critical + 15 Important，全部修复
- **策略**: 7 Phase，按依赖/风险排序，每 Phase 独立可提交

## 技术方案

### 依赖关系图
```
Phase 1 (C1, C2) ─── Critical 安全/类型修复，无依赖
    │
Phase 2 (I1, I4, I5, I7) ─── 依赖声明 + 类型修复，I4 依赖 C1
    │
Phase 3 (C3) ─── 查询门面测试，依赖 C1 的 SQL 防注入
    │
Phase 4 (I6, I8) ─── 参数分组 + 长方法重构
    │
Phase 5 (I11, I15) ─── 测试迁移 + 新测试
    │
Phase 6 (I9, I10) ─── 大文件拆分（依赖 Phase 5 的测试验证）
    │
Phase 7 (I2, I3, I12, I13) ─── 导入耦合 + 文档（依赖 Phase 6 路径稳定）
```

---

## 任务清单

### Phase 1: Critical Bug Fixes [S]

#### Task 1.1: SQL 注入修复 — research.py `_export_sqlite` [S]
- **验收**: 恶意 dataset_id（如 `"; DROP TABLE --`）抛 ValueError；正常 ID 不受影响；测试通过
- **文件**: `packages/app/src/ditto_app/query/research.py`
- **方案**:
  1. 添加 `_sanitize_table_name()` 辅助函数，用正则 `^[A-Za-z_][A-Za-z0-9_]*$` 校验
  2. 替换 `table_name = dataset_id.replace("-", "_")` 为 `_sanitize_table_name(dataset_id)`
  3. 两处 f-string SQL 加 `# noqa: S608  # table_name validated by _sanitize_table_name`

#### Task 1.2: `Any` → 具体类型 — quality.py [S]
- **验收**: basedpyright 零新错误；测试通过
- **文件**: `packages/app/src/ditto_app/process/quality.py`
- **方案**:
  - Line 144: `result: Any` → `result: DQResult`（已导入 line 13）
  - Line 492: `engine: Any` → `engine: QualityEngine`（已导入 line 11）

---

### Phase 2: 依赖声明 + 类型修复 [M]

#### Task 2.1: engine pyproject.toml 添加 ditto-data 依赖 [S]
- **验收**: `lint-imports` 通过；engine 测试通过
- **文件**: `packages/engine/pyproject.toml`
- **方案**: `dependencies` 添加 `"ditto-data"`

#### Task 2.2: deploy.py 消除 type:ignore [S]
- **验收**: basedpyright 零错误；deploy 测试通过
- **文件**: `interfaces/src/ditto_interfaces/jobs/flows/deploy.py`
- **方案**: 用 `cast(Flow[Any, Any], ...)` 替换 3 处 `# type: ignore[return-value]`

#### Task 2.3: engine TYPE_CHECKING 添加说明注释 [S]
- **验收**: 注释说明 TYPE_CHECKING 的必要性；无功能变更
- **文件**: `packages/engine/src/ditto_engine/risk/post_trade.py`
- **方案**: 在 `if TYPE_CHECKING:` 块添加注释，解释 risk→backtest 仅类型标注，运行时无循环

---

### Phase 3: 查询门面测试 [M]

#### Task 3.1: DerivedQueryFacade 单元测试 [S]
- **验收**: 测试 delegation + error handling；遵循现有 MagicMock(spec=[...]) 模式
- **文件**: 新建 `packages/app/tests/unit/query/test_derived_query_facade_unit.py`
- **参考**: `packages/app/tests/unit/query/test_capital_query_facade_unit.py`

#### Task 3.2: FactorEvaluationFacade 单元测试 [S]
- **验收**: 同上
- **文件**: 新建 `packages/app/tests/unit/query/test_evaluation_facade_unit.py`

#### Task 3.3: ResearchDatasetFacade 单元测试 + SQL 注入测试 [M]
- **验收**: 覆盖 export()/build() delegation + 恶意 dataset_id 抛 ValueError
- **文件**: 新建 `packages/app/tests/unit/query/test_research_facade_unit.py`

---

### Phase 4: 参数分组 + 长方法重构 [L]

#### Task 4.1: IngestionCoordinatorConfig dataclass 提取 [M]
- **验收**: 移除 `# noqa: PLR0913`；调用方更新；测试通过
- **文件**: `packages/app/src/ditto_app/process/ingestion.py` + 调用方
- **方案**: 提取 `IngestionCoordinatorConfig` dataclass，将 5 个可选参数合并为 1 个 config 参数

#### Task 4.2: quality.py 长方法拆分 [M]
- **验收**: 每个方法 < 50 行；无行为变更；测试通过
- **文件**: `packages/app/src/ditto_app/process/quality.py`
- **方案**: `check_dataset()` 提取 `_fetch_check_data()/_compute_thresholds()/_format_result()`；`daily_reconciliation()` 提取 `_convert_tickers()/_apply_golden_filter()/_execute_comparison()`

#### Task 4.3: research.py build() + _write_dataset_snapshot() 重构 [M]
- **验收**: build() < 60 行；无重复元数据构建；测试通过
- **文件**: `packages/app/src/ditto_app/query/research.py`
- **方案**: 提取 `_resolve_derived_versions()/_join_derived_frames()/_build_snapshot_metadata()`

#### Task 4.4: ingestion.py PLR0911 修复 [S]
- **验收**: 移除 `# noqa: PLR0911`；测试通过
- **文件**: `packages/app/src/ditto_app/process/ingestion.py`
- **方案**: 数据集类型→处理函数的 dict 分发模式

---

### Phase 5: 测试迁移 + 新测试 [XL → 拆 5 子任务]

#### Task 5.1: 迁移 ingestion 测试（13 文件）→ packages/app/tests/unit/process/ingestion/ [L]
- **验收**: 13 文件在新位置通过；无 ditto_interfaces 导入
- **方案**: Copy → 更新 import → 验证 → 保留原文件待 Phase 6 后清理

#### Task 5.2: 迁移 quality 测试（4 文件）→ packages/app/tests/unit/process/quality/ [M]

#### Task 5.3: 迁移 strategy 测试（10 文件）→ packages/app/tests/unit/process/strategy/ [L]

#### Task 5.4: 迁移 derived/materialization 测试（12 文件）→ process/materialization/ + query/ [L]

#### Task 5.5: builders/strategy.py 新测试 [M]
- **文件**: 新建 `packages/app/tests/unit/builders/test_strategy_builder_unit.py`

---

### Phase 6: 大文件拆分 [XL → 拆 4 子任务]

#### Task 6.1: 拆分 ingestion.py（3290 行 → 6 文件）[XL]
- **方案**:
  | 新文件 | 内容 | ~行数 |
  |--------|------|-------|
  | `ingestion_config.py` | `IngestionConfig`, `IngestionCoordinatorConfig` | ~80 |
  | `metadata_manager.py` | `MetadataManager`, 辅助函数 | ~280 |
  | `data_writer.py` | `IngestionDataWriter`, 行业辅助 | ~900 |
  | `list_date_inference.py` | `ListDateInferenceService` | ~250 |
  | `result_handler.py` | `IngestionResultHandler`, 计数工具 | ~500 |
  | `coordinator.py` | `IngestionCoordinator`, `BackfillManager`, `RetryManager`, `create_coordinator` | ~1500 |
- **向后兼容**: `ingestion.py` → re-export shim
- **验收**: 每文件 < 1000 行；旧 import 路径仍可用；`lint-imports` 通过

#### Task 6.2: 拆分 materialization.py（3011 行 → 5 文件）[XL]
- **方案**: `materialization_types.py` / `materialization_helpers.py` / `publication_facade.py` / `cascade_orchestrator.py` / `materialization_orchestrator.py` + re-export shim

#### Task 6.3: 拆分 strategy.py（1247 行 → 3 文件）[L]
- **方案**: `strategy_types.py` / `backtest_service.py` / `strategy_run_service.py` + re-export shim

#### Task 6.4: 拆分 builders/strategy.py（1003 行 → 3 文件）[L]
- **方案**: `runtime_builder.py` / `slice_builder.py` / `service_factory.py` + re-export shim

---

### Phase 7: 导入耦合 + 文档 [L]

#### Task 7.1: types.py 评估 — 添加设计决策注释 [S]
- **验收**: 注释说明 re-export 的设计意图；无代码变更
- **文件**: `packages/app/src/ditto_app/types.py`
- **决策**: 保留 re-export 模式（集中 app 层公共 API 表面）

#### Task 7.2: interfaces/models/__init__.py 减少耦合 [M]
- **验收**: 移除 `from ditto_app.types` 导入；调用方改为直接从 `ditto_data.*` 导入
- **文件**: `interfaces/src/ditto_interfaces/models/__init__.py` + 调用方

#### Task 7.3: docs/ 旧包名批量更新 [L]
- **验收**: 活跃文档无旧包名；archive/ 不改
- **方案**: `ditto_kernel` → `ditto_kernel`，`ditto_interfaces` → `ditto_interfaces`，`ditto_data` → `ditto_data`

#### Task 7.4: 更新 app/CLAUDE.md + Phase 4 计划状态 [S]
- **文件**: `packages/app/CLAUDE.md`, Phase 4 设计文档
- **方案**: 添加 `backtest_serialization.py` 到 CQRS 列表；更新状态表

---

## 关键文件索引

| 文件 | 涉及任务 |
|------|----------|
| `packages/app/src/ditto_app/query/research.py` | C1, I4, I8(4.3) |
| `packages/app/src/ditto_app/process/quality.py` | C2, I8(4.2) |
| `packages/app/src/ditto_app/process/ingestion.py` | I6(4.1, 4.4), I10(6.1) |
| `packages/app/src/ditto_app/process/materialization.py` | I10(6.2) |
| `packages/app/src/ditto_app/process/strategy.py` | I9(6.3) |
| `packages/app/src/ditto_app/builders/strategy.py` | I9(6.4) |
| `packages/engine/pyproject.toml` | I1(2.1) |
| `packages/engine/src/ditto_engine/risk/post_trade.py` | I7(2.3) |
| `interfaces/src/ditto_interfaces/jobs/flows/deploy.py` | I5(2.2) |
| `interfaces/src/ditto_interfaces/models/__init__.py` | I3(7.2) |
| `packages/app/src/ditto_app/types.py` | I2(7.1) |

## 验证方案

每 Phase 完成后运行：
```bash
pixi run -e dev check    # lint + fmt + type + test --fast
pixi run -e dev ci       # CI 完整检查（Phase 6+ 需要）
```

Phase 6 文件拆分额外验证：
- `from ditto_app.process.ingestion import IngestionCoordinator` 仍可用
- `lint-imports` 22 个合约全部通过
- 迁移测试在新位置全部通过
