# Ditto 开发路线图状态评估（2026-08-04）

> **视角**：首席架构师，整合全量源码审计 + AI 能力平面设计 + Capability Benchmark 路线图
> **基准文档**：[capability-benchmark-design.md §7-§8](../plans/2026-07-10-capability-benchmark-design.md)（阶段与 Release Gate）、[2026-08-04-comprehensive-architecture-audit.md](2026-08-04-comprehensive-architecture-audit.md)（全 12 包审计）、[已归档的 2026-08-04 AI 平面设计](../plans/archive/2026-08-04-ai-agent-capability-plane-design.md)（当时的 AI 判断）
> **状态日期**：2026-08-06（G2 重跑验证通过日 2026-08-05）

---

## 2026-08-25 当前执行入口

本文现在只作为 2026-08-04—08-06 的历史审计记录。R4/R5、前端完成度、当前产品
边界和后续任务的统一裁决，已迁移到
[2026-08-25 统一产品路线图](../plans/2026-08-25-integrated-product-roadmap.md)。

当前事实是：R1—R4/G3 已在 `main` 完成；R5 已在
`codex/r5-governed-agent@a971a253` 完成 38/38 tasks 与 release preflight，尚待合并；
完整用户产品仍因前端视觉、交互、live 工作流和跨仓库验收缺口而只有约 50%—60%
完成度。以下历史表格中的“R4/R5 未开始”和 G4 当前优先级均不得继续用于排期。

当前 P0—P5 不建设复杂认证、RBAC、多租户或机构隔离；只保留本机单操作者所需的
最低运行基线。

---

## 2026-08-12 状态补充（当前裁决）

本文主体是 2026-08-04—08-06 的历史状态快照，不回写当时的审计过程。其“R4
未开始、旧 Phase A 计划就绪”的当前性结论已经失效：

1. R4 portfolio/risk 与 G3 controls 已由提交 `9ee6c48c`（PR #72）完成。
2. R5 当前方向已在 GitHub 交易/Stock Agent、成熟交易引擎、OpenAI 官方资料和
   金融/程序化交易治理材料复核后重构为**治理型量化研究 Agent**。
3. 新的当前事实源为 [R5 设计](../plans/2026-08-12-r5-governed-quant-research-agent-design.md)
   与 [38-task 实施计划](../plans/2026-08-12-r5-governed-quant-research-agent-implementation-plan.md)。
4. 生产默认改为单 Agent + 确定性状态机；R5.3 是预算受限的自主研究 Campaign，
   多 Agent 仅保留为离线对照，不再作为 R5.3 产品阶段。
5. `ditto_agent` 的当前依赖方向是 `apps -> agent -> application`，不再使用本文所引
   旧设计中的 “application peer”、Platform LLM Gateway 或强制 Langfuse 方案。

以下各节保留历史文字，用于说明当时为什么先完成 R4；执行工作不得引用其中的旧
AI 路径、旧 SDK 示例或旧任务顺序。

---

## 0. 一句话结论

> R1-R3 已完成且 **G2 现已合法 PASS**（08-05 重跑，证据可复现）。**R4（cvxpy 组合优化 + 连续风控）是下一个硬里程碑**，是 G3 与 agentic AI 的共同前提。AI 被提为优先是对的——**read-only Copilot 可与 R4 并行启动**（数据平面 R3 已交付），但 **write/decision AI 必须等 R4**。AI 是叠加能力，不改变 G 门禁结构（G4 外部 Beta 仍在 R4/R5 后）。

---

## 1. 路线图全貌与当前状态

### 1.1 阶段 × R × Release Gate

| 阶段 | R | 范围 | 状态 | 门禁 |
|------|---|------|:---:|------|
| **I 日频闭环** | R0-R2 | 本机日频人工交易 Beta；A 股 ETF/个股/宏观数据可靠 | ✅ | **G1 = PASS (7.9/10)** |
| **II 研究产品化** | R3 | 回测/选股/策略管理/研究治理（W0-W5） | ✅ | **G2 = PASS**（08-05 重跑） |
| **II 研究产品化** | R4 | cvxpy 组合优化 + 连续风控/统一 RiskGate | ❌ 未开始 | G3（决策工作台 Beta） |
| **III AI 与盘中** | R5 | AI Copilot/Agent（⑨ 0→3.5★） | ❌ 未开始（已优先，计划就绪） | — |
| **III AI 与盘中** | R6 | 分钟级数据/盘中信号 | ❌ 未开始（架构级空白） | — |
| **IV 全球化/机构化** | R7 | 全资产标的 + 多市场 + 机构级 | ❌ 未开始 | G4（受控外部 Beta） |

### 1.2 门禁定义与状态

