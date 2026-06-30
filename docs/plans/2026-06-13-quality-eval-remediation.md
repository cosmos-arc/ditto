# 质量评估整改计划 2026-06-13

## 概述

- **来源**: [docs/reviews/2026-06-13-quality-eval.md](../reviews/2026-06-13-quality-eval.md) Top 5 改进项 + D7 因子交叉验证 + O3 追踪补齐
- **创建**: 2026-06-13
- **范围**: 7 个改进方向（A4 / A5 / D7 / O3 / T1 / T10 / 稳定 API 表）
- **不含**: O7 安全、O4 容错、重启 integration CI 等"现在就该补"项的其余部分（用户明确"其他部分先不处理"）
- **基线门禁**: lint/type/test(8197)/arch(37) 当前全绿；整改过程中每步必须保持全绿

## 执行结果（2026-06-14 完成）

全部 5 Phase / 17 任务完成，`pixi run -e dev check` 全绿（lint + fmt + type + test --fast 8245 passed / 1 xfailed + arch 37 合约 + arch-smells 18 项含新增 `__all__` 守护）。

| Phase | 任务 | 结果 |
|-------|------|------|
| 1 | A4 消除生产 TYPE_CHECKING | ✅ source_fallback_policy 改 leaf 路径 + 抽 `_maturity_types.py`（**7 个** DTO，非计划 5 个：含 `DatasetStatus` + `ReadinessReport` 传递依赖 `EffectCount`）；生产 TYPE_CHECKING = 0（字面零匹配） |
| 1 | A5 子模块 `__all__` 覆盖 | ✅ **关键纠正**：原报告"34 个缺 `__all__`"实际未被修复（前期 grep 命令 bug 漏报误判完成），AST 实测确认 34 个真实缺失，全部补齐至 186/186=100%；arch-smells 新增 `check_missing_dunder_all` fitness function（第 18 项检查） |
| 2 | D7 因子交叉验证 | ✅ 39 测试（scalar 9 + cs 7 + ts 10 + 复合 7 + 框架/PIT 反例）+ **发现 cs_rank 截面 bug**（缺 `.over(time_keys)`，xfail 跟踪） |
| 3 | O3 关键路径 @traced | ✅ backtest 1→14（8 step + input_bundle + assemble_result + 4 statistics）+ execution 10→30（reconciliation + broker + orders）+ span 覆盖测试 |
| 4 | T10 长测试拆分 | ✅ test_reconciliation_executor_unit.py 1685 行 → 6 文件（23 test 等价）；SqlEngine 2 skip → xfail；3 个超 500 行 conformance 评估为合理保留 |
| 4 | T1 覆盖率门禁 | ✅ 基线 94.97%（单元），门禁 80→85（实际远超，一步到位） |
| 5 | 稳定 API 表 | ✅ [docs/architecture/public-api-maturity.md](../architecture/public-api-maturity.md)（kernel/features/application 三级标注） |

**遗留/后续**（独立 PR）：
- **cs_rank 截面 bug**：需 codegen 物化 ts 中间结果以消除 polars 嵌套 `.over()` 限制（不同分组键嵌套返回 all-null），xfail 跟踪于 test_expression_cross_section_crosscheck_unit.py。
- **pyarrow 依赖**：duckdb `.pl()` 转 polars 需 pyarrow（CLAUDE.md 白名单未含），SqlEngine integration 测试 xfail 待依赖决策。
- O7 安全 / O4 容错不在本计划范围（用户明确）。

## 技术方案

### A4 消除 4 处生产 TYPE_CHECKING（实为 2 文件 2 块，导入 6 个类型）

根因（已核查确认为**真实双向循环**，非冗余）：
1. `ingestion_status.py:35` 正向导入 `_maturity_governance`（用其函数）→ `_maturity_governance.py:16` 用 TYPE_CHECKING 反向导回 5 个 maturity DTO
2. `catalog.py:61` 正向导入 `source_fallback_policy` → `source_fallback_policy.py:9` 用 TYPE_CHECKING 反向导回 `CatalogSourceHealthReport`

