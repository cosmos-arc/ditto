# Ditto Edition Review 分析

> 日期：2026-04-28
> 范围：`docs/designs/specs/`、`docs/designs/specs/prototypes/`、页面合同、原型门禁、27 个页面标准/紧凑视口截图
> 模式：`/ditto-design-cycle --edition-review` + 设计大师视角审阅 + 业界最佳实践对标

## 结论

当前 Edition v1 已经从“页面集合”进入“专业量化工作台系统”的阶段。27 个活跃原型在 IA、Shell、Page Pattern、状态覆盖、Overlay 覆盖和 Chrome 合同上基本成立，逐页视觉审查与自动门禁均未发现阻断级问题。

本轮更适合继续做“体验手感与系统可信度”的精修，而不是大改信息架构。下一阶段最值得投入的是：

1. 把 Studio / Ops 的底部日志与状态栏做成可折叠、可调整高度的 Bottom Tray，避免紧凑视口下遮挡工作面。
2. 给热力图、相关矩阵、趋势条补充非颜色编码：标签、边界、纹理或符号，降低色觉依赖。
3. 为 Light mode 和 Comfortable density 建立代表页视觉审计，不只验证交互状态。
4. 增强全局 Command 的可发现性，保持 icon-only 的克制，同时在 hover/focus/open 态露出 `Ctrl+K` 和作用域。
5. 将评分体系从“页面完成度”升级为“专家工作流效率”，避免 9.x 分数膨胀掩盖体验细节。

## 审阅证据

### 自动验证

已运行：

```bash
bun test scripts/prototype-design-consistency.test.ts scripts/prototype-view-preferences.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-a-shares.html --out-dir test-results/edition-gates/a-shares
bun test scripts/prototype-design-consistency.test.ts scripts/prototype-view-preferences.test.ts scripts/page-orders-ledger-prototype.test.ts scripts/page-agent-console-prototype.test.ts
bun run check
```

收尾验证结果：

- targeted 原型测试：84 pass / 0 fail
- `bun run check`：136 个测试文件通过，1501 个测试通过

批量 Edition Gates 结果：

- 活跃原型：27
- 失败页面：0
- 阻断问题：0
- 非阻断问题：0
- 视口：1536x1080、1366x768

跨页指标：

| 指标 | 结果 |
|---|---:|
| 活跃页面 | 27 |
| Shell 分布 | radar 2 / ops-console 4 / command-center 1 / catalog 8 / analytical 6 / object-hub 4 / studio 2 |
| Overlay | 93 |
| Tab | 69 |
| 状态变体 | 278 |
| Manifest 平均分 | 9.62 |

视觉审查资产：

- 全页对照图：`test-results/edition-review/per-page/*.png`
- 标准视口：1536x1080
- 紧凑视口：1366x768
- 审查方式：逐页检查首屏任务、主工作面、右侧 rail、底栏/状态栏、筛选/Tab/Overlay 入口、视觉层级、响应式压缩和跨页一致性

### 已修复的小问题

发现 `page-a-shares.html` 存在负字距 fallback：

- `letter-spacing: var(--letter-spacing-tight, -0.01em)`
- `letter-spacing: var(--letter-spacing-heading, -0.02em)`

同时现有测试只匹配 `letter-spacing: -...`，漏掉了 `var(..., -...)`。本轮已补强测试并将 fallback 修正为 `0`。

## 业界最佳实践对标

### 1. 系统状态与信任

NN/g 的可用性启发式强调系统应及时告知用户当前状态，并用一致反馈建立信任。Ditto 在这点上做得很强：Home、Agent Console、Platform、Orders 都有持续状态条、运行态、延迟、风险与审批状态。

待加强点是“状态层级过多时的主次”：部分页面同时出现 pulse、status bar、右栏状态、badge、日志，紧凑视口中会让用户难以判断哪一处是当前最关键状态。

参考：https://www.nngroup.com/articles/ten-usability-heuristics/

### 2. 可访问性与颜色表达

WCAG 2.2 覆盖 Use of Color、Non-text Contrast、Focus Visible、Focus Not Obscured、Target Size 等要求。Ditto 的 token 化和双重表达方向正确，但数据可视化仍应进一步减少“只看红绿热度”的依赖。

Carbon 也强调：标准文本 4.5:1、大文本和 UI 图形 3:1；不要只靠颜色表达含义。对金融终端而言，这意味着涨跌色必须配合正负号、标签、方向、线型或图例。

参考：

- https://www.w3.org/WAI/WCAG22/Understanding/
- https://carbondesignsystem.com/guidelines/accessibility/color/

