# 文档审计与全面修复计划

**日期**: 2026-05-07
**状态**: Done
**范围**: README.md / CLAUDE.md / AGENTS.md / .claude/ / docs/ 全量审计修复

---

## 背景

对项目全部文档进行系统性审计，发现 4 项高优先级、7 项中优先级、3 项低优先级问题。
本计划按逻辑分组组织，各组可并行执行。

---

## 第一组：配置修正（4 项）

### T1.1 修正 Ruff target-version [H4]

**文件**: `pyproject.toml`
**变更**: `target-version = "py312"` → `target-version = "py313"`
**原因**: 所有包 `requires-python = ">=3.13"`，BasedPyright `pythonVersion = "3.13"`

### T1.2 修正 platform CLAUDE.md 依赖表述 [H3]

**文件**: `packages/platform/CLAUDE.md`
**变更**: 将"禁止依赖 kernel"改为精确表述："platform 禁止对 kernel 的业务性依赖；仅允许 `ditto_platform.exceptions` 继承 `ditto_kernel.exceptions.DittoError`（全局异常根），此豁免已在 `.importlinter` 中精确声明"
**验证**: 实际代码中仅 `exceptions.py` 一处导入，已确认无其他 kernel 依赖

### T1.3 修正 ops-manual Python 版本 [M2]

**文件**: `docs/ops-manual.md`
**变更**: 系统要求中 `3.12+` → `3.13+`

### T1.4 修正 RATE_LIMIT_PROFILE 文档 [M3]

**文件**: `docs/configuration.md`, `docs/ops-manual.md`
**变更**:
- `configuration.md`: 标注 `rate_limit_profile` 当前为未生效的配置项（死代码），有效值预留 `free`/`paid`/`conservative`
- `ops-manual.md`: 将 `free/pro` 修正为 `free/paid`
- 添加注释说明该字段尚未接入运行时

---

## 第二组：缺失 README 补全（2 项）

### T2.1 补全 strategy README [H1]

**文件**: `packages/strategy/README.md`
**当前**: 22 行，仅 4 个要点 + 安装/测试命令
**目标**: 与同层级包 README（如 data 210 行、application 131 行）对齐
**内容框架**:

```markdown
# Strategy 策略包
## 架构定位
## 模块结构树
  - alpha/ (Pipeline + Stage 架构)
  - signals/ (Protocol + 信号模型)
  - storage/ (SQLite 持久化)
  - runs/ (策略运行模型)
## 核心概念
  - StrategySpec / StrategyPipeline / DecisionStage
  - DecisionFrame 列名约定
  - SignalStore Protocol
## 依赖规则
## 策略模板列表
## 快速开始
```

### T2.2 新建 ditto-app README [H2]

**文件**: `/home/chevy/projects/ditto-app/README.md`（新建）
**内容框架**:

```markdown
# Ditto App
## 项目简介（前端 SPA，与 ditto 后端 API 交互）
## 技术栈（TypeScript + React + bun + Vite + Tailwind v4）
## 快速开始（bun install → bun dev）
## 项目结构（Feature-based 目录）
## 测试（bun test）
## 部署（Cloudflare Pages）
## 详细规范 → 参见 CLAUDE.md
```

---

## 第三组：简陋文档扩充（2 项）

### T3.1 扩充 docs/architecture/README.md [M1]

**文件**: `docs/architecture/README.md`
**当前**: 14 行，仅 2 个 Draft 文档链接
**目标**: 作为架构规范的主导航入口
**补充内容**:
- 12 包依赖图速查（ASCII 图）
- 包放置决策树（简化版）
- 关键约束速查表（禁止项一行一条）
- 将 agent-context-pack.md 和 boundaries-and-abstraction-standards.md 推进为正式状态

### T3.2 扩充 data/storage/README.md [M5]

