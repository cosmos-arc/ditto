# Phase 4 代码审查修复（Round 2）

## 概述

- **来源**: 6 维度并行代码审查
- **创建**: 2026-04-06
- **范围**: `refactor/phase4-app-layer-extraction` 分支合并前修复

## 审查摘要

| 维度 | Critical | Important | Suggestion |
|------|----------|-----------|------------|
| 架构 | 0 | 3 | 3 |
| PIT | 0 | 0 | 0 |
| 编码规约 | 2 | 7 | 2 |
| 可维护性 | 0 | 6 | 5 |
| 代码质量 | 0 | 4 | 1 |
| 测试覆盖 | 0 | 1 | 2 |
| **合计** | **2** | **21** | **13** |

## 技术方案

- **C1/C2**: coordinator_factory / retry_manager / backfill_manager 的导入提升到顶层 — 无循环依赖（importlinter 已验证），延迟导入完全多余
- **I1/I2**: `_resolve_tickers` / `_resolve_benchmark` 提取到 `builders/_resolution.py` 共享模块
- **I3**: ingestion_coordinator 的错误处理提取为 `_handle_fetch_error` 私有方法
- **I10**: coordinator_factory 补充单元测试

---

## 任务清单

### Phase 1: Critical 修复（零容忍规则）

- [ ] Task 1: coordinator_factory.py 消除 `# type: ignore` `[S]`
  - 验收: `# type: ignore` 从源码中移除，pyright 通过，`from __future__ import annotations` 保留
  - 文件:
    - `packages/app/src/ditto_app/process/coordinator_factory.py`
  - 方案: 将行 70 的 lazy import 提升到模块顶层（行 33 后），移除行 37/49 的 `# type: ignore`

- [ ] Task 2: retry_manager + backfill_manager 消除 `TYPE_CHECKING` `[S]`
  - 验收: `TYPE_CHECKING` 守卫替换为直接 import，pyright 通过
  - 文件:
    - `packages/app/src/ditto_app/process/retry_manager.py` (行 5, 13-14)
    - `packages/app/src/ditto_app/process/backfill_manager.py` (行 7, 16-17)
  - 方案: 移除 `from typing import TYPE_CHECKING` 和 `if TYPE_CHECKING:` 守卫，改为 `from ditto_app.process.ingestion_coordinator import IngestionCoordinator`

### Phase 2: 代码重复消除

- [ ] Task 3: 提取 `_resolve_tickers` 到共享模块 `[M]`
  - 验收: 3 处重复代码收敛为 1 处实现 + 2 处调用
  - 文件:
    - **新增**: `packages/app/src/ditto_app/builders/_resolution.py`
    - **修改**: `packages/app/src/ditto_app/builders/service_factory.py` (行 158-176)
    - **修改**: `packages/app/src/ditto_app/builders/slice_builder.py` (行 70-88)
    - **修改**: `packages/app/src/ditto_app/process/strategy_types.py` (行 297-317)
  - 方案:
    ```python
    # builders/_resolution.py
    def resolve_tickers(
        instrument_ids: list[int],
        metadata_service: MetadataService,
    ) -> tuple[tuple[str, ...], dict[str, InstrumentId]]: ...

    def resolve_display_map(
        instrument_ids: list[int],
        metadata_service: MetadataService,
    ) -> dict[InstrumentId, str]: ...
    ```
  - 测试: `packages/app/tests/unit/builders/test_resolution_unit.py` — 正常/空列表/无 instrument 场景

- [ ] Task 4: 提取 `_resolve_benchmark` 到共享模块 `[S]`
  - 验收: 2 处重复代码收敛为 1 处实现
  - 文件:
    - **修改**: `packages/app/src/ditto_app/builders/_resolution.py`
    - **修改**: `packages/app/src/ditto_app/builders/service_factory.py` (行 178-195)
    - **修改**: `packages/app/src/ditto_app/builders/slice_builder.py` (行 90-100)
  - 方案:
    ```python
    def resolve_benchmark(
        spec_benchmark: str | None,
        metadata_service: MetadataService,
        source: str,
        as_of: str,
        config_benchmark: InstrumentId | None = None,
    ) -> InstrumentId | None: ...
    ```

