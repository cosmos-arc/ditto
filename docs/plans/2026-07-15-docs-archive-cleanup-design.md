# docs 文档归档清理设计

> Date: 2026-07-15
> Status: design（待执行）
> Scope: 全 docs 目录梳理，分类「保留 / 归档 / 修复」，建立两层归档区结构 + 补总索引
> 来源: brainstorming 产出

---

## 1. 背景与目标

`docs/` 经历数月迭代后积累了大量一次性 plan、历史评审快照、被取代的战略文档与已废弃工作流的产物。当前状态：

- 非归档 md 约 130 个，其中过半为已完成里程碑或被取代的历史文档。
- **仅 `docs/plans/` 有归档约定**（`plans/archive/` 已含 446 个历史文件，但自 2026-05-08 后未再维护）；其余目录（reviews/audit/sprints/improvements/reports/brainstorms）无归档机制。
- 无 `docs/README.md` 总入口，新人/Agent 难以定位当前权威文档。
- 存在 2 个含空格的坏文件名。

**目标**：

1. 逐文件判定「保留 / 归档」，让 `docs/` 仅保留**当前活跃参考 + 永久档案**。
2. 建立一致的**两层归档区**结构，历史可追溯、不丢失。
3. 补 `docs/README.md` 总索引，标注各文档的时效与权威性。
4. 全程 `git mv`（保留历史），**不删除任何文件**。

**非目标**：不修改文档内容（除 README 索引更新），不动 `packages/*/CLAUDE.md`，不重写架构。

---

## 2. 梳理结论汇总

130 个非归档文档 → **保留 46 / 归档 100 / 修复 2（含于归档）**。无删除。

| 目录 | 总 | 保留 | 归档 | 处置要点 |
|------|---:|----:|----:|------|
| `docs/`（根） | 4 | 3 | 1 | `verification-plan-2025` 归档（被 acceptance/ 取代） |
| `acceptance/` | 3 | 2 | 1 | rc1 归档；最新 wave1a/data-readiness 保留（被 roadmap 引用） |
| `adr/` | 11 | **11** | 0 | ADR 永久档案，永不归档 |
| `architecture/` | 13 | 12 | 1 | 仅 `2026-05-31-current-architecture-review`（1722L 快照）归档 |
| `brainstorms/` | 1 | 0 | 1 | hybrid-plane-v2 已落地为 ADR0006 |
| `design/`（根） | 15 | 2 | 13 | **README 自声明 historical**，`01-13` 归档；仅留 README+PRD |
| `design/unified-feature-factor-engine/` | 子系统 | 全留 | — | 自带 archive，结构良好，独立于根 historical 声明 |
| `operations/` | 2 | 2 | 0 | 活跃手册 |
| `plans/` | 24 | 6 | 18 | ⬇️ 见 §4 |
| `plans/improvements/` | 8 | 0 | 8 | 3-4 月设计，被取代/搁置 |
| `reports/` | 1 | 0 | 1 | V1 readiness 已取代 |
| `research/` | 3 | 3 | 0 | 长效行业参考 |
| `reviews/` | 13 | 2 | 11 | 仅留最新（06-16 质量 / 06-14 就绪） |
| `reviews/audit/` | 23 | 2 | 21 | 仅留 v2(05-21) + ledger |
| `reviews/audit/modules/` | 12 | 0 | 12 | 5 月初分模块 review，已沉淀 |
| `sprints/` | 6 | 0 | 6 | sprint 工作流已被 plans 取代（README 停更 5 月） |
| `superpowers/plans/` | 4 | 0 | 4 | 全部已完成/被取代 |
| `superpowers/specs/` | 3 | 1 | 2 | 仅留 roadmap(07-10 母版) |

---

## 3. 归档判定原则

| 判定 | 标准 |
|------|------|
| ✅ **保留** | (a) 永久档案（ADR）；(b) 当前活跃规范/手册；(c) 进行中的实施计划；(d) 最新版快照；(e) 长效行业参考 |
| 📦 **归档** | (a) 已完成的一次性 plan/整改；(b) 被更新版本取代的旧快照；(c) 已落地或被 supersede 的设计；(d) 已废弃工作流产物；(e) 自声明 historical 的旧架构文档 |
| 🔧 **修复** | 含空格的坏文件名（归档时一并规范化） |

**关键取代链**（决定多个文档去留）：

