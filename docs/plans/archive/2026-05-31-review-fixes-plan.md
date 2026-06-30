# Review Fixes — PR#66 审查修复计划

## 概述
- 创建: 2026-05-31
- 完成: 2026-05-31
- 分支: `dev/architecture-remediation-batch2-6`
- 来源: 6 维度并行审查 + 5 代理 code review 发现
- 状态: ✅ **全部完成** — 22/22 任务实施完毕

## 修复统计
- **Critical**: 1 → 0 需修（S608 已验证为误报）
- **Important**: 15
- **Suggestion**: 18（合并去重后 16 独立项）
- **总计**: 31 原子任务 → 22 实施任务（去重合并后）

## 验证结果
- **Lint**: All checks passed ✅
- **Type**: 0 errors, 0 warnings, 0 notes ✅
- **Tests**: 7594 passed, 25 skipped ✅
- **Architecture**: 37 contracts kept, 0 broken ✅

## 技术方案

### 关键决策
1. **RuntimeKernel 统一**: 在 kernel 提取参数化 `_BaseRuntimeKernel`，Backtest/Paper 各自继承并配置 Clock + mode
2. **data_store.py API**: 删除顶层便利属性，全部委托到 `paths.*`
3. **Mutable globals**: 统一使用 `functools.cache` 替代 `global` + `_cached_*` 模式

---

## Phase 1: 文档更新 [Critical]

### T1: 更新 11 个包级 CLAUDE.md `[M]`
- 验收: 目录树反映当前源码，API 成熟度表无事实错误
- 文件:
  - `packages/data/CLAUDE.md` — 修正 DataCatalog 成熟度表（"无具体实现" → "InMemoryDataCatalog 已实现"），新增 `catalog/` 子包
  - `packages/features/CLAUDE.md` — codegen 拆为 5 文件，新增 hypothesis.py，IC 拆分，新增 _report_builder.py
  - `packages/execution/CLAUDE.md` — 新增 sqlite_journal、broker/runtime、errors、OrderPreSubmitCheck
  - `packages/strategy/CLAUDE.md` — 新增 composite.py (CompositeDecisionStage + FusionMethod)
  - `packages/risk/CLAUDE.md` — 新增 kill_switch.py (KillSwitchLevel/KillSwitchDecision)
  - `packages/platform/CLAUDE.md` — 新增 _path_resolver.py、_xdg_paths.py
  - `packages/application/CLAUDE.md` — 新增 backtest_audit.py
  - `packages/backtest/CLAUDE.md` — 新增 runtime.py (BacktestRuntimeKernel)
  - `packages/apps/CLAUDE.md` — 新增 test_golden_e2e.py 集成测试
  - `packages/analysis/CLAUDE.md` — 更新 research/ 子模块拆分
  - `packages/portfolio/CLAUDE.md` — 新增 WeightAllocator、Constraint Protocol

### T2: 创建 CHANGELOG.md `[S]`
- 验收: 包含 PR#66 所有 API 变更条目
- 文件: `CHANGELOG.md`（新建）

---

## Phase 2: 架构修复 [Important]

### T3: data_store.py 删除旧 API `[L]`
- 验收: 顶层便利属性全部删除，所有调用点改为 `settings.paths.market.*` 形式，`pixi run -e dev type` 通过
- 文件:
  - `packages/data/src/ditto_data/config/data_store.py`
  - 所有调用 data_store 便利属性的文件（需 Grep 确认范围）
- 风险: 破坏性 API 变更，需全面搜索调用点

### T4: RuntimeKernel 统一 `[L]`
- 验收: kernel 提供 `_BaseRuntimeKernel` 参数化基类，backtest/execution 各自 < 30 行
- 文件:
  - `packages/kernel/src/ditto_kernel/runtime.py` — 新增 `_BaseRuntimeKernel`
  - `packages/backtest/src/ditto_backtest/runtime.py` — 继承基类
  - `packages/execution/src/ditto_execution/broker/runtime.py` — 继承基类
  - 对应测试文件更新
