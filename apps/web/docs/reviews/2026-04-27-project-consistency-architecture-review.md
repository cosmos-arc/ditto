# Ditto 项目一致性与原型落地审查报告

**日期**：2026-04-27  
**范围**：当前完整项目、产品 specs / 蓝图、`.arch-manifest.json`、Edition v1 原型 manifest、React 路由与组件实现  
**结论级别**：不建议直接进入候选原型批量功能落地；应先完成路由、Page Contract、Overlay Registry、组件 token 四条主线收敛。

---

## 1. 总体结论

当前项目的**原型层质量已经很高**：Edition v1 已有 29 个 route page 进入 `reviewed`，此前 `prototype:gates` 对 29 个 route page 通过，仅 `token-showcase` 作为辅助 specimen 不适用标准 route gate。

但**React 实现层与治理层已经明显滞后于 specs / 蓝图 / 原型层**。核心问题不是单页视觉 polish，而是“真源分裂”：

1. `01_product_information_architecture.md` 明确 v2.0 已从 6 域收敛为 5 域，AI 域拆散；React 仍保留 `/ai`、`/ai/copilot`、`/ai/agents` 和导航 AI 域。
2. IA / Shell spec 要 27 条主路由；当前 React `createFileRoute` 目标有 24 个，其中缺失 11 条目标路由，同时存在 8 条旧口径或辅助路由。
3. `.edition-manifest.json` 已覆盖 29 个 route page；`.arch-manifest.json` 仍停留在 2026-04-20 的 27 IA / 28 blueprint 口径，且没有反映本轮 29 route page 的 Edition 审查结果。
4. `page-contracts.generated.ts` 只生成了 `/` 一条合同，因为 `docs/contracts/pages/` 当前只有 `home.contract.json`；而手写 `page-contracts.ts` 固化了 21 条旧路由。测试也在验证旧口径，而不是防止漂移。
5. Overlay 在蓝图中是“页面工作流的一部分”，但当前原型层基本是 gallery-only 展示；React 层只有 Trading Orders / Risk 少数页面直接实现 Drawer。两种方式混用，会阻断候选原型到完整功能的落地。

一句话：**视觉候选稿已经领先，工程契约和路由骨架没有跟上。** 下一阶段应该优先做“收口”，不是继续横向新增页面。

---

## 2. 审计基线

### 2.1 规格真源

- `docs/designs/specs/01_product_information_architecture.md`
  - v2.0：AI 域拆散嵌入，域结构从 6 域收敛为 5 域，路由总数从 29 精简为 27。
  - Sitemap 包含 `/platform/agents`、`/platform/settings`、`/trading/portfolio`、`/research/strategies/[id]` 等目标路由。
  - 明确 `/ai`、`/ai/copilot`、`/ai/agent` 不再作为独立路由。
- `docs/designs/specs/02_core_page_blueprints.md`
  - v2.2：27 个页面模板 + 1 个全局组件。
  - 多个页面包含 `Overlay Registry`，overlay 是工作流动作，不只是展示状态。
- `docs/designs/specs/04_interaction_state_spec.md`
  - 每个页面上线前要检查 selected、loading / empty / failed、stale、blocker、bulk、compare、detail drill-down 等状态。
- `docs/designs/specs/10_ditto_shell_family_spec.md`
  - v1.4：7 类 Shell Family。
  - 全局 Rail 从 6 项缩减为 5 项，移除 AI。
  - `/markets/watchlist` 归 Catalog，`/trading/portfolio` 归 Analytical，`/platform/agents` 归 Studio。
- `DESIGN.md`
  - 定义 Graphite Studio 的颜色、字体、间距、圆角、密度、Overlay、Shell 与组件 token。

### 2.2 当前项目证据

- `.arch-manifest.json`
  - `lastAudit.date`: `2026-04-20`
  - `lastAudit.score`: `9.5/10`
  - `existingSpecs.iaPages`: `27`
  - `existingSpecs.blueprintPages`: `28`
