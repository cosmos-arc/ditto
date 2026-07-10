# Ditto 功能能力评级与业界对标（2026-07-10）

> **目的**：在长时间迭代后重新建立对系统功能能力的全景认知，对标业界优秀量化系统（LEAN / NautilusTrader / QLib / OpenBB / TradingAgents / FinRobot 等），梳理缺陷与离真正产品的差距，给出分阶段优先级路线图。
>
> **目标系统画像**：全球全品类 AI 量化平台，优先 A 股 ETF/个股 + 宏观 + 商品大宗；日级优先、给出信号做人工交易（非全自动）；后续支持分钟级盘中信号/因子；支持回测/选股/仓位管理与优化/策略管理；AI 辅助（编写策略/投研/仓位与买卖建议/宏观及市场分析）+ AI Agent。
>
> **评分轴声明**：本文 5★ 评的是 **「功能能力完整度」对标业界**，**不是**工程质量评分（memory 中的 4.56★ 是工程质量）。ditto 是典型的「基建极其扎实、工程纪律严格，但功能覆盖面窄」——工程质量高 ≠ 功能完整度高。

---

## 一、评级标尺（5★ 制）

| ★ | 含义 | 业界参照 |
|---|---|---|
| 5★ | 业界领先/天花板 | LEAN / QLib / Nautilus 在该维度的最高水准 |
| 4★ | 生产可用且有特色 | 能支撑真实业务，部分超越平均 |
| 3★ | 功能闭环可用 | 跑通但有明显短板 |
| 2★ | 有实现但不完整 | 半成品，补全才能用 |
| 1★ | 骨架/占位 | 结构在，缺实质 |
| 0★ | 空白 | 无实现 |

---

## 二、10 维度能力评级总表

