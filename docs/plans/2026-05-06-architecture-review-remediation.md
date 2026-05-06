# Architecture Review Remediation

## 概述
- 创建: 2026-05-06
- 来源: architecture-refactor 分支 6 维度并行审查
- 范围: 2 Critical + 9 Important + 7 Minor

## 技术方案

审查发现无活跃架构违规（所有依赖边界在运行时均被遵守），问题集中在：
1. **防御层覆盖缺口** — import-linter 和运行时边界测试未覆盖全部禁止依赖
2. **Kernel 桶超标** — 41 个符号超出 30 个限制，需精简
3. **临时文件入库** — .merge-backups/ 不应被 Git 跟踪

修复策略：逐项精确修改，每项独立可验证，不引入新风险。

## 任务清单

### Phase 1: Critical（必须修复）

- [x] Task 1: 清理入库的临时文件 `[S]`
  - 验收: .merge-backups/ 不再被 Git 跟踪；.gitignore 包含覆盖规则
  - 文件: `.merge-backups/`, `.gitignore`
  - 步骤:
    1. `git rm -r .merge-backups/`
    2. `.gitignore` 添加 `.merge-backups/`
    3. 验证 `git status` 无 .merge-backups 文件

- [x] Task 2: 精简 Kernel 桶导出到 ≤30 个 `[M]`
  - 验收: `__all__` ≤ 30；所有消费者已迁移到叶模块导入；`pixi run -e dev check` 通过
  - 文件: `packages/kernel/src/ditto_kernel/__init__.py`
  - 步骤:
    1. 从 `__all__` 移除 11 个低频符号（全部已从叶模块导入，0 处 barrel 导入）:
       - 6 个 publication_safety 记录: `CertificationReportRecord`, `CompatibilityManifestRecord`, `DerivedMinimalDQSummaryRecord`, `ShadowDiffReportRecord`, `ShadowTraceRecordRecord`, `DerivedShadowSlotRecord`
       - 2 个常量映射: `CALENDAR_TO_TIMEZONE`, `GRAIN_TO_TIME_KEYS`
       - 1 个 Protocol: `MacroDataProvider`
       - 1 个枚举: `RunStatus`
       - 1 个根异常（检查后确认应保留）: `DataError`
    2. 从 `__init__.py` 的 import 语句中同步移除这些符号
    3. 最终 `__all__` 应为 30 个（41 - 11）
    4. 运行 `pixi run -e dev check` 验证无破坏

### Phase 2: Important — 防御层补全

- [x] Task 3: 补全 backtest import-linter 契约 `[S]`
  - 验收: `backtest-boundary` 的 forbidden_modules 包含 `ditto_features.**` 和 `ditto_platform.**`
  - 文件: `.importlinter` (L263-273)
  - 步骤:
    1. 在 `backtest-boundary` 的 `forbidden_modules` 添加 `ditto_features.**` 和 `ditto_platform.**`
    2. `pixi run -e dev arch-check` 验证通过

- [x] Task 4: 补全 portfolio 运行时边界测试 `[S]`
  - 验收: forbidden_prefixes 包含 `ditto_data` 和 `ditto_features`
  - 文件: `packages/portfolio/tests/unit/test_portfolio_import_boundary_unit.py`
  - 步骤:
    1. 在 `forbidden_prefixes` 元组中添加 `"ditto_data"`, `"ditto_features"`
    2. `pixi run -e dev test packages/portfolio/tests/unit/test_portfolio_import_boundary_unit.py` 通过

- [x] Task 5: 补全 execution 运行时边界测试 `[S]`
  - 验收: forbidden_prefixes 包含 `ditto_data` 和 `ditto_features`
  - 文件: `packages/execution/tests/unit/test_execution_import_boundary_unit.py`
  - 步骤:
    1. 在 `forbidden_prefixes` 元组中添加 `"ditto_data"`, `"ditto_features"`
    2. `pixi run -e dev test packages/execution/tests/unit/test_execution_import_boundary_unit.py` 通过

- [x] Task 6: 补全 analysis 运行时边界测试 `[S]`
  - 验收: forbidden_prefixes 覆盖 CLAUDE.md 中所有 9 个禁止包
  - 文件: `packages/analysis/tests/unit/test_analysis_import_boundary_unit.py`
  - 步骤:
    1. 在 `forbidden_prefixes` 元组中添加: `"ditto_data"`, `"ditto_features"`, `"ditto_strategy"`, `"ditto_portfolio"`, `"ditto_risk"`
    2. `pixi run -e dev test packages/analysis/tests/unit/test_analysis_import_boundary_unit.py` 通过

- [x] Task 7: 重写 risk 运行时边界测试 `[S]`
  - 验收: 测试包含完整的 forbidden_prefixes，覆盖 CLAUDE.md 中 8 个禁止包
  - 文件: `packages/risk/tests/unit/test_risk_import_boundary_unit.py`
  - 步骤:
    1. 参照其他包的模板重写，添加 `forbidden_prefixes`: `"ditto_data"`, `"ditto_features"`, `"ditto_strategy"`, `"ditto_execution"`, `"ditto_backtest"`, `"ditto_analysis"`, `"ditto_application"`, `"ditto_apps"`
    2. `pixi run -e dev test packages/risk/tests/unit/test_risk_import_boundary_unit.py` 通过

- [x] Task 8: 修正 importlinter Platform 契约名 `[S]`
  - 验收: 契约名准确反映实际约束（Platform 禁止依赖业务层，允许依赖 kernel）
  - 文件: `.importlinter`
  - 步骤:
    1. 将 Platform 契约名从 "must not depend on other layers" 改为 "must not depend on business layers"
    2. 或从 forbidden_modules 中移除 `ditto_kernel`（如果 kernel 不应被禁止）
    3. `pixi run -e dev arch-check` 验证通过

### Phase 3: Important — 其他

- [ ] Task 9: 拆分 data/errors.py `[L]`
  - 验收: errors.py 核心异常 ≤100 行；源特有异常下沉到 sources/ 适配器附近
  - 文件: `packages/data/src/ditto_data/errors.py`, 新文件
  - 步骤:
    1. 将源相关错误（`SourceAuthenticationError`, `SourceRateLimitError`, `SourceTransformationError` 等）移到 `sources/` 子模块
    2. 保留 data 包核心错误在 errors.py
    3. 更新所有导入路径
    4. 测试通过
  - 注: 风险较低但涉及多文件修改，可在后续迭代处理

- [ ] Task 10: 活跃设计文档添加弃用横幅 `[M]`
  - 验收: `docs/design/` 下活跃文档顶部有弃用说明
  - 文件: `docs/design/01_system_design.md` 等活跃文档
  - 步骤:
    1. 在 `docs/design/` 下直接引用旧包名的文档顶部添加横幅
    2. 不修改历史评审/计划文档

## 执行依赖

```
Task 1 (独立) ─┐
Task 2 (独立) ─┤
Task 3 (独立) ─┤─→ Phase 1+2 完成后运行 pixi run -e dev check
Task 4 (独立) ─┤
Task 5 (独立) ─┤
Task 6 (独立) ─┤
Task 7 (独立) ─┤
Task 8 (独立) ─┘
                    ↓
Task 9, 10 可并行
```

## 最终验证

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # 架构边界检查
```
