# 审查修复计划 — cross-module-b1-b7 Review Fixup

## 概述

- Sprint: remediation/cross-module-b1-b7 | Phase: Review Fixup
- 创建: 2026-05-11
- 范围: 6 维度审查发现的 11 项问题全部修复
- 风险: 低（6 文档 + 4 代码 + 1 重命名）
- 状态: **已完成** — 6396 tests passed, 36/36 arch contracts kept, 0 type errors, lint clean

## 技术方案

1. **文档优先**：先修文档，再改代码，确保 CLAUDE.md 始终与代码一致
2. **kernel barrel 扩展**：当前 26 符号 → 加 4 符号 = 30（恰好到上限）
3. **config 规约修复**：提取 `now_iso()` 到独立模块，`__init__.py` 纯 re-export
4. **PIT 修复**：`_execute_delayed_signal` 复用 `knowledge_lag_days` 而非硬编码
5. **重命名**：`kernel_types.py` → `quality_types.py`，消除命名歧义

## 任务清单

### Phase 1: 文档修复（6 任务，纯编辑，零风险）

- [x] Task A1: 修复 kernel/CLAUDE.md 残留引用 `[S]`
  - 验收:
    - 类型清单表中移除 DerivedRole / DerivedSpec / MaterializationProfile 三行
    - Barrel 分级表更新：strategy.py 行从 6 符号改为 3 符号（ExecutionPolicy / ImpactModel / RiskScope）
    - Barrel 总数 30 → 26（当前实际值）
    - "需叶模块导入" 表移除 events/time_context/synchronizer 行（将在 E1 加入 barrel）
  - 文件: `packages/kernel/CLAUDE.md`

- [x] Task A2: 修复 kernel/README.md 过时内容 `[S]`
  - 验收:
    - 版本号 v0.3.0 → v0.3.1
    - 模块结构添加 `time_context.py` 和 `synchronizer.py`
    - order.py 描述从 `OrderSide` 改为 `OrderSide / OrderType`
    - 类型清单移除 DerivedRole / DerivedSpec / MaterializationProfile
    - 类型清单添加 EventName / TimeContext / TimeSlice / Synchronizer
  - 文件: `packages/kernel/README.md`

- [x] Task A3: 修复 kernel/AGENTS.md 过时引用 `[S]`
  - 验收:
    - 移除 quality.py 行（已迁移至 data）
    - strategy.py 行从 `DerivedRole / DerivedSpec / RunStatus` 改为 `ExecutionPolicy / ImpactModel / RiskScope / RunStatus`
    - 添加 time_context.py / synchronizer.py / math.py 行
    - 核心模块表与 CLAUDE.md 模块结构一致
  - 文件: `packages/kernel/AGENTS.md`

- [x] Task G1: 更新 features/CLAUDE.md 记录 publication_safety_records.py `[S]`
  - 验收:
    - storage/runtime/publication_safety/ 说明中标注 `publication_safety_records.py` 来源（从 kernel 迁入的 6 个 frozen dataclass）
  - 文件: `packages/features/CLAUDE.md`

- [x] Task G2: 更新 analysis/CLAUDE.md 记录 research.domain 迁入 `[S]`
  - 验收:
    - research/ 目录说明中标注 `domain.py` 包含从 kernel 迁入的 4 个 frozen dataclass
  - 文件: `packages/analysis/CLAUDE.md`

- [x] Task G3: 更新 data/CLAUDE.md 记录 quality.kernel_types 迁入 `[S]`
  - 验收:
    - quality/ 目录说明中标注 `kernel_types.py`（将在 F1 重命名为 `quality_types.py`）包含从 kernel 迁入的 DQLevel / DQSeverity / DQIssue / DQResult
  - 文件: `packages/data/CLAUDE.md`

### Phase 2: 代码规约修复（1 任务，低风险）