- 战略评估：`2026-06-24-strategic-positioning` ← 被 `2026-07-10-capability-benchmark` 取代
- 定位评估：`2026-06-24-ditto-system-positioning-assessment`（reviews + superpowers/specs 各一份）← 同被 07-10 取代
- wave1 计划：`06-24 主索引 + a0/a1/b0/b1/b3` → `06-30 final` → `07-01 completion` → `07-02 frontend-wiring`，**整条链已完成**（Wave1 后端 07-02 + 前端 07-05 完成）
- 质量评估快照：`06-03 → 06-04 → 06-13 → 06-16`，仅留最新 `06-16`
- 架构评估：`audit/` 下 4-5 月迭代快照，仅留 `2026-05-21-...-v2`
- design 根：`README` 自声明「旧 engine/analytics/infra/interfaces 架构时期 historical」，当前架构以 `packages/*/CLAUDE.md` + `docs/architecture/` 为准

---

## 4. 完整逐文件清单

### 4.1 ✅ 保留清单（46）

**永久档案 / 活跃规范**：

| 文件 | 理由 |
|------|------|
| `adr/*.md`（11） | ADR 永久档案 |
| `architecture/README.md` + 11 个 spec/adr-* | 活跃架构规范（boundaries / capability-maturity / public-api* / agent-context-pack / adr-*） |
| `configuration.md` / `data-manual.md` / `ops-manual.md` | 活跃操作手册 |
| `operations/dataset-promotion.md` / `factor-ic-diagnosis.md` | 活跃操作手册 |
| `research/*.md`（3） | 长效行业/数据源参考 |
| `design/unified-feature-factor-engine/**` | 因子引擎设计子系统，自带 archive |

**当前活跃工作文档**：

| 文件 | 理由 |
|------|------|
| `acceptance/wave1-data-readiness.md` | 最新 readiness 证据，被 roadmap 引用 |
| `acceptance/wave1a-first-real-use.md` | 最新 live smoke 证据，被 roadmap 引用 |
| `plans/2026-06-02-software-quality-evaluation-framework.md` | 质量评估通用框架，skill 理论基础 |
| `plans/2026-07-10-capability-benchmark-design.md` | **权威**功能能力评级，被 roadmap 引用 |
| `plans/2026-07-10-phase-a-implementation-plan.md` | 阶段 A 实施计划，活跃 |
| `plans/2026-07-10-r1-implementation-plan.md` | R1 日频人工交易 MVP，活跃 |
| `reviews/2026-06-14-production-readiness-eval.md` | 生产就绪度里程碑评估 |
| `reviews/2026-06-16-quality-eval.md` | **最新**质量评估基线 |
| `reviews/audit/2026-05-21-comprehensive-architecture-evaluation-v2.md` | 最新架构评估 v2 |
| `reviews/audit/module-review-ledger.md` | 模块 review 台账 |
| `roadmaps/ditto-development-roadmap.md` | **母版**路线图 |
| `plans/README.md` / `plans/task-template.md` | 索引与模板（需修正） |
| `design/README.md` | 设计索引（需更新） |

> ⚠️ **PRD.md 待定**：`design/PRD.md`（2025-12 v2.0）属产品需求。design 根整体 historical，且产品路线已被 `2026-07-10-development-roadmap` 取代。**默认建议归档**；若仍需产品需求参考则保留。执行时确认。

### 4.2 📦 归档清单（100）

#### `docs/plans/` → `plans/archive/`（18）

| 文件 | 归档原因 |
|------|------|
| `2026-05-25-architecture-remediation-roadmap.md` | 架构整改 46/46 完成 |
| `2026-06-02-quality-eval-skill-design.md` | skill 已实现（ditto-quality-eval） |
| `2026-06-03-review-fixes-batch2-6.md` | PR#66 review fixes 已完成 |
| `2026-06-04-documentation-remediation-plan.md` | 一次性文档整改，已完成 |
| `2026-06-13-quality-eval-remediation.md` | 一次性质量整改，已完成 |
| `2026-06-14-production-launch-roadmap.md` | 生产上线 Phase 0-2 完成 |
| `2026-06-15-phase2-implementation-design.md` | Phase 2 已完成 |
| `2026-06-23-trend-discovery-design.md` | Phase T 未采纳（产品闭环优先主线外） |
| `2026-06-24-strategic-positioning-and-functional-gap-analysis.md` | 被 07-10 capability-benchmark 取代 |
| `2026-06-24-wave1-a0-frontend-backend-wiring.md` | 被 wave1-final/completion 取代 |
| `2026-06-24-wave1-a1-eod-publish-signals.md` | 同上 |
| `2026-06-24-wave1-b0-portfolio-optimizer.md` | 同上 |
| `2026-06-24-wave1-b1-volume-constrained-fills.md` | 同上 |
| `2026-06-24-wave1-b3-real-data-promotion.md` | 同上 |
| `2026-06-24-wave1-implementation-plan.md` | 主索引，被 final/completion 取代 |
| `2026-06-30-wave1-final-implementation-plan.md` | 被 completion 取代 |
| `2026-07-01-wave1-completion-plan.md` | Wave1 已完成 |
| `2026-07-02-wave1-frontend-wiring-design.md` | 前端接线已完成 |