| Gate | 归属 R | 定义 | 状态 | 证据 |
|------|--------|------|:---:|------|
| G1 内部本机 Beta | R1 | 单操作者闭环、5 阻塞清零、loopback-only、可恢复、验收证据包 | ✅ PASS | 就绪度 7.9/10 |
| G2 日频研究 Beta | R3 | 数据许可明确、策略/回测可复现、API 契约稳定、备份恢复演练 | ✅ **PASS** | `deb614e0`，4 golden lanes on certified live data |
| G3 决策工作台 Beta | R4 | 组合/风险解释、账本对账、运行手册、SLO/告警 | ⏳ 待 R4 | — |
| G4 受控外部 Beta | R4/R5 后 | 认证/RBAC、密钥治理、安全扫描、隐私与数据再分发审查、用户隔离 | ⏳ 待 R4/R5 | — |

### 1.3 G2 闭环经过（诚实记录）

G2 经历了一次"假 PASS → 审计推翻 → 合法重过"的完整闭环，证明门禁有效：

1. **08-04 源码审计推翻**：提交的 `r2-report.json` 实为 `configuration_blocked` 残桩，`r3-report.json` 引用从未提交的 ready 报告 → `a2bc3042` 降级为 **R3 ENGINEERING COMPLETE / G2 BLOCKED**。
2. **修复**：`49871058`（r2_data_acceptance replay-robust）+ scheduler lease/lease-recycling（`7e887cf5`/`ba39e0ed`）+ live golden-lane tick loop 钟表约束（`26c78c2f`）等一系列工程修复。
3. **重跑合法 PASS**：`deb614e0` — `r3-report.json` `generated_at=2026-08-05T14:10:42Z`、`r2_live_gate=PASS`、`status=ready`、4 golden lanes 全过；`r2-report.json`（256KB 真实内容）`passed=true`。

> 教训：evidence artifact 的 SHA 必须与实际提交一致；"声称通过"与"证据可复现通过"必须区分。

---

## 2. 当前完成度的能力维度（十维评级，源自 benchmark）

| # | 维度 | 分 | 评级 | 归属 R |
|---|------|:---:|:---:|--------|
| 2 | 数据治理与 PIT | 9.0 | A | R2（强项） |
| 3 | 因子与特征工程 | 7.0 | B | R3 |
| 5 | 回测与仿真 | 7.0 | A/B | R3 |
| 8 | 执行/OMS/账户 | 7.0 | A/B | R1 |
| 10 | 平台/体验/运营 | 7.0 eng / 6.0 product | A/B | 横向 |
| 1 | 数据覆盖与接入 | 6.0 | B | R2/R6/R7 |
| 4 | 策略与研究 | 6.0 | A/B | R3/R5 |
| 6 | **组合构建与优化** | **5.0** | B | **R4** |
| 7 | **风险管理** | **5.0** | B | **R4** |
| 9 | **AI/ML/Agent** | **0 runtime / 2 adjacent** | C | **R5** |

**等权能力广度分 5.9/10**（不含未来规划分）。短板集中在 ⑥⑦（R4）与 ⑨（R5）——正是下一程的目标。

---

## 3. 审计发现映射到路线图

| 审计发现 | 严重度 | 归属 R | 处置 |
|----------|:---:|--------|------|
| backtest Sortino 自由度 / turnover 双向 2× / engine_runtime 零测试 | P0 | R3 技术债 | 未阻塞 G2（G2 关注复现性/API/恢复），但影响指标可信度，应尽快修 |
| application 97K god-layer + 贴线切片（ARCH-001/002） | P1 横向 | 全 R | 影响后续 R 可演进性；R4 前值得收口 experiments 子域 |
| cvxpy 凸优化缺位（CovarianceProvider Protocol 已就位） | P2 | **R4** | G3 前置；也是 agentic AI 写入靶点 |
| 连续风控 / 统一 RiskGate Protocol / VaR / 压力测试 | P2 | **R4** | G3 前置 |
| AI runtime 0★ | 战略 | **R5** | Phase A-D 计划就绪，依赖已批准 |
| kernel Money/Decimal 缺失、FeeModel Port 错置、naive datetime | P2/P3 | 横向 | 精度根基，可随 R4 一并 |

> 详见 [2026-08-04-comprehensive-architecture-audit.md](2026-08-04-comprehensive-architecture-audit.md) §0 Top 6 与 §5 路线图。

---

## 4. 核心张力：AI 排序 vs 当前优先级

### 4.1 roadmap 原逻辑（AI 推 R5）

[benchmark §9 + memory](../plans/2026-07-10-capability-benchmark-design.md)：AI 整体推 R5，**需先有稳定的 Daily Decision + 报告 artifacts，否则 AI"空心"**。

### 4.2 裁决：部分成立、部分过时

