# Prototype → React 实现待办

> **来源**: 原型迭代审查与页面合同（`contracts/pages/*.contract.json`）。
> **目标**: 把 prototype-only polish 与必须进入 React 产品实现的工作分离，并为每个已落地 React route 建立 contract → feature → test 的交接链路。

---

## 状态语义

### Prototype-only polish

仅服务静态 HTML 原型或已经在原型层完成的视觉表达，不直接进入 React 产品 backlog。若未来发现影响真实产品体验，再提升为 React product work。

- Tooltip 静态标注：原型中的 `data-tooltip` 只证明信息架构，不代表 React 交互实现。
- Inline SVG sparkline：原型中的静态曲线只作为视觉基线，React 需由 Chart Cockpit 接管真实数据渲染。
- CSS-only status pulse：原型动画只表达状态意图，React 需由状态模型驱动。
- 原型 opacity 层级：`.decision-cta.secondary`、`findings-feed-subtitle` 等原型 polish 不直接新增 token；若产品实现需要，走 Design Token 审批。
- Workspace emoji placeholder：原型占位只记录空状态意图，React 由 Workspace Memory epic 处理真实空态与图标体系。
- Prototype overlay gallery：只保留为合同证据，不等同于 React overlay 焦点管理、ESC、inert、动画与状态机。

### React product work

必须进入应用实现、测试和视觉审计队列。

- `landing.visualAuditStatus = "missing"`：React route 缺失或尚无可审计页面。
- `landing.visualAuditStatus = "queued"`：React route、feature module、`reactTestRefs` 已建立，等待视觉审计执行。
- `landing.visualAuditStatus = "implemented"`：React 视觉审计 harness 已能稳定执行并产出基线，但尚未达到验收证据。
- `landing.visualAuditStatus = "verified"`：有明确视觉审计通过证据；禁止无证据标记。

---

## React Product Epics

### Epic 1: Command Action Bus

**范围**: 统一 Command Palette、上下文动作、批量动作、对象选择状态与权限过滤。

- 合同来源：`overlays[].trigger`、`data-command-scope`、`data-command-context-actions`、catalog/queue/ops 页面交互。
- 首批动作：Watchlist `generate-signal/open-instrument-hub/send-to-research/remove-watch`；Strategy List `run-backtest/clone-strategy/view-recent-runs/pause-strategy`；Backtest List `add-to-compare/view-curve/copy-params/generate-report`；Signals Inbox `approve/reject/send-to-order/view-evidence`；Platform `retry/view-logs/mute-alert/create-incident`。
- 涉及 routes：`/markets/watchlist`、`/research/strategies`、`/research/backtest`、`/trading/signals`、`/platform`。
- 涉及 modules：`src/features/markets`、`src/features/strategy`、`src/features/backtest`、`src/features/trading`、`src/features/platform`、`src/features/shell`。
- 测试交接：各页面合同的 `landing.reactTestRefs` 加 feature 组件测试；新增 shell/action bus 单元测试覆盖过滤、选区同步、禁用态与键盘触发。

### Epic 2: Chart Cockpit

**范围**: 用真实数据与可测试 chart abstraction 替换原型静态 sparkline、K 线、回测曲线、风险曲线和市场脉搏。

- 合同来源：`pagePattern = analytical-overview | object-hub | global-command-center` 的主数据可视化区域。
- 涉及 routes：`/`、`/markets`、`/markets/a-shares`、`/markets/intelligence`、`/instruments/$id`、`/research/backtest/$id`、`/trading`、`/trading/risk`。
- 涉及 modules：`src/features/home`、`src/features/markets`、`src/features/instruments`、`src/features/backtest`、`src/features/trading`。
- 测试交接：复用合同 `reactTestRefs` 中的 page/component tests；新增 chart adapters 测试覆盖空态、stale、实时刷新、reduced-motion 和 resize。

### Epic 3: Workspace Memory

**范围**: 持久化用户工作台状态，包括 rail 折叠、bottom tray、表格列宽、冻结列、面板尺寸、选中对象和最近上下文。

