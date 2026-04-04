# Phase 4 审查修复计划

## 概述

- Sprint: Phase 4 收尾 | 修复审查发现的问题
- 创建: 2026-04-04
- 来源: 6 维度并行代码审查（架构/PIT/规约/可维护/质量/文档）

## 技术方案

### 修复策略

分两批执行：
1. **Critical + Important**（合并前必须修复）
2. **Suggestion**（合并后跟进，本计划仅记录，不实施）

### 依赖关系

```
Task 1 (pyproject.toml) ──→ Task 4 (app pyproject.toml)
Task 2 (CI) ──────────────→ 无前置
Task 3 (README) ───────────→ 无前置
Task 5 (serialization I/O) → 无前置
Task 6 (importlinter) ────→ Task 5
Task 7 (engine CLAUDE.md) → 无前置
Task 8 (interfaces CLAUDE.md) → 无前置
```

---

## 任务清单

### Batch 1: Critical（合并阻塞）

- [x] Task 1: 修复 pyproject.toml 路径配置 `[S]` ✅
  - 验收: extraPaths/pythonpath 包含 `packages/app/src`；移除 `packages/data/src` 重复项
  - 文件: `pyproject.toml` (L261-288)
  - 变更:
    1. extraPaths 添加 `"packages/app/src"`
    2. pythonpath 添加 `"packages/app/src"`
    3. 移除两处重复的 `"packages/data/src"`

- [x] Task 2: 修复 CI 配置引用 `[M]` ✅
  - 验收: CI yml 所有路径引用与当前目录结构一致
  - 文件: `.github/workflows/ci.yml`
  - 变更:
    1. L149: `packages/datahub/tests/unit/` → `packages/data/tests/unit/` + `packages/engine/tests/unit/` + `packages/analytics/tests/unit/` + `packages/kernel/tests/unit/` + `packages/app/tests/unit/`
    2. L163: `--cov=apps` → 移除（pyproject.toml 已有 `--cov=packages --cov=interfaces`）
    3. L160: port 测试步骤保留 `interfaces/tests/unit/`
    4. L209-211: 构建步骤改为 `packages/infra`, `packages/engine`, `packages/data`, `packages/app`, `packages/analytics`, `packages/kernel`

- [x] Task 3: 更新 README.md `[M]` ✅ (已无需修改，Phase 4 后已同步)
  - 验收: 架构图、项目结构、文档链接反映 Phase 4 后的实际布局
  - 文件: `README.md`
  - 变更:
    1. 架构图: 替换 `ditto-core`/`ditto-datahub`/`port` 为 `ditto-engine`/`ditto-data`/`ditto-interfaces` + 新增 `ditto-app`/`ditto-analytics`/`ditto-kernel`
    2. 依赖方向: `interfaces → app → engine → data → infra`
    3. 项目结构: 删除 `apps/` 目录，用 `interfaces/` 替代；`packages/core/` → `packages/engine/`；`packages/datahub/` → `packages/data/`；新增 `packages/app/`/`packages/analytics/`/`packages/kernel/`
    4. 文档链接: `packages/datahub/CLAUDE.md` → `packages/data/CLAUDE.md`；`apps/port/CLAUDE.md` → `interfaces/CLAUDE.md`

### Batch 2: Important（强烈建议）

- [x] Task 4: app pyproject.toml 添加 dependencies `[S]` ✅
  - 验收: packages/app/pyproject.toml 声明对 kernel/data/engine/analytics/infra 的依赖
  - 文件: `packages/app/pyproject.toml`
  - 变更: 添加 `dependencies = ["ditto-kernel", "ditto-data", "ditto-engine", "ditto-analytics", "ditto-infra"]`

- [x] Task 5: 提取 serialization.py 的 I/O 到 App 层 `[L]` ✅
  - 验收: engine/backtest/serialization.py 不再依赖 ditto_infra；App 层负责文件写入
  - 文件:
    - `packages/engine/src/ditto_engine/backtest/serialization.py` — 重构为纯序列化（返回 bytes + dict），移除 `atomic_bytes_write`/`atomic_write` 导入
    - `packages/app/src/ditto_app/process/strategy.py` L167 — 改为调用新接口 + 执行文件写入
    - `packages/engine/tests/unit/backtest/test_serialization_unit.py` — 适配新接口
  - 技术方案:
    1. `serialize()` 重构为 `serialize_report(report) -> tuple[bytes, dict[str, pl.DataFrame]]`，返回 JSON bytes + Parquet DataFrame 字典
    2. 在 App 层 `strategy.py` 中新增 `write_report(report, output_dir)` 函数负责文件写入
    3. 或更简单的方案：将 `serialize()` 整个函数移到 App 层（因为序列化+写入是一体的），engine 不再需要 serialization.py
  - 风险: **+1 级**（影响回测核心路径）

- [x] Task 6: 添加 engine → infra 禁止合约 `[S]` ✅
  - 验收: importlinter 新增 engine-no-infra-dependency 合约；`pixi run -e dev arch-check` 通过
  - 前置: Task 5（否则 serialization.py 的 infra 导入会被检测为违规）
  - 文件: `.importlinter`
  - 变更: 新增 forbidden 合约

- [x] Task 7: 修复 Engine CLAUDE.md 过时描述 `[S]` ✅
  - 验收: 模块结构描述与实际目录一致
  - 文件: `packages/engine/CLAUDE.md`
  - 变更:
    1. L16: `engine/ # 核心引擎` → 移除（该子目录不存在）
    2. 新增 `risk/` 子目录描述
    3. 更新测试目录描述

- [x] Task 8: 修复 Interfaces CLAUDE.md 重复表格 `[S]` ✅
  - 验收: 层级访问规则表格只出现一次
  - 文件: `interfaces/CLAUDE.md`
  - 变更: 删除 L82-88 的重复表格

---

## 不在本计划范围（合并后跟进）

以下 Suggestion 级别问题记录但不在本计划实施：

| ID | 问题 | 说明 |
|----|------|------|
| S1 | FX/Commodity Facade 重复 | 可后续抽取公共基类 |
| S2 | IngestionDataWriter 重复模式 | 可后续提取辅助方法 |
| S3 | quality.py logger 来源不一致 | 统一为 `ditto_infra.foundation` |
| S4 | quality.py `Any` 类型 | 替换为具体类型 |
| S5 | process/__init__.py 导出过多 | 考虑按需导入 |
| S6 | research.py noqa 缺注释 | 补充安全说明 |
| S7 | 根 CLAUDE.md 依赖图不完整 | 补充 app → kernel/analytics |
| S8 | ingestion.py (3290行) 拆分 | 需独立计划 |
| S9 | materialization.py (3011行) 拆分 | 需独立计划 |
| S10 | strategy.py (1239行) 拆分 | 需独立计划 |

## 验证

所有任务完成后运行：

```bash
pixi run -e dev check    # lint + fmt + type + test --fast
pixi run -e dev arch-check
```