### 3. Dashboard 与数据可视化

Carbon Dashboard 指南强调先按重要性建立强层级，减少干扰指标，跨图表保持颜色一致；探索型 dashboard 应支持搜索、排序、过滤、下钻与联动。Ditto 的主表 / 右栏 / 底栏工作面结构符合这个方向。

待加强点在于“联动可见性”：selected row 驱动右栏和底栏已在规范中明确，但若要达到专业终端质感，原型需要更显式地展示选中对象如何影响图表、日志和建议。

参考：https://v10.carbondesignsystem.com/data-visualization/dashboards/

### 4. 图表配色与渐变纪律

Carbon 的数据可视化配色强调 categorical、sequential、diverging palette 的区分，且提醒多个渐变往往不易访问。Ditto 的市场语义红涨绿跌是业务约束，但应把红绿只用于业务方向，把相关性、风险、系统、数据质量放回各自语义域，避免跨域混色。

参考：https://carbondesignsystem.com/data-visualization/color-palettes/

## 五维评分

| 维度 | 评分 | 判断 |
|---|---:|---|
| 克制度 | 8.8 | 灰阶骨架、窄 rail、低装饰是成熟的；部分状态色、边框和底部日志仍略抢注意力。 |
| 一致性 | 9.4 | Header Utility、View Preferences、Shell 合同已经很稳；局部页面仍有自定义 CSS 语法，需要继续收敛。 |
| 高级感 | 8.9 | 专业终端气质明确；下一步高级感不来自更多效果，而来自遮挡治理、响应式状态和数据图例纪律。 |
| 品牌方向 | 9.2 | Linear/Vercel 的克制 + Bloomberg/quant desk 的专业感方向成立；AI/Agent 已融入工作台语法。 |
| 信息效率 | 9.3 | 密度、状态、表格和右栏效率高；紧凑视口下的 Bottom Tray、Right Rail 优先级还可优化。 |
| 综合 | 9.1 | 已达高质量 edition，可进入体验精修与 React 对齐阶段。 |

## 当前优势

### IA 与 Shell 成熟

5 个一级域、27 个路由、7 类 Shell、8 套 Page Pattern 已形成清晰系统。不同页面不是强行长一样，而是通过同一套工作台语法保持统一：导航后退、上下文靠前、主工作面明确、右栏承接上下文。

### Chrome 合同变清晰

全局 Header Utility 顺序固定为 command / copilot / notifications / help / account。Theme 和 density 收敛进 View Preferences，不再污染 rail 或 header。这个方向符合专业工具预期：高频工作面不被低频偏好控件打断。

### 状态覆盖非常充分

93 个 Overlay、278 个状态变体说明页面不是静态展示稿，而是有 loading、empty、failed、stale、selected、running、approval 等完整状态意识。这是 Ditto 区别于普通 dashboard 的关键。

### 数据工作面优先级正确

大部分页面都能看出主表、主图、队列、右侧 detail / logs / inspector 的工作角色。Orders Ledger、Agent Console、Platform Settings 是当前最接近“可长期使用工具”的页面。

## 逐页审查

> 结论等级说明：P1 为下一轮必须优先修的体验问题；P2 为高级感、效率和一致性精修；P3 为可进入后续 React 对齐阶段的增强。