- 合同来源：`responsiveBehavior`、catalog detail panel、studio inspector、ops detail、Home workspace placeholder。
- 涉及 routes：`/`、所有 catalog 页面、studio 页面、ops console 页面。
- 涉及 modules：`src/features/home`、`src/features/screener`、`src/features/research`、`src/features/strategy`、`src/features/backtest`、`src/features/trading`、`src/features/platform`、`src/features/shell`。
- 测试交接：`src/features/shell/hooks/use-ui-preferences.test.ts` 承接 shell 偏好；各 feature test refs 承接页面恢复、降级和选中对象联动。

### Epic 4: Context Menu

**范围**: 统一右键/更多菜单/行级动作菜单，承接 Command Action Bus 的动作注册与可访问性要求。

- 合同来源：catalog rows、queue rows、ops rows、object hub action slots、prototype overlay triggers。
- 涉及 routes：`/markets/screener`、`/markets/watchlist`、`/research/factors`、`/research/strategies`、`/research/backtest`、`/trading/signals`、`/trading/orders`、`/platform`。
- 涉及 modules：`src/features/screener`、`src/features/markets`、`src/features/research`、`src/features/strategy`、`src/features/backtest`、`src/features/trading`、`src/features/platform`、`src/features/shell`。
- 测试交接：新增 shell context menu 行为测试；feature tests 覆盖菜单项可见性、disabled reason、键盘导航和焦点返回。

### Epic 5: Toast System

**范围**: 将 prototype toast 合同转换为 React toast provider、队列策略、语义级别与可访问播报。

- 合同来源：`overlays[].kind = "toast"`，尤其是 strategy studio validation、ops retry/mute、signals/order 操作反馈。
- 涉及 routes：`/research/strategies/$id/studio`、`/trading/signals`、`/trading/orders`、`/platform`、`/platform/agents`。
- 涉及 modules：`src/features/strategy`、`src/features/trading`、`src/features/platform`、`src/features/shell`。
- 测试交接：新增 shell toast provider 测试；feature tests 覆盖成功、失败、撤销、重复合并和 `aria-live` 播报。

---

## Contract Handoff Matrix

