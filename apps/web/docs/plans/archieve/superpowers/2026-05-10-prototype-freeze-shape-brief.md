# 原型冻结前最后一轮 Shape Brief

> 日期：2026-05-10
> 范围：`docs/designs/specs/prototypes/` 下全部 active 原型
> 质量档位：高保真原型冻结候选，不是 React 生产落地
> 注册类型：product

## 1. Feature Summary

本轮 shape 是 Ditto active 原型集冻结前的最后一次设计收口。目标不是重做视觉风格、扩展功能目录或进入 React 实现，而是把已经接近冻结候选的高保真原型整理成可验收、可交接、可长期维护的专业工作台样本。

最终产物应让后续执行者清楚知道：先修哪些门禁，哪些页面族需要任务差异化，哪些增强会提升专家判断速度，哪些想法必须延后到 React 落地阶段。

## 2. Primary User Action

用户进入任意 active prototype 后，5 秒内必须完成一个判断：

> 当前最重要的状态是什么，为什么重要，下一步该做什么。

这条判断由页面唯一的 Primary Answer 承载，并通过主工作面、右栏上下文、命令动作、关键状态和后果提示共同支撑。若页面需要用户先拼凑多张卡片或多处状态才能理解重点，该页不能冻结。

Primary Answer 固定结构：

1. 一句话判断。
2. 一个关键数字。
3. 两到三条证据。
4. 一个主动作。
5. 一个影响范围或后果提示。

## 3. Design Direction

**Color strategy**：Restrained。沿用 Graphite Studio，颜色继续作为业务语义，不扩张为装饰。

**Theme scene**：专业量化用户在交易时段或盘后长时间坐在多屏工作站前，环境偏暗或中性，需要快速判断风险、机会、数据质量和下一步动作。

**Anchor references**：

- Bloomberg Terminal 的专业密度，但不做表皮模仿。
- VS Code 的可记忆工作台结构和上下文稳定性。
- Linear / Raycast 的克制交互、灰阶秩序和清晰组件语法。

**Visual probe**：跳过。本轮是既有高保真原型集的冻结前收口，方向已由 `PRODUCT.md`、`DESIGN.md`、Page Pattern Library 和现有原型评审确定，不需要 net-new 视觉探索。

## 4. Scope

**Breadth**：全部 active route prototypes，以 manifest 中的 active 原型集合为准。

**Fidelity**：冻结候选级高保真原型。允许修正布局、状态、文案、语义、可访问性和低噪声微可视化，不允许重开视觉语言。

**Interactivity**：原型级交互收口。必须覆盖可触发 overlay、tab、drawer、tooltip、command、batch action 等已有交互合同；不新增需要后端或 React 状态机才能成立的功能。

**Time intent**：冻结前最后一轮。任何改动都必须能解释为提高冻结质量，而不是“顺手再做一点”。

## 5. Design System Alignment

本轮必须先对齐设计系统，再做页面级 polish。否则只是把偏差装饰得更精致。

设计系统来源：

- `PRODUCT.md`：克制、可信、敏锐；判断先于操作，操作先于美感。
- `DESIGN.md`：Graphite Studio、OKLCH token、三层颜色语义、density preset、shell 尺寸、domain signature。
- `src/styles/design-tokens/`：base、semantic、domain、component、data-viz、interaction、density、shell、theme tokens。
- `docs/designs/specs/00_ditto_visual_constitution.md`：统一工作台逻辑、主工作面、业务语义颜色、双维表达。
- `docs/designs/specs/11_ditto_page_pattern_library.md`：8 套 Page Pattern 和 Primary Answer 合同。
- `docs/designs/specs/prototypes/.edition-manifest.json`：active 原型、页面族、得分和落地状态。

发现 drift 时先分类，再修：