- `docs/designs/specs/prototypes/.edition-manifest.json`
  - `edition`: `v1`
  - `status`: `edition-reviewed`
  - `editionReviewedAt`: `2026-04-27`
  - route pages：29
  - 21 个早期 page 缺少 `shellFamily` / `blueprintId`
- `src/routes`
  - 当前实际 `createFileRoute` 目标：24 个
- `docs/contracts/pages`
  - 当前仅有 `home.contract.json`
- `src/features/shell/page-contracts.generated.ts`
  - 当前仅有 `/` 一条合同
- `src/features/shell/page-contracts.ts`
  - 手写 legacy 合同 21 条，包含 `/ai`、`/ai/copilot`、`/ai/agents`、`/strategies/$id` 等旧口径

---

## 3. 关键量化结果

### 3.1 路由一致性

IA 目标主路由：27  
React 当前 `createFileRoute` 目标：24

**缺失的 IA 目标路由：**

| 路由 | 当前原型状态 | 影响 |
|---|---|---|
| `/markets/watchlist` | 有 `page-watchlist.html` | Watchlist 候选原型无法进入 React 功能落地 |
| `/research/factors` | 有 `page-factor-list.html` | Factor List 缺入口，Factor Analysis 只能详情化存在 |
| `/research/strategies` | 有 `page-strategy-list.html` | Strategy List 缺入口 |
| `/research/strategies/$id` | 有 `page-strategies-detail.html` | 当前在 `/strategies/$id`，域归属错误 |
| `/research/strategies/$id/studio` | 有 `page-strategy-studio.html` | 当前在 `/research/strategy-studio`，缺对象上下文 |
| `/research/backtest` | 有 `page-backtest-list.html` | Backtest List 缺入口 |
| `/research/experiments` | 有 `page-experiment-list.html` | Experiment List 缺入口 |
| `/research/universes` | 有 `page-universe-list.html` | Universe List 缺入口 |
| `/trading/portfolio` | 有 `page-portfolio.html` | Portfolio 合并页未落地 |
| `/platform/settings` | 有 `page-platform-settings.html` | 平台配置页未落地 |
| `/platform/agents` | 有 `page-agent-console.html` | Agent Console 仍落在 `/ai/agents` |

**当前多出的旧口径 / 辅助路由：**

| 路由 | 判定 |
|---|---|
| `/ai` | specs 已 deprecated，应拆入 Home + Platform Agents + 全局 Sidecar |
| `/ai/copilot` | specs 已 deprecated，应升级为全局 Copilot Sidecar |
| `/ai/agents` | 应迁移到 `/platform/agents` |
| `/strategies` | IA 中应为 `/research/strategies` |
| `/strategies/$id` | IA 中应为 `/research/strategies/$id` |
| `/research/strategy-studio` | IA 中应为 `/research/strategies/$id/studio` |
| `/instruments` | IA 只定义 `/instruments/[id]`；如保留应作为搜索/跳转辅助页明确标注 |
| `/showcase` | 应标记 dev-only，不应进入产品 IA / contract |

### 3.2 Contract / Visual Audit 管线

当前有三套不一致的“页面合同”：

1. `docs/contracts/pages/home.contract.json`：新 contract schema，但只有 Home。
2. `src/features/shell/page-contracts.generated.ts`：由 contract 生成，也只有 `/`。
3. `src/features/shell/page-contracts.ts`：手写 legacy 合同，21 条旧实现路由。

风险：

- `src/features/shell/index.ts` 同时导出 legacy 和 generated，默认导出的 `PAGE_CONTRACTS` 是 generated，因此下游如果使用默认合同，只会看到 Home。
- `src/features/shell/page-contracts.test.ts` 的 “Legacy route coverage” 手写 21 条旧路由，测试会保护旧架构，而不是保护 IA v2.0。
- `scripts/visual-audit.config.generated.mjs` 也只有 Home；`visual:audit --all` 无法覆盖当前 29 个 reviewed prototypes。
- 当前工作区中大量 `docs/visual-audit/...` 历史产物处于删除状态，React/prototype 对比证据层不可用或路径已迁移，治理链路不闭合。