- 设计:
  ```python
  @dataclass(slots=True)
  class _BaseRuntimeKernel:
      _clock: Clock
      _event_bus: EventBus
      _mode: str
      _lifecycle: RuntimeLifecycle = field(default_factory=RuntimeLifecycle)
      # ... shared transition_to, snapshot, etc.
  ```

### T5: Mutable globals → functools.cache `[M]`
- 验收: 无 `global` 关键字，无 `PLW0603` noqa，缓存行为不变
- 文件:
  - `packages/data/src/ditto_data/catalog/metadata.py` — `_cached_metadata` → `@cache`
  - `packages/application/src/ditto_application/processes/ingestion/dataset_registry.py` — `_cached_registry` → `@cache`

---

## Phase 3: 可维护性修复 [Important]

### T6: dataset_registry.py 声明提取 `[M]`
- 验收: `default_dataset_registry()` < 30 行，各域子列表为模块常量
- 文件: `packages/application/src/ditto_application/processes/ingestion/dataset_registry.py`
- 设计: 提取 `_METADATA_REGISTRATIONS`、`_MARKET_REGISTRATIONS`、`_CAPITAL_REGISTRATIONS` 等

### T7: ResearchDatasetFacade.build() 拆分 `[M]`
- 验收: `build()` < 70 行，嵌套 ≤ 3
- 文件:
  - `packages/application/src/ditto_application/queries/research.py`
  - 提取 `_resolve_derived_inputs()` 方法
  - 提取 `_persist_artifact_snapshot()` 共享 helper（消除 `_build_spine_snapshot` + `_write_dataset_snapshot` 重复）

### T8: records.py from_row() 简化 `[S]`
- 验收: `from_row()` < 50 行，JSON 反序列化提取为通用 helper
- 文件: `packages/analysis/src/ditto_analysis/research/records.py`
- 设计: 提取 `_deserialize_json_field(raw, fallback_factory)`

---

## Phase 4: 质量修复 [Important]

### T9: _xdg_paths.py 清理 `[S]`
- 验收: runtime_dir 嵌套 ≤ 3，无冗余 XDG_RUNTIME_DIR 检查
- 文件: `packages/platform/src/ditto_platform/foundation/config/_xdg_paths.py`

### T10: paper.py nesting 降低 `[S]`
- 验收: submit_order 嵌套 ≤ 3
- 文件: `packages/execution/src/ditto_execution/broker/gateways/paper.py`
- 设计: 提取 `_validate_buying_power()` 私有方法

---

## Phase 5: 规约修复 [S]

### T11: composite.py 添加 future annotations `[S]`
- 验收: 文件首行为 `from __future__ import annotations`
- 文件: `packages/strategy/src/ditto_strategy/alpha/builtins/composite.py`

### T12: 添加缺失的 __all__ `[S]`
- 验收: 所有公共模块有 `__all__`
- 文件:
  - `packages/analysis/src/ditto_analysis/research/experience.py`
  - `packages/features/src/ditto_features/evaluation/evaluator/_report_builder.py`

### T13: 私有模块添加 __all__（低优先级） `[S]`
- 文件:
  - `packages/features/src/ditto_features/expression/codegen/_ts_operators.py`
  - `packages/features/src/ditto_features/expression/codegen/_cs_operators.py`
  - `packages/features/src/ditto_features/expression/codegen/_scalar_operators.py`
  - `packages/features/src/ditto_features/expression/codegen/_helpers.py`

### T14: 修复测试文件名拼写错误 `[S]`
- 验收: 文件名 `test_codegen_helpers_unit.py`
- 文件: `packages/features/tests/unit/test_codege_helpers_unit.py` → 重命名

### T15: 修复误导注释 `[S]`
- 验收: "并行独立执行" → "独立执行"
- 文件: `packages/strategy/src/ditto_strategy/alpha/builtins/composite.py:121`

