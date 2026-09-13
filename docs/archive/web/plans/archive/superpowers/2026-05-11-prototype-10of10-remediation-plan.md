# 原型 10/10 满分整改计划

> 日期：2026-05-11
> 范围：`prototype/` active route prototypes
> 来源：冻结前最终评审追加要求
> 注册类型：product
> 目标：把当前 9.2 到 9.7 的高位冻结候选推进到每页接近 10/10 的可验证状态

## 1. 结论

当前 active prototype 集不是视觉方向问题，也不是通用 AI slop 问题。

`npx impeccable --json --fast <28 active html>` 对 28 个 active HTML 返回空结果，说明 active 页面没有命中 detector 级别的典型反模式。Graphite Studio 的克制、高密、状态语义、交易门控和 Agent 证据链方向成立。

满分缺口集中在：

- 交互基础设施未逐页统一加载。
- 视觉审计状态没有从 queued / missing 收口到 verified。
- 窄屏安全降级缺少逐页真实浏览器门禁。
- 每页键盘、ARIA、overlay、chart、batch action 的满分证据不足。
- 部分页面材质、阴影、tab、动作数量仍偏满，虽不阻塞冻结，但会拖低长期使用质量。

因此，本轮目标不是继续加视觉，而是：

1. 补门禁。
2. 补证据。
3. 减噪声。
4. 让每页都能独立通过 10/10 级别验收。

## 2. 当前硬证据

### Active 页面范围

以 `.edition-manifest.json` active route 过滤为准，当前 active prototype 为 28 页。

页面族：

| Shell family | 页面 |
|---|---|
| command-center | `home` |
| radar | `cross-market`, `a-shares` |
| catalog | `markets-screener`, `markets-calendar`, `watchlist`, `factor-list`, `strategy-list`, `backtest-list`, `experiment-list`, `universe-list` |
| analytical | `research`, `trading-overview`, `risk-center`, `regime-monitor`, `markets-intelligence`, `portfolio` |
| studio | `alpha-explorer`, `strategy-studio`, `agent-console-v2` |
| object-hub | `instrument-hub`, `strategies-detail`, `factor-analysis`, `backtest-result` |
| ops-console | `platform`, `signals-inbox`, `orders-ledger`, `platform-settings` |

### Detector 结果

Active HTML 扫描：

```bash
npx impeccable --json --fast <28 active html>
```

结果：`[]`。

判断：active 页面没有命中 detector 级 AI slop、side tab、gradient text、layout transition 等问题。后续满分优化应聚焦项目级标准，而不是泛化 detector。

### 关键缺口

| 缺口 | 当前证据 | 严重度 |
|---|---|---|
| Agent Console V2 未加载共享交互 | `page-agent-console-v2.html` 只有 `theme-switcher.js`，缺 `prototype-interactions.css/js` | P0 |
| 390px 安全降级有 1 页缺失 | 28 页真实浏览器检查中，`agent-console-v2` 未显示 `.prototype-viewport-guard` | P0 |
| visual audit 未收口 | 27 个 `queued`，1 个 `missing`（`alpha-explorer`） | P1 |
| 满分门禁未覆盖真实页面加载 | 现有测试验证共享 CSS / JS 存在，但没有逐页浏览器验证 guard 可见性 | P1 |
| 标准验证输出不够稳 | `bun run check` 在当前 harness 曾被 SIGTERM 打断；拆分验证可通过 | P1 |

## 3. P0 必修

### P0-1: Agent Console V2 接入共享交互基础设施

问题：

`page-agent-console-v2.html` 没有加载：

```html
<link rel="stylesheet" href="shared/prototype-interactions.css">
<script src="shared/prototype-interactions.js"></script>
```

影响：

- 390px 窄屏不会显示桌面安全提示。
- tooltip、command、row context、keyboard shortcut、reduced-motion 同步等共享能力不保证一致。
- Agent 审批和治理页在窄屏下看起来仍可操作，会造成危险误判。

修复：

- 在 `theme-switcher.js` 后补齐共享交互 CSS / JS。
- 复核页面内已有局部交互是否与共享交互重复绑定。
- 运行 390px guard 浏览器检查。

验收：

- `agent-console-v2` 在 390px 显示 `.prototype-viewport-guard`。
- 页面桌面 1200 / 1366 / 1536 gates 继续通过。
- detector 对 active HTML 仍返回 `[]`。

### P0-2: 新增 390px 全 active guard 门禁

问题：

现有测试只检查共享窄屏策略声明存在，未验证每个 active HTML 实际加载并显示 guard。

修复：

- 在 prototype interaction / expert efficiency 测试中新增 Playwright 或等价浏览器测试。
- 遍历 `.edition-manifest.json` active route pages。
- 390px viewport 加载每页，断言 `.prototype-viewport-guard` 可见。

验收：

```bash
bun vitest run scripts/prototype-interaction-ux-contract.test.ts -t "viewport guard"
```

若测试名不同，以实际新增测试名为准。

### P0-3: 恢复标准门禁可观测性

问题：

项目标准要求完成前运行：

```bash
bun run check
```