### 3.3 Overlay / 弹窗画廊一致性

原型 manifest 中：

- route pages：29
- 声明 overlay 的页面：28
- 默认页面中可触发 overlay 的页面：0
- gallery-only overlay 页面：28

React 当前：

- `src/components/indicator/overlay/drawer.tsx` 存在统一 Drawer 包装。
- 只有 `src/features/trading/components/orders-page.tsx` 和 `src/features/trading/components/risk-page.tsx` 直接使用 Drawer。
- `Dialog` / `Sheet` primitives 存在，但没有页面级 Overlay Registry，也没有 “原型 overlay id → React trigger → React component” 的映射。

判定：当前 overlay 不是统一的产品交互资产，而是分裂为两类：

1. 原型层：作为独立 overlay gallery 展示候选状态。
2. React 层：少数页面按局部需求直接实现 Drawer。

这会导致候选原型落地时无法判断：某个 overlay 是必须进入默认 workflow，还是只是 gallery specimen。

### 3.4 组件 / token 使用一致性

对 `src` 中 TS/TSX 文件做静态扫描：

| 指标 | 命中数 | 说明 |
|---|---:|---|
| `style={{ ... }}` inline style | 14 | 项目规则禁止 inline styles；部分动态 chart / progress / rail 仍在用 |
| arbitrary text class，如 `text-[10px]` | 58 | 字体 scale 没有完全收敛到 token / Tailwind alias |
| arbitrary radius class，如 `rounded-[...]` | 37 | 圆角 token 使用不统一 |
| 原生 Tailwind spacing，如 `gap-4`、`px-3` | 767 | 不全是错误，但说明 density token 不是主控层 |
| shadcn 默认 token，如 `bg-primary`、`ring-ring` | 53 | 与 Ditto semantic token 命名层不一致 |
| 大圆角，如 `rounded-lg/xl/full` | 56 | 部分合理，部分与按钮/卡片 ≤8px 的克制原则冲突 |

突出例子：

- `src/components/ui/button.tsx`
  - 使用 `bg-primary`、`text-primary-foreground`、`border-border`、`bg-muted`、`ring-ring`、`bg-destructive` 等 shadcn 默认 token。
  - `src/styles/globals.css` 当前映射的是 `--color-accent`、`--color-border`、`--color-surface-*`、`--color-foreground-*` 等 Ditto token，没有定义 `--color-primary` / `--color-muted` / `--color-ring` / `--color-destructive` 这一套。
  - 结果是共享 UI primitive 与 Ditto token layer 存在语义断层。
- `src/components/ui/dialog.tsx` / `src/components/ui/sheet.tsx`
  - Overlay 背景使用 `bg-black/50`，而 DESIGN 定义了 `--surface-overlay` / `--surface-modal` / overlay opacity scale。
  - 关闭按钮使用 `&times;` 文本符号，不符合“按钮尽量使用熟悉图标”的组件约定。
- `src/components/data/flow-bar.tsx`、`src/components/chart/line-chart.tsx`、`src/components/chart/area-chart.tsx`、`src/features/research/components/factor-table.tsx` 等存在 inline style。
  - 这些有动态尺寸诉求，但当前项目规则是硬禁 inline styles，因此需要明确例外策略或改为 bounded variants / CSS custom property wrapper。

### 3.5 字体 / 间距 / 圆角

DESIGN 定义：

- 字号：10 / 11 / 12 / 13 / 14 / 16 / 18 / 20 / 24
- 间距：4pt scale，常用 2 / 3 / 4 / 6 / 8 / 10 / 12 / 16 / 20 / 24 / 32
- 圆角：2 / 3 / 4 / 6 / 8 / 12
- Button primary / secondary：`rounded.4`，font 12px，高度 compact action-height 2rem
- Panel：标准 `rounded.8`

