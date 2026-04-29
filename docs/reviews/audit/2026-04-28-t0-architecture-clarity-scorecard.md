# T0 Architecture Clarity Scorecard

> Date: 2026-04-28
> Plan: `docs/plans/2026-04-28-t0-architecture-clarity-improvement-plan.md`

## Baseline

| Metric | Value | Command |
|---|---:|---|
| Source files | 733 | `find packages interfaces -path '*/src/*' -name '*.py' \| wc -l` |
| Source lines | 97,447 | `find packages interfaces -path '*/src/*' -name '*.py' -print0 \| xargs -0 wc -l \| tail -1` |
| Data source lines | 42,138 | package line count |
| analytics.expression → materialization imports | 2 | `rg materialization.contracts packages/analytics/src/ditto_analytics/expression` |

### Per-Package Metrics

| Package | @traced | Protocols | except Exception |
|---------|--------:|----------:|-----------------:|
| analytics | 0 | 7 | 2 |
| app | 1 | 12 | 21 |
| data | 190 | 37 | 18 |
| engine | 0 | 23 | 1 |
| infra | 2 | 1 | 11 |
| kernel | 0 | 4 | 0 |
| interfaces | 0 | 3 | 18 |

## T0 Gates

| Gate | Before | After | Status |
|---|---|---|---|
| Docs/import-linter model alignment | mismatch | aligned (注释 + boundaries doc Section 14) | ✅ |
| Expression boundary | reversed dependency | clean (contracts.py 提取 + forbidden 合约) | ✅ |
| CQRS storage method purity | partial | guarded (CQRS guard test 覆盖 metadata stores) | ✅ |
| Engine exception taxonomy | root + scattered StateTransitionError | baseline accepted (待 P1/P5 后按需扩展) | ✅ |
| Agent context pack | scattered docs | one fast path (agent-context-pack.md) | ✅ |
| Architecture smell check | none | script + pixi task (arch-smells) | ✅ (new) |

## Final Results

| Verification | Result |
|---|---|
| `pixi run -e dev lint-imports` | 34 contracts kept, 0 broken |
| `pixi run -e dev arch-smells` | 0 issues |
| `pixi run -e dev type` | 0 errors, 0 warnings, 0 notes |
| `pixi run -e dev test --fast` | 5878 passed, 25 skipped |

### Resolved Findings

| ID | Resolution |
|---|---|
| F01 | .importlinter 注释 + boundaries doc Section 14 对齐 diamond 模型说明 |
| F03 | `Exchange` → `SourceExchangeCode` (data 层重命名) |
| F04 | `StrategyRunService` → `StrategyRunLifecycleStore` |
| F05 | CQRS guard test 覆盖 metadata stores，V1 memory test 修复 |
| F06 | 命名词典规则 5：已知缩写保持大写 (ETF/FX/API/SQL/DQ/PIT/HTTP) |
| F07 | expression/contracts.py 提取 + expression→materialization forbidden 合约 |
| F08 | 评估为可接受基线，待 P1/P5 后按需扩展 |
| F09 | engine/analytics 关键路径已添加 @traced（5 个 hot-path entry points） |
| F11 | DQSettings `config_root` 通过 DI 注入，路径解析 CWD-independent |
| F12 | 架构 smell Checker 上线 (f-string logging + missing __init__.py + oversized files) |
| F14 | 4 个 oversized 文件已拆分 |

### T0 Task Execution Summary

| Task | Change | Verified By |
|---|---|---|
| Task 1: Missing `__init__.py` | 补全缺失 `__init__.py`，4 个 oversized 文件拆分 | `arch-smells` 0 issues |
| Task 2: Import-linter alignment | 34 contracts, 0 broken | `lint-imports` 34 kept, 0 broken |
| Task 3: Tracing kernel hook | `kernel.tracing`: `@traced` default no-op, `install_trace_handler()` 注入 handler | `arch-check` passes |
| Task 4: DQ path handling | `config_root` DI 注入，CWD-independent | `test --fast` 5878 passed |
| Task 5: Expression contract ownership | types owned by `expression.contracts`, materialization imports canonical | `lint-imports` expression→materialization forbidden KEPT |
