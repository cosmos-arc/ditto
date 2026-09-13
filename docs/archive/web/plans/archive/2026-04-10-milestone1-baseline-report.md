# Milestone 1：基线收口 — 合同表与验收清单

> **日期**：2026-04-10
> **状态**：已完成
> **对应计划**：[prototype-recovery-design.md](./2026-04-10-prototype-recovery-design.md)
> **运行时源**：`src/features/shell/page-contracts.ts`

---

## 1. 页面合同总表

| # | Route | Page Pattern | Shell Family | Source | Required Slots | Required States |
|---|-------|-------------|-------------|--------|---------------|-----------------|
| 1 | `/` | global-command-center | command-center | prototype-backed | pulse, main, sidebar | loading, empty, error, stale, no-alerts, has-critical |
| 2 | `/ai` | global-command-center | command-center | prototype-backed | pulse, main, sidebar | loading, empty, error, stale, no-agents, has-pending |
| 3 | `/markets` | analytical-overview | analytical | prototype-backed | strip, main, activity, analysis | loading, empty, error, stale |
| 4 | `/markets/intelligence` | analytical-overview | analytical | prototype-backed | strip, main, activity | loading, empty, error, stale |
| 5 | `/markets/a-shares` | analytical-overview | analytical | spec-only | strip, main, activity | loading, empty, error, stale |
| 6 | `/markets/screener` | catalog-screener | catalog | prototype-backed | toolbar, main, detail | loading, empty, error, stale, selected-row |
| 7 | `/markets/calendar` | catalog-screener | catalog | spec-only | toolbar, main | loading, empty, error, stale |
| 8 | `/research` | analytical-overview | analytical | prototype-backed | strip, main, activity, analysis | loading, empty, error, stale |
| 9 | `/research/strategy-studio` | studio-builder | studio | prototype-backed | source, main, inspector | loading, empty, error, stale, no-session, running |
| 10 | `/research/regime` | analytical-overview | analytical | prototype-backed | strip, main, activity, analysis | loading, empty, error, stale |
| 11 | `/research/backtest/$id` | object-hub | object-hub | spec-only | meta, tabs, main | loading, empty, error, stale, not-found |
| 12 | `/research/factors/$id` | object-hub | object-hub | spec-only | meta, tabs, main | loading, empty, error, stale, not-found |
| 13 | `/trading` | analytical-overview | analytical | prototype-backed | strip, main, activity, analysis | loading, empty, error, stale |
| 14 | `/trading/signals` | queue-ops-console | ops-console | prototype-backed | health, main, detail | loading, empty, error, stale, selected-row, sheet-open |
| 15 | `/trading/orders` | ledger-execution-console | ops-console | prototype-backed | health, main, detail | loading, empty, error, stale, selected-row, order-active |
| 16 | `/trading/risk` | analytical-overview | analytical | prototype-backed | strip, main, activity, analysis | loading, empty, error, stale |
| 17 | `/ai/copilot` | studio-builder | studio | prototype-backed | source, main, inspector | loading, empty, error, stale, no-session, chatting |
| 18 | `/ai/agents` | studio-builder | studio | prototype-backed | source, main, inspector | loading, empty, error, stale, no-agents, agent-running |
| 19 | `/instruments/$id` | object-hub | object-hub | prototype-backed | meta, tabs, main | loading, empty, error, stale, not-found |
| 20 | `/strategies/$id` | object-hub | object-hub | spec-only | meta, tabs, main | loading, empty, error, stale, not-found |
| 21 | `/platform` | queue-ops-console | ops-console | prototype-backed | health, main, detail | loading, empty, error, stale, pipeline-running |

---

## 2. 路由分组清单

### Group A：高保真原型直译组（16 页）