当前 React 实现的方向是“部分使用 token，部分直接 Tailwind utility”。这不是立即不可用，但会让候选原型进入 React 后出现微观差异：

- 同一类按钮在 `Button` primitive、页面局部按钮、prototype button 之间圆角/高度/字号不完全一致。
- `text-sm` 在 Tailwind alias 中被映射到 12px，但部分页面仍直接写 `text-[10px]`、`text-[13px]`、`text-[24px]`。
- 部分 badge / status dot 使用 `rounded-full` 合理；但通用按钮、tabs、message bubble 使用 `rounded-lg` 时需要逐一判断是否超过设计意图。

### 3.6 Domain Identity

规格要求：

- 产品域：Home / Markets / Research / Trading / Platform。
- AI 是嵌入式智能层，不是独立域。

当前实现：

- `src/features/navigation/types.ts` 仍定义 6 个域：`home`、`markets`、`research`、`trading`、`ai`、`platform`。
- `src/features/shell/hooks/use-active-domain.ts` 依赖 `DOMAINS` 做 prefix match。
- `/strategies` 和 `/strategies/$id` 不属于任何 `DOMAINS` 前缀，会回落到 `home`，导致域签名色、Rail active、Header atmosphere 都可能错误。
- `DESIGN.md` 中 Overview 段落仍写“Covers Home, Markets, Research, Trading, AI, Platform — six business domains”，与 IA v2.0 冲突。

更合理的判断：可以保留 `agent-*` / `copilot-*` 业务状态 token，但不能保留 AI 作为导航域和产品域。

---

## 4. 不达标项清单

### P0-1：React 路由未对齐 IA v2.0

**问题**：缺失 11 条目标路由，同时保留 8 条旧口径 / 辅助路由。  
**影响**：原型无法按 IA 的产品闭环进入功能落地；导航域、breadcrumb、active domain、page contract、visual audit 都会继续漂移。  
**建议**：

1. 以 IA v2.0 为唯一主路由表。
2. 执行路由迁移：
   - `/ai/agents` → `/platform/agents`
   - `/ai/copilot` → 全局 Sidecar，不再作为 route page
   - `/strategies` → `/research/strategies`
   - `/strategies/$id` → `/research/strategies/$id`
   - `/research/strategy-studio` → `/research/strategies/$id/studio`
3. 补齐已 reviewed 原型对应的目标 routes。
4. `/showcase` 和 `/instruments` 若保留，标记为 dev-only / utility route，不能进入 IA 主合同。

### P0-2：Page Contract 真源分裂

**问题**：generated contract 只有 Home，legacy contract 是旧 21 route，tests 也硬编码旧口径。  
**影响**：合同不能保护 29 个 reviewed prototypes，也不能驱动 visual audit / app implementation。  
**建议**：

1. 立即停止把 `page-contracts.ts` 作为主真源。
2. 为 29 个 reviewed route page 建立 `docs/contracts/pages/*.contract.json`。
3. `bun run generate-contracts` 生成：
   - `src/features/shell/page-contracts.generated.ts`
   - `scripts/visual-audit.config.generated.mjs`
4. 修改测试：用 IA route list + generated contracts 做 coverage，不再硬编码 legacy route list。
5. legacy contract 只保留为迁移参考，或删除。

### P0-3：候选原型与功能模块落地队列缺少映射

**问题**：新增候选原型已经覆盖 Watchlist、Factor List、Strategy List、Backtest List、Experiment List、Universe List、Platform Settings、Portfolio 等，但 React route / feature module 未跟进。  
**影响**：设计完成度与工程落地状态无法一眼判断，后续会出现“原型通过，但产品功能没入口”的假完成。  
**建议**：

在 `.edition-manifest.json` 或 contract JSON 中补充落地字段：

