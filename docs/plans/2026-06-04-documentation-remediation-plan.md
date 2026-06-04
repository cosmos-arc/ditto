# 文档体系整改计划

> **日期**：2026-06-04
> **状态**：已完成
> **范围**：CLAUDE.md / AGENTS.md / README.md / .claude/ 全部文档
> **目标**：消除冗余、修复过时、统一术语、补全缺失、优化 token 效率

---

## 审计摘要

| 维度 | 评级 | 关键问题数 |
|------|------|-----------|
| 冗余治理 | 🔴 需整改 | 4 项 |
| 时效性 | 🔴 需整改 | 4 项 |
| 一致性 | 🟡 可改进 | 2 项 |
| 完善性 | 🟡 可改进 | 3 项 |
| Token 效率 | 🟡 可改进 | 2 项 |

**总计 15 项改进任务**，按优先级分为 P0（紧急）、P1（高）、P2（中）、P3（低）四档。

---

## 文档全景统计

| 分类 | 文件数 | 总行数 | 受众 |
|------|--------|--------|------|
| CLAUDE.md（root + 12 包） | 13 | ~2,604 | Agent |
| AGENTS.md（root + 12 包） | 14 | ~548 | Agent |
| README.md（root + 包级 + 子包） | 37 | ~4,800+ | 人类 |
| .claude/rules/ | 10 | ~3,588 | Agent |
| .claude/commands/ | 5+1 py | ~1,365 | Agent |
| .claude/skills/ | 8 | ~741 | Agent |
| .claude/checklists/ | 2 | ~68 | Agent |
| .claude/hooks/ | 2 | ~128 | 系统 |
| docs/architecture/ | 11 | ~2,941 | 人类+Agent |
| docs/adr/ | 11 | ~1,276 | 人类 |
| docs/design/（含子目录） | 57 | ~25,000+ | 人类（历史） |
| docs/plans/（活跃） | 56 | ~20,000+ | 人类 |
| docs/plans/archive/ | ~396 | — | 归档 |

---

## P0：紧急（影响正确性）

### P0-1：补充 README.md v0.15.0 变更日志

- **问题**：README 标注 v0.15.0 但 changelog 停在 v0.14.0。v0.14→v0.15 期间完成了 V2 架构整改（46 原子任务）、Batch 1-6 实施、PR#64/#65/#66——项目最大规模重构无记录。
- **操作**：
  1. 读取 `git log v0.14.0..HEAD --oneline` 提取变更摘要
  2. 在 README.md changelog 节补充 v0.15.0 条目，覆盖：
     - V2 架构整改路线图 46/46 任务完成
     - Batch 1-6 能力包治理（Catalog/PIT/Lineage/Replay/Quality）
     - PR#65 type:ignore 清零、regime 子包提取
     - PR#66 22 项 review fix（BaseRuntimeKernel 统一、data_store API 清理等）
     - 质量评估 Skill 上线
- **验收**：changelog v0.15.0 覆盖 2026-04 至 2026-05 全部重大变更

### P0-2：修复 README.md 项目结构漂移

- **问题**：kernel 列出 4 个幽灵文件（quality.py, research.py, publication_safety.py, json_types.py），缺失 5 个实际文件（runtime.py, synchronizer.py, time_context.py, time_semantics.py, trading.py）。几乎所有包缺失新增的 `observability/` 子目录。
- **操作**：
  1. 编写脚本从实际 `packages/*/src/` 目录树自动生成当前结构
  2. 用生成结果替换 README.md 项目结构节
  3. 人工校验确保描述准确