| Route | Contract | React component | Feature module | React tests | Visual audit |
| --- | --- | --- | --- | --- | --- |
| `/` | `home.contract.json` | `HomePage` | `src/features/home` | `home-components.test.tsx`, `home-hooks.test.tsx` | `queued` |
| `/markets` | `cross-market.contract.json` | `MarketsPage` | `src/features/markets` | `markets-page.test.tsx`, `markets-components.test.tsx` | `queued` |
| `/markets/a-shares` | `a-shares.contract.json` | `ASharesPage` | `src/features/markets` | `a-shares-components.test.tsx` | `queued` |
| `/markets/screener` | `markets-screener.contract.json` | `ScreenerPage` | `src/features/screener` | `info-level-annotations.test.tsx`, `screener-components.test.tsx` | `queued` |
| `/markets/watchlist` | `watchlist.contract.json` | `WatchlistPage` | `src/features/markets` | `markets-components.test.tsx` | `queued` |
| `/markets/intelligence` | `markets-intelligence.contract.json` | `IntelligencePage` | `src/features/markets` | `intelligence-page.test.tsx`, `intelligence-components.test.tsx` | `queued` |
| `/markets/calendar` | `markets-calendar.contract.json` | `CalendarPage` | `src/features/markets` | `calendar-components.test.tsx` | `queued` |
| `/instruments/$id` | `instrument-hub.contract.json` | `InstrumentHubPage` | `src/features/instruments` | `info-level-annotations.test.tsx`, `instrument-components.test.tsx` | `queued` |
| `/research` | `research.contract.json` | `ResearchPage` | `src/features/research` | `info-level-annotations.test.tsx`, `research-components.test.tsx` | `queued` |
| `/research/alpha` | `alpha-explorer.contract.json` | none, route missing | `src/features/research` | none, route missing | `missing` |
| `/research/factors` | `factor-list.contract.json` | `FactorListPage` | `src/features/research` | `research-components.test.tsx`, `factor-components.test.tsx`, `factor-table.test.tsx` | `queued` |
| `/research/factors/$id` | `factor-analysis.contract.json` | `FactorPage` | `src/features/research` | `info-level-annotations.test.tsx`, `factor-components.test.tsx` | `queued` |
| `/research/strategies` | `strategy-list.contract.json` | `StrategyListPage` | `src/features/strategy` | `strategy-components.test.tsx` | `queued` |
| `/research/strategies/$id` | `strategies-detail.contract.json` | `StrategyDetailPage` | `src/features/strategy` | `info-level-annotations.test.tsx`, `strategy-detail-components.test.tsx` | `queued` |
| `/research/strategies/$id/studio` | `strategy-studio.contract.json` | `StrategyPage` | `src/features/strategy` | `info-level-annotations.test.tsx`, `strategy-components.test.tsx`, `studio-mode-bar.test.tsx` | `queued` |
| `/research/backtest` | `backtest-list.contract.json` | `BacktestListPage` | `src/features/backtest` | `backtest-components.test.tsx` | `queued` |
| `/research/backtest/$id` | `backtest-result.contract.json` | `BacktestPage` | `src/features/backtest` | `info-level-annotations.test.tsx`, `backtest-components.test.tsx` | `queued` |
| `/research/experiments` | `experiment-list.contract.json` | `ExperimentListPage` | `src/features/research` | `research-components.test.tsx` | `queued` |
| `/research/regime` | `regime-monitor.contract.json` | `RegimePage` | `src/features/research` | `info-level-annotations.test.tsx`, `regime-components.test.tsx` | `queued` |
| `/research/universes` | `universe-list.contract.json` | `UniverseListPage` | `src/features/research` | `research-components.test.tsx` | `queued` |
| `/trading` | `trading-overview.contract.json` | `TradingPage` | `src/features/trading` | `trading-components.test.tsx` | `queued` |
| `/trading/signals` | `signals-inbox.contract.json` | `SignalsPage` | `src/features/trading` | `signals-components.test.tsx` | `queued` |
| `/trading/orders` | `orders-ledger.contract.json` | `OrdersPage` | `src/features/trading` | `orders-components.test.tsx` | `queued` |
| `/trading/portfolio` | `portfolio.contract.json` | `PortfolioPage` | `src/features/trading` | `trading-components.test.tsx`, `positions-summary.test.tsx` | `queued` |
| `/trading/risk` | `risk-center.contract.json` | `RiskPage` | `src/features/trading` | `risk-components.test.tsx`, `risk-breach-detail.test.tsx` | `queued` |
| `/platform` | `platform.contract.json` | `PlatformPage` | `src/features/platform` | `platform-components.test.tsx`, `info-level-annotations.test.tsx`, `platform-hooks.test.tsx` | `queued` |
| `/platform/settings` | `platform-settings.contract.json` | `PlatformSettingsPage` | `src/features/platform` | `platform-components.test.tsx`, `platform-hooks.test.tsx` | `queued` |
| `/platform/agents` | `agent-console.contract.json` | `PlatformAgentsPage` | `src/features/platform` | `platform-components.test.tsx` | `queued` |

---

## 维护规则

- 每次原型迭代完成后，只把“必须在 React 中实现”的项加入 React product epics；静态 HTML polish 留在 prototype-only 区域。
- 每个已实现 React route 的合同必须有 `landing.featureModule`、`landing.reactComponentRefs`，并且至少一个存在的 `landing.reactTestRefs` 要覆盖对应 page component 或显式 handoff marker。
- `visualAuditStatus` 只能使用 `missing | queued | implemented | verified`；没有视觉审计通过证据时不得写 `verified`。
- 完成 React 实现后，在对应 epic 下记录 commit hash，并同步合同与 generated artifacts。