```json
{
  "landing": {
    "route": "/research/strategies",
    "reactRouteStatus": "missing | scaffolded | implemented",
    "featureModule": "src/features/strategy",
    "contractStatus": "missing | draft | generated | verified",
    "overlayStatus": "gallery-only | triggerable | implemented",
    "visualAuditStatus": "missing | baseline | pass"
  }
}
```

### P1-1：Overlay Gallery 需要统一为 Registry 驱动

**问题**：蓝图将 overlay 定义为页面工作流动作；原型大多将 overlay 放在独立 gallery 展示；React 少数页面直接实现 Drawer。  
**影响**：交互一致性不可控，也不利于候选原型完整落地。  
**更优选择**：

采用“三层统一模型”：

1. **Overlay Registry 是真源**
   - 每个 page contract 必须声明 overlays：

```json
{
  "overlays": [
    {
      "id": "order-confirm",
      "kind": "modal",
      "blocking": true,
      "trigger": {
        "slot": "signal-detail",
        "action": "approve-signal"
      },
      "prototypeSelector": "[data-overlay='overlay-order-confirm']",
      "reactComponent": "OrderConfirmDialog",
      "requiredInDefaultFlow": true,
      "closeBehavior": ["escape", "outside-click", "confirm"]
    }
  ]
}
```

2. **默认页面必须实现核心 overlay 入口**
   - 如果 `requiredInDefaultFlow: true`，原型默认页面必须有触发器，不能只出现在 gallery tab。
   - Gallery 只作为“状态样本镜像”，不作为唯一展示方式。

3. **React 统一消费 Overlay Registry**
   - Drawer / Sheet：用于非阻断详情、配置、检查器、Copilot Sidecar。
   - Modal / AlertDialog：用于确认、删除、审批、下单等阻断动作。
   - Toast：只用于成功/失败反馈，不承载需要决策的信息。
   - Inline / Right rail：用于持续可见的 drill-down，不滥用弹窗。

推荐统一规则：

| 场景 | 组件 | 进入默认页面 | Gallery |
|---|---|---:|---:|
| 行详情 / 审阅 / 配置 | Drawer / Sheet | 必须 | 可镜像 |
| 确认 / 删除 / 下单 / 审批 | Modal / AlertDialog | 必须 | 可镜像 |
| Copilot | Global Sidecar Sheet | 必须全局 | 不作为页面 route |
| 成功 / 失败反馈 | Toast | 动作后触发 | 不需要 gallery |
| 长任务审批 | Inline approval panel / Drawer | 状态驱动 | 可镜像 |

### P1-2：共享 UI primitive 未完全接入 Ditto token 命名层

**问题**：`Button` / `Badge` / `Tabs` 仍大量使用 shadcn 默认 token 名称，而项目 token 层已经是 Ditto semantic 命名。  
**影响**：局部组件可能渲染不到预期颜色，或形成与 prototype 不一致的视觉语法。  
**建议**：

1. 将 `components/ui` 迁移到 Ditto token：
   - `bg-primary` → `bg-(--color-accent)`
   - `text-primary-foreground` → `text-(--color-accent-fg)`
   - `border-border` → `border-(--color-border-default)` 或 `border-(--color-border-subtle)`
   - `ring-ring` → `ring-(--color-focus-ring)`
   - `bg-muted` → `bg-(--color-surface-muted)` 或 interaction token
2. Button / Badge / Tabs 圆角回到 `--radius-4` 为主。
3. Dialog / Sheet overlay 背景使用 overlay opacity scale，不直接 `bg-black/50`。
4. close 按钮改为 icon button，并统一 aria label。

### P1-3：状态栏渲染由页面手动决定，容易漏 padding / 漏合同

**问题**：`StatusBar` 是 fixed overlay，页面需要手动 render，并手动添加 `pb-(--height-status-bar)`。  
**影响**：新页面落地时很容易漏掉 padding 或合同字段，导致底部内容被遮挡。  
**建议**：