**文件**: `packages/data/src/ditto_data/storage/README.md`
**当前**: 34 行，仅目录结构 + CQRS 说明
**补充内容**:
- 各 Store 的职责说明（MarketStore / CapitalStore / FundamentalStore 等）
- CQRS 读写接口示例
- 与 Service 层的交互模式
- Reader vs Writer 职责边界

---

## 第四组：AGENTS.md 充实（13 项）

### T4.1-T4.5 充实现有 5 个 AGENTS.md

将现有的纯重定向 AGENTS.md 改为内联核心规则摘要：
- `AGENTS.md`（根目录）
- `packages/apps/AGENTS.md`
- `packages/platform/AGENTS.md`
- `packages/kernel/AGENTS.md`
- `packages/data/AGENTS.md`

每个文件内容框架（约 30-50 行）：
```markdown
# [包名] Agent 指南

## 定位
## 核心模块
## 依赖规则（允许/禁止）
## 关键约束
## 详细规范 → CLAUDE.md
```

### T4.6-T4.13 新建 8 个缺失的 AGENTS.md

为以下包新建 AGENTS.md（与 T4.1 同等规格）：
- `packages/analysis/AGENTS.md`
- `packages/strategy/AGENTS.md`
- `packages/portfolio/AGENTS.md`
- `packages/risk/AGENTS.md`
- `packages/execution/AGENTS.md`
- `packages/backtest/AGENTS.md`
- `packages/features/AGENTS.md`
- `packages/application/AGENTS.md`

---

## 第五组：历史文档标注改进（2 项）

### T5.1 docs/design/ 导航改进 [M6]

**文件**: `docs/design/README.md`
**变更**: 在文件头部增加醒目提示框：
> ⚠️ 本目录为历史设计文档（旧 engine/analytics/infra/interfaces 架构时期）。
> 当前架构请参阅各包的 `CLAUDE.md` 和 `docs/architecture/`。

### T5.2 docs/sprints/ 导航改进 [M6]

**文件**: `docs/sprints/README.md`
**变更**: 增加当前阶段说明和 CLAUDE.md 导航指引

### T5.3 删除废弃文档 [M7]

**操作**: 删除 `docs/operations/operations-manual.md`（v1.0），已被 `docs/ops-manual.md`（v2.0）完全取代

---

## 第六组：低优先级修复（3 项）

### T6.1 Exchange 命名注释 [L1]

**文件**: `docs/data-manual.md`
**变更**: 在 Exchange 枚举附近添加注释，说明 SSE/SZSE 是文档层面的交易所简称，与 kernel 的 InstrumentId 前缀（XSHE/XSHG）属不同抽象层级

### T6.2 Alpha README 版本号同步 [L2]

**文件**: `packages/strategy/src/ditto_strategy/alpha/README.md`
**变更**: 移除独立的 `v3.1` 版本标注，改为与项目版本对齐

### T6.3 pit marker 补充 [L3]

**文件**: `.claude/rules/python-test.md`
**变更**: 在 Marker 列表中补充 `@pytest.mark.pit` 及其用途说明

---

## 执行计划

| 阶段 | 任务 | 依赖 | 预估 |
|------|------|------|------|
| 1 | T1.1-T1.4 配置修正 | 无 | 15 min |
| 2 | T2.1-T2.2 README 补全 | 无 | 30 min |
| 3 | T3.1-T3.2 文档扩充 | 无 | 20 min |
| 4 | T4.1-T4.13 AGENTS.md | 需读各包 CLAUDE.md | 40 min |
| 5 | T5.1-T5.3 历史文档改进 | 无 | 10 min |
| 6 | T6.1-T6.3 低优先级修复 | 无 | 10 min |
| 7 | 全量验证 | 全部完成 | 5 min |

阶段 1-3、5-6 可并行执行。阶段 4 需要读取各包 CLAUDE.md 后才能编写摘要。

## 验证

完成后运行：
```bash
pixi run -e dev check   # 确认代码无影响
git diff --stat         # 确认变更范围
```
