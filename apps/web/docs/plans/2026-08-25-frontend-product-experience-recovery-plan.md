# Ditto 前端产品体验恢复计划

> 日期：2026-08-25<br>
> 状态：待执行<br>
> 目标分支基线：`codex/r1-r5-frontend-completion@a54122a0dcf3a1c3ed58a510ee2c37029210008c`<br>
> 上游主路线图：[Ditto 统一产品路线图与执行计划](https://github.com/cosmos-arc/ditto/blob/main/docs/plans/2026-08-25-integrated-product-roadmap.md)<br>
> 定位：统一路线图的前端专项施工图；保留数据接线与工程底座，以已批准原型为冻结基线，重做 React 呈现层并恢复完整交互。

## 1. 结论

当前分支应定义为“R1–R5 功能接线稿”，不能定义为“前端产品完成版”。

仓库已经具备成熟的产品架构、28 个高完成度原型、设计 token、页面合同、API hooks、路由和较强测试底座；主要问题不是缺设计，而是 React 实现没有把原型作为不可移动的验收基线：mock 与 live 使用不同页面结构，部分 live 页面仍是占位，视觉审计只收集截图和几何数据但不执行差异阈值，最终造成工程门禁全绿而产品体验严重漂移。

推荐方案不是推倒重写，也不是继续逐页打补丁，而是：

1. 冻结现有批准原型，不允许在对应 React 页面完成前同步修改验收基线。
2. 保留 routes、API client、generated types、TanStack Query hooks、Zustand 状态和业务测试。
3. 把每个页面拆成唯一呈现组件和数据容器；mock/live 只切换数据源，不切换 DOM 结构。
4. 先恢复 Shell 与 6 个核心交易闭环页，再按 Research、Markets、Agent/Platform 推进。
5. 把视觉审计改成真正会失败的门禁；固定数据、字体、时间和视口后执行几何与像素阈值。

## 2. 当前基线与完成度

### 2.1 已有资产

- 5 个产品域：Home、Markets、Research、Trading、Platform。
- 33 条当前 IA 审计路由；页面合同中 31 条标记为 implemented。
- 28 个 active route prototypes，已有 desktop / compact / narrow 三视口证据。
- 7 类 Shell：Command Center、Analytical、Radar、Catalog、Object Hub、Studio、Ops Console。
- 9 层设计 token、深浅主题、3 档密度、A 股红涨绿跌语义。
- React 19、TanStack Router / Query、Zustand、Radix、AG Grid、Recharts / lightweight-charts。
- `bun run check` 通过：165 个测试文件、1426 个测试；架构与 Harness 门禁通过。
- route audit 通过，WCAG gating color pairs 无失败，token export 校验通过。

### 2.2 实际产品完成度判断

| 维度 | 估计完成度 | 判断 |
|---|---:|---|
| 产品定位与信息架构 | 85% | 五域、核心链路、页面模式和优先级清楚 |
| 原型与视觉语言 | 90% | 原型质量较高，足以作为正式实现基线 |
| 工程与测试底座 | 80% | 路由、类型、hooks、门禁较完整 |
| 路由/功能接线 | 70% | 多数路由存在，但 live 深度不一致 |
| live 页面可用性 | 45% | Home、Markets、Platform live 仍是 prototype-only；其他页深浅不一 |
| React 视觉还原度 | 30% | 核心壳层、信息层级和工作面比例明显漂移 |
| 交互与 overlay 完整度 | 35% | 23 份页面合同仍包含 79 个 `PrototypeOnlyOverlay` |
| 发布可用性 | 40% | 工程检查绿，但核心工作流和视觉验收未闭环 |

综合产品可交付完成度约为 **45%–55%**。这不是代码量比例，而是用户能否用它完成稳定量化工作流的判断。

### 2.3 已确认的主要偏差

1. **mock/live 双 UI**
   - Home、Markets、Platform 在 live 模式直接显示 `PrototypeOnlyEmpty`。
   - Trading 在 mock 模式使用原型式工作台，在 live 模式插入另一套 scope form、Daily Decision workspace 和通用面板。
   - Research live 页面被收缩为实验与审查两块，丢失原型中的 Factor Monitor 主工作面。

2. **视觉门禁假绿**
   - Agent Console desktop 审计已经记录：Header 下移 68px、Tabs 下移约 100px 且宽度少 1272.64px、主区整体下移约 95.84px。
   - 审计脚本只截图、记录 selectors 和 metrics，不执行页面合同声明的 `pixelDiffRatio` 或 slot threshold。
   - 因此“没有缺 selector”被误当作视觉通过。

3. **合同状态语义失真**
   - 28 个页面合同标记 `visualAuditStatus=verified`，但它主要证明 prototype 自身通过，不证明 React 与 prototype 一致。
   - `/research/alpha` 合同标记 React route missing；route audit 的硬编码 IA 列表却未包含该路由，仍报告 33/33 通过。

4. **页面结构债务**
   - `agent-console-page.tsx` 达 1438 行，并在页面内部重新实现 Header、Toolbar 和三栏工作台，没有复用既有 Studio Shell 比例。
   - 页面级条件分支、数据映射、空态、工具栏和视觉结构混在一起，后续很容易再次出现 mock/live 漂移。

5. **交互完成度不足**
   - 79 个 overlay 仍是 prototype-only，涉及筛选、对比、详情、确认、发送到研究、回测配置等真实工作流。
   - Loading / empty / failed 虽有测试，但不少 live 状态退化为大片空白或通用面板，没有保持原型工作面稳定。

## 3. 目标产品体验

### 3.1 用户、任务与气质

- 核心用户：单人全栈量化交易者；研究、交易、风控、运维角色在同一工作台切换。
- 核心任务：把市场、研究和组合证据转成可信的下一步决策，并沿同一上下文执行或复盘。
- 产品气质：克制、可信、敏锐；专业工作台，不是 SaaS 后台、卡片墙、AI 聊天壳或金融大屏。

### 3.2 视觉基线

不另起品牌系统，沿用 Graphite Studio：

| 角色 | Token 值 | 用途 |
|---|---|---|
| Graphite App | `oklch(0.166 0.010 253)` | 应用背景 |
| Graphite Panel | `oklch(0.184 0.011 253)` | 主工作面 |
| Primary Text | `oklch(0.940 0.004 253)` | 主要判断与数据 |
| Lapis | `oklch(0.640 0.120 235)` | 全局交互与 Platform |
| Brass | `oklch(0.760 0.055 74)` | Home / Trading 决策强调 |
| Research Purple | `oklch(0.732 0.095 300)` | Research 域签名 |

字体继续使用四角色体系：UI 使用 Inter + 中文 fallback，标题 Geist Sans，金融数字 JetBrains Mono，代码 Geist Mono。

固定壳层基线：Rail 56px、Header 68px、Status 24px；主工作面承担 55%–70% 注意力，辅工作面 20%–30%。不新增卡片墙，不用渐变/发光制造“金融感”。

### 3.3 签名交互：Decision Spine

全产品保留同一条判断语法，而不是新增一个到处占位的大组件：

`当前判断 → 关键证据 → 影响范围 → 下一步动作`

- Home：今日主决策与跨域优先级。
- Trading：readiness、风险证据、可执行动作。
- Research：因子状态、退化证据、进入诊断/回测。
- Agent：Objective、Tool、Evidence、Guardrail、Artifact、Approval。

不同页面可用 Banner、表格联动、时间线或 Inspector 表达，但信息顺序和动作层级保持一致。

## 4. 前端实现架构

### 4.1 保留与重做边界

保留：

- TanStack Router 路由与 URL 状态。
- API client、OpenAPI generated types、业务 DTO。
- TanStack Query hooks、mutation 与缓存策略。
- Zustand UI preferences。
- 已验证的业务规则、状态机、A 股交易语义测试。
- 设计 token、基础 UI primitives、图表数据适配层。

重做：

- 页面呈现层、Shell composition、workspace 比例与视觉层级。
- mock/live 分叉页面。
- PrototypeOnly 页面和 overlay。
- 不会失败的视觉审计与错误的 contract 状态语义。

### 4.2 单一呈现树

每个页面按以下边界实现：

```text
API / Fixture
    ↓
Query hooks
    ↓
PageModel mapper
    ↓
PageContainer（数据、URL、mutation）
    ↓
PageView（唯一 DOM 与视觉结构）
```

约束：

- `VITE_USE_MOCK` 只能选择 adapter / fixture，不能选择另一套 PageView。
- loading / empty / failed / stale 在固定 slot 内渲染，不改变 Shell 和主辅工作面几何。
- PageView 不直接发请求；Container 不定义另一套视觉结构。
- 复杂页面拆为 `source / main / inspector / activity / status` 等与 Page Contract 一致的区域组件。
- Agent Console 从 1438 行单文件拆成 Run List、Evidence Spine、Inspector、Toolbar、Overlays，但不引入新全局状态框架。

### 4.3 最小共享组件

只增加能消除真实重复的组件：

- `PageStateBoundary`：在现有 slot 内处理 loading / empty / failed / stale。
- `PrimaryAnswer`：统一判断、证据、影响、动作语法；允许各 Page Pattern 自定义视觉。
- `WorkspaceToolbar`：页面动作和全局 Header utility 分离。
- `InspectorPanel`：选中对象详情、证据和动作容器。
- `BottomTray`：日志、验证、运行状态；仅 Studio / Ops / Agent 使用。

不建设新的通用 schema renderer、不做低代码页面引擎、不引入第二套组件库。

## 5. 执行波次

### M0 — 冻结基线与修复验收（1–2 人日）

目标：先让“完成”这个词重新可信。

任务：

- 给当前批准 prototype 基线记录 commit/tag 与截图哈希。
- 实现 React vs prototype 固定 fixture 对比；实施期间禁止修改对应 prototype。
- 视觉审计对缺 selector、slot geometry 超阈值、pixel diff 超阈值返回非零。
- route audit 从 page contracts / edition manifest 生成，补入 `/research/alpha`。
- 将 `visualAuditStatus` 拆成 `prototypeVerified` 与 `reactParityVerified`。
- 建立页面完成看板：route、live data、visual parity、states、overlays、workflow 六列。

验收：故意移动 Header 8px 或删除主 slot，视觉门禁必须 RED。

### M1 — Shell 与视觉骨架（3–5 人日）

目标：全站先回到同一个专业工作台。

任务：

- 固定 Rail、Header、utility 顺序、Status Bar、domain signature。
- 校准 7 类 Shell 的 grid、scroll owner、panel width 和 responsive degradation。
- 清理页面内重复 Header 与 Toolbar；Agent Console 回归 Studio Shell。
- 校准字体、数字、边线、surface、密度和 focus-visible。
- 选择 Home、Trading、Research、Agent 四页做 Shell golden screenshots。

验收：4 页 shell 几何误差 ≤4px；无双 Header、全页滚动和状态栏遮挡。

### M2 — 日常交易闭环（8–12 人日）

页面顺序：

1. Trading Overview
2. Signals Inbox
3. Orders Ledger
4. Portfolio
5. Risk Center
6. Home

任务：

- 将 Daily Decision V3 数据绑定到冻结的 Trading 原型布局。
- 恢复 Session Strip、Primary Answer、Signal-to-Order pipeline、PnL、持仓、风险、订单和信号联动。
- Signals 恢复 Table + Detail + AI Interpretation + Risk Officer + Evidence Chain。
- Orders、Portfolio、Risk 使用相同 account / strategy / trade date 上下文。
- Home 使用真实聚合投影；后端缺项允许局部 unavailable，不允许整页 prototype-only。
- 完成该闭环涉及的所有确认、详情和复盘 overlay。

验收场景：

- Ready / Review / Blocked 三种 Daily Decision。
- Signal → 人工复核 → Order preview → Ledger → Position / Risk 反馈。
- T+1、涨跌停、stale、券商断开均有明确非颜色表达。
- 6 页 desktop / compact / narrow 视觉通过，关键动作键盘可达。

### M3 — 研究闭环（8–12 人日）

页面顺序：

1. Research Workspace
2. Factor List / Factor Analysis
3. Strategy List / Detail / Studio
4. Backtest List / Result
5. Experiments / Reviews
6. Universe / Regime
7. Alpha Explorer

任务：

- 恢复 Research 的 Factor Monitor 主工作面，实验/审查回到辅工作面。
- Strategy Studio 保持 Form / Code / Guided 的同一 Studio 语法。
- Backtest Result 恢复收益、风险、交易、暴露与诊断主次层级。
- 新增缺失的 `/research/alpha` React 路由，Agent Console 只负责 Run 治理，Alpha Explorer 负责候选审阅。
- 完成 compare、回测配置、因子采纳、artifact preview 等核心 overlay。

验收场景：Factor 退化 → 诊断 → Strategy 修改 → Backtest → Review；上下文不丢失。

### M4 — 市场发现闭环（6–9 人日）

页面顺序：

1. Cross-Market / A-Shares
2. Screener
3. Watchlist
4. Instrument Hub
5. Intelligence / Calendar

任务：

- 移除 Markets live prototype-only；真实市场数据进入 Radar 原型布局。
- 恢复跨市场矩阵、A 股结构扫描、Screener table/detail、Watchlist 与 Instrument Hub 上下文连续性。
- 完成筛选、列管理、比较、加入观察、发送研究、新闻/公告详情 overlay。
- 保留 A 股红涨绿跌，并通过正负号、文本和形状提供第二表达维度。

验收场景：市场扫描 → 筛选 → 标的详情 → Watchlist / Research，URL 携带对象与来源上下文。

### M5 — Agent 与 Platform（5–8 人日）

页面顺序：

1. Agent Console
2. Platform Ops
3. Data Products
4. Settings

任务：

- Agent Console 按冻结原型重构为 source / evidence / finding / inspector 四区，并保留真实 Run、Campaign、Approval API。
- Platform live 绑定真实 health、provider、pipeline、alert、log 投影，移除整页 prototype-only。
- 仅保留必要的高风险确认和 Agent 审批；不扩展复杂权限、角色或安全隔离 UI。
- Settings 只服务数据源、券商、模型/工具必要配置，不发展为后台大全。

验收场景：Run → Evidence → Approval → Artifact / Signal；服务 disabled / degraded / running / failed 状态稳定可读。

### M6 — 全站收口与发布验收（5–8 人日）

任务：

- 清零 active pages 的 `PrototypeOnlyEmpty` 和核心工作流 `PrototypeOnlyOverlay`。
- 校准空态、错误、stale、partial、blocked、running 与 reduced motion。
- 处理 1200px narrow；小于工作站下限只提供明确 guard，不建设移动端交易产品。
- 收口图表 tooltip、crosshair、legend、数据新鲜度和数字对齐。
- 做一轮 3 小时连续使用审查：视觉疲劳、密度、滚动、选中状态、返回路径。
- `bun run ci`、全页面视觉矩阵和人工核心路径验收。

## 6. 每页完成定义

一个页面只有同时满足以下条件才可标记完成：

- 路由存在且可从产品导航到达。
- live API 可用；局部缺数据有真实 empty / unavailable 状态。
- mock 与 live 使用同一 PageView 和 DOM 结构。
- 5 秒内给出唯一 Primary Answer。
- 主工作面、辅工作面和 selected-object 联动成立。
- loading / empty / failed / stale 以及页面专属状态完整。
- 合同要求的核心 overlay 可触发、可关闭、动作闭环。
- desktop 1536×900、compact 1366×768、narrow 1200×800 视觉门禁通过。
- 键盘焦点、reduced motion、关键状态非颜色表达通过。
- 目标测试、`bun run check` 与 milestone 视觉审查通过。

## 7. 视觉验收规则

### 自动门禁

- 固定 fixture、系统时间、字体与动画。
- Shell hard geometry：Rail/Header/Status 误差 ≤4px。
- 固定宽度 panel：误差 ≤4px；content-driven slot 的 x/y ≤8px，宽高差 ≤3%。
- 固定 fixture 截图 perceptual diff 初始目标 ≤5%，单页稳定后收紧至 ≤2%。
- 缺少 required selector、console error、page error 直接失败。
- 动态图表只 mask 数据路径，不 mask 坐标、legend、toolbar 和容器几何。

### 人工审查

- 页面第一眼焦点是否与原型一致。
- 是否形成一个主工作面，而不是均匀卡片墙。
- 数据、证据、影响和动作的层级是否清楚。
- live 数据较少或失败时，页面是否仍保持专业工作台结构。
- 连续切换域时是否像同一个产品，而非多套后台拼接。

## 8. 明确不做

为避免过度设计，本轮不做：

- RBAC、复杂角色矩阵、多租户、组织/空间隔离。
- 微前端、SSR/RSC、第二套设计系统或组件库。
- Schema-driven 通用页面引擎、低代码搭建器。
- K8s、复杂发布后台、完整审计中心。
- 多 Agent 可视化编排器和自定义 Pipeline builder。
- 独立移动端；仅保证 narrow workstation 降级与小屏 guard。
- 为追求“全平台一致”而把不同任务页强行做成同一模板。

## 9. 推荐启动切片

先执行 M0 + M1，然后以 Trading Overview 作为第一张真正完成的 React 页面。

原因：它同时覆盖 Shell、Primary Answer、图表、表格、风险、状态、右 Rail、Bottom Tray 和真实 R4 数据，是检验新架构能否避免 mock/live 双 UI 的最小但完整样本。Trading 通过人工确认后，再复制同一方法到 Signals、Orders、Portfolio、Risk 和 Home；在第一张页面确认前，不批量改 28 页。

## 10. 预计投入

- 单人全职并复用现有资产：约 35–54 人日。
- 推荐按 6–8 周推进，每个 milestone 独立可验收。
- 若只先完成日常交易闭环（M0–M2）：约 12–19 人日，可先得到可持续使用的核心产品。

时间估计不包含新增后端展示 API；若页面所需投影缺失，应优先补窄 DTO，不允许前端自行拼接多个内部接口或用 mock 伪装完成。