1. 让 Shell Layout 或 route contract wrapper 负责 `hasStatusBar`。
2. 页面只声明合同，不直接处理 fixed status bar。
3. visual audit 检查 status bar presence / bottom clearance。

### P1-4：AI 域残留影响导航、域色与心智

**问题**：导航仍有 AI 域，React routes 仍有 AI 三页，DESIGN 仍有 “six business domains” 文案。  
**影响**：产品心智与 v2.0 specs 冲突；域签名色会继续分裂。  
**建议**：

1. `DomainId` 移除 `"ai"`。
2. `DOMAINS` 移除 `/ai`。
3. AI 状态 token 保留为功能 token，不作为 domain token 参与 Rail。
4. `/platform/agents` 使用 Platform 域 + Studio Shell。
5. Copilot 改为全局 Sidecar，可在任意页面通过 command / header button 唤起。

### P1-5：设计文档与 manifest 元数据不同步

**问题**：

- `.arch-manifest.json` 最后审计停留在 2026-04-20。
- `.edition-manifest.json` 已进入 2026-04-27 edition review。
- 21 个 prototype page 缺 `shellFamily` / `blueprintId`。
- `DESIGN.md` 局部仍保留 6 域表述。

**影响**：后续自动生成合同、视觉审计、候选原型排期都会缺少稳定归属。  
**建议**：

1. 更新 `.arch-manifest.json`，记录本轮 edition review 与 route/contract drift。
2. 补齐 `.edition-manifest.json` 的 `shellFamily` / `blueprintId`。
3. 同步 `DESIGN.md`：产品域改 5 域；AI 作为 embedded intelligence / global sidecar。
4. Manifest 增加 `sourceOfTruth` 字段，明确 IA / blueprint / contract / prototype 的上下游顺序。

### P2-1：inline style 与动态尺寸策略不清晰

**问题**：项目规则禁止 inline styles，但 chart / flow / progress 类组件仍用 `style={{ width }}` / `style={{ height }}`。  
**建议**：

- 对纯动态数值组件建立统一例外策略：例如 `DataBar` / `ChartFrame` 这种组件内部允许 CSS variable style，但必须集中封装，业务页面不得直接写 inline styles。
- 如果坚持零 inline style，则使用 bounded variant 或 data attribute + CSS class 映射，但会牺牲任意百分比表达能力。

更优选择是：**允许 design-system primitive 内部极小范围使用 CSS variables，禁止 feature page 直接 inline style。**

### P2-2：跨 feature 组件导入边界需要澄清

当前多个 feature 页面直接 import `@/features/shell/components/panel`、`SidebarToggle` 等。Shell 组件本身是基础设施，这个问题不如跨业务 feature 严重，但建议：

- `features/shell/index.ts` 作为唯一 barrel export。
- feature 页面只从 `@/features/shell` 导入。
- 避免直接深链到 `@/features/shell/components/*`。

---

## 5. 推荐收敛路线

### 第一阶段：治理真源收敛

1. 以 IA v2.0 的 27 路由为主路由表。
2. 更新 `.arch-manifest.json`，记录当前 edition review、route drift、contract drift。
3. 补齐 `.edition-manifest.json` 的 `shellFamily` / `blueprintId` / landing 状态。
4. 为所有 reviewed route pages 创建 contract JSON。
5. 重新生成 `page-contracts.generated.ts` 与 `visual-audit.config.generated.mjs`。
6. 修改 tests：验证 IA route coverage、prototype coverage、contract coverage 三者一致。

### 第二阶段：路由与域迁移

1. 移除 Rail AI 域。
2. 新增 `/platform/agents`，复用现有 Agent Console 组件迁移。
3. 把 `/ai/copilot` 改为全局 Sidecar。
4. 迁移 Strategy routes 到 Research 域。
5. 补齐 Watchlist / Portfolio / Settings / List pages 的 route scaffold。
6. 为旧路由提供 redirect 或明确 deprecation，不让旧路由进入合同。