| 页面 | Shell | 视觉与风格一致性 | 交互与页面设计 | 待加强方向 |
|---|---|---|---|---|
| Cross Market | radar | Radar 语法成熟，矩阵、右栏、顶部状态与市场域一致；红/绿/青的业务语义清楚。 | 首屏能回答跨市场风险与相关性，Tab 和右栏联动方向正确。 | P2：紧凑视口下底部相关性/宏观内容露出不足；相关矩阵继续强化 legend、正负标记和强相关边界。 |
| Platform | ops-console | 工程控制台气质强，状态色、任务卡、右侧系统 rail 与平台域一致。 | 健康、任务、配额、日志形成可诊断闭环。 | P2：右栏警告、日志、任务状态同时出现时主次略密；建议统一 warning 层级和“下一步动作”位置。 |
| Home | command-center | 首页不是营销页，而是指挥台，方向正确；全局 pulse、工作队列和市场状态统一。 | 首屏入口清楚，适合高频回到总控。 | P2：紧凑视口中 pulse 卡片略拥挤，活动流下移；建议强化“当前最该处理的一件事”。 |
| Markets Screener | catalog | Catalog 模式稳定，表格、筛选、右栏详情和动作按钮保持系统风格。 | 条件筛选、选中行、右栏解释链路成立。 | P2：筛选/criteria 区域偏高，右栏动作色略抢；建议把低频筛选折叠到高级条件。 |
| Research | analytical | 研究页面非常稳，主列表、分析摘要、右栏说明形成克制的研究工作面。 | 选中对象到右栏和分析 band 的路径清楚。 | P2：可再显式展示来源置信度、更新时间和选中对象如何影响下方图表。 |
| Trading Overview | analytical | 执行工作台的紧张感成立，风险、仓位、订单状态的颜色语义清楚。 | 快速下单、状态提醒和风险提示具备专业交易场景的防错意识。 | P1/P2：红色风险 CTA 视觉权重很高，需配套撤销/确认/限价保护等防错交互说明。 |
| Instrument Hub | object-hub | 对象页气质成熟，图表、关键指标、右栏事件统一，首屏重点明确。 | 从标的摘要到走势、事件、动作的流转顺。 | P2：顶部动作较多，紧凑视口可收进 overflow；图表 legend 与右栏事件联动可更显性。 |
| Strategy Studio | studio | Studio 方向强，编辑区、参数、日志构成真实工作面。 | 策略构建和运行反馈完整。 | P1：底部日志/状态 tray 在紧凑视口占用过大，压缩主编辑区；需要 collapsed / peek / expanded 三态与高度门禁。 |
| Signals Inbox | ops-console | 队列页面很统一，信号强弱、状态、右栏解释都符合 ops-console。 | 批量处理、选中信号、生成动作的路径清晰。 | P2：列表下方留白较大；可增加批处理 sticky bar、选中摘要或下一条建议，提升工作流连续性。 |
| Orders Ledger | ops-console | Ledger 的表格、Tab、状态条、右侧订单详情一致性高。 | 订单筛选、状态切换和右栏日志对交易追溯有价值。 | P2：紧凑视口右栏费用/日志靠下，接近底部状态栏；建议给 detail rail 设置内部滚动与关键摘要 sticky。 |
| Risk Center | analytical | 风险中心层级清楚，红/黄/绿语义使用克制。 | 风险指标、暴露、阈值与操作入口可以支撑风险巡检。 | P2：图表网格和阈值线偏弱；建议加阈值标签、异常注释和非颜色形态编码。 |
| Regime Monitor | analytical | 宏观 regime 的语义色和状态标签整体稳定，有专业监控感。 | regime 变化、概率、事件解释形成良好叙事。 | P2：多图联动可再明确，legend 固定位置，避免用户只靠色块理解 regime。 |
| Markets Intelligence | analytical | 情报页内容密度合适，新闻/主题/影响评估统一。 | 选中情报到影响、来源、动作建议的路径自然。 | P2：建议强化来源可信度、时间衰减和“已读/待处理”状态，减少信息流疲劳。 |
| Agent Console | studio | Agent 工作台成熟，当前任务、状态、队列和右栏动作统一。 | 状态过滤、当前 agent、日志与动作链路完整。 | P1/P2：需要和 Strategy Studio 共用 Bottom Tray 合同；大屏底部留白可承接队列或近期事件。 |
| Strategies Detail | object-hub | 策略对象页有高质量终端感，主图与指标节奏清楚。 | Tab、绩效、风险、操作区的对象工作流成立。 | P2：benchmark / strategy 线条和 legend 可读性继续提升；Tab 当前态可更强。 |
| Factor Analysis | object-hub | 因子页克制、留白足，适合研究型阅读。 | 因子指标、趋势、关联策略形成基础分析链路。 | P2：页面略显稀疏；建议补充样本区间、覆盖 universe、异常点注释和关联策略跳转。 |
| Backtest Result | object-hub | 回测对象页图表权重正确，指标卡和右栏保持一致。 | 回测摘要、净值曲线、风险指标能快速判断质量。 | P2：下方诊断内容首屏露出不足；建议增加 sticky verdict：可上线/需复测/失败原因。 |
| Markets Calendar | catalog | 日历/事件 catalog 和其他列表页一致，事件标签可读。 | 筛选、日期、事件重要性和右栏详情清楚。 | P2：筛选 chip 偏多；建议增加键盘日期导航、时区提示和事件重要性非颜色标记。 |
| A Shares | radar | A 股雷达有鲜明市场特色，热力图和资金流视觉抓手强。 | 板块、资金、龙虎榜/事件等工作流方向正确。 | P1/P2：红绿热力图依赖较强；需 legend、数值标签、选中边界、涨跌箭头或纹理，照顾色弱与投屏。 |
| Portfolio | analytical | 组合页稳，P&L、持仓表、右栏曲线形成成熟资产视图。 | 持仓、交易、归因 Tab 合理，右栏表现能承接选中组合。 | P2：大屏下方留白偏大；可把风险暴露、行业分布或异常持仓提前，提高首屏信息效率。 |
| Watchlist | catalog | 观察列表是当前 catalog 家族里完成度很高的一页，表格和右栏详情非常统一。 | 选中标的、信号、观察事项和动作按钮链路完整。 | P2：选中态不要只靠底色；建议增加左边界/checkbox 状态和批量操作 sticky 反馈。 |
| Factor List | catalog | 因子列表保持研究域风格，筛选、表格、右栏指标一致。 | 对比、详情、健康状态的路径明确。 | P2：筛选维度较多但仍可控；建议显式展示对比篮数量和已选因子组合。 |
| Strategy List | catalog | 策略列表与 detail / studio 能形成统一家族。 | 运行、克隆、删除、查看详情的动作层级清楚。 | P2：右栏操作区偏低；建议把“运行回测/克隆”固定为右栏首屏主要动作，并增强最近运行状态。 |
| Backtest List | catalog | 回测列表结构稳定，状态、绩效、回撤与右栏预览一致。 | 查看曲线、加入对比、状态筛选可支撑复盘。 | P2：排队/运行中回测可再有进度 affordance；失败原因应提供可恢复建议。 |
| Experiment List | catalog | 实验列表非常贴合研究工作流，显著性、状态、负责人信息清楚。 | 应用提交、打开详情、复现实验路径合理。 | P2：p-value / effect size 等统计语义可加 tooltip 或右栏解释；失败/不显著状态需提供下一步建议。 |
| Universe List | catalog | Universe 管理页与 catalog 家族一致，右栏构成/规则/关联策略完整。 | 编辑、导出、删除等管理动作明确。 | P2：删除是高风险动作，必须有确认与影响面提示；状态也应不只靠颜色区分。 |
| Platform Settings | ops-console | 设置页像生产配置台，profile、diff、audit log 风格成熟。 | 保存草稿、验证配置、回滚、审计链路完整。 | P1/P2：保存/验证/回滚属于高成本操作，应有 sticky action、diff preview、二次确认和失败恢复路径。 |