- ✅ **仍成立**：write/agentic AI（Phase C Agentic 发现、Phase D 决策回路）依赖 R4（cvxpy 组合 + 连续风控）与 live daily-decision（需策略定义 publish 到 catalog）。R4/G2 未就绪前，Agent 没有可靠写入/执行靶点。
- ❌ **已过时**：**read-only Copilot（Phase A）的数据平面 R3 已交付**——ReviewPacket read-model、FactorEvaluationFacade、experiment read-model 齐全；护栏（R3 11-hard-gate）也已就位。"空心"风险不存在。

### 4.3 AI 平面 Phase A-D 与 roadmap L0-L3 对齐

| 我的 AI Phase | roadmap L 层 | 依赖 | 可启动时机 |
|---------------|-------------|------|-----------|
| **A Copilot**（read-only） | L0 基建 + L1 分析解读 | R3 read-model（已交付） | **现在，与 R4 并行** |
| **B NL 创作** | L2 建议/编写 | features DSL + StrategySpec（R3 已交付） | R4 中后期 |
| **C Agentic 发现** | L3 自主 | evaluation 引擎 + R3 治理 + **R4 组合** | R4 后 |
| **D 决策回路** | L2/L3 advisory | live daily-decision + **G2 unblock**（策略 publish） | R4 + G2 落地后 |

> 当时的 AI 平面设计见 [归档设计](../plans/archive/2026-08-04-ai-agent-capability-plane-design.md)；Phase A 计划见 [归档计划](../plans/archive/2026-08-04-agent-capability-plane-phase-a-copilot.md)。两者已被 2026-08-12 R5 文档取代。

---

## 5. 整合推荐序列

```
立刻（小，无争议）：
  ① P0 backtest 指标正确性（Sortino/turnover/engine_runtime 测试）—— R3 指标可信度
  ② application/processes/experiments 子域收口（解 ARCH-001 god-layer）—— 为 R4/AI 可演进清障

下一程（并行双轨）：
  ③ R4 主线：cvxpy ConstrainedMVOSolver（复用 CovarianceProvider Protocol）
            + 连续风控/统一 RiskGate + VaR/压力测试 → 冲 G3
  ④ AI Phase A：read-only Copilot（计划就绪，依赖 openai-agents+langfuse 已批准）
            ← 与 R4 并行，资源不争（R4=能力包，AI=新编排层包）

再下一程（依赖 ③④）：
  ⑤ AI Phase B-D（NL 创作 → Agentic → 决策回路）—— 需 R4 成熟 + live daily-decision
  ⑥ R6 分钟级/盘中（最贵，后置）
  ⑦ R7 全资产/机构化 + G4 外部 Beta（认证/RBAC/安全）
```

**为什么 R4 不能跳过**：它是 G3 前置，也是 agentic AI 能"建议/执行"而非"空谈"的根基。即使 AI 提到最高优先，cvxpy + 连续风控仍是必经之路。

**为什么 AI 不改变门禁**：G4（外部 Beta：认证/RBAC/密钥治理/安全扫描）仍在 R4/R5 之后。AI 是叠加能力，不是绕过门禁的捷径。

---

## 6. 终态定位（对标）

- **对标 LEAN（5★）**：十几年积累，Ditto 终态合理目标 ~4.7★。
- **Ditto 护城河**：① AI 原生（Agent + 治理护栏天然结合）；② A 股本土化（涨跌停/T+1/印花税/手数规整已工程化）；③ 数据治理严谨度（PIT fail-closed + promotion 不自造通过，机构级）。
- **功能完整度**（对标全资产 + AI 北极星）当前 ~2.5-3.0★；**工程质量** 4.4★（真功夫，是护城河底气）。

---

## 7. 验证命令

```bash
# G2 证据复现
pixi run -e dev python scripts/acceptance/r3_research_acceptance.py --real-data
# r3-report.json 应：passed=true, r2_live_gate=PASS, status=ready

# 架构门禁
pixi run -e dev arch-check   # 37 contracts kept, 0 broken

# 全量质量
pixi run -e dev check        # lint + fmt + type + test --fast
```

## 8. 相关文档索引

- 路线图母版：`docs/plans/2026-07-10-capability-benchmark-design.md`
- 全量审计：`docs/reviews/2026-08-04-comprehensive-architecture-audit.md`
- 当前 R5 设计：`docs/plans/2026-08-12-r5-governed-quant-research-agent-design.md`
- 当前 R5 实施计划：`docs/plans/2026-08-12-r5-governed-quant-research-agent-implementation-plan.md`
- 历史 AI 平面设计：`docs/plans/archive/2026-08-04-ai-agent-capability-plane-design.md`
- 历史 Phase A 计划：`docs/plans/archive/2026-08-04-agent-capability-plane-phase-a-copilot.md`
- R3 源码审计（G2 闭环经过）：`docs/reviews/2026-08-04-r3-source-audit.md`