### 第三阶段：Overlay Registry

1. 从蓝图抽取每页 Overlay Registry。
2. 原型层：所有 required overlay 在默认页面提供真实触发入口，gallery 只镜像。
3. React 层：统一用 `OverlayProvider` / `Drawer` / `Dialog` / `AlertDialog` 组件落地。
4. 测试层：每个 required overlay 至少覆盖 open / close / primary action / keyboard close。
5. visual audit：验证 overlay selector、尺寸、遮罩、焦点管理基础项。

### 第四阶段：组件 token 收敛

1. 迁移 `components/ui` 到 Ditto token。
2. 引入 `DittoButton` / `DittoDialog` / `DittoSheet` 的 contract test，禁止 shadcn 默认 token 泄漏。
3. 收敛 typography：禁止新增 arbitrary `text-[...]`，现有保留项逐步改为 token alias。
4. 收敛 spacing：页面布局优先用 density token，局部组件可以用 4pt utility，但必须符合 density preset。

---

## 6. Overlay 统一落地规范草案

候选原型到 React 功能落地时，建议采用以下准入标准：

### 6.1 原型准入

每个 page prototype 若声明 `stateCoverage.overlays > 0`，必须满足：

- 有 `overlays-gallery`：用于完整展示所有 overlay 变体。
- 有默认页面触发器：用于核心工作流中的 required overlay。
- 每个 overlay 有稳定 id：如 `overlay-order-confirm`。
- 每个触发器能映射到一个工作流动作：如 `approve-signal`、`edit-watchlist`、`open-detail`。

### 6.2 Contract 准入

每个 contract 必须声明：

- `overlays[].id`
- `overlays[].kind`
- `overlays[].blocking`
- `overlays[].requiredInDefaultFlow`
- `overlays[].trigger.slot`
- `overlays[].trigger.action`
- `overlays[].prototypeSelector`
- `overlays[].reactComponent`
- `overlays[].closeBehavior`

### 6.3 React 准入

每个 required overlay 必须有：

- 可访问触发入口（button / row action / menu item）
- Radix Dialog / Sheet 基础焦点管理
- ESC 关闭
- 合理 aria label / title / description
- 对主动作的测试
- 对关闭后的页面状态恢复测试

### 6.4 Gallery 定位

Gallery 不应被取消，但定位要变：

- Gallery 是 QA / Design Review / Snapshot 的状态样本页。
- 默认页面是用户真实工作流。
- 同一 overlay 内容由 Registry 驱动，避免 gallery 与页面实现分叉。

---

## 7. 当前更优选择判断

### 更优选择 A：先收 Page Contract，不先批量补页面

原因：当前 route / contract / visual-audit 三者断裂。如果先补 React 页面，会继续复制旧路由和旧 token 问题。  
预期收益：一次性建立 29 个 reviewed prototypes 的落地地图，后续每补一个页面都有验收门禁。

### 更优选择 B：AI 不再作为域，只作为 capability

原因：IA / Shell spec 已统一为 5 域，AI sidecar 是跨域能力。继续保留 AI 域会让导航、域色、路由、合同全部分裂。  
预期收益：产品心智更清楚，Agent Console 归 Platform，Copilot 归全局交互层。

### 更优选择 C：Overlay Registry 优先于组件局部实现

原因：订单确认、审批、删除、配置、详情查看都是跨页面一致性问题，不应由每个页面各自拼 Drawer / Dialog。  
预期收益：原型、合同、React、测试能围绕同一组 overlay id 对齐。

### 更优选择 D：组件 token 层先清理 `components/ui`

原因：Button / Badge / Tabs 是后续所有页面的基础。如果 primitive 仍是 shadcn 默认 token，页面越多越难收。  
预期收益：颜色、字体、圆角、focus、density 在基础层统一。

---

## 8. 建议优先级