### T16: domain.py private re-exports 清理 `[S]`
- 验收: `__all__` 中无不带下划线的公共名，或函数去掉下划线前缀
- 文件: `packages/analysis/src/ditto_analysis/research/domain.py`

### T17: InMemoryDataCatalog conformance 测试 `[S]`
- 验收: 测试包含 `assert isinstance(InMemoryDataCatalog(), DataCatalogReader)`
- 文件: `packages/data/tests/unit/catalog/test_store_unit.py`

---

## Phase 6: 文档补充 [S]

### T18: 添加缺失的 __init__ docstrings `[S]`
- 文件:
  - `packages/execution/src/ditto_execution/broker/gateways/paper.py` — PaperBrokerGateway.__init__
  - `packages/execution/src/ditto_execution/broker/runtime.py` — PaperRuntimeKernel.__init__
  - `packages/backtest/src/ditto_backtest/runtime.py` — BacktestRuntimeKernel.__init__
  - `packages/analysis/src/ditto_analysis/research/experience.py` — MarkdownExperienceMemory.__init__
  - `packages/data/src/ditto_data/catalog/store.py` — InMemoryDataCatalog.__init__

### T19: 添加缺失的函数 docstrings `[S]`
- 文件:
  - `packages/features/src/ditto_features/expression/codegen/_builders.py` — compile_call

### T20: README 版本更新 `[S]`
- 文件: `README.md`

---

## Phase 7: 建议项 [S]

### T21: Magic numbers 提取为常量 `[S]`
- 文件:
  - `packages/analysis/src/ditto_analysis/research/experience.py` — `_SUMMARY_RECENT_COUNT = 5`
  - `packages/features/src/ditto_features/expression/codegen/_cs_operators.py` — `_DEFAULT_WINSORIZE_SIGMA = 3`
  - `packages/features/src/ditto_features/evaluation/metrics/ic_computation.py` — `_DEFAULT_IC_DECAY_LAGS = [1, 2, 3, 5, 10, 20]`

### T22: PIT 观察项标注 `[S]`
- 文件:
  - `packages/features/src/ditto_features/evaluation/metrics/ic_computation.py` — `maintain_order=True` 旁加注释说明脆弱依赖
  - `packages/data/src/ditto_data/sources/tushare/processors/mappings/capital.py` — pledge ratio knowledge_date 注释说明

---

## 执行顺序与依赖

```
Phase 1 (文档) ─────────────────────────────────┐
  T1, T2 (可并行)                                │
                                                  │
Phase 2 (架构) ─────────────────────────────────┤
  T4 (RuntimeKernel) → 无前置                    │
  T3 (data_store) → 无前置                       │
  T5 (cache) → 无前置                            │
                                                  │
Phase 3 (可维护性) ────────────────────────────┤
  T6, T7, T8 → 可并行                            │
                                                  │
Phase 4 (质量) ─────────────────────────────────┤
  T9, T10 → 可并行                               │
                                                  │
Phase 5 (规约) ─────────────────────────────────┤
  T11-T17 → 可并行                               │
                                                  │
Phase 6 (文档补充) ────────────────────────────┤
  T18-T20 → 可并行                               │
                                                  │
Phase 7 (建议) ─────────────────────────────────┤
  T21, T22 → 可并行                              │
                                                  ▼
                                          验证: pixi run -e dev check
```

## 预估复杂度

| Phase | 任务 | 复杂度 | 文件数 | 预估 LOC |
|-------|------|--------|--------|----------|
| 1 | T1-T2 | S-M | 13 | ~500 |
| 2 | T3-T5 | L | ~15 | ~400 |
| 3 | T6-T8 | M | 4 | ~200 |
| 4 | T9-T10 | S | 2 | ~50 |
| 5 | T11-T17 | S | ~10 | ~100 |
| 6 | T18-T20 | S | ~7 | ~80 |
| 7 | T21-T22 | S | 3 | ~30 |
| **Total** | **22** | — | **~54** | **~1,360** |

## 验证命令

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # 架构边界检查
```