| Drift 类型 | 判定 | 本轮处理方式 |
|---|---|---|
| Missing token | 页面需要的尺寸、状态、颜色或动效应由系统承载，但当前散落在局部实现里 | 优先改为现有 token。若必须新增 token，先记录为 React 落地阶段或设计系统任务，不在冻结轮擅自扩张 |
| One-off implementation | 已有共享组件或共享交互可复用，但页面局部手写 | 换回共享 CSS / JS / 组件语法，减少页面私有规则 |
| Conceptual misalignment | 页面流程、信息架构或主答案不符合对应 Page Pattern | 重排信息层级或收紧内容结构，不靠换颜色和加装饰解决 |

## 6. Freeze Gates

P0 门禁未清零时，禁止进入 P1/P2 美化。

冻结前所有 active prototype 必须满足：

- `bun run check` 回绿。
- Primary Answer 完整且唯一，或明确标记 `data-primary-answer-equivalent`。
- 关键状态不只靠颜色：市场涨跌、风险、数据 stale、Agent 置信度、审批阻断都必须有文本、符号、位置、形状或线型辅助。
- 操作和扫视文本不低于可读门槛。按钮、tab、链接、表头、关键指标、审批后果、错误恢复路径不得使用 11px。
- 每个页面本地 keyframes 和 motion class 都有 `prefers-reduced-motion` 或共享 reduced-motion 覆盖。
- Light / Dark 不割裂，尤其是数据可视化、热力图、状态背景和 hover / selected 状态。
- 键盘与 ARIA 合同不破：tabs、tabpanel、drawer、tooltip、command、batch actions、可点击行都必须有可达路径。
- 活跃原型 HTML 不新增直接 `oklch(`、裸 `rgba()`、任意结构尺寸、装饰性 glow 或未归属业务语义的状态色。
- 禁止把状态做成彩色侧边粗线。需要强调时使用完整边框、背景 tint、图标、文本、位置或数值结构。
- manifest、page contract、review 或 remediation 记录同步。

当前门禁快照：

| Gate | 当前失败项 | 冻结处理 |
|---|---|---|
| Reduced motion | Cross-Market 的 `tab-reveal`、`pair-chart-panel`，Trading Overview 的 `flow-pulse` 缺少 targeted reduce 覆盖 | 先补页面级或共享层降级，再考虑任何新动效 |
| Non-color semantics | Cross-Market `correlation-cell` 有 1 处缺少 sign | 补符号、文本或结构性标记，不能只靠色阶表达方向 |
| Operational typography | Cross-Market pill tab、Agent Console batch button、Backtest / Portfolio benchmark selector、Portfolio exposure name 使用 11px | 操作、tab、按钮、表头和关键扫描文本提升到可读层级 |
| Structural dimension tokens | `tokens-style.css` 中 `--surface-noise-opacity: 0` 未通过结构 token 合同 | 按测试合同改为批准 token 或记录为设计系统任务 |
| Glow budget | `shared/layout-components.css` 的表格 hover `box-shadow` 被判定为 decorative glow | 改为背景、边框或语义状态反馈 |
| Direct color declarations | Agent Console v2 仍有 4 处 direct `oklch(` | 收敛到 token、`color-mix(in oklch, var(--*))` 或已批准局部变量 |
| Tab ARIA wiring | Instrument Hub bottom tabs 3 个 tab 缺 id，3 个 panel 缺 `aria-labelledby` | 补成完整 tab / tabpanel 关系，消除 orphan panel |

## 7. Layout Strategy

本轮布局策略是“稳定骨架，强化任务差异”。

保持不变：

- Shell family 不重做。
- Graphite Studio 不换风格。
- Rail、header、status bar、sidebar、detail rail 的总体合同不变。
- 已成熟页面不做大面积拓扑重排。

需要加强：

- 每页只有一个主工作面，占据 55% 到 70% 注意力。
- 每页只有一个 Primary Answer，位置稳定且能被盲测识别。
- 同一页面族保持语法一致，页面之间的差异来自任务心智，而不是换标题、换颜色或换装饰。
- Catalog 家族不能继续读成同一张表。每个列表页都要有任务专属 summary、诊断右栏和低噪声扫描辅助。
- AI / Agent 不另起视觉体系。差异化来自来源、证据链、置信度、审批后果和阻断恢复。