- [ ] Task 5: 提取 ingestion_coordinator 错误处理为共享方法 `[M]`
  - 验收: `_try_fetch_data` 和 `_try_fetch_data_by_instrument` 的 try/except 块收敛为 `_handle_fetch_error`
  - 文件:
    - `packages/app/src/ditto_app/process/ingestion_coordinator.py` (行 466-512, 1015-1067)
  - 方案: 提取 `def _handle_fetch_error(self, dataset, trade_date, error) -> SourceFetchError` 方法

### Phase 3: 类型安全

- [ ] Task 6: quality.py `Any` → `DQIssue` `[S]`
  - 验收: `issue: Any` → `issue: DQIssue`，`list[Any]` → `list[DQIssue]`
  - 文件:
    - `packages/app/src/ditto_app/process/quality.py` (行 180, 434)

- [ ] Task 7: S608 `# noqa` 补充安全注释 `[M]`
  - 验收: 所有 S608 noqa 均附带安全说明注释
  - 文件（13 处无注释）:
    - `packages/app/src/ditto_app/query/research.py` (行 249)
    - `packages/data/src/ditto_data/helpers/pit/sql.py` (行 102)
    - `packages/data/src/ditto_data/storage/base/sqlite_store.py` (行 310, 316, 322)
    - `packages/data/src/ditto_data/runtime/instrument_id_allocator.py` (行 45)
    - `packages/data/src/ditto_data/storage/market/index/constituent/constituent_writer.py` (行 113, 164, 176, 252, 257)
    - `packages/data/src/ditto_data/storage/features/technical/technical_indicator_metadata_reader.py` (行 116)
    - `packages/data/src/ditto_data/storage/runtime/derived_sqlite/writer.py` (行 470)

### Phase 4: 测试补充

- [ ] Task 8: coordinator_factory.py 单元测试 `[M]`
  - 验收: 覆盖率 ≥ 80%，覆盖正常路径 + ValueError + FRED 降级
  - 文件:
    - **新增**: `packages/app/tests/unit/process/test_coordinator_factory_unit.py`
  - 测试用例:
    1. 字符串 source_name → Source 枚举 → 创建协调器
    2. Source 枚举直接传入
    3. 无效 source_name 抛出 ValueError
    4. FRED 数据源不可用时降级

### Phase 5: 日志一致性

- [ ] Task 9: f-string 日志调用改为结构化 keyword 形式 `[M]`
  - 验收: 源码中无 `logger.xxx(f"...")` 调用
  - 文件:
    - `packages/app/src/ditto_app/process/ingestion_coordinator.py` (行 293-294, 325)
    - `packages/app/src/ditto_app/process/coordinator_factory.py` (行 94)
    - `packages/app/src/ditto_app/process/data_writer.py` (行 498-499, 553-554)
    - `packages/app/src/ditto_app/process/list_date_inference.py` (行 93-94, 123-124)
  - 方案:
    ```python
    # Before
    logger.warning(f"FRED source not available: {e}")
    # After
    logger.warning("FRED source not available", error=str(e))
    ```

---

## 不修复项（记录原因）

| 项 | 原因 |
|----|------|
| `client: Any, cache: Any` (14 文件) | data 层 storage 重构范围过大，独立处理 |
| `IngestionCoordinator` 1509 行 | 核心编排器复杂度固有，需专项重构 |
| `ResearchDatasetFacade.build()` 110 行 | 功能稳定后考虑拆分 |
| `DerivedSpec` @property | 逻辑极简（查表），可接受 |
| `types.py` re-export | 当前 interfaces 依赖模式需要，暂不调整 |
| `PLR0913` 参数过多 | 编排层参数传递场景多，改为 config 对象是独立重构 |

---

## 验收标准

```bash
pixi run -e dev check  # lint + fmt + type + test --fast 全部通过
```

- [ ] `# type: ignore` 在 app/src 中为 0
- [ ] `TYPE_CHECKING` 在 app/src 中仅用于真正的循环依赖（当前应为 0）
- [ ] `_resolve_tickers` 无重复实现
- [ ] coordinator_factory.py 覆盖率 ≥ 80%
- [ ] S608 noqa 全部附带安全注释