### 逐页审查后的共性判断

1. 页面不是“同质化模板”，而是通过 Header Utility、左 rail、右 detail rail、Tab、状态条和 token 保持家族一致，这一点是高级的。
2. 主要问题集中在紧凑视口：底部 tray、右栏下段、下方诊断区容易被压到首屏外，影响专家的 5 秒判断。
3. Catalog 家族已经非常统一，下一步价值不在重画，而在批量操作、选中反馈、危险动作确认和右栏 sticky 摘要。
4. Analytical / Radar 页需要继续补图例、阈值标签、联动注释，避免专业数据可视化变成“只能靠颜色读”。
5. Studio / Ops 页的核心待办是状态层级治理：什么是当前状态、什么是历史日志、什么是下一步动作，必须在布局上持续固定。

## 待加强方向

### P1-1：Bottom Tray 遮挡与可控性

代表页：Strategy Studio、Agent Console、Platform、Trading Overview。

问题：紧凑视口中底部日志 / 状态条会占据明显垂直空间，虽然门禁没有判定为遮挡，但实际使用会压缩主编辑区、表格或右栏。Studio 类页面尤其明显。

建议：

- 抽象统一 Bottom Tray 合同：`collapsed / peek / expanded` 三态。
- VP-COMPACT 默认 `peek`，只展示最新状态与关键错误。
- 支持展开、折叠、拖拽高度，并保证 focus 不被底栏遮挡。
- 给 Bottom Tray 添加门禁：展开态高度上限、默认态主工作面最小高度。

### P1-2：数据可视化的非颜色编码

代表页：Cross-Market、A Shares、Factor Analysis、Backtest Result。

问题：红绿、热度和透明度表达已经很成熟，但部分矩阵和热图仍依赖颜色读取强弱。对色弱用户、投屏场景、低对比屏幕都不够稳。

建议：

- 相关矩阵保留数值标签、强相关边框、对角线弱化，并进一步加入正负方向标记。
- 热力图新增小型 legend + sign marker + threshold label。
- 高风险 / critical 不只用红色，用图标、左边界、权重和文字同时表达。
- 图例位置保持跨页一致：矩阵右上或底部，不随页面任意漂移。

### P1-3：全局 Command 可发现性

当前 icon-only command 很克制，但对新用户可能不够可发现。专业工具可以接受快捷键优先，但入口仍需在 hover / focus / active 态解释作用域。

建议：