页面族收口矩阵：

| 页面族 | 页面 | 冻结前主答案 | 允许的 P1 polish |
|---|---|---|---|
| Home | `page-home.html` | 今天最该处理什么，为什么，下一步进哪里 | Global Pulse 分组收紧，Decision Card 首屏锚定，P1/P2 队列优先，右栏正常健康信息降权 |
| Catalog | Strategy、Backtest、Experiment、Factor、Watchlist、Universe | 当前最值得处理、比较或排除的对象是什么 | 任务专属 summary、行内 sparkline / micro bar / heat signal、stale 行统一、右栏从通用详情改为诊断 |
| Studio / Builder | Strategy Studio、Alpha Explorer、Factor Analysis | 当前构建或研究是否可信，下一步应验证什么 | 证据链、数据来源、运行状态、候选风险和审批影响前置 |
| Agent / Ops | Agent Console、Platform、Platform Settings | 哪个任务或服务需要处置，阻断影响是什么 | Finding 来源、confidence bar + 数字、审批后果、批量风险汇总、恢复路径 |
| Trading / Portfolio | Trading Overview、Portfolio、Orders Ledger、Signals Inbox、Risk Center | 哪个风险、信号或执行状态需要立刻判断 | 持仓、PnL、暴露、基准、回撤用低噪声微可视化辅助扫描 |
| Market / Radar | Cross-Market、A-Shares、Screener、Regime、Calendar、Intelligence、Instrument Hub | 当前市场范围内最重要的驱动、异常或对象是什么 | 已高分页面只做交互深度和说明清晰度增强，不大改结构 |

## 8. Key States

必须继续覆盖：

- default
- loading
- empty
- error
- stale
- selected object
- critical risk
- waiting approval
- blocked
- reduced motion
- light mode
- collapsed sidebar
- keyboard focus

状态验收不是“页面里存在 class 名”，而是用户能快速判断：

- 当前状态是什么。
- 影响范围在哪里。
- 是否需要行动。
- 行动后会发生什么。
- 失败或阻断时如何恢复。

## 9. Interaction Model

全站交互围绕“选中对象”联动：

- 表格行、右栏、bottom tray、command suggestions、overlay 使用同一对象上下文。
- Command Palette 提供当前页面和当前对象的动作，不只是全局入口。
- Catalog / Studio 的面板宽度、表格列宽、排序、密度偏好应沉淀为后续 React 落地的专家效率合同。
- Tab、drawer、sheet、tooltip、batch bar 按 ARIA 和键盘模型收口。
- 危险操作、交易确认、Agent 审批必须说明影响范围和后果，不混入普通对话文本。
- 动效只表达状态变化、反馈、加载或 reveal。不得为了“高级感”添加装饰动效。

## 10. Content Requirements

全站文案保持“冷静的专业同事”语气：直接、准确、有边界感。

页面文案要求：

- Primary Answer 不写泛泛摘要。避免“总数、活跃、异常”这种无任务含义的指标组合。
- Catalog 页面必须写任务专属判断，例如“哪些策略可运行”、“哪次回测值得比较”、“哪个因子正在衰减”、“哪个标的触发下一动作”。
- 空状态说明下一步动作，不只写“暂无数据”。
- 错误状态说明影响范围和恢复路径，不只写“加载失败”。
- 审批按钮和危险动作使用具体动词和对象，例如“批准 3 条调仓建议”、“保留当前仓位”。
- AI / Agent 文案必须说明来源、置信度、证据链、审批后会发生什么、被阻断时如何恢复。

## 11. Recommended Route

### P0: 清零冻结门禁

先处理所有会阻止冻结的系统性问题：

- Reduced motion 覆盖缺口。
- Market / risk / stale / confidence / approval 等状态的 non-color semantics。
- 11px operational typography。
- Prototype structural dimension token 违规。
- Decorative glow budget 违规。
- Active prototype direct `oklch(` 违规。
- Instrument Hub bottom tab ARIA wiring。
- Tooltip、command、tab、drawer、batch action 的键盘和 ARIA 合同。