#### `docs/plans/improvements/` → `plans/archive/`（8，整目录废弃）

| 文件 | 归档原因 |
|------|------|
| `2026-03-05-industry-benchmark-analysis.md` | 被 07-10 capability-benchmark 取代 |
| `2026-03-05-materialization-terminology-analysis.md` | 术语已落地 |
| `2026-03-08-realtime-stream-pipeline-design-v2.md` | 分钟级在 roadmap 远期 |
| `2026-03-17-questdb-kvrocks-infrastructure-plan.md` | 技术栈已转向 parquet/duckdb/sqlite，方案搁置 |
| `2026-03-17-questdb-kvrocks-infrastructure-review.md` | 同上 |
| `2026-03-19-append-write-compaction-design.md` | 针对旧架构 ParquetStore，已被新实现取代 |
| `2026-04-08-crossgate-design.md` | 未实施，AI 推至 R5 |
| `datahub-metadata-optimizations.md` | DataHub 旧名，已重构为 data 包域 |

#### `docs/reviews/` → `reviews/archive/`（11）

| 文件 | 归档原因 |
|------|------|
| `2026-04-03-openbb-research.md` | 4 月调研，被 capability-benchmark 对标覆盖 |
| `2026-04-07-architecture-deep-dive-and-industry-benchmark.md` | 被后续 v2 取代 |
| `2026-04-07-industry-benchmark-gap-analysis.md` | 被 07-10 取代 |
| `2026-04-15-data-source-research.md` | 4 月调研 |
| `2026-04-24-comprehensive-industry-benchmark.md` | 被 07-10 取代 |
| `2026-05-04-capability-architecture-100-point-review.md` | 被后续取代 |
| `2026-05-04-capability-package-architecture-audit.md` | 整改已完成 |
| `2026-06-03-quality-eval.md` | 旧快照，仅留 06-16 |
| `2026-06-04-quality-eval.md` | 旧快照 |
| `2026-06-13-quality-eval.md` | 旧快照 |
| `2026-06-24-ditto-system-positioning-assessment.md` | 被 07-10 取代 |

#### `docs/reviews/audit/` → `reviews/audit/archive/`（21 + modules/ 12 = 33）

| 文件 | 归档原因 |
|------|------|
| `2026-04-17-*`（7 个：deep-analysis / audit-findings / design-quality-analysis / phase1-6 审计） | 4 月初轮审计快照 |
| `2026-04-24-current-full-project-audit.md` | 4 月快照 |
| `2026-04-28-comprehensive-architecture-evaluation.md` | 被 v2 取代 |
| `2026-04-28-t0-architecture-clarity-scorecard.md` | T0 快照 |
| `2026-04-28-t0-gap-analysis-and-design.md` | T0 快照 |
| `2026-05-07-comprehensive-architecture-evaluation.md` | 被 v2 取代 |
| `2026-05-07-deep-architecture-evaluation.md` | 被 v2 取代 |
| `2026-05-08-global-and-module-review-plan.md` | review 计划，已执行 |
| `2026-05-08-runtime-architecture-critique-part1.md` | critique 快照 |
| `2026-05-08-runtime-architecture-critique-part2.md` | critique 快照 |
| `2026-05-10-full-re-audit-report.md` | 被 v2 取代 |
| `2026-05-13-comprehensive-architecture-evaluation.md` | 被 v2 取代 |
| `2026-05-14-comprehensive-architecture-evaluation-and-review-plan.md` | 被 v2 取代 |
| `2026-05-21-current-architecture-evaluation-and-review-plan.md` | review 计划，已执行 |
| `modules/*.md`（12） | 5 月初分模块 review，已沉淀进 ledger + v2 |

