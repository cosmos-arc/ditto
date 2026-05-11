# v2 交互范式实施计划

## Context

v1 原型的核心交互问题是 `100vh; overflow: hidden` 锁定视口导致信息遮挡、区块内滚动体验差。设计决策文档 `docs/designs/decisions/2026-04-15-v2-interaction-paradigm.md` 定义了 5 个核心变更（D1-D5）。

**本计划仅覆盖 Phase 1（交互范式变更）**，不包含 Phase 2（样式 Bug 修复）。

**范围**：仅修改 Prototype HTML 文件和 `layout-base.css`，不涉及 React 代码。

---

## Phase 1：Foundation — layout-base.css 共享样式

### 1.1 body overflow 解锁
- **文件**: `docs/designs/specs/prototypes/shared/layout-base.css` L22
- **改**: `overflow: hidden` → `overflow-y: auto`
- **影响**: 所有页面。Shell 本身仍 `height: 100vh; overflow: hidden`，不受影响

### 1.2 新增 `.shell-v2` grid（替代 `.shell` 的 pulse 行为）
- **文件**: 同上，L98 后新增
- **内容**: 新增 `.shell-v2` class，grid-template-areas 中 pulse → status
- **风险**: 低。纯新增，不影响现有 `.shell`

### 1.3 `.shell-main` overflow 改为可滚动
- **文件**: 同上，L338
- **改**: `overflow: hidden` → `overflow-y: auto`
- **影响**: 仅 page-home.html 使用 `.shell-main`

### 1.4 `.main-primary` 去掉 max-height 约束
- **文件**: 同上，L342-350
- **改**: 删除 `overflow: hidden` 和 `max-height: 66%`
- **影响**: 仅 page-home.html

### 1.5 新增 Status Bar 样式
- **文件**: 同上，L329 后新增
- **内容**: `.shell-status-bar`, `.status-bar-item`, `.status-bar-separator` 样式

### 1.6 新增 Sidebar collapsed 模式
- **文件**: 同上，L369 后新增
- **内容**: `.shell-sidebar-collapsed` 及子元素样式
- **文件**: `src/styles/design-tokens/tokens-shell.css` — 新增 `--shell-sidebar-collapsed-width: 48px`

### 1.7 共享 Shell 变量 overflow 更新

按 D5 规则，以下 shell 变量从 `height: 100vh; overflow: hidden` 改为 `height: 100vh; overflow: hidden`（**保持锁定**）或 `min-height: 100vh; overflow-y: auto`（**改为滚动**）：

| Shell Class | 行号 | 变更 | 原因 |
|---|---|---|---|
| `.shell-analytical` | L2667 | `min-height: 100vh; overflow-y: auto` | D5: Main 自然滚动 |
| `.shell-catalog` | L2772 | **保持锁定** | D5 例外: 表格内部滚动 |
| `.shell-ops` | L2815 | `min-height: 100vh; overflow-y: auto` | D5: Main 自然滚动 |
| `.shell-research` | L2183 | `min-height: 100vh; overflow-y: auto` | D5: Main 自然滚动 |
| `.shell-risk` | L2454 | `min-height: 100vh; overflow-y: auto` | D5: Main 自然滚动 |
| `.shell-screener` | L1466 | **保持锁定** | D5 例外: 表格内部滚动 |
| `.shell-signals` | L1840 | `min-height: 100vh; overflow-y: auto` | D5: Main 自然滚动 |

`.shell-radar` 和 `.shell-intel` 已经是滚动模式，无需修改。

---

## Phase 2：Home 页面（D3 + D4）— 最复杂

**文件**: `docs/designs/specs/prototypes/page-home.html`

### 2.1 Shell class 切换
- L799: `class="shell shell-home"` → `class="shell-v2 shell-home"`

### 2.2 Pulse Strip → Status Bar（D4）
- L870-901: 将 `.shell-pulse` div 替换为 `.shell-status-bar` div
- 保留核心信息（盘中状态、PnL、风险、Regime、待处理/运行中）
- 缩减为 10px 字号的轻量状态行

### 2.3 去掉 shell-secondary，单列流式（D3）
- L1095-1182: 将 Research Progress 和 Agent Findings 从 `.shell-secondary` 移出
- 放入 `.main-primary` 内作为全宽 panel
- 删除 `.shell-secondary` wrapper

### 2.4 删除 Workspace Placeholder
- L1080-1085: 删除整个 `.workspace-placeholder` div

### 2.5 添加 Sidebar toggle 按钮
- 在 `.context-rail` 末尾添加 `.sidebar-toggle` 按钮

### 2.6 Sidebar 区块折叠（D2）
- 市场脉搏: 3 个核心指标默认展示，北向资金折叠
- 全局预警: critical 默认展示，warning/info 折叠
- 数据健康: gauge 条 + 异常项始终展示，正常项折叠

### 2.7 Priority Queue 折叠（D1 Progressive Disclosure）
- P1 项完整展示（通常 1-3 项）
- P2/P3 折叠到 `[+N more ▾]`

---

## Phase 3：layout-base.css 共享 Shell 页面