- **涉及包**（按严重度排序）：
  - `kernel`：4 幽灵 + 5 缺失（最严重）
  - `data`：缺 `catalog/`, `lineage/`, `di/`, `utils/`
  - `application`：缺 `providers_builder.py`, `providers_command.py`, `providers_process.py`, `catalog_freshness.py`, `catalog_maturity.py`, `runtime/`
  - `strategy`：缺 `runs/`, `audit/`
  - `portfolio`：缺 `holdings/`, `positions/`, `target_portfolios/`, `projection.py`
  - `risk`：缺 `pre_trade.py`, `post_trade.py`, `kill_switch.py`
  - `features`：缺 `derived_types.py`, `evaluation/`
  - 所有包：缺 `observability/`
- **验收**：`README.md` 项目结构节与 `ls -R packages/*/src/` 输出一致

---

## P1：高优先级（消除显著冗余）

### P1-1：精简 .claude/rules/architecture.md，消除与 boundaries doc 重叠

- **问题**：architecture.md（623 行）与 boundaries-and-abstraction-standards.md（613 行）约 60% 内容重叠——放置决策树几乎完全相同，包职责表重复，can/cannot 规则重复。
- **策略**：将 `architecture.md` 重新定位为"Agent 架构速查卡"（rules 层专用于路径匹配注入），保留其独有内容，删除与 boundaries doc 重复的部分，改为链接引用。
- **具体操作**：
  1. **删除**：放置决策树（~43 行）→ 替换为"详见 boundaries doc Section 7"
  2. **删除**：包职责表（~16 行）→ 替换为"详见 boundaries doc Section 3"
  3. **精简**：can/cannot 规则（~168 行）→ 仅保留硬性禁令摘要表（~30 行），详细说明链接 boundaries doc Section 4
  4. **保留（独有）**：PLC0415 处理决策树、延迟初始化 vs 延迟导入模式、SRP 案例研究、R8 Application CQRS 互斥矩阵、子域层规约表
- **目标行数**：623 → ~350 行（减少 ~270 行 / ~1.5K tokens）
- **验收**：architecture.md 无与 boundaries doc 重复的段落，所有链接可点击跳转

### P1-2：统一 root AGENTS.md 与 agent-context-pack.md

- **问题**：root AGENTS.md（44 行）与 agent-context-pack.md（63 行）80% 重叠，服务相同目的。
- **操作**：
  1. 精简 root `AGENTS.md` 为纯入口文档（~15 行）：
     - 项目一句话定位
     - 链接到 `docs/architecture/agent-context-pack.md`（架构快参）
     - 链接到 `CLAUDE.md`（开发规则）
     - 链接到 `docs/architecture/boundaries-and-abstraction-standards.md`（详细标准）
  2. 保留 per-package AGENTS.md 不变（它们作为包级轻量摘要卡是合理的）
- **验收**：root AGENTS.md ≤ 15 行，无与 agent-context-pack.md 重复的内容

### P1-3：明确 per-package README.md vs CLAUDE.md 分工

- **问题**：data/README.md 与 data/CLAUDE.md ~70% 内容重复，kernel ~50% 重复。
- **策略**：建立明确分工协议：
  | 文档 | 受众 | 内容 | 不含 |
  |------|------|------|------|
  | README.md | 人类浏览者 | 版本号、变更日志、快速开始、贡献指南、一行定位 | 模块树、架构规则、约束红线 |
  | CLAUDE.md | AI Agent | 架构规则、导入模式、约束红线、放置决策、测试位置 | 版本号、变更日志、人类叙述 |
- **操作**：
  1. 对现有 6 个有 README 的包（apps, application, data, kernel, platform, strategy）：
     - README.md 中删除与 CLAUDE.md 重复的模块树 → 替换为"目录结构详见 CLAUDE.md"
     - README.md 中删除与 CLAUDE.md 重复的层级职责表、CQRS 描述 → 替换为链接
     - 保留 README.md 中的：版本/changelog、数据源表、快速开始示例、人类叙述
  2. 在 `.claude/rules/doc.md` 中增加 README vs CLAUDE.md 分工规范
- **验收**：每个有 README 的包，README 与 CLAUDE.md 内容重叠率 < 30%

