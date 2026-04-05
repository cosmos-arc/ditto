# Phase 2 集成修复 + 残留清理

## 概述

- **Sprint**: Hybrid Plane v2 迁移
- **创建**: 2026-04-01
- **范围**: 修复 2a-2c 迁移遗留的集成问题 + 清理残留

## 背景

Phase 2a-2c 代码迁移已完成（ditto_data / ditto_analytics 创建、ditto_kernel → ditto_engine 改名），但集成层面存在阻塞问题：

1. `ditto-data` 和 `ditto-analytics` 未注册到 `pixi.toml`，导致包不可导入
2. `arch-check` 完全失败（`Could not find package 'ditto_data'`）
3. 三个残留目录仍含陈旧 `__pycache__`（quality、expression、materialization）
4. `ditto_kernel.egg-info` 未清理

## 技术方案

**最小改动原则**：只修阻塞项，不做架构变更。

### 依赖顺序分析

```
ditto-kernel（无依赖）
ditto-infra（无依赖）
ditto-data → ditto-kernel           ← 新增
ditto-engine → ditto-kernel
ditto-analytics → ditto-kernel, ditto-engine  ← 新增
ditto-datahub → ditto-kernel
ditto-port → ditto-engine, ditto-datahub, ...
```

## 任务清单

- [ ] Task 1: pixi.toml 注册 ditto-data + ditto-analytics `[S]`
  - 验收: `pixi run -e dev python -c "import ditto_data; import ditto_analytics"` 成功
  - 文件: `pixi.toml`
  - 操作: 在 pypi-dependencies 本地包区域按依赖顺序添加两行
  - 注意: 不重排现有条目，仅追加到合适位置

- [ ] Task 2: 清理陈旧目录 `[S]`
  - 验收: 目录不存在 + `pixi run -e dev check` 无新增失败
  - 文件/目录:
    - `packages/core/src/ditto_engine/quality/`（含 checkers/，零 .py 文件）
    - `packages/core/src/ditto_engine/engine/expression/`（零 .py 文件）
    - `packages/core/src/ditto_engine/engine/materialization/`（零 .py 文件）
    - `packages/core/src/ditto_kernel.egg-info/`（改名遗留）
  - 操作: `rm -rf` 四个目录

- [ ] Task 3: pixi install + 验证 `[S]`
  - 验收:
    - `pixi clean && pixi install -e dev` 成功
    - `pixi run -e dev arch-check` 全部 contract 通过
    - `pixi run -e dev check` 通过（lint + type + test）
  - 操作: 顺序执行验证命令

## 风险

| # | 风险 | 概率 | 缓解 |
|---|------|------|------|
| 1 | ditto_data/ditto_analytics 导入后暴露依赖问题 | 低 | pyproject.toml 声明已正确，deps 已列出 |
| 2 | arch-check 通过但暴露新的架构违规 | 低 | .importlinter 已包含两个包的 contract |
| 3 | pixi install 解析顺序问题 | 低 | 两个新包依赖链简单（→ kernel / → kernel+engine） |

## 不做的事

- 不改动 2d（TradingOrchestrator / Runtime Contracts / EventBus 隔离）— 留后续单独规划
- 不清理 datahub errors shim — Strangler 中间态，消费者迁移需独立任务
- 不重排 pixi.toml 现有条目
