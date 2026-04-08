# Review Round 3 修复计划

## 概述
- 创建: 2026-04-07
- 分支: refactor/phase4-app-layer-extraction
- 目标: 解决架构审查发现的 5 个问题 + 新发现的 Pyright 诊断

## 技术方案

### 审查结论
大方向正确，需继续收口：
1. ~~CLI 旧路径~~ — **已修复**（create_query_context + facade 收口完成）
2. builders 去查询化 — `_resolution.py` 去重 + 长期查询上提
3. process 大文件拆分 — 提取子模块（认证规则、输入加载、因子正交、auto-init）
4. data.query 死层 — 清理孤儿文件 + 固化唯一路径
5. importlinter 豁免规则 — 收紧至真实边界

### 执行策略
- 每个任务独立可合并，无跨任务依赖
- Task 1-4 按 MEDIUM 优先级排序
- Task 5-6 为 LOW 优先级收尾
- Task 7 顺手修

---

## 任务清单

### Task 1: builders `_resolution.py` 去重 `[S]`
- **问题**: `resolve_tickers` 和 `resolve_display_map` 逻辑近乎相同，都遍历 instrument_ids 调用 `get_instrument`
- **方案**: 合并为单次遍历 `resolve_instrument_display(instrument_ids, metadata_service) -> ResolutionResult`，返回 tickers + id_map + display_map
- **文件**: `packages/app/src/ditto_app/builders/_resolution.py`, `service_factory.py`, `slice_builder.py`
- **验收**: 无重复逻辑，调用方适配，`pixi run -e dev check` 通过
- **测试**: 更新 `_resolution` 相关单元测试

### Task 2: publication_facade.py 认证规则引擎提取 `[M]`
- **问题**: 底部 ~260 行（lines 761-1021）是自包含的认证规则引擎，与 facade 编排无直接关系
- **方案**: 提取到 `packages/app/src/ditto_app/process/certification_rules.py`，包含：
  - `build_certification_checks()` + 所有 `_pub_build_*` 辅助函数（共 ~15 个）
  - `_pub_shadow_report_passed`, `_pub_shadow_report_metric_int`, `_pub_shadow_report_error_count`
- **文件**:
  - 新建 `packages/app/src/ditto_app/process/certification_rules.py`
  - 修改 `packages/app/src/ditto_app/process/publication_facade.py`（删除提取的代码，改为 import）
  - 修改 `packages/app/src/ditto_app/process/__init__.py`（如需 re-export）
- **验收**: `publication_facade.py` 减至 ~760 行，认证规则可独立测试，`pixi run -e dev check` 通过
- **测试**: 认证规则有独立单元测试（从现有测试迁移或新建）

### Task 3: materialization_orchestrator.py 子模块提取 `[M]`
- **问题**: 994 行混合编排 + 输入加载 + 因子正交 + 数据转换 + 依赖解析
- **方案**: 提取 3 个独立模块：
  1. `runtime_input_provider.py` — `RuntimeDerivedInputProvider` 类（lines 630-762, ~133 行）
  2. `factor_orthogonalization.py` — `FactorOrthogonalizationService` 类（lines 886-994, ~109 行）
  3. `materialization_dependencies.py` — 依赖解析辅助函数（`_classify_dependencies`, `_resolve_adj_type`, `_resolve_market_dependency`, `_resolve_etf_dependency`, `_prepare_market_frame`, `_prepare_derived_frame`, `_join_frames`，lines 764-883, ~120 行）
- **文件**:
  - 新建 `packages/app/src/ditto_app/process/runtime_input_provider.py`
  - 新建 `packages/app/src/ditto_app/process/factor_orthogonalization.py`
  - 新建 `packages/app/src/ditto_app/process/materialization_dependencies.py`
  - 修改 `packages/app/src/ditto_app/process/materialization_orchestrator.py`
  - 修改 `packages/app/src/ditto_app/process/__init__.py`
- **验收**: `materialization_orchestrator.py` 减至 ~630 行，每个提取模块可独立测试
- **测试**: 每个提取模块有独立单元测试
- **注意**: `apply_cs_amplification`（lines 558-588）是纯数据转换函数，与依赖解析函数一起归入 `materialization_dependencies.py`

### Task 4: ingestion_coordinator.py 子模块提取 `[M]`
- **问题**: 1,269 行混合编排 + auto-init 规则链 + backfill 逻辑 + fetch dispatch
- **方案**: 提取 2 个子模块：
  1. `auto_init.py` — auto-init 标识符解析链（`_resolve_identifier_with_auto_init`, `_auto_init_stock_instrument`, `_resolve_stock_source_ticker`, `_fetch_and_register_stock`, `_infer_exchange_suffix`，lines 683-830 + line 51, ~150 行）
  2. `backfill_handler.py` — backfill adj_factor 编排（`backfill_adj_factor`, `_detect_adj_factor_gaps`, `_fetch_adj_factor_range`, `_write_adj_factor_range`, `_group_contiguous_dates`，lines 1154-1267, ~115 行）
- **文件**:
  - 新建 `packages/app/src/ditto_app/process/auto_init.py`
  - 新建 `packages/app/src/ditto_app/process/backfill_handler.py`
  - 修改 `packages/app/src/ditto_app/process/ingestion_coordinator.py`
  - 修改 `packages/app/src/ditto_app/process/__init__.py`
- **验收**: `ingestion_coordinator.py` 减至 ~1,000 行，auto-init 和 backfill 可独立测试
- **测试**: 提取模块有独立单元测试