验收：`bun run check` 回绿，且整改记录能逐项对应 P0。

### P1-A: Catalog 家族任务差异化

优先处理 Strategy、Backtest、Experiment、Factor、Watchlist、Universe。

目标：

- 补任务专属 summary。
- 补行内 sparkline / micro bar / heat signal。
- 右栏从通用详情转为任务诊断。
- stale 行视觉、文案和可访问语义统一。

验收：盲测截图时，不读标题也能通过结构和主答案区分页面任务。

### P1-B: Home 主答案收束

目标：

- Global Pulse 保持紧凑，只承载首屏背景事实。
- Decision Card 成为首屏锚点。
- Priority Queue 默认只展示 P1/P2。
- 右栏普通健康信息降权，异常、审批、数据延迟和运行阻断优先。

验收：5 秒内能回答“今天最该处理什么，为什么，下一步做什么”。

### P1-C: Agent Console 透明度

目标：

- Finding 加数据来源。
- Confidence 从纯数字升级为 bar + 数字。
- 审批动作显示后果和预计影响。
- 批量审批显示汇总风险。

验收：AI 差异化来自证据和门控，而不是视觉另起炉灶。

### P1-D: Trading / Portfolio 数据扫描增强

目标：

- 持仓、PnL、暴露、基准对比、回撤区间用低噪声微可视化补足判断速度。
- 价格变化 flash 只表达状态，不做装饰。
- Benchmark selector 在 Portfolio / Backtest Result 形成一致占位。

验收：交易页和组合页更像扫描面板，而不是静态列表。

### P2: Cross-Market 小步深化

目标：

- 相关矩阵 tooltip。
- Pair chart 展开。
- Macro drivers bar 增强。

验收：不破坏当前高分结构，只提升专家探索深度。

## 12. Non-goals

本轮不做：

- 重开视觉风格。
- 大改 Shell family。
- 重建 token 架构。
- 新增大面积装饰、发光、渐变或品牌表达。
- 新增独立 AI 聊天产品语法。
- 把最后一轮变成大范围功能扩张。
- 为单页便利新增不可复用的私有组件或私有交互。
- 在 P0 未绿时投入 P2 探索。

## 13. Recommended References

执行时优先参考：

- `PRODUCT.md`
- `DESIGN.md`
- `.agents/skills/impeccable/reference/product.md`
- `.agents/skills/impeccable/reference/polish.md`
- `.agents/skills/impeccable/reference/shape.md`
- `.agents/skills/impeccable/reference/layout.md`
- `.agents/skills/impeccable/reference/interaction-design.md`
- `.agents/skills/impeccable/reference/color-and-contrast.md`
- `.agents/skills/impeccable/reference/responsive-design.md`
- `.agents/skills/impeccable/reference/motion-design.md`
- `.agents/skills/impeccable/reference/ux-writing.md`
- `docs/designs/specs/00_ditto_visual_constitution.md`
- `docs/designs/specs/11_ditto_page_pattern_library.md`
- `docs/designs/specs/prototypes/.edition-manifest.json`

## 14. Open Questions

无阻塞问题。当前假设如下：

- active 原型集合以 `.edition-manifest.json` 为准。
- 本轮质量条是“冻结候选可交接”，不是“最终 React 生产实现”。
- 新 token、新依赖、CI/CD 和架构边界变更不在本轮范围内。

## 15. Completion Definition

这轮冻结前 shape 完成后，后续工作应进入 `polish 当前原型` 或按 P0/P1 拆成整改计划。

最终完成标准：

```bash
bun run check
```

通过，并生成一份冻结前整改结果记录，说明：

- 修复了哪些 P0/P1。
- 哪些页面族被改变。
- 哪些门禁已回绿。
- 哪些剩余问题被明确降级为 React 落地阶段处理。