- hover tooltip：`全局命令 Ctrl+K`。
- focus 态展示 mini label 或 keyboard hint。
- 打开后显示作用域：全局 / 当前 Workspace / 当前对象。
- 搜索框只在 workspace filter、table search 中作为本地动作出现，避免和全局 command 混淆。

### P1-4：Light Mode 视觉审计不足

当前测试验证了 light / density 交互能生效，但截图审阅主要发生在 dark default。Light mode 对专业金融工具很重要：会议、投屏、复盘、打印都会用到。

建议：

- 为 7 类 Shell 各选 1 个代表页，生成 dark / light + compact / comfortable 截图矩阵。
- 重点检查：状态色 contrast、表格 hover / selected、chart gridline、right rail 分隔、badge 可读性。
- 将 Light mode 的视觉问题纳入 Edition Review，而不只做交互测试。

### P2-1：局部 CSS 仍偏散

共享 `layout-base.css` 已承接了大量系统语法，但一些页面仍有较多本地 CSS。短期可接受，长期会影响 React 对齐和 token 迁移。

建议：

- 不急着大重构。
- 优先抽象被 3 个以上页面重复使用的结构：Header Utility、Bottom Tray、Status Bar、Data Toolbar、Right Rail Section。
- 页面本地 CSS 只保留业务图表与页面特殊布局。

### P2-2：评分体系需要校准

Manifest 平均分 9.62，且无低分页面。这说明页面完成度很高，但也说明评分区间可能不够敏感。

建议新增“专家效率扣分项”：

- 首屏 5 秒任务答案是否明确。
- 选中对象是否驱动两个以上区域联动。
- 紧凑视口主工作面是否仍可完成核心任务。
- 关键状态是否不靠颜色也能理解。
- 本地动作是否没有进入全局 chrome。

## 推荐迭代顺序

### Round 1：无产品决策的系统精修

1. Bottom Tray 合同与门禁。
2. Light mode 代表页视觉审计。
3. Data Viz 非颜色编码规范与页面抽检。
4. Global Command hover / focus discoverability。

### Round 2：跨页体验校准

1. 对 7 类 Shell 各选代表页进行截图矩阵审阅。
2. 给每类 Shell 固化“首屏任务答案”。
3. 对右栏信息节奏做一次统一：summary → risk → event → action。
4. 校准评分体系，降低虚高分。

### Round 3：需 PM 确认的功能增强

以下属于产品层变更，不建议 AI 自行决定：

- 角色化密度预设：Research-Heavy / Trading-Heavy / Platform-Heavy。
- Copilot 输出进入 Signals / Strategy Studio 的审批策略细化。
- Agent Finding 生命周期与 Signal 状态机的边界。
- 可转债 T+0 等 A 股扩展交易规则。

## 设计原则收束

下一轮不要追求“更炫”。Ditto 现在最需要的是：

- 更少遮挡。
- 更明确的主工作面。
- 更稳定的状态层级。
- 更少颜色歧义。
- 更可验证的联动。

真正的高级感会从这些约束里长出来。

---

## 2026-04-29 Remediation Update

本轮已将 P1/P2 中无需产品决策的项目转成原型合同、规范和自动测试。

### 视觉矩阵审计

新增代表页矩阵：

```text
test-results/edition-review/visual-matrix/<page-id>/<theme>-<density>.png
```

覆盖 7 类 Shell：

| Shell | 代表页 |
|-------|--------|
| radar | A Shares |
| ops-console | Platform Settings |
| command-center | Home |
| catalog | Watchlist |
| analytical | Risk Center |
| object-hub | Instrument Hub |
| studio | Strategy Studio |

每页生成 dark / light 与 compact / comfortable 四种组合，共 28 张截图。当前矩阵用于检查 light mode 的状态色、表格 selected、图表网格、右栏分隔和 badge 可读性。

### 已纳入门禁的项目

- Bottom Tray 三态：`data-bottom-tray-state="collapsed|peek|expanded"`。
- 数据可视化非颜色编码：legend、sign marker、threshold label、selected / strong cell。
- Global Command 可发现性：`data-command-scope="global"` 与 `Ctrl+K` 标签。
- Catalog 交互：sticky summary、selected marker、batch action bar、danger confirmation。
- 高风险动作：impact summary、confirm、cancel、recovery hint、非颜色危险标记。
- 专家效率：`data-primary-answer`、`data-selected-object-region`、Studio / Agent contract slot。

### 后续仍需产品决策

- 角色化密度预设。
- Copilot 输出进入 Signals / Strategy Studio 的审批策略。
- Agent Finding 生命周期与 Signal 状态机边界。
- A 股扩展交易规则。