---

## P2：中等优先级（改善维护性）

### P2-1：批量归档已完成计划

- **问题**：~15-20 个 2026-05 月的计划已完成（对应 PR#64/#65/#66 已合并）但仍在活跃目录。
- **操作**：
  1. 列出 `docs/plans/2026-05-*` 所有文件
  2. 对比 git log 确认哪些已合并
  3. 将已完成计划 `mv` 到 `docs/plans/archive/`
  4. 保留仍活跃的计划（remediation-roadmap、batch2-6 fixes、quality-eval 相关）
- **已知待归档文件**：
  - `2026-05-08-cross-module-remediation-strategy.md`
  - `2026-05-10-b8-b9-b10-remediation-plan.md`
  - `2026-05-10-phase1-runtime-spine-design.md`
  - `2026-05-10-phase1-runtime-spine-plan.md`
  - `2026-05-10-phase1-runtime-spine-remediation.md`
  - `2026-05-11-phase2-oms-lite-plan.md`
  - `2026-05-15-architecture-remediation-plan.md`
  - `2026-05-18-architecture-remediation-fixes.md`
  - `2026-05-18-review-fixes-batch1.md`
  - `2026-05-25-batch-1c-trading-runtime-kernel-design.md`
  - `2026-05-31-fix-noqa-violations-pr66.md`
  - `2026-05-31-review-fixes-plan.md`
- **已知保留文件**：
  - `2026-05-25-architecture-remediation-roadmap.md`（活跃路线图）
  - `2026-06-02-quality-eval-skill-design.md`
  - `2026-06-02-software-quality-evaluation-framework.md`
  - `2026-06-03-review-fixes-batch2-6.md`（执行中）
- **验收**：`docs/plans/` 活跃文件数 ≤ 10

### P2-2：统一术语——"平面" vs "层"

- **问题**：architecture.md 用"层"（layer），boundaries doc 用"平面"（plane），AGENTS.md 用"模块"（module），描述同一个架构概念。
- **操作**：
  1. 确认 `boundaries doc` 的"平面"（plane）概念为权威术语（已有 Section 10.1 背书）
  2. 在 architecture.md 中将"层"替换为"平面"（或用"平面（包）"表达）
  3. 在 root AGENTS.md 中将"模块"替换为"包"（package）
  4. 在 CLAUDE.md 中检查一致性（当前主要用"包"，已较一致）
- **验收**：三份文档对同一概念使用统一术语

### P2-3：补充 6 个缺失包的 README.md

- **问题**：backtest, execution, features, portfolio, risk, analysis 缺 README.md。
- **操作**：按 `.claude/rules/doc.md` 中的模块 README 模板，为每个包创建精简 README：
  - 包定位（一句话）
  - 核心子域表
  - 链接到 CLAUDE.md 获取详细架构规则
  - 链接到测试目录
  - 版本号（如适用）
- **优先级排序**：backtest > execution > features > analysis > portfolio > risk
- **注意**：遵循 P1-3 建立的分工协议——README 只含人类视角信息
- **验收**：12 个包全部有 README.md，且不与 CLAUDE.md 重复

### P2-4：更新 architecture.md 包文件清单

- **问题**：application 层缺少 `providers_builder.py`, `providers_command.py`, `providers_process.py`, `catalog_freshness.py`, `catalog_maturity.py`, `runtime/`。其他包类似。
- **操作**：
  1. 对每个包，运行 `find packages/$pkg/src -name "*.py" -type f` 获取实际文件列表
  2. 更新 architecture.md 中的包文件描述
  3. 注意 P1-1 精简后此文件结构已变化，需在新版本上操作
- **验收**：architecture.md 中列出的文件 100% 与实际目录一致

---

## P3：低优先级（锦上添花）

### P3-1：考虑拆分 python-test.md