### 3.1 `.shell-analytical` 页面（3 个）
| 页面 | 额外变更 |
|---|---|
| `page-risk-center.html` | 无 sidebar，Phase 1.7 已处理滚动 |
| `page-trading-overview.html` | 同上，L281 `.trading-variant` 保持 |
| `page-research.html` | 同上 |

### 3.2 `.shell-catalog` 页面（2 个）— 保持锁定
| 页面 | 额外变更 |
|---|---|
| `page-markets-screener.html` | 无 |
| `page-markets-calendar.html` | 无 |

### 3.3 `.shell-signals` 页面（1 个）
| 页面 | 额外变更 |
|---|---|
| `page-signals-inbox.html` | Phase 1.7 已处理滚动 |

### 3.4 `.shell-ops` 页面（1 个）
| 页面 | 额外变更 |
|---|---|
| `page-platform.html` | Phase 1.7 已处理滚动 |

---

## Phase 4：页面级 Grid 覆盖页面

每个页面修改自己的 shell class 中的 `height: 100vh; overflow: hidden` → `min-height: 100vh; overflow-y: auto`。

| 页面 | Shell Class | 行号 | D5 备注 |
|---|---|---|---|
| `page-instrument-hub.html` | `.shell-hub` | L134-135 | 无 sidebar |
| `page-backtest-result.html` | `.shell-hub` | L62 | 同上 |
| `page-factor-analysis.html` | `.shell-hub` | L107-108 | 同上 |
| `page-strategies-detail.html` | `.shell-hub` | L118-119 | 同上 |
| `page-strategy-studio.html` | `.shell-studio` | L159-160 | D5: 保持三栏 grid，Source/Inspector 可折叠 |
| `page-regime-monitor.html` | `.shell-regime` | L137-138 | 有 activity 列，可收窄 |
| `page-ai-overview.html` | `.ai-shell` | L168-169 | 有 sidebar，可收窄 |
| `page-ai-copilot.html` | `.shell-copilot` | L132-134 | D5: Studio family，保持三栏 |
| `page-agent-console.html` | `.shell-agent` | L108-110 | 有 detail 列 |
| `page-orders-ledger.html` | `.shell-ledger` | L125-127 | 有 trace 列 |

---

## Phase 5：已滚动页面 — 仅 D2 Sidebar/Rail 收窄

| 页面 | Shell Class | 变更 |
|---|---|---|
| `page-markets-intelligence.html` | `.shell-intel` | 右侧 rail 添加 toggle |
| `page-a-shares.html` | `.shell-radar` | 右侧 rail 添加 toggle |
| `page-cross-market.html` | `.shell-radar` | 右侧 rail 添加 toggle |

---

## 执行顺序

```
Phase 1 (layout-base.css + tokens-shell.css)
  ↓
Phase 2 (Home) ──┐
Phase 3 (共享 shell 页面) ──┼── 可并行
Phase 4 (页面级 grid 页面) ──┤
Phase 5 (已滚动页面) ───────┘
  ↓
浏览器逐页验证
```

**建议**：先完成 Phase 1 + Phase 2（Home），在浏览器中验证效果后，再批量处理其余页面。

---

## 验证方式

每个页面修改后：
1. `cd docs/designs/specs/prototypes && python3 -m http.server 8888`
2. 浏览器打开 `http://localhost:8888/page-xxx.html`
3. 检查项：
   - [ ] 无双滚动条
   - [ ] Main 区域可自然滚动
   - [ ] Sidebar/Rail 有 toggle 按钮
   - [ ] 折叠组件展开/收起正常
   - [ ] 首屏无信息遮挡
   - [ ] 暗色/亮色主题切换正常
   - [ ] 紧/标/松密度切换正常

---

## 关键文件清单

| 文件 | 变更类型 |
|---|---|
| `docs/designs/specs/prototypes/shared/layout-base.css` | 核心变更 |
| `src/styles/design-tokens/tokens-shell.css` | 新增 token |
| `docs/designs/specs/prototypes/page-home.html` | 最大变更 |
| `docs/designs/specs/prototypes/page-*-hub.html` (×4) | overflow 变更 |
| `docs/designs/specs/prototypes/page-strategy-studio.html` | overflow 变更 |
| `docs/designs/specs/prototypes/page-regime-monitor.html` | overflow 变更 |
| `docs/designs/specs/prototypes/page-ai-overview.html` | overflow 变更 |
| `docs/designs/specs/prototypes/page-ai-copilot.html` | overflow 变更 |
| `docs/designs/specs/prototypes/page-agent-console.html` | overflow 变更 |
| `docs/designs/specs/prototypes/page-orders-ledger.html` | overflow 变更 |
| `docs/designs/specs/prototypes/page-risk-center.html` | 验证（Phase 1 自动生效） |
| `docs/designs/specs/prototypes/page-trading-overview.html` | 验证 |
| `docs/designs/specs/prototypes/page-research.html` | 验证 |
| `docs/designs/specs/prototypes/page-signals-inbox.html` | 验证 |
| `docs/designs/specs/prototypes/page-platform.html` | 验证 |
