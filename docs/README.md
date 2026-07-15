# Ditto 文档索引

> **当前架构权威来源**：`packages/*/CLAUDE.md` + [`docs/architecture/`](architecture/README.md)
> **历史文档**：各目录 `archive/` 子目录与 [`docs/archive/`](archive/)
> **维护说明**：已完成里程碑、历史评审快照与被取代的设计统一归档（`git mv` 保留历史，`git log --follow` 可追溯）。

## 🧭 活跃文档导航

### 架构与边界
- [架构规范索引](architecture/README.md) — 12 包依赖图、边界约束、放置决策树
- [Agent 快速参考](architecture/agent-context-pack.md) — 依赖图、边界规则、关键路径
- [分层与抽象标准](architecture/boundaries-and-abstraction-standards.md)
- [能力成熟度分级](architecture/capability-maturity.md)
- [架构决策记录 (ADR)](adr/README.md)

### 操作手册
- [配置系统](configuration.md) · [数据集手册](data-manual.md) · [运维手册](ops-manual.md)
- [数据集晋级治理](operations/dataset-promotion.md) · [因子 IC 诊断](operations/factor-ic-diagnosis.md)

### 路线与计划（当前活跃）
- [母版路线图](superpowers/specs/2026-07-10-ditto-development-roadmap-design.md) — 分阶段产品/工程路线
- [功能能力评级与业界对标](plans/2026-07-10-capability-benchmark-design.md)
- [阶段 A 实施计划](plans/2026-07-10-phase-a-implementation-plan.md)
- [R1 日频人工交易 MVP](plans/2026-07-10-r1-implementation-plan.md)

### 最新评估（基线）
- [质量评估 2026-06-16](reviews/2026-06-16-quality-eval.md)
- [生产上线就绪度 2026-06-14](reviews/2026-06-14-production-readiness-eval.md)
- [架构评估 v2 2026-05-21](reviews/audit/2026-05-21-comprehensive-architecture-evaluation-v2.md)
- [模块 review 台账](reviews/audit/module-review-ledger.md)

### 验收证据
- [Wave1 数据 readiness](acceptance/wave1-data-readiness.md)
- [Wave1a 首次真实使用](acceptance/wave1a-first-real-use.md)

### 研究参考
- [因子评估最佳实践](research/quantitative-factor-evaluation-best-practices.md)
- [Tushare 外汇与商品调研](research/tushare-fx-commodity-research.md)
- [Yahoo / Alpha Vantage 调研](research/yahoo-alpha-vantage-data-research.md)

### 因子引擎设计
- [Unified Feature/Factor Engine](design/unified-feature-factor-engine/README.md) — 表达式编译、物化、IC、PIT

## 📦 归档区

| 位置 | 内容 |
|------|------|
| [plans/archive/](plans/archive/) | 已完成的实施计划（含原 `improvements/`） |
| [reviews/archive/](reviews/archive/) | 历史评审快照 |
| [reviews/audit/archive/](reviews/audit/archive/) | 历史架构评估与分模块 review |
| [design/archive/](design/archive/) | 旧架构（engine/analytics/infra/interfaces）时期设计 01-13 + PRD |
| [architecture/archive/](architecture/archive/) | 一次性架构 review 快照 |
| [archive/](archive/) | 零散与废弃目录：reports / brainstorms / sprints / acceptance(rc1) / superpowers 旧产物 |