当前拆分命令可通过，但默认 `vitest run` 在当前 harness 曾被 SIGTERM 打断。满分交付不应依赖口头解释。

修复：

- 优先确认是否为当前 harness 输出静默导致。
- 若需要，给 `check` 增加稳定 reporter 或拆出 `check:ci`，但修改脚本前需确认不会破坏团队习惯。
- 在本轮整改记录里记录实际通过命令与测试数量。

验收：

```bash
bun run check
```

必须得到完整绿色结果，或明确改为项目批准的新门禁命令。

## 4. P1 满分证据

### P1-1: Visual audit verified 收口

问题：

manifest 当前 visual audit 状态仍是：

- `queued`: 27
- `missing`: 1（`alpha-explorer`）

修复：

- 对 28 个 active 页面生成或确认视觉审计截图。
- 每页状态推进到 `verified`。
- `alpha-explorer` 必须补齐 visual audit record，不能继续 missing。
- 截图证据路径写入 review / result 文档，避免只有 manifest 状态。

验收：

```bash
node -e 'const fs=require("fs"),path=require("path"); const dir="prototype"; const m=JSON.parse(fs.readFileSync(path.join(dir,".edition-manifest.json"),"utf8")); const archived=new Set(["ai-overview","ai-copilot"]); const active=m.pages.filter(p=>p.file?.startsWith("page-")&&p.file.endsWith(".html")&&p.id!=="token-showcase"&&p.status!=="archived-specimen"&&!archived.has(p.id)); const bad=active.filter(p=>p.landing?.visualAuditStatus!=="verified").map(p=>`${p.id}:${p.landing?.visualAuditStatus||"missing"}`); console.log(bad.length ? bad.join("\\n") : "all verified");'
```

### P1-2: 每页键盘和 ARIA 巡检证据

目标：

每页都证明以下路径可达：

- Primary Answer 主动作。
- 顶部关键 CTA。
- tabs / tabpanel。
- overlay open / close。
- drawer / sheet / modal。
- row action / batch action。
- command palette。
- chart action（有图表的页面）。

重点页面：

- `instrument-hub`
- `strategy-studio`
- `signals-inbox`
- `orders-ledger`
- `risk-center`
- `agent-console-v2`
- `markets-screener`
- `alpha-explorer`

验收：

- 不只看 DOM 属性，要至少覆盖代表页面的真实浏览器键盘路径。
- 对低风险 catalog 页面可用 JSDOM contract，加一批抽样 Playwright。

### P1-3: Reduced motion 逐页闭环

问题：

部分页面本地 reduced-motion 计数低，并不等于失败，但满分需要证明：

- 本地动画有 targeted reduce。
- 共享脚本 `data-reduced-motion` 生效。
- 图表、reveal、pulse、drawer、chart range 都尊重 reduced motion。

优先页面：

- `portfolio`
- `a-shares`
- `strategies-detail`
- `platform-settings`
- `agent-console-v2`
- `markets-intelligence`
- `regime-monitor`

验收：

```bash
bun vitest run scripts/prototype-interaction-ux-contract.test.ts -t "reduced motion"
```

若测试覆盖不足，先补测试。

## 5. P1 页面级 10/10 优化

### Home

当前问题：

- 分数低位（9.2）。
- `focus-visible` 本地证据偏少。
- 需要证明 5 秒 Primary Answer 在 1200 / 1366 / 1536 都是首屏锚点。

修复：

- 补主动作、队列、右栏关键链接的 focus-visible 证据。
- 做首屏盲测：不读页面标题也能答出“今天最该做什么”。
- 保持 Global Pulse 背景化，不再扩展健康噪声。

### Markets Screener

当前问题：

- 分数低位（9.2）。
- 按钮、筛选、动作数量多，决策点容易超过 4 个。

修复：

- 把低频筛选、列管理、导出、保存 preset 收进 overflow / command。
- Primary Answer 保留筛选结果去向，而不是工具集合。
- 右栏从通用说明转为“当前筛选为什么值得行动”。

### Alpha Explorer

当前问题：

- visual audit missing。
- `data-primary-answer` 和 `data-primary-answer-equivalent` 同时出现在同一主容器，语义上可接受，但满分应避免歧义。

修复：

- 补 visual audit verified。
- 确认 Primary Answer 只暴露一个语义入口。
- 补候选采纳、审批、阻断、证据链的键盘路径。

### Agent Console V2

当前问题：

- 未加载共享交互。
- 390px guard 缺失。
- 治理/审批页面风险高，必须高于普通页面标准。

修复：

- P0 先补共享交互。
- 补批量审批后果汇总的键盘可达证据。
- 确认待审批、已阻断、质量评测、工具追踪的状态不是只靠颜色。

### Trading / Risk / Orders

页面：

- `trading-overview`
- `signals-inbox`
- `orders-ledger`
- `risk-center`
- `portfolio`

修复：

- 每个危险动作必须有影响范围、后果预览、退出路径。
- 信号批准、订单重试、暂停交易、风险压力测试必须有明确确认语义。
- 图表和表格中市场方向不能只靠红绿。
- 保持状态持续可见，避免用户滚动后失去风险上下文。