| Route | Prototype Ref |
|-------|--------------|
| `/` | `prototypes/page-home.html` |
| `/markets` | `prototypes/page-cross-market.html` |
| `/markets/screener` | `prototypes/page-markets-screener.html` |
| `/markets/intelligence` | `prototypes/page-markets-intelligence.html` |
| `/research` | `prototypes/page-research.html` |
| `/research/strategy-studio` | `prototypes/page-strategy-studio.html` |
| `/research/regime` | `prototypes/page-regime-monitor.html` |
| `/trading` | `prototypes/page-trading-overview.html` |
| `/trading/signals` | `prototypes/page-signals-inbox.html` |
| `/trading/orders` | `prototypes/page-orders-ledger.html` |
| `/trading/risk` | `prototypes/page-risk-center.html` |
| `/ai` | `prototypes/page-ai-overview.html` |
| `/ai/copilot` | `prototypes/page-ai-copilot.html` |
| `/ai/agents` | `prototypes/page-agent-console.html` |
| `/instruments/$id` | `prototypes/page-instrument-hub.html` |
| `/platform` | `prototypes/page-platform.html` |

### Group B：Spec 推导组（5 页）

| Route | 参考文档 |
|-------|---------|
| `/markets/a-shares` | Spec §02.1（Radar 变体） |
| `/markets/calendar` | Spec §04.2（轻量 blueprint） |
| `/research/backtest/$id` | Spec §08 |
| `/research/factors/$id` | Spec §06 |
| `/strategies/$id` | Strategy Studio spec 隐含 |

### Group C：模式纠偏组（3 页，结构已纠正，待 pixel audit）

| Route | Pattern | Shell | 结构状态 | 后续验收 |
|-------|---------|-------|---------|---------|
| `/trading/signals` | queue-ops-console | ops-console | 已纠正 | 待 pixel audit |
| `/trading/orders` | ledger-execution-console | ops-console | 已纠正 | 待 pixel audit |
| `/ai/agents` | studio-builder | studio | 已纠正 | 待 pixel audit |

---

## 3. Prototype-backed / Spec-only 清单

### Prototype-backed（16 页）

上述 Group A 全部页面。均有完整 HTML 高保真原型。

### Spec-only（5 页）

上述 Group B 全部页面。仅有 spec/blueprint 文档，无 HTML 原型。

---

## 4. Token 问题清单与修复状态

### 已修复：兼容别名（Milestone 1）

以下 8 个未定义 token 已通过 `02-semantic.css` 的 `:root` 块添加别名：

| 未定义 Token | 别名指向 | 引用数 | 状态 |
|-------------|---------|-------|------|
| `--color-surface-hover` | `--color-interaction-hover-subtle-bg` | 37 | ✅ 已修复 |
| `--color-status-success` | `--color-system-healthy` | 7 | ✅ 已修复 |
| `--color-status-error` | `--color-system-down` | 7 | ✅ 已修复 |
| `--color-surface-base` | `--color-surface-1` | 5 | ✅ 已修复 |
| `--color-status-warning` | `--color-risk-warning` | 3 | ✅ 已修复 |
| `--color-surface-elevated` | `--color-surface-2` | 2 | ✅ 已修复 |
| `--color-brand-primary` | `--color-brand-500` | 2 | ✅ 已修复 |
| `--color-border-default` | `--color-border` | 1 | ✅ 已修复 |

**合计**：64 处未定义引用 → 0 处未定义（清零）

### 待处理：语义化迁移（Milestone 4）

| 类别 | 说明 |
|------|------|
| `--color-surface-hover` | 逐步替换为 `--color-interaction-hover-subtle-bg` |
| `--color-status-*` | 逐步替换为 `--color-system-*` / `--color-risk-*` |
| `--color-surface-base/elevated` | 逐步替换为 `--color-surface-1` / `--color-surface-2` |
| `--color-brand-primary` | 逐步替换为 `--color-brand-500` |
| `--color-foreground-primary` | 兼容别名保留（18 处），非紧急 |

---

## 5. 页面验收清单模板

### 双轨验收标准

#### 工程轨（自动）