### Task 5: data.query 清理 + 死层固化 `[S]`
- **问题**: `data.query` 只剩 `ServiceBackedDataProvider`（engine Protocol 适配器），旧 querist 已删除但留有孤儿 `.pyc`；app.query 100% 绕过 data.query
- **方案**:
  1. 删除孤儿 `.pyc` 文件：`packages/data/src/ditto_data/query/__pycache__/market.cpython-313.pyc`, `metadata.cpython-313.pyc`
  2. 重命名 `data.query` 为 `data.providers`（更准确反映其职责：engine DataProvider Protocol 实现）
  3. 更新 `data/__init__.py` 导出路径
  4. 更新 `app/providers.py` import 路径
- **文件**:
  - 删除 `packages/data/src/ditto_data/query/__pycache__/*.pyc`
  - 重命名 `packages/data/src/ditto_data/query/` → `packages/data/src/ditto_data/providers/`
  - 修改 `packages/data/src/ditto_data/__init__.py`
  - 修改 `packages/app/src/ditto_app/providers.py`
  - 修改 `.importlinter` 中相关路径（如有）
- **验收**: 无孤儿文件，模块名反映真实职责，`pixi run -e dev check` 通过
- **测试**: 现有 `test_service_backed_provider.py` 路径更新后通过

### Task 6: importlinter 豁免规则收紧 `[M]`
- **问题**: `data-storage-no-model-import` 使用 `** -> **` 通配豁免，绿灯给虚假安全感
- **方案**:
  1. 审计 `ditto_data.storage.** -> ditto_data.models` 的实际 import，列出每个 storage 子模块实际使用的 models 子模块
  2. 将通配豁免替换为具体的 import 路径（如 `ditto_data.storage.market -> ditto_data.models.storage`）
  3. 如果豁免数量 > 15 条，考虑改为分层规则：storage 只能 import `models.storage` + `models.common`
- **文件**:
  - 修改 `.importlinter` 中 `[importlinter:contract:data-storage-no-model-import]` 段
- **验收**: 规则无通配豁免，`pixi run -e dev arch-check` 通过
- **测试**: arch-check 绿灯

### Task 7: Pyright 未使用参数修复 `[S]`
- **问题**: 6 个未使用参数诊断
- **方案**: 逐一分析并修复：
  - `ingestion_coordinator.py:851` — `force` 参数未使用：添加 `_force = force` 消费或删除参数
  - `materialization_orchestrator.py:639` — `data_root` 参数未使用：删除（构造函数不需要）
  - `data_writer.py:403` — `on_duplicate` 参数未使用：传递给下游或删除
  - `data_writer.py:635,657,679` — `trade_date` 参数未使用：确认签名是否需要保留（接口兼容性），加下划线前缀
  - `quality.py:151` — `df` 参数未使用：加下划线前缀或确认是否应该被使用
- **文件**:
  - `packages/app/src/ditto_app/process/ingestion_coordinator.py`
  - `packages/app/src/ditto_app/process/materialization_orchestrator.py`
  - `packages/app/src/ditto_app/process/data_writer.py`
  - `packages/app/src/ditto_app/process/quality.py`
- **验收**: `pixi run -e dev type` 零错误
- **测试**: 现有测试通过

---

## 依赖关系

```
Task 1 (resolution 去重)    ← 独立
Task 2 (认证规则提取)        ← 独立
Task 3 (物化子模块提取)      ← 独立
Task 4 (摄取子模块提取)      ← 独立
Task 5 (data.query 清理)    ← 独立
Task 6 (importlinter 收紧)  ← 独立，建议在 Task 3/4 之后执行（提取后边界更清晰）
Task 7 (Pyright 修复)       ← 独立，可随时执行
```

## 预期效果

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| `publication_facade.py` | 1,021 行 | 751 行 |
| `materialization_orchestrator.py` | 994 行 | 549 行 |
| `ingestion_coordinator.py` | 1,269 行 | ~1,000 行 |
| `_resolution.py` 重复代码 | 2 个近乎相同函数 | 1 个统一函数 |
| `data.query` 模块 | 名不副实 | 重命名为 `data.providers` |
| importlinter 通配豁免 | `** -> **` | 具体路径 |
| Pyright 未使用参数 | 6 个 | 0 个 |

## 执行结果

- **日期**: 2026-04-07
- **状态**: ✅ 全部完成
- **验证**: `pixi run -e dev check` 通过（lint + fmt + type + test + arch-check）
  - basedpyright: 0 errors, 0 warnings
  - ruff: all checks passed
  - 4,395 tests passed, 25 skipped
  - import linter: 22 contracts kept, 0 broken

### 各 Task 执行详情

| Task | 状态 | 关键变更 |
|------|------|----------|
| Task 1 | ✅ | `resolve_instrument_display()` 单次遍历，返回 `ResolutionResult` dataclass |
| Task 2 | ✅ | `certification_rules.py` 新建（~260 行），`publication_facade.py` 1021→751 行 |
| Task 3 | ✅ | 3 个新模块：`runtime_input_provider.py`, `materialization_dependencies.py`, `factor_orthogonalization.py`；编排器 994→549 行 |
| Task 4 | ✅ | 2 个新模块：`auto_init.py`, `backfill_handler.py`；coordinator ~1000 行 |
| Task 5 | ✅ | `data.query` → `data.providers`，2 个孤儿 `.pyc` 已删除 |
| Task 6 | ✅ | 新增 3 条具体 exemption（derived, ingestion, publication_safety） |
| Task 7 | ✅ | 6 个未使用参数已修复（`_force` 删除, `data_root` 删除, `on_duplicate` 删除, `_trade_date` 前缀, `_df` 前缀）|