> 保留：`2026-05-21-comprehensive-architecture-evaluation-v2.md`（最新 v2）+ `module-review-ledger.md`（台账）。

#### `docs/architecture/` → `architecture/archive/`（1）

| 文件 | 归档原因 |
|------|------|
| `2026-05-31-current-architecture-review.md`（1722L） | 一次性快照评审，规范已沉淀至其他 spec |

#### `docs/design/`（根）→ `design/archive/`（13，含文件名修复）

`design/README.md` 自声明「历史设计文档（旧 engine/analytics/infra/interfaces 架构时期）」，当前架构以 `packages/*/CLAUDE.md` + `docs/architecture/` 为准。

| 文件 | 归档原因 |
|------|------|
| `01_system_design.md` | 旧架构系统设计 |
| `02_data_design.md`（6658L） | 旧架构数据设计 |
| `03_engine_design.md`（4363L） | 自标注「历史参考」 |
| `04_deployment_topology.md` | 旧部署拓扑 |
| `05_observability.md` | 旧可观测性方案 |
| `06_ roadmap.md` → 修复为 `06_roadmap.md` | 旧路线图 + **坏文件名** |
| `07_research_playground.md` | 旧研究环境 |
| `08_risk constitution.md` → 修复为 `08_risk_constitution.md` | 旧风险宪法 + **坏文件名** |
| `09_data_quality_design.md` | 旧 DQ 设计 |
| `10_data_ingestion_scheduler_design.md` | 旧摄取调度 |
| `11_interfaces_architecture.md` | 旧 Port 层 |
| `12_quant_architecture_alignment.md` | 自声明 historical |
| `13_golden_dataset_design.md` | 旧黄金数据集 |

> 保留：`README.md`（更新索引）+ `PRD.md`（待定，见 §4.1）。`unified-feature-factor-engine/` 不受影响。

#### `docs/`（根）零散 + 废弃目录 → `docs/archive/<type>/`

| 来源 | 目标 | 归档原因 |
|------|------|------|
| `docs/verification-plan-2025.md` | `docs/archive/reports/` | 2025 旧验证计划，被 acceptance/ 取代 |
| `docs/reports/2026-04-11-data-readiness.md` | `docs/archive/reports/` | V1 readiness 已取代 |
| `docs/brainstorms/2026-03-31-hybrid-plane-v2-refined-requirements.md` | `docs/archive/brainstorms/` | 已落地为 ADR0006 |
| `docs/sprints/*`（6：README + backlog + sprint-01~04） | `docs/archive/sprints/` | sprint 工作流已被 plans 取代 |
| `docs/acceptance/rc1-release-checklist.md` | `docs/archive/acceptance/` | RC1 已通过 |
| `docs/superpowers/plans/*`（4） | `docs/archive/superpowers/plans/` | 全部已完成/被取代 |
| `docs/superpowers/specs/2026-06-14-ditto-research-backtest-readiness-design.md` | `docs/archive/superpowers/specs/` | 评估已完成 |
| `docs/superpowers/specs/2026-06-24-ditto-system-positioning-assessment-design.md` | `docs/archive/superpowers/specs/` | 被 07-10 取代 |

> 废弃目录（reports/brainstorms/sprints）整体移入 `docs/archive/` 后，原目录留 pointer README 或删除空目录（git 不跟踪空目录）。

---

## 5. 两层归档区结构设计

**原则**：大目录就近 `archive/`（延续现有 `plans/archive` 约定）；零散文件与整目录废弃的集中到 `docs/archive/`。

```
docs/
├── README.md                      # 🆕 总索引（活跃文档导航 + 时效标注）
├── archive/                       # 🆕 集中归档（零散 + 废弃目录）
│   ├── reports/                   #   verification-plan-2025, data-readiness V1
│   ├── brainstorms/               #   hybrid-plane-v2
│   ├── sprints/                   #   sprint-01~04 + README + backlog
│   ├── acceptance/                #   rc1-release-checklist
│   └── superpowers/{plans,specs}/ #   已完成/被取代的 superpowers 产物
├── adr/                           # 永久档案（不动）
├── architecture/
│   ├── archive/                   # 🆕 就近归档（current-architecture-review 快照）
│   └── ...spec                    # 活跃规范
├── design/
│   ├── archive/                   # 🆕 就近归档（01-13 旧架构设计）
│   ├── README.md / PRD.md         # 保留
│   └── unified-feature-factor-engine/  # 保留（自带 archive）
├── plans/
│   ├── archive/                   # ✅ 已有（446 个），新增 18+8 个
│   └── ...活跃 plan               # 4 个 date plan + README + template
├── reviews/
│   ├── archive/                   # 🆕 就近归档（11 个历史 review）
│   └── ...最新 review             # 06-14 / 06-16
│   └── audit/
│       ├── archive/               # 🆕 就近归档（21 + modules/12）
│       └── ...v2 + ledger         # 最新
├── acceptance/  operations/  research/   # 活跃，不动
└── configuration.md  data-manual.md  ops-manual.md  # 活跃手册
```

