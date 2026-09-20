# 2026-09-17 设计队列裁决记录

> 状态：原裁决保留；核心旅程与执行顺序已由 2026-09-20 维护者裁决替代（见下文）。其他待审条款未默认通过。
> 来源：2026-09-16/17 全景评审（六路调研 + 业界对标 + 数据源两轮调研）后续
> 跟踪：GitHub epic cosmos-arc/ditto#192；本文件为裁决的仓库侧持久化记录

---

## 2026-09-20 核心旅程与顺序修订

维护者已确认[核心旅程与建设顺序](https://github.com/cosmos-arc/ditto/issues/242)的三项决定：

- 股票与 ETF 均属首期完整旅程，可分批交付。股票覆盖选池、研究、组合、Paper 与复盘；ETF 覆盖暴露选择、工具比较、配置与复盘，不以行情页代替。
- 正常旅程无需手填内部 ID/hash/JSON 或 CLI 救援；高级导入保留。真实状态、跨页上下文和失败恢复必须可用，页面存在与视觉 parity 不能代替用户任务验收。
- 数据与恢复优先；核心交互、图表语义和数据取证可以并行。ML 的数据与研究协议就绪即可启动，不等待全部布局记忆、右键、Toast 或 MCP。前向使用独立记录，不追溯改变旧发布 Gate。

本修订替代下文“先还全部 parity 债，再谈新交互”与第四节的全局串行顺序；交互效率票按上述核心旅程先交付，其余既有范围保留为后续批。图表已合入切片不重新实施。ETF 估值收益、数据准入、ML/文本协议、Agent 边界和架构简化仍由各自开放决策票处理；本次未批准这些剩余建议。

## 一、设计史吸收结论（北极星）

本仓库设计决策史（视觉宪章、20+ specs、D1–D16、页面合同、Primary Answer 合同）为机构级治理资产，方向几乎全部正确，**不重新设计，只执行**。当前债务不在设计层而在 React 执行层的 parity 债：spec 已定义、React 未兑现——全应用仅 1 张图表、⌘K 假按钮、五个原型→React 遗留 Epic 未动、可调面板审计 2.0/10、StatusBar 硬编码假数据。

执行策略：先还 parity 债，再谈新交互。全部 UI 票验收统一加 `reactParityVerified` 硬门，不再允许「结构闭环」掩盖「体验空缺」。即便不考虑成本也不做：docking 全可定制引擎（单操作者收益不抵复杂度）、推翻五域 IA、第二套设计系统、更多无实施票绑定的 spec。

### 设计流程校准（四项）

① 设计起点=图表工作台；② 交付形态=代码原型先行（复用 /showcase 机制）；③ 视觉基线=深化 Graphite Studio（新增 chart.* 语义层）；④ 工作台形态=面板可调宽档。

### 遗留 Epic 归并

| 原型→React 遗留 Epic | 归并到 |
| --- | --- |
| Chart Cockpit | #193 + #194（设计定稿见 `apps/web/design/specs/21_chart_cockpit_design.md`） |
| Command Action Bus | #195 |
| Workspace Memory | #195 |
| Context Menu | #195 |
| Toast System | #195 |

20 号交互审计（2026-04-30）中所有「延后到 React 层」条目（图标治理、ContextDisclosureSection、Bottom Tray 状态机、react-resizable-panels 安装）自 2026-09-17 起视为已批准，纳入 #195 验收范围。

## 二、各票裁决摘要

### #195 交互效率（设计定稿）

⌘K 真接线（导航=页面+对象搜索，动作=创建/发起/偏好，频率排序）；通用 EntityPicker 替换全部手填内部 ID/粘贴 JSON；`react-resizable-panels` 落地 Workspace Memory（约束按 20 号审计表：Rail 固定 48–56px、右栏 170px–40% viewport 可折叠、主区 ≥40%），localStorage 页面级持久化；右键最小集（图表/表格行/对象页 header）；Toast=L1 反馈统一；StatusBar 接真实 healthz/readyz 并删除硬编码假值。

### #197 条件式 Screener（设计定稿）

**run-first 防退化**为首要约束（实施计划 §24 已注册「选股工作台退化为筛选器」风险）：条件构建器的产物是可保存、可比较、可重放的 SelectionSpec/Run（带 reason code 与排除证据链），不是临时结果页。条件字段分组映射既有 102 FactorSpec 的 12 类；PIT 合格列才可入条件；结果表为 Analytical 子类型；不做自然语言输入（留给 D17 会话层）。

### #198 结构化会话式研究交互（新增 D17 裁决）

按 §18.2 重开程序记录；P2「非 AI Chat UI」保留且不弱化。裁决文本：

1. 会话 = 业务上下文锚定的多轮 run 容器；每轮仍是独立可审计 run（事件链、预算、审批、grounding 逐轮完整）。
2. 跨轮只携带结构化上下文（上下文对象 + 上轮 evidence_refs 引用），不携带自由文本对话状态。
3. UI = 研究侧栏内 run 序列时间线 + 每轮证据块（facts/interpretations/uncertainties + evidence_refs）；禁止社交气泡与自由对话流。
4. 工具 allowlist 按会话首个上下文锁定；跨域工具请求触发显式换上下文。
5. 会话粒度 SSE，语义不变（重放持久化事件、不执行工具）。

实施边界：eval 增加会话类 case 集（上下文保持、跨会话越权、证据引用篡改）；后端仅新增会话容器与轮间引用，不改 Agent 运行时治理内核。

### #201 治理内截面 ML 管线（设计定稿）

与 IA spec §6.7「ML 能力保留，但不在 v1 作为一级重页面」对齐：无新页面、无新域、无 ML 平台化。候选类型 `model_candidate`：特征矩阵快照（PIT 白名单列，内容哈希）→ 训练器（首期 LightGBM ranker + 线性 baseline）→ 预测进既有评估；walk-forward fold 内训练、purge/embargo 照常；holdout/PBO/trial ledger/promotion gates 零豁免；模型卡片为内容寻址 artifact。future-sentinel 测试为合并硬门；新增生产依赖（lightgbm/sklearn）按授权规则单独确认。

### #202 LLM 文本因子线（设计定稿）

四段管道：公告/研报快照（knowledge_date=公告时间）→ 打分器（首期本地 FinBERT2 类模型，LLM 批量评估为受控备选）→ alternative 类 FactorSpec 注册 → IC/分层/holdout 既有管道。边界：不做通用 RAG/聊天/开放 Web 抓取；打分可重放（模型版本+输入哈希）；原文存 artifact 目录不进 OLTP。数据前提：优先 Tushare 官方加购（研报包 500 元/年；公告先试巨潮 webapi），不新增数据源。

## 三、ML 与旧裁决关系确认

IA spec §6.7 拒绝的是「ML 平台成为 v1 主战场/一级重页面」，非 ML 能力本身。#201 形态（模型候选进既有实验协议）与旧裁决一致，无需重开；实施守住「不建 ML 一级页面」。

## 四、原执行顺序（已由 2026-09-20 决定替代）

#200（Tushare 档位）→ #193 切片 #209→#210/#212 并行 → #195 → #194/#196/#199 → #198/#201/#202。图表工作台完整设计与切片见 `apps/web/design/specs/21_chart_cockpit_design.md` 与 issue #208/#209–#215。
