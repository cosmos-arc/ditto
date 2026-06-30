# 审查修复计划 — 20 分及以上问题

## 概述

- **来源**: 6 维度并行审查（架构/PIT/规约/可维护/质量/文档）
- **范围**: `remediation/cross-module-b1-b7` 分支合入前修复
- **创建**: 2026-05-12

## 风险评估与分值

| # | 问题 | 分值 | 维度 | 理由 |
|---|------|------|------|------|
| T1 | Risk 依赖声明不同步（CLAUDE.md + 顶层依赖表） | 30 | 架构+文档 | 架构边界文档与实际代码严重不一致，误导开发者对依赖方向的判断 |
| T2 | `SQLiteClient.count()` where 参数缺乏防御 | 25 | PIT+安全 | SQL 注入向量（理论级，但需防御性编程） |
| T3 | strategy `__all__` 缺失 | 20 | 规约+文档 | 包级 API 边界缺失，`from ditto_strategy import *` 导入不受控 |
| T4 | portfolio `__all__` 缺失 | 20 | 规约+文档 | 同上 |

### 20 分以下（不纳入本次修复）

| 问题 | 分值 | 原因 |
|------|------|------|
| Execution CLAUDE.md planner LOC 过时 | 15 | 纯文档数字过时，不影响架构判断 |
| Platform CLAUDE.md `validate_identifier()` 归属 | 15 | 文档归属描述错误，不影响代码行为 |
| `pit_cutoff` 文档语义细化 | 10 | 文档措辞优化 |
| features CLAUDE.md 树注释位置 | 10 | 文档注释位置错误 |
| 计划文档验收清单未勾选 | 5 | 行政性任务 |

## 技术方案

### T1: Risk 依赖声明同步

Phase 2 OMS Lite 将 `Order`/`OrderTicket` 迁移到 `ditto_execution.orders`，risk 的 PreTrade 逐单校验需要引用这些类型。`importlinter` 已正确配置豁免（`orders.model` + `orders.ticket`），但文档未同步。

**修改范围**:
- `packages/risk/CLAUDE.md`: 允许依赖增加 `ditto_execution.orders`，删除"无外部依赖"声明
- `CLAUDE.md`（顶层）: `risk → kernel, portfolio` 改为 `risk → kernel, portfolio, execution.orders（窄依赖：仅 orders.model + orders.ticket）`

### T2: SQLiteClient.count() where 参数防御

`count()` 方法的 `where` 参数直接拼接到 SQL，虽然 `table` 已有 `validate_identifier()` 保护，但 `where` 无校验。当前无生产代码调用带 `where` 的 `count()`，但仍需防御。

**方案**: 在 `where` 非空时要求同时传入 `params`，否则抛出 `ValueError`。

### T3-T4: `__all__` 定义

strategy 和 portfolio 的 `__init__.py` 只有 docstring，缺少 `__all__`。需要：
1. 定义 `__all__: list[str] = []`（当前无有意公开的包级符号，消费者应从叶模块导入）
2. 保持与 data/features/risk/analysis/execution 等包的一致性

## 任务清单

- [x] T1: Risk 依赖声明同步 `[M]`
  - 验收: Risk CLAUDE.md 允许依赖包含 execution.orders；顶层 CLAUDE.md 依赖表 risk 行更新；`pixi run -e dev arch-check` 通过
  - 文件: `packages/risk/CLAUDE.md`, `CLAUDE.md`
  - 依赖: 无

- [x] T2: SQLiteClient.count() where 参数防御 `[S]`
  - 验收: `where` 非空且 `params` 为 None 时抛出 ValueError；对应测试通过；`pixi run -e dev test --fast` 通过
  - 文件: `packages/platform/src/ditto_platform/foundation/storage/sqlite_client.py`, `packages/platform/tests/unit/storage/test_sqlite_client_unit.py`（或新建测试）
  - 依赖: 无

- [x] T3: strategy `__all__` 定义 `[S]`
  - 验收: `ditto_strategy/__init__.py` 包含 `__all__: list[str] = []`；与 data/features/risk 等包风格一致；`pixi run -e dev type` 通过
  - 文件: `packages/strategy/src/ditto_strategy/__init__.py`
  - 依赖: 无

- [x] T4: portfolio `__all__` 定义 `[S]`
  - 验收: `ditto_portfolio/__init__.py` 包含 `__all__: list[str] = []`；与 data/features/risk 等包风格一致；`pixi run -e dev type` 通过
  - 文件: `packages/portfolio/src/ditto_portfolio/__init__.py`
  - 依赖: 无

## 执行顺序

T1-T4 无依赖关系，可并行执行。建议按优先级顺序：T1 → T2 → T3 → T4。

## 完成验证

```bash
pixi run -e dev check    # lint + fmt + type + test --fast
pixi run -e dev arch-check
```