- **问题**：python-test.md 有 1,519 行，每次编辑测试文件全部注入上下文（~8K tokens）。
- **操作**：评估拆分为：
  - `python-test-core.md`（~500 行）：目录结构、命名约定、AAA 模式、覆盖率要求、性能阈值（必加载）
  - `python-test-advanced.md`（~1,000 行）：Hypothesis、snapshot、async、parametric、fixture 高级用法（按需引用）
- **风险**：拆分可能导致核心规则遗漏。需确保 core 覆盖所有"红线"规则。
- **验收**：python-test-core.md ≤ 500 行且包含所有强制性规则

### P3-2：更新 docs/architecture/README.md 索引

- **问题**：缺少 `capability-maturity.md`、`public-api-and-guard-backlog.md` 等新增文档的索引。
- **操作**：更新索引表，添加所有 11 个 architecture/ 目录文件的条目。
- **验收**：索引覆盖 docs/architecture/ 下所有 .md 文件

### P3-3：清理 .agents/ 空目录

- **问题**：`.agents/` 是空目录。
- **操作**：如果确认不再使用，删除此目录。
- **验收**：不再存在空 `.agents/` 目录

### P3-4：AGENTS.md 同步日期标记

- **问题**：per-package AGENTS.md 是 CLAUDE.md 的摘要，但无同步机制。
- **操作**：在每个 AGENTS.md 的 frontmatter 中添加 `last_synced: YYYY-MM-DD` 字段，建立更新 CLAUDE.md 时检查 AGENTS.md 的习惯。
- **验收**：所有 13 个 AGENTS.md 文件包含 last_synced 字段

---

## 执行计划

### 推荐批次

| 批次 | 任务 | 预计工作量 | 前置依赖 |
|------|------|-----------|---------|
| **Batch A** | P0-1, P0-2 | 2-3h | 无 |
| **Batch B** | P1-1, P1-2, P1-3 | 3-4h | P1-1 需先完成再执行 P2-4 |
| **Batch C** | P2-1, P2-2 | 1-2h | 无 |
| **Batch D** | P2-3, P2-4 | 3-4h | P1-1 完成后执行 P2-4 |
| **Batch E** | P3-1~P3-4 | 2-3h | 无 |

**总计预估**：11-16 小时

### 预期收益

| 指标 | 改进前 | 改进后 |
|------|--------|--------|
| Agent 上下文行数（单文件编辑） | ~4,400 行 | ~3,800 行（-14%） |
| 架构文档重复率 | ~60% (architecture.md vs boundaries) | <10% |
| README 结构准确性 | ~60%（kernel 最低） | ~100% |
| 活跃计划文件数 | 56 | ≤10 |
| 有 README 的包 | 6/12 | 12/12 |
| Changelog 覆盖 | 停在 v0.14.0 | 覆盖至 v0.15.0 |

---

## 文档分工协议（新增规范）

写入 `.claude/rules/doc.md`：

```
### README.md vs CLAUDE.md 分工

| 维度 | README.md | CLAUDE.md |
|------|-----------|-----------|
| 受众 | 人类（浏览者/新成员） | AI Agent（Claude Code） |
| 定位 | 项目/包的公开名片 | Agent 的操作手册 |
| 包含 | 版本号、changelog、快速开始、数据源表、人类叙述 | 架构规则、导入模式、约束红线、放置决策、测试位置 |
| 不含 | 模块树（→链接CLAUDE.md）、架构约束 | 版本号、changelog |
| 重叠率上限 | <30% | — |

### AGENTS.md 定位

- root AGENTS.md = 纯入口索引（≤15 行），链接到 agent-context-pack.md 和 CLAUDE.md
- per-package AGENTS.md = 包级轻量摘要卡（35-50 行），是 CLAUDE.md 的有意子集
- AGENTS.md 不含独有信息，所有内容在 CLAUDE.md 中有更详细版本
- 更新 CLAUDE.md 时须检查对应 AGENTS.md 是否需要同步
```