---

## 6. 执行计划

全部用 `git mv`（保留历史），分 8 批，每批可独立提交。建议在 `feat/wave1-backend-capabilities` 或新开 `chore/docs-archive` 分支执行。

### Batch 1：plans（18）→ plans/archive/
### Batch 2：improvements（8）→ plans/archive/（整目录移入后删空目录）
### Batch 3：reviews（11）→ reviews/archive/
### Batch 4：reviews/audit（21 + modules/12）→ reviews/audit/archive/
### Batch 5：design 根（13）→ design/archive/（含 06/08 文件名修复）
### Batch 6：architecture（1）→ architecture/archive/
### Batch 7：零散 + 废弃目录 → docs/archive/<type>/
### Batch 8：README 更新
- 🆕 新建 `docs/README.md` 总索引
- 更新 `plans/README.md`（删除不存在的 `app/` 子目录引用 + 补 archive 说明）
- 更新 `design/README.md`（01-13 移走后，索引指向 `archive/` + 当前架构入口）
- 更新 `architecture/README.md`（补 archive 说明）

---

## 7. docs/README.md 总索引草案

```markdown
# Ditto 文档索引

> 当前架构权威来源：`packages/*/CLAUDE.md` + `docs/architecture/`
> 历史文档：各目录 `archive/` 子目录与 `docs/archive/`

## 活跃文档

### 入门与导航
- [架构规范](architecture/README.md) — 分层、边界、命名、抽象标准
- [Agent 快速参考](architecture/agent-context-pack.md)

### 操作手册
- [配置系统](../configuration.md) · [数据集手册](../data-manual.md) · [运维手册](../ops-manual.md)
- [数据集晋级治理](operations/dataset-promotion.md) · [因子 IC 诊断](operations/factor-ic-diagnosis.md)

### 当前路线与计划
- [母版路线图](../roadmaps/ditto-development-roadmap.md)
- [功能能力评级](plans/2026-07-10-capability-benchmark-design.md)
- [阶段 A 实施](plans/2026-07-10-phase-a-implementation-plan.md) · [R1 MVP](plans/2026-07-10-r1-implementation-plan.md)

### 最新评估（基线）
- [质量评估 06-16](reviews/2026-06-16-quality-eval.md)
- [生产就绪度 06-14](reviews/2026-06-14-production-readiness-eval.md)
- [架构评估 v2](reviews/audit/2026-05-21-comprehensive-architecture-evaluation-v2.md)

### 验收证据
- [Wave1 数据 readiness](acceptance/wave1-data-readiness.md)
- [Wave1a 首次真实使用](acceptance/wave1a-first-real-use.md)

### 永久档案
- [ADR](adr/README.md) · [研究参考](research/)

## 归档
各目录 `archive/` 与 `docs/archive/` 存放已完成里程碑、历史评审快照与被取代的设计。
```

---

## 8. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 误归档仍活跃文档 | 全部 `git mv`，`git log --follow` 可追溯；每批独立提交，可 `git revert` 单批 |
| 引用断裂（其他文档链接到被移动文件） | 归档前 grep 全仓 markdown 链接，更新或确认无活跃引用；README 总索引统一导航 |
| PRD 误判 | 单独标注待定，执行时二次确认 |
| 坏文件名修复影响链接 | 06/08 仅在 design/README.md 内部引用，同步更新 |

**回滚**：任一批次 `git revert <commit>` 即可恢复原位。

---

## 9. 待确认

1. **PRD.md**：归档 or 保留？（默认建议归档）
2. **执行分支**：当前 `feat/wave1-backend-capabilities` 还是新开 `chore/docs-archive`？
3. **执行方式**：本会话直接执行全部 8 批，还是先执行 Batch 1-2（plans）验证流程后再继续？
