# 原型 Critique 后优化计划

> 日期：2026-05-10
> 范围：`prototype/`
> 来源：`impeccable critique prototype/`
> 注册类型：product
> 目标：把当前高保真原型从“冻结候选”推进到“可稳定交接的实现锚点”

## 1. 结论

当前原型不像通用 AI 生成稿。Graphite Studio 方向成立，桌面端已经具备专业量化工作台应有的密度、状态语义、交易门控、证据链和低噪声主工作面。

主要问题不是视觉方向错误，而是冻结前的收口问题：

- 窄屏视口直接裁切，未形成明确的桌面最小宽度策略或移动降级策略。
- 默认页面仍混入状态覆盖样例，真实业务态和 prototype gallery 态边界不够干净。
- 顶部工具、tab 和局部动作过多，部分页面超过 4 个决策选项。
- `border-left` / `border-right` 粗侧边强调成为惯性，违反 impeccable side-stripe ban。
- frosted、gradient、glow 等材质语言数量偏高，已经接近从“少量 chrome”变成“默认装饰”。

设计健康分：28 / 40，Good 低位。

## 2. 关键证据

抽检页面：

- `page-home.html`
- `page-trading-overview.html`
- `page-strategy-studio.html`
- `page-risk-center.html`
- `page-agent-console-v2.html`
- `page-orders-ledger.html`

本地静态扫描结果：

| 指标 | 结果 | 判断 |
|---|---:|---|
| active prototype 页面 | 29 | 范围完整 |
| `border-left/right >= 2px` | 43 | 需要系统性收敛 |
| `backdrop-filter: blur` | 78 | 材质语言偏满 |
| `linear-gradient(` | 90 | 需区分数据可视化和装饰背景 |
| decorative glow | 5 | 数量不高，但冻结前应清零或解释 |
| 顶层 tab 超过 4 个的页面 | 5 | 需要重新分组或渐进披露 |

窄屏抽检结论：

- 390px 视口下多个页面仍按约 1024px 宽渲染。
- Header、主表、右侧 inspector、状态栏均出现横向裁切。
- 如果产品策略是桌面专业工作台，需要显式声明最小支持宽度和窄屏提示；如果需要移动可用，则必须进入结构性 adapt。

## 3. 优先级

### P1: 窄屏策略

问题：

390px 下页面不是重排，而是直接裁切。对交易、风险、订单和 Agent Console 这类高风险页面，裁切会让用户误判状态或看不到关键动作。

处理目标：

- 明确原型的最小可用宽度。
- 若不支持移动，增加窄屏提示和安全降级，不让用户误以为页面可操作。
- 若支持移动，定义移动结构：rail、header、主工作面、right rail、status bar 如何折叠。

推荐命令：

```bash
bunx impeccable adapt prototype/
```

### P1: 默认态与状态画廊隔离

问题：

Home 默认视图里可以看到 stale / selected 样例块继续出现在主滚动面。它对状态覆盖测试有价值，但对真实默认态是噪声。

处理目标：

- 默认态只保留当前业务状态。
- loading、empty、error、stale、selected 等样例进入独立 states/gallery 视图。
- 保留 `data-state` 覆盖合同，但不污染 default-view。

推荐命令：

```bash
bunx impeccable distill prototype/
```

### P2: 顶部工具和 tab 收敛

问题：

多个页面首屏 prominent controls 在 18 到 24 个之间，Agent Console V2 有 8 个顶层 tab。专家用户能理解，但仍会拖慢“5 秒判断当前状态和下一步动作”的目标。

处理目标：

- 顶层 tab 收到 3 到 4 个以内。
- 低频工具进入 command、overflow menu 或 page-local toolbar。
- Header 只保留全局必要工具，局部筛选和导出回到 workspace。

推荐命令：

```bash
bunx impeccable layout prototype/
```

### P2: 侧边强调线收敛

问题：

多处状态、事件、订单、timeline 使用 2px 到 3px 的左侧彩色边线。impeccable 明确禁止 side-stripe border，因为它容易变成模板化状态装饰。

处理目标：

- 用完整边框、背景 tint、图标、文本、数值权重、badge 或位置结构替代。
- 交易、风险、数据 stale、Agent approval 均保持 color + text / icon / shape 双维表达。
- 保留真正的 rail active indicator，但不要把它扩散到卡片、列表、callout。

推荐命令：

```bash
bunx impeccable quieter prototype/
```

### P2: 材质语言预算

问题：

frosted、gradient、glow 的使用已经偏多。桌面观感仍然专业，但冻结后进入 React 落地时，过多材质规则会增加维护成本和视觉漂移。

处理目标：

- frosted 只保留在 sticky header、context bar、必要 overlay。
- 数据可视化的 gradient 可以保留，装饰性背景 gradient 要减少。
- glow 清零或绑定为明确 focus / selected / live state。

推荐命令：

```bash
bunx impeccable polish prototype/
```

## 4. 建议执行路线

推荐先执行一条主命令：

```bash
bunx impeccable adapt prototype/
```

原因：

窄屏裁切是当前最接近 P1 的结构性问题。先决定“只支持桌面最小宽度”还是“做移动结构降级”，后续 distill、layout、quieter、polish 才不会反复返工。

完成 adapt 后再按顺序执行：

```bash
bunx impeccable distill prototype/
bunx impeccable layout prototype/
bunx impeccable quieter prototype/
bunx impeccable polish prototype/
```

如果通过 Codex skill 调用，而不是直接跑 CLI，请使用：

```text
[$impeccable] adapt prototype/
```

## 5. 验收标准

每轮完成后必须验证：

```bash
bun run check
```

设计验收：

- 桌面默认态不再混入 state gallery 样例。
- 窄屏策略明确，不出现“看似可用但实际裁切”的危险状态。
- 顶层 tab 和同一决策点 visible options 控制在 4 个以内，确有必要时通过分组解释。
- active prototype 中 card、list、callout 不再使用粗侧边彩色边框。
- frosted / gradient / glow 均能解释为 chrome、数据可视化、focus、selected 或 live state。
- 关键交易、风控、数据 stale、Agent 审批仍然保持双维表达。

## 6. 备注

本计划只记录设计优化路线，不修改 active prototype。后续执行任一命令时，应先读取对应页面、共享 CSS、状态覆盖合同和 manifest，再按项目规则运行 `bun run check`。