### Object Hub

页面：

- `instrument-hub`
- `strategies-detail`
- `factor-analysis`
- `backtest-result`

修复：

- tabs 多的页面要证明渐进披露成立，而不是只靠用户记忆。
- 对象动作后果预览必须清楚说明去向。
- 图表 action、overlay close、bottom tab 都要有完整键盘路径。

### Catalog 家族

页面：

- `watchlist`
- `factor-list`
- `strategy-list`
- `backtest-list`
- `experiment-list`
- `universe-list`
- `markets-calendar`

修复：

- 做盲测差异化：不看标题也能分辨页面任务。
- 每页右栏诊断不能复用通用详情语法。
- `focus-visible` 证据偏少的页面补齐主表、行动作、overlay close。
- stale 行必须保持文本、位置、形状或图标辅助。

## 6. P2 克制与材质预算

这些不是冻结阻断，但会影响 10/10。

### 高材质页面

优先检查：

- `cross-market`
- `research`
- `markets-screener`
- `markets-intelligence`
- `a-shares`

处理原则：

- 保留数据可视化 gradient。
- 保留 sticky chrome frosted。
- 减少不承担状态语义的 shadow。
- glow 只允许绑定 focus、selected、live 或 critical，不做“高级感”装饰。

### Tab / Action 密度

优先检查：

- `instrument-hub`
- `strategy-studio`
- `signals-inbox`
- `orders-ledger`
- `backtest-result`
- `trading-overview`

处理原则：

- 顶层决策点控制在 4 个以内。
- 低频动作进 command / overflow / local toolbar。
- 高风险动作保留显性按钮，不藏进菜单。

## 7. 推荐执行命令

### Step 1: 修 P0 基础设施

```text
[$impeccable] harden prototype/page-agent-console-v2.html
```

目标：

- 补共享 `prototype-interactions.css/js`。
- 补 390px guard 验证。
- 不改变 Agent Console V2 视觉语言。

### Step 2: 给全站新增满分门禁

```text
[$impeccable] audit prototype/
```

目标：

- 新增 390px active 页面 guard 测试。
- 补 visual audit verified 证据。
- 补键盘 / ARIA / reduced-motion 的代表页面门禁。

### Step 3: 处理低分页面

```text
[$impeccable] layout prototype/page-home.html prototype/page-markets-screener.html
```

目标：

- Home 首屏主答案更强。
- Screener 选择压力和工具噪声收敛。

### Step 4: 处理 Studio 和高风险交易页

```text
[$impeccable] harden prototype/page-alpha-explorer.html prototype/page-agent-console-v2.html prototype/page-trading-overview.html prototype/page-signals-inbox.html prototype/page-orders-ledger.html prototype/page-risk-center.html
```

目标：

- 审批、交易、风险、阻断、恢复路径全部可验证。
- 每个危险动作都有后果和退出路径。

### Step 5: 处理材质预算和长期耐看

```text
[$impeccable] quieter prototype/page-cross-market.html prototype/page-research.html prototype/page-markets-screener.html prototype/page-markets-intelligence.html prototype/page-a-shares.html
```

目标：

- 减少不承担业务语义的 shadow / blur / glow。
- 保留 Graphite Studio，不重开风格。

### Step 6: 最终满分 polish

```text
[$impeccable] polish prototype/
```

目标：

- 每页只做收口，不新增功能野心。
- manifest、review、screenshots、tests 全部同步。

## 8. 验收命令

每一步完成后执行：

```bash
bunx biome check .
bunx tsc -b
bun vitest run --reporter=dot
bun run prototype:gates
timeout 60s npx impeccable --json --fast $(node -e 'const fs=require("fs"),path=require("path"); const dir="prototype"; const m=JSON.parse(fs.readFileSync(path.join(dir,".edition-manifest.json"),"utf8")); const archived=new Set(["ai-overview","ai-copilot"]); console.log(m.pages.filter(p=>p.file?.startsWith("page-")&&p.file.endsWith(".html")&&p.id!=="token-showcase"&&p.status!=="archived-specimen"&&!archived.has(p.id)).map(p=>path.join(dir,p.file)).join(" "));')
```

最终必须执行项目标准门禁：

```bash
bun run check
```

如 `bun run check` 在当前 harness 仍被 SIGTERM 打断，不能直接宣称满分冻结。需要先修复验证可观测性，或经项目确认把上面的拆分命令固化为新的等价门禁。

## 9. 完成定义

满分完成必须同时满足：

- 28 个 active 页面都有 `visualAuditStatus: verified`。
- 390px 全 active 页面都显示 `.prototype-viewport-guard`。
- active HTML detector 返回 `[]`。
- `bun run prototype:gates` 全页三视口通过。
- `bun run check` 完整绿色。
- 每个页面都有唯一 Primary Answer。
- 每个高风险动作有后果预览和退出路径。
- 每个页面键盘路径可证明，不只依赖 DOM 静态属性。
- reduced motion、light / dark、stale、critical、waiting approval、blocked、selected object 都有明确证据。