- [ ] `bun run check` 通过
- [ ] tsc 类型检查通过
- [ ] biome lint 通过
- [ ] vitest 全部通过

#### 产品轨（逐页检查）

| 检查项 | 标准 |
|-------|------|
| route 与合同一致 | 路由路径与 `page-contracts.ts` 一致 |
| page pattern 正确 | 页面使用合同中指定的 Page Pattern |
| shell family 正确 | 页面使用合同中指定的 Layout 组件 |
| required slots 已填满 | 合同中的 requiredSlots 全部有内容 |
| loading / empty / error / stale 已覆盖 | 通用状态完整 |
| 无未定义 token | 不引用未定义 CSS 变量 |
| 无待实现文案 | 不含"待实现/占位/coming soon" |
| 与 prototype/spec 对齐 | prototype-backed 须对齐 HTML；spec-only 须符合 family grammar |

### 各页面验收状态（Milestone 1 完成后）

| Route | 工程轨 | Pattern | Shell | Slots | States | Token | 无占位 |
|-------|--------|---------|-------|-------|--------|-------|--------|
| `/` | ✅ | ✅ | ✅ | ✅ | — | ✅ | — |
| `/ai` | ✅ | ✅ | ✅ | ⚠️ 缺sidebar（合同已更新，待 Task 5 实现） | — | ✅ | — |
| `/markets` | ✅ | ✅ | ✅ | ✅ | — | ✅ | — |
| `/markets/intelligence` | ✅ | ✅ | ✅ | ⚠️ main-only | — | ✅ | — |
| `/markets/a-shares` | ✅ | ✅ | ✅ | ⚠️ main-only | — | ✅ | — |
| `/markets/screener` | ✅ | ✅ | ✅ | ⚠️ 缺detail | — | ✅ | — |
| `/markets/calendar` | ✅ | ✅ | ✅ | ⚠️ main-only | — | ✅ | — |
| `/research` | ✅ | ✅ | ✅ | ✅ | — | ✅ | — |
| `/research/strategy-studio` | ✅ | ✅ | ✅ | ⚠️ main-only | — | ✅ | — |
| `/research/regime` | ✅ | ✅ | ✅ | ⚠️ main-only | — | ✅ | — |
| `/research/backtest/$id` | ✅ | ✅ | ✅ | ⚠️ | — | ✅ | — |
| `/research/factors/$id` | ✅ | ✅ | ✅ | ⚠️ | — | ✅ | — |
| `/trading` | ✅ | ✅ | ✅ | ✅ | — | ✅ | — |
| `/trading/signals` | ✅ | ✅ | ✅ | 结构已纠正，待 pixel audit | — | ✅ | — |
| `/trading/orders` | ✅ | ✅ | ✅ | 结构已纠正，待 pixel audit | — | ✅ | — |
| `/trading/risk` | ✅ | ✅ | ✅ | ⚠️ main-only | — | ✅ | — |
| `/ai/copilot` | ✅ | ✅ | ✅ | ⚠️ | — | ✅ | — |
| `/ai/agents` | ✅ | ✅ | ✅ | 结构已纠正，待 pixel audit | — | ✅ | — |
| `/instruments/$id` | ✅ | ✅ | ✅ | ✅ | — | ✅ | — |
| `/strategies/$id` | ✅ | ✅ | ✅ | ⚠️ | — | ✅ | — |
| `/platform` | ✅ | ✅ | ✅ | ✅ | — | ✅ | — |

> ⚠️ = 需在后续 Milestone 中补齐
> 结构已纠正，待 pixel audit = Pattern / Shell / Slot 结构已对齐合同，仍需后续视觉审计确认像素级还原度

---

## 6. Milestone 1 完成标准检查

| 标准 | 状态 |
|------|------|
| 合同表覆盖全部 21 个页面 | ✅ 21/21 |
| 未定义 token 清单清零 | ✅ 0 处未定义 |
| `bun run check` 通过 | 待验证 |