- [x] Task B1: 提取 now_iso() 到独立模块 `[M]`
  - 验收:
    - 新建 `packages/application/src/ditto_application/config/helpers.py`，包含 `now_iso()`
    - `config/__init__.py` 改为从 `helpers` re-export `now_iso`，自身无内联定义
    - 6 个调用方无需变更（仍通过 `from ditto_application.config import now_iso` 导入）
    - `__all__` 不变
    - `pixi run -e dev check` 通过
  - 文件:
    - 新建: `packages/application/src/ditto_application/config/helpers.py`
    - 编辑: `packages/application/src/ditto_application/config/__init__.py`
  - 测试: 现有测试应继续通过（导入路径不变）

### Phase 3: 类型安全 & Barrel 改进（2 任务，低风险）

- [x] Task D1: 替换 StepDeps.trade_builder: Any 为 TradeBuilder Protocol `[S]`
  - 验收:
    - `engine_steps.py` 中 `trade_builder: Any` 改为 `trade_builder: TradeBuilder`
    - 添加 `from ditto_execution.trade_builder import TradeBuilder`
    - `pixi run -e dev type` 通过
  - 文件: `packages/backtest/src/ditto_backtest/engine_steps.py`

- [x] Task E1: 扩展 kernel barrel 加入 4 个公共类型 `[M]`
  - 验收:
    - `kernel/__init__.py` 的 `__all__` 添加 `EventName`, `Synchronizer`, `TimeSlice`, `TimeContext`
    - 对应 import 语句添加
    - barrel 总数 26 → 30（≤30 限制内）
    - CLAUDE.md 更新：
      - Barrel 分级表添加 4 个新符号（EventName → Candidate, 其余 → Stable）
      - "需叶模块导入" 表移除 events/time_context/synchronizer 行
      - Barrel 总数更新为 30
    - `pixi run -e dev check` 通过
  - 文件:
    - `packages/kernel/src/ditto_kernel/__init__.py`
    - `packages/kernel/CLAUDE.md`

### Phase 4: PIT 修复（1 任务，需测试）

- [x] Task C1: 修复 _execute_delayed_signal knowledge_date 硬编码 `[M]`
  - 验收:
    - EngineLoop 存储 `knowledge_lag_days`（从构造参数或 config 获取）
    - `_execute_delayed_signal` 中 `timedelta(days=1)` 改为 `timedelta(days=self._knowledge_lag_days)`
    - 新增/更新测试验证 flush 路径使用正确的 lag
    - `pixi run -e dev check` 通过
  - 文件:
    - `packages/backtest/src/ditto_backtest/engine.py`
    - `packages/backtest/tests/unit/test_engine_loop_unit.py`
  - 测试: 新增 flush 路径 knowledge_date 一致性测试

### Phase 5: 重命名（1 任务，中风险）

- [x] Task F1: 重命名 kernel_types.py → quality_types.py `[M]`
  - 验收:
    - 文件重命名: `data/quality/kernel_types.py` → `data/quality/quality_types.py`
    - 更新 `data/quality/__init__.py` 的 import 路径
    - 更新所有 20 个 import 站点（18 个在 data 内，2 个在 apps）
    - 更新 1 个 kernel 测试引用
    - data/CLAUDE.md 已在 G3 中更新
    - `pixi run -e dev check` 通过
  - 文件:
    - 重命名: `packages/data/src/ditto_data/quality/kernel_types.py` → `quality_types.py`
    - 编辑: ~20 个 import 站点
  - 测试: 现有测试应继续通过（功能不变）

## 执行顺序

```
Phase 1 (文档) ──→ Phase 2 (规约) ──→ Phase 3 (类型/barrel) ──→ Phase 4 (PIT) ──→ Phase 5 (重命名)
  A1-A3, G1-G3        B1                D1, E1                    C1                F1
  (可并行)            (独立)            (D1 独立, E1 依赖 A1)    (独立)            (依赖 G3)
```

**关键依赖**:
- E1 依赖 A1（barrel 文档先修正，再实际扩展）
- F1 依赖 G3（文档先记录新名称，再执行重命名）

## 验证

每个 Phase 完成后运行:
```bash
pixi run -e dev check  # lint + fmt + type + test --fast
pixi run -e dev arch-check  # 架构契约
```

全部完成后运行:
```bash
pixi run -e dev ci  # 完整 CI
```