**方案**（最小破坏，保持消费者兼容）：
- **case 2 直接改路径**：`CatalogSourceHealthReport` 已定义在 leaf `catalog_source_health.py:56`，`source_fallback_policy.py` 改为 `from ditto_application.queries.catalog_source_health import CatalogSourceHealthReport`（正向），删除 TYPE_CHECKING 块。
- **case 1 抽 leaf 模块**：新建 `_maturity_types.py`，迁移 5 个 DTO（`DatasetMaturitySummary` / `DatasetPromotionStatusCount` / `DatasetPromotionCriterionCount` / `DatasetPromotionReadinessItem` / `DatasetPromotionReadinessReport`）；`_maturity_governance.py` 正向从 leaf 导入；`ingestion_status.py` 从 leaf 导入并保持同名 re-export（24 处内部引用零改动）。

### A5 子模块 `__all__` 覆盖 81.7% → 100% + fitness function

34 个缺 `__all__` 的 `__init__.py` 分两类处理：
- **空命名空间包（~15 个，0 行）**：补 `__all__: list[str] = []`（显式空表面积，符合 CLAUDE.md「强制消费者直接引用叶模块」）
- **有内容包（~19 个，1-8 行）**：补真实 `__all__` 导出清单
- **守护**：`scripts/architecture/check_architecture_smells.py` 新增 1 项检查——所有 `src/**/__init__.py` 必须定义 `__all__`（root 与 submodule 双覆盖），纳入 CI。

### D7 因子数值交叉验证（全算子含组合）

**核心原则**：参考实现必须**完全独立于 codegen**——用原生 polars API 手写每个算子的等价计算，再与 `compile_expression` 引擎输出做数值对比。现有 `test_cs_scalar_operators_unit.py` 是「引擎自洽测试」（验证引擎产出某 expr），D7 要的是「独立交叉验证」（抓 codegen 的 shift 偏移 / window 边界 / PIT 泄漏）。

**算子清单（26 + 组合）**：
- scalar（9）: `abs` `ceil` `exp` `floor` `log`（一元，在 `_visitor._compile_unary_node`）+ `round` `clip` `if_else` `coalesce`（call）
- cs 截面（7）: `cs_rank` `cs_scale` `cs_zscore` `cs_demean` `cs_winsorize`（sigma/quantile 双模式）+ `group_rank` `group_zscore`
- ts 时序（10）: `ts_delay` `ts_delta` `ts_pct_change` `ts_rank` `ts_argmax` `ts_argmin` `ts_corr` `ts_cov` `ts_ema` `ts_decay_linear`

**PIT 对齐**（关键风险）：ts 算子引擎统一用 `shift(1)` 排除当前行 T（见 [pit.md](.claude/rules/pit.md) 与 `_ts_operators.py` 注释），参考实现必须严格复刻同一 `shift(1)` + window 语义，否则会误报。

### O3 backtest/execution 关键路径补 `@traced`