| # | 能力维度 | ditto | 业界 5★ 标杆 | 证据 / 缺口 |
|---|---|:---:|---|---|
| ① | 数据覆盖与接入 | 3.0★ | LEAN(多资产) / Nautilus(盘中) | 日级 ETF initial-focus 扎实；stock/macro/fx/commodity **默认 registry 仍 experimental 分类**（RC1 已对含 stock/macro 的 8 个数据集 promotion override）；真问题：**历史深度浅 / 默认环境可迁移性 / fx·commodity 弱**；无分钟级/tick |
| ② | 数据治理(PIT/质量/promotion) | **4.5★** | 多数开源标杆不如 ditto 严格 | 🔥**最强项**：knowledge_date fail-closed + promotion evidence 闭环（绝不自造通过）+ source-health/fallback + lineage，机构级严谨 |
| ③ | 因子/特征工程 | 3.5★ | QLib(alpha 库) / WorldQuant | 表达式编译/物化/IC 诊断 CLI 扎实；缺丰富因子库 + alpha 挖掘 |
| ④ | 策略与研究 | 2.5★ | LEAN(模板+Alpha Streams) / 聚宽 | pipeline 严谨 + DecisionFrame 可解释；仅 2 ETF + 2 stock 模板，无配置化策略框架/策略市场/AI 辅助 |
| ⑤ | 回测引擎 | 3.5★ | LEAN / Nautilus / QLib | 引擎严谨 + checkpoint/resume + replay proof + PIT 安全 TimeSlice；佣金/印花税/滑点/**T+1 交收**完整；**涨跌停矩阵已实现**（`AShareFillModel`）；**缺口：手数规整 + 可成交量/流动性解释 + 订单 round 后 cash/remainder 解释 + 归因深度** |
| ⑥ | 组合构建与优化 | 2.5★ | LEAN(PC+优化器) / PyPortfolioOpt | `MeanVarianceAllocator` + `CovarianceProvider` + `EqualWeightAllocator` 框架在；**缺风险平价/Black-Litterman/数值求解器/有效前沿** |
| ⑦ | 风险管理 | 2.5★ | LEAN / 机构风控引擎 | 规则齐全（集中度/最大回撤/单笔止损/市场异常/**kill_switch**）+ `RiskGate` Protocol；**缺连续状态/审计持久化/崩溃恢复** |
| ⑧ | 执行与对接(OMS/券商) | 3.0★ | LEAN(broker built-in) / Nautilus | 🔥OMS FSM(7 态 5 触发) + 对账(5 mismatch) + 修复(workflow/claim/audit)工业级严谨；**无真实券商 adapter**(reserved，人工交易目标下够用) |
| ⑨ | AI/ML 与 AI Agent | **0★** runtime / **1★** adjacent | QLib / OpenBB Copilot / TradingAgents / FinRobot | **AI runtime 0★**（无 LLM/Agent SDK 集成，`analysis.experiments` 空命名空间）；**AI-adjacent 1★**（hypothesis 桥接点 + 前端 AI Review 原型 + Experience Memory 已有，但无正式 runtime） |
| ⑩ | 平台与体验 | 3.5★ | LEAN(IDE+cloud) / OpenBB(终端) / 聚宽 | 后端 API/OpenAPI maturity/CLI(jobs)/可观测/架构分层(37 合约)扎实；前端 prototype；**部署/认证/多租户缺失** |

**综合功能完整度 ≈ 2.9★**。

**整体定位**：ditto 是一个「日级 A 股 ETF 的数据治理 + 回测 + 信号」专精平台，工程纪律达机构级（治理/执行协议层世界级），但在「全品类、组合优化、风控、AI Agent」四个维度离目标差距巨大。当前形态最接近「机构级数据中台 + 严谨回测引擎」，而非「全功能量化平台」。

---

## 三、四个深坑剖析

### 深坑一：AI / AI Agent（runtime 0★ / adjacent 1★）— 最大、最确定、却最容易补

- **现状（runtime 0★）**：全 SRC 0 个 LLM/Agent SDK 导入，`analysis.experiments` 是 `__all__=[]` 空命名空间。**AI-adjacent 1★**：hypothesis 桥接点 + 前端 AI Review 原型 + Experience Memory 已存在，但无正式 runtime。
- **业界标杆**：TradingAgents（80k★，多 agent debate）、FinRobot（多 agent 平台）、OpenBB Copilot（AI 分析师嵌入终端）、QLib（AI 量化研究天花板）。
- **关键认知**：AI 是「接入」不是「自研」。ditto 的 daily-decision 信号 + 因子 IC + 宏观数据 + PIT 严格数据是绝佳的 agent grounding 工具集。最优解 = LLM API + 借鉴 TradingAgents 多 agent 架构 + ditto 数据/信号作为 tool。
- **补齐路径**（详见第四章 AI 目标体系）。

### 深坑二：分钟级 / 盘中（0★）— 架构级，最贵

- **现状**：所有 `Bar` 都是日级 OHLC；`Synchronizer`/`TimeSlice`/`EngineLoop` 是日级 step 设计；无频率枚举、无 minute/tick 存储。
- **业界标杆**：NautilusTrader（Rust 内核 event-driven，tick+bar 盘中天花板）、LEAN。
- **关键认知**：架构级改造（数据存储/pipeline/回测引擎/实时信号）。当前目标「日级优先」，现在不必碰，但**必须确保抽象留好分钟级扩展点**，避免日后推翻重写。

### 深坑三：组合优化（2.5★）— 基础在，高级缺

- **现状**：等权 + 均值方差 + 对角协方差 provider 框架在。
- **缺**：风险平价、Black-Litterman、完整数值优化求解器、有效前沿可视化、多约束求解。
- **补齐**：接 `cvxpy` 实现风险平价 + 带约束均值方差（性价比最高）。

### 深坑四：风控（2.5★）— 规则在，运行时连续性缺

- **现状**：规则齐全（集中度/最大回撤/单笔止损/市场异常/熔断）+ `RiskGate` Protocol。
- **缺**：continuous risk gate（盘中持续监控）、typed audit payload 持久化、状态崩溃恢复、风控事件流。
- **补齐**：把 `RiskGate` 从「每笔 pre/post check」升级为「持续状态机 + 事件流 + 审计」，与 OMS 对账层打通。

---

## 四、AI 能力目标体系（业界对标完善 + OpenAI Agents SDK 映射）

### 4.1 OpenAI Agents SDK 与 ditto 架构的天然映射

| SDK 原语 | ditto 映射（复用而非新建） |
|---|---|
| Tools（function tools） | 包装 ditto 的 daily-decision / 因子 IC / 回测 / RiskGate / 数据查询 API 为 LLM 可调工具 |
| Handoffs（多 agent 委托） | analyst / researcher / trader / risk-manager 分工（TradingAgents 模式） |
| Guardrails（输入/输出校验） | 复用 `RiskGate` 的 pre/post-trade check 作为 agent 输出 guardrail |
| Sessions/Memory | 接入 ditto 已有的 `Experience Memory` |
| Tracing（自动全链路） | 接入 ditto 的 OpenTelemetry 可观测 |
| Resumable Approval（可恢复审批流） | 完美契合「人工交易」：agent 产建议 → 人工审批 → 执行，SDK 原生支持 |

### 4.2 业界 AI 金融能力 Gap（原提 6 项之外必补/进阶）

| 业界 AI 金融能力 | 成熟度 | 原目标 | 建议 |
|---|:---:|:---:|---|
| 情绪/舆情分析 → 情绪因子/alpha（NLP 把新闻/社媒变 alpha） | 成熟 | 漏 | **必补**：AI 量化最经典应用，契合因子体系 |
| 可解释 AI / 决策解释 | 成熟 | 漏 | **必补**：人工交易刚需 |
| Text-to-SQL 对话式查询 | 成熟 | 投研隐含 | **补为独立能力**：投研低门槛入口 |
| RAG 私有文档库问答（研报/公告/纪要） | 成熟 | 投研隐含 | **补**：投研基础设施 |
| Resumable Approval 交易闭环 | 成熟(SDK 原生) | 漏 | **必补**：契合「非全自动」目标 |
| 回测/因子报告 LLM 解读 | 成熟 | 漏 | 补：低成本高价值（已有 factor-ic 报告） |
| 另类数据/财报文本挖掘 | 成熟 | 漏 | 补：与情绪因子协同 |
| 多模态（PDF/图表/K 线识别） | 中 | 漏 | 进阶 |
| 知识图谱/产业链关联（A 股轮动、风险传染） | 中 | 漏 | 进阶（A 股特色） |
| Forecasting 预测（宏观/波动率/基本面） | 成熟 | 宏观隐含 | 进阶 |
| 策略代码 AI 审计 | 中 | 漏 | 进阶（与「编写策略」对称） |
| 合规/异常检测 AI | 成熟 | 风控隐含 | 后置 |

### 4.3 整合后的 ditto AI 目标体系（四层演进，被动 → 主动）

```
L0 AI 基础设施（一次性打底）
  ├─ LLM 网关（多 provider 抽象：OpenAI/Anthropic/本地）
  ├─ Agent 运行时（OpenAI Agents SDK）
  ├─ 工具层（ditto 全部 API/数据 → function tools）
  ├─ 记忆（复用 Experience Memory）
  └─ 可观测（Tracing → OpenTelemetry）

L1 分析与解读（被动，最低门槛，最快出价值）
  ├─ 宏观/市场信息解读（RAG + chat）
  ├─ 情绪/舆情分析 → 情绪因子 ⭐新增
  ├─ Text-to-SQL 对话式数据查询 ⭐独立化
  ├─ RAG 研报/公告/纪要库问答 ⭐独立化
  ├─ 回测/因子报告 LLM 解读 ⭐新增
  ├─ 决策可解释（每个建议附理由）⭐新增
  ├─ 多模态（PDF 公告/研报图表/K 线图） ⭐进阶
  └─ Forecasting 预测（宏观/波动率/基本面） ⭐进阶

L2 建议与辅助（半主动）
  ├─ 仓位/买卖建议（agent 调 daily-decision + RiskGate guardrail）
  ├─ AI 辅助编写策略（DSL + LLM 生成）
  ├─ 策略代码 AI 审计 ⭐新增
  ├─ 个性化 robo-advisor（风险偏好定制）
  ├─ 知识图谱/产业链关联（A 股轮动） ⭐进阶
  └─ 合规/异常检测 AI ⭐进阶

L3 自主 Agent（主动，终极形态）
  ├─ 多 agent 投研（TradingAgents 模式：analyst/researcher/trader/risk）
  ├─ Resumable Approval 交易闭环（建议→审批→执行） ⭐新增
  └─ Agent 自主复盘/经验学习（接 Experience Memory）
```

---

## 五、分阶段优先级路线图

### 当前基线

综合功能完整度 **2.9★**。当前处于「**内部日频人工交易 Beta 前夜**」——live smoke 已证明 daily-decision 后端接通 + 结构化 blocked 空态（**非真实信号 ready**，受策略定义未发布阻塞）；数据治理/执行协议世界级；AI runtime(0★)/分钟级(0★)/组合优化(2.5★)/风控(2.5★) 是结构性短板。

### 阶段 A：日级人工交易闭环深化 ｜ 2.9★ → 3.5★ ｜ 对标聚宽/米筐日级

> ⚠️ **范围修订（2026-07-10 纠偏）**：阶段 A 已按「产品闭环优先」重新切分为 **R1-R4**（详见 `docs/superpowers/specs/2026-07-10-ditto-development-roadmap-design.md` + `docs/plans/2026-07-10-r1-implementation-plan.md`）。下表 A1-A6 现为**候选任务池**，不再作为单一第一批：R1 只取「策略发布 + EOD 闭环 + Daily Decision V2 + 前端真实态 + 手工复盘」；A3 组合优化 / A4 连续风控推 **R4**；fx/commodity promotion 推 **R2**；AI 基建推 **R5**。原 `phase-a-implementation-plan.md` 已降级为候选任务池。

| 工作项 | 内容 | 维度 |
|---|---|---|
| A1 | 数据 promotion：stock/macro/fx/commodity 从 experimental 提级（用已有 promotion 闭环，真实证据驱动） | ① |
| A2 | A 股撮合补全：涨跌停 limit_up/down + 手数取整 | ⑤ |
| A3 | 组合优化：引 `cvxpy`，实现风险平价 + 带约束均值方差 + 有效前沿 | ⑥ 2.5→3.5★ |
| A4 | 风控连续性：RiskGate 连续状态机 + typed audit 持久化 + 崩溃恢复 | ⑦ 2.5→3.5★ |
| A5 | 前端 production：ditto-app trading 域从 Wave1a 接线做到可用 | ⑩ |
| A6 | 修 Wave1a 两个后端 gap：`wave1_env.sh` 补 TUSHARE_TOKEN export + 策略定义 publish 流程 | — |

**里程碑 ①（修订）：内部日频人工交易 Beta** —— 每天可生成并复核真实 A 股信号、目标仓位、建议操作、风险提示，人工记录成交与偏差（**非「可商用」**，可商用是 R7 之后）。

### 阶段 B：AI 能力注入 ｜ ⑨ 0★ → 3.5★ ｜ 对标 OpenBB Copilot + TradingAgents

| 子阶段 | 内容 |
|---|---|
| B0 | L0 基础设施：LLM 网关 + OpenAI Agents SDK 运行时 + 工具层(ditto API→tools) + Memory(复用 Experience Memory) + Tracing→OTel |
| B1 | L1 分析解读：宏观/市场解读、**情绪因子(⭐alpha 切入)**、Text-to-SQL、RAG 文档问答、回测报告解读、决策可解释 |
| B2 | L2 建议辅助：仓位/买卖建议、AI 编写策略、策略代码审计、robo-advisor |
| B3 | L3 自主 agent：多 agent 投研、Resumable Approval 交易闭环、自主复盘 |
| B+ | 进阶全补：多模态、知识图谱、forecasting、合规 AI |

**里程碑 ②③④：AI 增强 → AI copilot → AI agent 平台。**

### 阶段 C：分钟级/盘中架构演进 ｜ ①⑤ 0★ → 3★ ｜ 对标 NautilusTrader

C1 分钟级 bar 存储 → C2 Synchronizer/TimeSlice 分钟 step → C3 event-driven 回测 → C4 盘中实时因子管线 → C5（可选）真实券商 adapter。

### 阶段 D：全球化/机构化 ｜ → 4.5★+ ｜ 对标 LEAN（北极星）

D1 多市场(港/美/期/期权) → D2 机构级(多账户/多租户/权限/审计) → D3 部署/认证/可观测产品化。

### 依赖与并行

```
A1─A6 (日级闭环) ──┬─→ A 完成【里程碑①】
                   └─→ B0 (AI 基建，依赖 A 的 API 稳定) ─→ B1 ─→ B2 ─→ B3【②③④】
A 完成后 ────────────────────────────────────────────→ C【⑤】
                                                              └─→ D【北极星】
```

### 两个关键洞察（R1 边界修订后）

1. **~~情绪因子提前到阶段 A 后期~~（已撤回）**：R1 严格不做 AI/情绪因子——AI 需依赖稳定的 Daily Decision + 报告 artifacts，否则变空心助手。情绪因子属 **R2/R3** 研究扩展期，届时作为 AI 投入产出比最高的桥接点。
2. **A3 组合优化 / A4 连续风控 推到 R4**：R1 只需 Daily Decision 里的日频风险摘要 + 可解释阻塞原因；完整 cvxpy 优化器 + 连续风控状态机属 R4。R1 **不并行启动 AI 基建（B0/B1）**。

### 离产品的差距（星级阶梯）

| 里程碑 | 星级 | 距今 | 业界定位 |
|---|:---:|---|---|
| 当前 | 2.9★ | — | 机构级数据中台 + 严谨回测 |
| 里程碑①（阶段 A） | 3.5★ | ~2-3 月 | 可商用日级 A 股平台（≈聚宽/米筐日级 + 治理优势） |
| 里程碑④（+B） | ~4.2★ | +3-6 月 | AI agent 量化平台（≈OpenBB Copilot + TradingAgents） |
| 里程碑⑤（+C） | ~4.5★ | +3-6 月 | 含盘中的全功能平台（≈NautilusTrader） |
| 北极星（+D） | ~4.7★ | +12-18 月 | 全球全品类 AI 量化（≈LEAN，AI/A 股/治理差异化） |

> **诚实结论**：完整对标 LEAN(5★) 是十几年积累，ditto 做完 A-D 约 4.5-4.7★，永远在追赶。但 ditto 在 **AI 原生、A 股本土、数据治理严谨度**三维度有 LEAN 没有的差异化——这是护城河，不必在 LEAN 强项(多资产/社区)上硬拼。

### 推荐立即行动（YAGNI）

1. **阶段 A 全量启动**（巩固日级主线，A1-A6 多为「补全」性价比最高）
2. **A 后期插入情绪因子**（AI 增强 Phase A）
3. **B0/B1 紧随**（AI 打底 + 投研解读/情绪因子，回报最高）
4. C/D 暂不启动（先确保抽象留扩展点）

---

## 六、业界对标来源

- [QuantConnect LEAN](https://www.quantconnect.com/) — 全功能机构级平台（多资产、broker built-in、275k+ 社区）
- [NautilusTrader](https://nautilustrader.io/) — Rust 内核 event-driven，tick+bar 盘中天花板
- [QLib (Microsoft)](https://github.com/microsoft/qlib) — AI 量化研究平台，A 股(CN)/美股，强 ML pipeline
- [OpenBB Copilot](https://openbb.co/blog/creating-an-ai-powered-financial-analyst/) — AI 分析师嵌入终端，chat + 全数据集访问
- [TradingAgents](https://github.com/TauricResearch/TradingAgents) — 多 agent LLM 交易框架（80k★），analyst/researcher/trader/risk 分工
- [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) / [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) — 金融多 agent 平台 / 金融 LLM 骨干
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) — Tools/Handoffs/Guardrails/Sessions/Tracing/Resumable Approval
- [RavenPack: AI in Finance 2026](https://www.ravenpack.com/blog/ai-in-finance-2026-the-autonomy-era) — 情绪/另类数据/自主 agent 行业报告
- [Stanford HAI 2026 AI Index](https://hai.stanford.edu/ai-index/2026-ai-index-report) — AI 能力宏观趋势
- [ScienceDirect: sentiment-based forecasting](https://www.sciencedirect.com/science/article/abs/pii/S0275531926000565) — 情绪预测模型学术验证
