# B3 · 真实数据 promotion（治理）计划

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** 14 个必需数据集到达 promotion-ready，满足 RC1 hard-gate（`rc1_real_data_acceptance.py --real-data --require-promoted` 返回 0），为 A0"看到真实信号"提供真实数据基础。

**Architecture:** 非纯代码工作流——**治理 + 真实环境**。promotion 唯一路径是客观收集证据 → reviewer 评审 → `ReviewDatasetPromotionEvidenceHandler` 自动晋级；**绝不自造通过**。与代码工作流（A1/B0/B1）并行推进，须在 A0 真实数据里程碑前到达 RC1。

**Tech Stack:** ditto CLI（`ditto ops promotion-*`）/ 真实 Tushare + FRED API / 真实环境。

**战略索引:** [wave1 主计划](2026-06-24-wave1-implementation-plan.md) §6；[战略定位](2026-06-24-strategic-positioning-and-functional-gap-analysis.md)；[生产上线路线图](2026-06-14-production-launch-roadmap.md)；[capability-maturity](../architecture/capability-maturity.md)。

> **⚠️ 性质：** 治理流程，非 TDD。需真实环境（真实 API token、真实交易日）+ 人工 governance 决策。不阻塞 A1/B0/B1 代码工作流，但阻塞 A0 联调与"首次真实使用"。

---

## 现状实证（来自项目记忆与 production-readiness 文档）

- promotion 三条 criteria 客观收集：`ditto ops promotion-collect`（`PromotionEvidenceCollector` 收集证据，**只收集不判定**）。
- reviewer evidence 写入 + 评估晋级：`ditto ops promotion-review`（委托 `ReviewDatasetPromotionEvidenceHandler`，assessment ready 时经 `DatasetMaturityPromotionWriter` 写 override）。
- RC1 hard-gate：`rc1_real_data_acceptance.py --real-data --require-promoted` 返回 0（14 必需数据集 maturity 达 initial-focus/stable + promotion ready）。
- FRED realtime PIT（F2-#2）已完成；Tushare A 股 ETF/指数 = initial-focus 生产范围。

---

## Task B3.0：确认 14 个必需数据集清单 + 当前 maturity

**Step 1：** `ditto ops status --json`（或 `/ingestion/status` `maturity_summary`）列出所有数据集当前 maturity / promotion readiness / missing criteria。
**Step 2：** 对照 RC1 acceptance 脚本（`rc1_real_data_acceptance.py`）确认"14 个必需数据集"确切清单 + 各自 promotion criteria。
**Step 3：** 产出差距表：每个数据集当前状态 → 距 promotion-ready 还差什么（freshness / 覆盖 / schema / 行数等 criteria）。

---

## Task B3.1：逐数据集收集 promotion 证据

对每个未 promotion-ready 的必需数据集：

**Step 1：** `ditto ops promotion-collect <dataset> --start <date> --end <date>`（真实环境，真实 API）→ `PromotionEvidenceCollector` 客观收集 3 条 criteria 证据。
**Step 2：** 审查收集到的证据是否真实满足 criteria；**不满足则先修数据/摄取**（回到 ingestion/backfill），不自造证据。
**Step 3：** 证据满足后 `ditto ops promotion-review <dataset>` → `ReviewDatasetPromotionEvidenceHandler` 评估 → ready 则自动晋级（`metadata_promoted` / maturity before-after）。

> 每个数据集独立 commit（若涉及 metadata/governance event 落库）或记录评审证据。

---

## Task B3.2：真实环境 E2E 全绿

**Step 1：** 真实环境跑真实数据 E2E pipeline（`e2e-validation.yml` 路径或 `ditto` CLI 真实数据流）：摄取 → 物化 → 策略 → 信号。
**Step 2：** 确认 FRED realtime PIT（need_pit 指标 knowledge_date=realtime_end）、Tushare 真实数据全链路无 fail-closed 阻断（除非显式 `allow_experimental_data`）。
**Step 3：** 失败项回到 B3.1 修数据/证据。

---

## Task B3.3：RC1 hard-gate 通过

**Step 1：** `pixi run -e dev python <path>/rc1_real_data_acceptance.py --real-data --require-promoted` → 返回 0。
**Step 2：** 确认手工信号闭环 + 生产因子 guard pass（RC1 收口要求，见 [production-launch-closure](../superpowers/plans/2026-06-21-production-launch-closure.md)）。
**Step 3：** 记录 RC1 通过证据（governance 决策、promoted 数据集清单、acceptance 输出）。

---

## DoD

- [ ] 14 个必需数据集 maturity 达 initial-focus/stable + promotion-ready。
- [ ] 真实环境 E2E 全绿；promotion 全经 `ReviewDatasetPromotionEvidenceHandler`，零自造。
- [ ] `rc1_real_data_acceptance.py --real-data --require-promoted` 返回 0。
- [ ] RC1 收口要求（手工信号闭环 + 生产因子 guard）满足。

## 风险

| 风险 | 缓解 |
|---|---|
| 真实数据有质量缺陷（缺口/延迟/Schema 漂移）致 promotion criteria 不满足 | 先修摄取/质量（回到 data 层），不自造证据；criteria 不满足 = 真实信号"还不该上线" |
| 真实环境 token/配额（Tushare 积分、FRED 限流） | 规划回填节奏；FRED realtime 已验证；Tushare 分批 |
| governance 审批等待 | 与代码工作流并行推进；不阻塞 A1/B0/B1 |
| RC1 收口的非代码 🔒 项（需人工决策） | 单列跟踪，明确 owner；不伪装成已完成 |