`@traced(operation)` 已定义于 [tracing.py:152](packages/platform/src/ditto_platform/foundation/observability/tracing.py#L152)，data 层有 100+ 处范例。补齐裸奔的关键路径：
- **backtest**: `engine_steps` 主循环 + `steps/*`（planning / strategy / risk_scan / pre_trade / execution / data_fetch / audit / input_bundle）+ statistics
- **execution**: `reconciliation/{reconciler, executor, repair}` 主路径 + broker gateway + orders lifecycle

**约束**：`@traced` 为纯观测装饰器，不改交易逻辑、不引入副作用；不触及 Kill Switch 路径。

### T1 覆盖率门禁分阶段 82→85

codecov trend 已就位（CI 上传 coverage-unit/integration.xml）。先跑一次获取实际覆盖率基线与 term-missing 薄弱清单 → 借 Phase 2/3 新增测试的自然提升 → 分 `82 → 84 → 85` 三步提升 `--cov-fail-under`，每步补薄弱路径测试至通过。

### T10 长测试拆分 + SqlEngine skip 清理

- `test_reconciliation_executor_unit.py` **1685 行**：按 5 类 mismatch（MISSING/EXTRA/QTY/PRICE/STATUS）+ claim/retry 机制拆为独立文件
- 2 个 `pytestmark = pytest.mark.skip("SqlEngine API changed")`：确认新 API → 更新测试适配 或 转 `xfail(strict=False)` 关联 issue

### 稳定 API 表（最小可行）

新建 `docs/architecture/public-api-maturity.md`：kernel / features / application 三包，按 stable / candidate / internal 三级标注高频 leaf API。纯文档，无自动守护（用户选定最小可行）。

---

## 任务清单

### Phase 1: 架构治理基础（先行，无依赖）

- [ ] Task 1.1: A4 `source_fallback_policy.py` 改 leaf 导入路径消除 TYPE_CHECKING `[S]`
  - 验收: `grep TYPE_CHECKING source_fallback_policy.py` = 0；basedpyright strict 全绿；catalog/source-fallback 功能行为不变
  - 文件: `packages/application/src/ditto_application/queries/source_fallback_policy.py`
  - 测试: 复跑 `source_fallback_policy` 相关现有单测全绿

- [ ] Task 1.2: A4 抽 `_maturity_types.py` leaf 模块消除 `_maturity_governance` TYPE_CHECKING `[M]`
  - 验收: 生产 `grep TYPE_CHECKING` 全仓 = 0；ingestion_status 24 处内部引用零改动（靠同名 re-export）；arch-check + type 全绿
  - 文件: 新建 `packages/application/src/ditto_application/queries/_maturity_types.py`；改 `_maturity_governance.py`、`ingestion_status.py`
  - 测试: maturity governance / ingestion_status 现有单测全绿；新增 1 个 import 边界测试验证无循环
  - 风险: grep 确认无外部消费者直接从 ingestion_status 导入这 5 个 DTO 名（若有，re-export 保持兼容）

- [ ] Task 1.3: A5 补齐 34 个子模块 `__all__` `[M]`
  - 验收: `find packages/*/src -name __init__.py | xargs grep -L __all__` = 空；每个 `__all__` 内容与实际导出一致
  - 文件: 34 个 `__init__.py`（见勘察清单，空包补 `[]`，有内容包补真实导出）
  - 测试: 现有 import 边界测试全绿；无新 import 报错

- [ ] Task 1.4: A5 arch-smells 新增 `__all__` 覆盖率 fitness function `[S]`
  - 验收: `pixi run -e dev arch-check` 含新检查项且通过；删一个 `__all__` 后检查会 fail
  - 文件: `scripts/architecture/check_architecture_smells.py`
  - 测试: 新增 1 个 arch-smells 单测验证守护生效（正/反例）

### Phase 2: 领域正确性 — D7 因子交叉验证

- [ ] Task 2.1: D7 建立独立参考实现框架与对比工具 `[M]`
  - 验收: 产出手写 polars 参考实现的共享 fixture（受控数值数据 + entity/time keys）+ `assert_expr_matches_reference(engine_expr, reference_expr, df)` 对比断言工具（处理 NaN/浮点容差）
  - 文件: 新建 `packages/features/tests/unit/evaluation/_reference_fixtures.py`（或 conftest）
  - 测试: 框架自检（已知算子的 trivial case 通过）

- [ ] Task 2.2: D7 scalar 算子参考实现（9 个）`[M]`
  - 验收: `abs/ceil/exp/floor/log/round/clip/if_else/coalesce` 各有独立 polars 参考并参数化对比通过；覆盖零值/负数/边界
  - 文件: 新建 `packages/features/tests/unit/test_expression_scalar_crosscheck_unit.py`
  - 测试: 该文件即为测试

- [ ] Task 2.3: D7 cs 截面算子参考实现（7 个）`[M]`
  - 验收: `cs_rank/cs_scale/cs_zscore/cs_demean/cs_winsorize`（sigma + quantile 双模式）+ `group_rank/group_zscore` 参数化对比通过；覆盖 NaN/极端值/分组边界
  - 文件: 新建 `packages/features/tests/unit/test_expression_cross_section_crosscheck_unit.py`
  - 测试: 该文件即为测试

- [ ] Task 2.4: D7 ts 时序算子参考实现（10 个）`[PIT 风险 +1]` `[M]`
  - 验收: 10 个 ts 算子独立参考对比通过；**参考实现严格复刻引擎 `shift(1)` PIT 语义**（见 pit.md）；覆盖 window 边界 / min_samples / 多 entity 分组
  - 文件: 新建 `packages/features/tests/unit/test_expression_time_series_crosscheck_unit.py`
  - 测试: 该文件即为测试；必须包含「故意错配 shift」的反例验证参考确实能抓 PIT 泄漏
  - 风险: PIT 数据正确性——参考实现 shift 必须与引擎一致，否则误报

- [ ] Task 2.5: D7 复合表达式组合交叉验证 `[M]`
  - 验收: 嵌套组合（如 `cs_zscore(ts_rank(close, 20))` + `if_else` / `coalesce` 混合）5-8 个场景对比通过
  - 文件: 新建 `packages/features/tests/unit/test_expression_composite_crosscheck_unit.py`
  - 测试: 该文件即为测试

### Phase 3: 可观测性 — O3 追踪补齐

- [ ] Task 3.1: O3 backtest 关键路径补 `@traced` `[M]`
  - 验收: `engine_steps` 主循环 + `steps/*` 8 个步骤 + statistics 关键方法均有 `@traced("backtest.<step>")`；行为不变
  - 文件: `packages/backtest/src/ditto_backtest/engine_steps.py`、`steps/*.py`、`statistics*.py`
  - 测试: 现有 backtest 单测全绿 + 新增 1 个 span 生成断言测试（用 `get_in_memory_exporter`）

- [ ] Task 3.2: O3 execution reconciliation/broker/orders 主路径补 `@traced` `[M]`
  - 验收: `reconcile/plan_repair/execute_report_actions` + broker gateway 关键方法 + orders lifecycle 补 `@traced("execution.<path>")`
  - 文件: `packages/execution/src/ditto_execution/reconciliation/{reconciler,executor,repair}.py`、`broker/*.py`、`orders/*.py`
  - 测试: 现有 execution 单测全绿 + 新增 span 生成断言测试
  - 约束: 不触及 Kill Switch / 交易决策逻辑

- [ ] Task 3.3: O3 trace 覆盖验证 `[S]`
  - 验收: 汇总 backtest/execution 新增 span 命名清单，确认关键链路（run→steps→reconcile→execute）可观测
  - 文件: 测试文件（含于 3.1/3.2）
  - 测试: span 命名规范一致性检查

### Phase 4: 测试质量强化（T10 先于 T1，新测试自然提升覆盖率）

- [ ] Task 4.1: T10 拆分 `test_reconciliation_executor_unit.py`（1685 行）`[L]`
  - 验收: 拆为按 mismatch 类型 + 机制的独立文件（每个 < 500 行）；测试用例总数与断言不丢失；全绿
  - 文件: 拆分 `packages/execution/tests/unit/test_reconciliation_executor_unit.py` → `test_reconciliation_executor_{missing,extra,qty,price,status,claim,retry}_unit.py`
  - 测试: 拆分后用例集合 == 原用例集合（行为等价）

- [ ] Task 4.2: T10 处理 2 个 SqlEngine skip `[S]`
  - 验收: 确认 SqlEngine 新 API → 更新测试适配 或 转 `xfail(strict=False, reason=...)` 关联 issue；不再静默 skip
  - 文件: `packages/data/tests/integration/runtime/test_sql_engine_integration.py`、`test_sql_engine_injection_integration.py`
  - 测试: 处理后状态明确（pass 或 xfail tracked）

- [ ] Task 4.3: T10 评估其余超 500 行 conformance 文件 `[S]`
  - 验收: `test_reconciliation_workflow_store_unit.py`(598) / `test_reconciliation_unit.py`(569) / `test_reconciliation_service_unit.py`(541) 给出拆分建议或标注「合理保留」理由
  - 文件: 上述 3 文件
  - 测试: 若拆分则行为等价

- [ ] Task 4.4: T1 获取覆盖率基线 + 识别薄弱路径 `[S]`
  - 验收: 产出当前实际分支覆盖率值 + term-missing Top 薄弱模块清单
  - 文件: `pixi run -e dev pytest --cov-report=term-missing` 输出归档
  - 测试: 无（度量任务）

- [ ] Task 4.5: T1 分阶段提升门禁 82→84→85 + 补薄弱路径 `[M]`
  - 验收: `--cov-fail-under` 经 82→84→85 三步提升至 85；每步补薄弱路径测试至 CI 通过；codecov trend 持续
  - 文件: `pyproject.toml`（门禁值）+ 薄弱路径补测文件
  - 测试: 门禁提升后 `pixi run -e dev test --unit` 全绿

### Phase 5: 文档治理（独立，可任意时点）

- [ ] Task 5.1: 稳定 API 表（最小文档表）`[S]`
  - 验收: 新建 `docs/architecture/public-api-maturity.md`，覆盖 kernel / features / application 三包高频 leaf API 的 stable / candidate / internal 三级标注
  - 文件: 新建 `docs/architecture/public-api-maturity.md`
  - 测试: 无（纯文档）

---

## 依赖与执行顺序

```
Phase 1 (A4/A5) ──┐
                   ├─→ Phase 4 (T10 ‖ T1)  ← T1 依赖 Phase 2/3 新增测试提升覆盖率
Phase 2 (D7) ──────┤
Phase 3 (O3) ──────┘
Phase 5 (API 表) ─── 独立，任意时点
```

- **Phase 1 先行**：架构基础，无依赖，为后续提供干净基线
- **Phase 2 ‖ Phase 3**：领域 + 可观测，相互独立可并行
- **Phase 4 置后**：T10 拆分先做（释放 conformance 文件），T1 门禁提升**依赖 Phase 2/3 新增的 D7/O3 测试自然抬高覆盖率**，故放最后
- **Phase 5 随时**：纯文档

**推荐执行批次**（每批次一个 PR）：
1. PR1 = Phase 1（A4 + A5，架构治理）
2. PR2 = Phase 2（D7，领域正确性，独立可审查）
3. PR3 = Phase 3（O3，可观测性）
4. PR4 = Phase 4 + Phase 5（测试强化 + 文档）

## 风险与约束

| 风险 | 等级 | 缓解 |
|------|------|------|
| D7 ts 算子参考实现 PIT 误报 | 中 | 参考必须严格复刻引擎 `shift(1)`；含「故意错配」反例验证参考能抓泄漏 |
| A4 抽模块破坏外部消费者 | 低 | ingestion_status 保持 5 个 DTO 同名 re-export；grep 确认无外部直接导入 |
| O3 `@traced` 引入副作用 | 低 | 纯观测装饰器，不改交易逻辑；现有单测回归验证 |
| T1 提门禁破坏 CI | 中 | 分 82→84→85 三步，每步补测至通过；不一步到位 |
| T10 拆分丢失用例 | 低 | 拆分前后用例集合 diff 校验 |

**硬性约束**（CLAUDE.md）：
- 数据操作（D7）→ PIT 处理，`closed="left"` / `shift(1)`
- 交易逻辑（O3 execution 路径）→ 不触及 Kill Switch / 决策逻辑
- 每个任务 → 测试要求（见上）
- 全程禁 pandas / json / TYPE_CHECKING 延迟导入

## 验收门禁（每任务完成前）

```bash
pixi run -e dev check          # lint + fmt + type + test --fast 全绿
pixi run -e dev arch-check     # 37 合约 + arch-smells（含新 __all__ 守护）全绿
```

**分支门禁**: basedpyright / ruff / 测试全通过；分支覆盖率 ≥ 80%（Phase 4 后 ≥ 85%）；生产 TYPE_CHECKING = 0；子模块 `__all__` 覆盖 = 100%。

## 预期成效

整改完成后 `--full` 重评预期：
- 架构 arch: 4.90 → ~4.95（A4 TYPE_CHECKING=0 + A5 `__all__`=100%）
- 领域 domain: 4.10 → ~4.40（D7 因子交叉验证 pass）
- 运维 ops: 3.60 → ~3.80（O3 关键路径 trace 覆盖，⚠️ O7/O4 不在本计划范围故 ops 提升有限）
- 测试 test: 4.50 → ~4.65（T1 门禁 85% + T10 拆分）
- 综合: 4.41 → ~4.50+

> 注: ops 维度因 O7 安全(P0)/O4 容错未纳入本计划，提升空间仍大——如需后续推进需另开计划。