| 优先级 | 工作项 | 目标结果 |
|---|---|---|
| P0 | 生成 29 个 page contract | `page-contracts.generated.ts` 覆盖 reviewed prototypes |
| P0 | IA route coverage test | 缺失 / 旧路由在 CI 中直接暴露 |
| P0 | Overlay Registry schema | gallery-only 和 default-flow overlay 有统一判定 |
| P1 | AI 域迁移 | Rail 5 域、Agent Console 到 `/platform/agents`、Copilot Sidecar |
| P1 | Strategy route 迁移 | Strategy List / Detail / Studio 全部归 Research |
| P1 | `components/ui` token 迁移 | 消除 shadcn token 泄漏 |
| P1 | StatusBar contract wrapper | 页面不再手写 status bar + padding |
| P2 | inline style 策略 | dynamic visual primitive 有明确例外边界 |

---

## 9. 本次审查命令与结果

已执行静态审计脚本：

- IA route list 与 `src/routes` 的 `createFileRoute` 对比。
- `.edition-manifest.json` page / overlay / metadata 扫描。
- `src` 中 inline style、arbitrary text、arbitrary radius、shadcn token、large radius、raw spacing 统计。
- `Dialog` / `Sheet` / `Drawer` / overlay usage 搜索。
- `StatusBar` 使用与合同字段搜索。
- `git status --short` 查看当前工作区证据状态。

最终验证：

```bash
bun run check
```

结果：

- `biome check .`：PASS，输出 `Checked 5 files in 360ms. No fixes applied.`
- `tsc -b`：FAIL，未进入 `vitest run`

失败集中在既有 TypeScript 问题：

- test globals 未导入或类型未配置：`beforeEach`、`afterEach`、`beforeAll`、`afterAll`、`vi`
- table / grid 泛型不匹配：`ColumnDef<TestRow>` 与 `ColumnDef<Record<string, unknown>>`
- TanStack Router route options：多处 `handle` 字段不被当前类型接受
- API 类型导出漂移：`OrdersSummaryResponse` / `GetOrdersSummaryResponse`、`SignalsQueueResponse` / `GetSignalsQueueResponse`
- mock fixture 与类型定义不一致：`AgentFinding`、`NorthboundFlow`、`RunStatus`
- Node / ImportMeta 类型缺口：`node:path`、`ImportMeta.dirname`
- 少量 unused imports / unused locals

本报告是审计文档，没有改动业务实现；上述失败不是由本报告新增代码触发，但会阻塞“工程全绿”声明。

---

## 附录：Remediation Completed — 2026-04-27

本报告列出的 P0/P1 一致性问题已按 `docs/plans/2026-04-27-consistency-remediation-plan.md` 完成治理闭环：

- `bun run check` 已恢复全绿：Biome、TypeScript、Vitest 均通过。
- IA v2.0 的 27 条产品路由已由 `scripts/audit-route-coverage.mjs` 守护；`/ai`、`/ai/copilot`、`/ai/agents` 不再作为产品路由保留。
- `docs/contracts/pages/` 已补齐 27 个页面 contract，并重新生成 `src/features/shell/page-contracts.generated.ts` 与 `scripts/visual-audit.config.generated.mjs`。
- AI 已从独立导航域迁出：Agent Console 落到 `/platform/agents`，Copilot 作为全局 sidecar，AI Overview / AI Copilot 原型在 edition manifest 中标为 deprecated prototype。
- Overlay schema 已支持 `landing` 与 `overlays`；Orders、Signals、Risk 等核心 required overlay 进入 contract 与 runtime registry 口径。
- Button、Badge、Tabs、Dialog、Sheet 已迁移到 Ditto semantic tokens，并新增 leakage tests 防止 shadcn 默认 token 回流。
- feature 层 inline style 已清零；动态 chart / progress 只允许在明确 allowlist 的 shared primitive 中存在。

最终治理状态以 `.arch-manifest.json` 与 `docs/designs/specs/prototypes/.edition-manifest.json` 为准。
