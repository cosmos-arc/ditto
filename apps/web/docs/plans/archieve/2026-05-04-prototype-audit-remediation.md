# 原型审计修复计划

## 概述
- 创建: 2026-05-04
- 来源: /impeccable:audit 审计报告 (14/20 Good)
- 范围: 仅原型层面（HTML/CSS/JS），图表库/虚拟滚动等 React 级优化不在此计划
- 策略: 均衡推进 — P1 视觉品质 + P2 工程健康同步，P3 Polish 收尾

## 技术方案

### 分组原则
- **Phase 1 — 视觉品质 (P1)**: 无障碍、Light Theme、信息密度、CVD — 直接影响设计评分
- **Phase 2 — 工程健康 (P2)**: CSS/JS 拆分合并、模块提取 — 降低技术债
- **Phase 3 — Polish (P3)**: Tooltip、空状态、动画 — 提升完成度

### 递延到 React 实现阶段
以下审计发现记录在此，但不执行原型改动：
- 交互式图表库引入（TradingView Lightweight Charts / ECharts）
- 数据表格虚拟滚动（TanStack Virtual）
- 列固定（sticky columns）
- 面板分离 / 多屏支持（Panel Pop-out）
- 响应式设计（1280px+ 适配）
- 实时数据层（WebSocket tick）
- 智能表格（行内编辑、列分组、拖拽排序）
- Command Palette 上下文感知（需要 React 路由集成）
- Onboarding 流程（需要 React 路由 + 状态管理）

---

## Phase 1 — 视觉品质 (P1)

### Task 1.1: CVD 色觉缺陷修复 `[M]`
- **验收**: 所有涨跌数据位置同时使用颜色 + 方向符号（▲/▼或文字），满足 WCAG 1.4.1
- **文件**:
  - `page-portfolio.html` — Positions Table PnL 列、Daily PnL 列
  - `page-signals-inbox.html` — Side Badge (Buy/Sell) 确认有方向符号
  - `page-cross-market.html` — Market Card change 值
  - `page-markets-intelligence.html` — Intel table 数据值
  - `page-backtest-result.html` — Metric cards change badges
  - `shared/layout-base.css` — 添加 `.dir-up::before` / `.dir-down::before` 方向符号工具类
- **方案**: 添加 `.dir-up::before { content: '▲ '; font-size: 0.7em; }` 和 `.dir-down::before { content: '▼ '; font-size: 0.7em; }` CSS 工具类，在涨跌数值前统一添加方向符号
- **测试**: grep 所有使用 `c-up`/`c-down`/`market-up`/`market-down` 类的位置，确认每个都有方向符号或已有等效非颜色编码

### Task 1.2: Light Theme Token 层修复 `[M]`
- **验收**: `data-theme="light"` 切换时，核心页面（Home、Instrument Hub、Trading Overview）的 surface/text/border 层级正确，无对比度失败
- **文件**:
  - `tokens-style.css` — atmosphere light 模式参数调整（noise opacity、ambient opacity）
  - `shared/theme-switcher.js` — 确认 light 模式下 CSS 变量正确切换
  - `page-home.html` — 验证 Light Mode 下 Global Pulse / Decision Card / Panels 可读性
  - `page-instrument-hub.html` — 验证 Light Mode 下 Meta Strip / Key Metrics / Chart 面板
  - `page-trading-overview.html` — 验证 Light Mode 下 Session/Margin/Pipeline strips
- **方案**: 在 `tokens-style.css` 的 `[data-theme="light"]` 块中添加针对性的 surface 层级覆盖和 ambient opacity 调整。检查 Design Token SSOT `src/styles/design-tokens/` 中的 light theme 定义是否完整传递到原型
- **测试**: 手动切换 Light Theme 验证 3 个核心页面可读性；如有自动化对比度检测工具则运行

### Task 1.3: 信息密度渐进式披露 `[L]`
- **验收**: Home/Cross-Market/Trading Overview 三个页面有可折叠区域，默认视图信息优先级清晰（AI 判断 > 待办 > 数据）
- **文件**:
  - `page-home.html` — Global Pulse Strip 可折叠、Context Panels 可折叠
  - `page-cross-market.html` — Bottom Tab Band 默认折叠、Right Rail sections 默认折叠（只展开第一个）
  - `page-trading-overview.html` — Margin Strip 可折叠、Activity Stack 可折叠
  - `shared/layout-base.css` — 添加 `.collapsible-strip` 样式（折叠时显示标题行 + 展开按钮）
  - `shared/prototype-interactions.js` — 添加 StripCollapse 模块或复用 CollapseToggle
- **方案**:
  - 使用现有 `data-collapse-toggle` + `data-collapsed` 属性机制
  - 在关键 strip 的 panel-header 上添加折叠按钮
  - 折叠状态只保留标题行（36px），展开恢复完整内容
  - 默认状态：Home 的 4 个 Context Panels 全展开（保持现状）、Global Pulse 全展开；Trading 的 Margin Strip 默认折叠（非核心）
- **测试**: 验证折叠/展开动画流畅、reduced-motion 下跳过动画、折叠后布局不跳动

### Task 1.4: 数据新鲜度视觉分层 `[M]`
- **验收**: 每种数据展示都有明确的新鲜度视觉标记（实时=脉冲绿点、延迟=静态灰点、日终=无标记）
- **文件**:
  - `shared/layout-base.css` — 添加 `.freshness-realtime`（脉冲绿点）、`.freshness-delayed`（静态灰点）、`.freshness-eod`（无标记）工具类
  - `page-home.html` — Global Pulse 各项标记新鲜度级别
  - `page-trading-overview.html` — Session Strip / Positions 数据标记
  - `page-instrument-hub.html` — Price / Change 标记为 realtime，Fundamentals 标记为 delayed
  - `page-watchlist.html` — 已有 stale indicator，统一到新体系
- **方案**: 定义三级新鲜度 token：`--freshness-realtime-dot`、`--freshness-delayed-dot`，在数据项的 meta 区域用 4px 圆点标记
- **测试**: grep 验证所有 `.pulse-dot` / `dot-pulse` 动画的使用一致性

### Task 1.5: Overlay 堆叠管理 `[M]`
- **验收**: 多个 overlay 同时打开时 z-index 正确叠加，Esc 键关闭最顶层 overlay
- **文件**:
  - `shared/prototype-interactions.js` — 添加 OverlayStack 模块
  - `shared/layout-base.css` — overlay z-index 使用 CSS 变量 `--overlay-z-index`
- **方案**:
  - 在 prototype-interactions.js 中添加 OverlayStack：监听所有 `[data-overlay-trigger]` 的 click 事件，记录打开顺序到数组
  - 每次打开 overlay 时递增 z-index
  - Esc 键只关闭数组末尾的 overlay
  - 关闭后从数组中移除
- **测试**: 手动验证打开 Drawer + Modal 后 Esc 只关闭 Modal，再 Esc 关闭 Drawer

---

## Phase 2 — 工程健康 (P2)

### Task 2.1: layout-base.css 按功能拆分 `[M]`
- **验收**: layout-base.css 拆为 4-5 个功能模块，每个页面只引用需要的模块；所有页面视觉无回退
- **文件**:
  - `shared/layout-base.css` → 拆分为:
    - `shared/layout-shell.css` — Shell 架构（rail、header、status-bar）
    - `shared/layout-overlay.css` — Overlay 系统（drawer、sheet、modal）
    - `shared/layout-gallery.css` — 三区切换（default-view、states、overlays）
    - `shared/layout-components.css` — 通用组件（panel、strip、badge、button、table）
    - `shared/layout-state.css` — 状态模式（empty、loading、error、stale、skeleton）
  - 所有 `page-*.html` — 更新 `<link>` 引用
- **测试**: 每个页面在 VP-STANDARD (1536x900) 和 VP-COMPACT (1280x800) 下视觉无变化

### Task 2.2: ScreenerWorkflow 提取为独立文件 `[S]`
- **验收**: ScreenerWorkflow 从 prototype-interactions.js 中移除，成为独立的 page-specific JS 文件
- **文件**:
  - `shared/prototype-interactions.js` — 移除 lines 408-731 (ScreenerWorkflow)
  - `shared/screener-workflow.js` — 新文件，包含完整的 ScreenerWorkflow IIFE
  - `page-markets-screener.html` — 添加 `<script src="shared/screener-workflow.js">`
- **测试**: page-markets-screener 的筛选/排序/比较功能不受影响；其他页面的 JS 模块正常工作

### Task 2.3: NumberTicker 与 AnimatedCounter 合并 `[M]`
- **验收**: 两个模块合并为统一的 `DataCounter` 模块，支持 IntersectionObserver 和 MutationObserver 两种触发模式
- **文件**:
  - `shared/prototype-interactions.js` — 重构 NumberTicker + AnimatedCounter → DataCounter
- **方案**:
  - `DataCounter` 接受配置 `{ trigger: 'visible' | 'mutation', ... }`
  - `trigger: 'visible'` = 原 NumberTicker 行为（IntersectionObserver）
  - `trigger: 'mutation'` = 原 AnimatedCounter 行为（MutationObserver）
  - 保留 `data-ticker` 和 `data-counter` 属性作为兼容别名
  - 共享 `_animate()` 缓动逻辑和 `_announce()` 无障碍播报
- **测试**: 所有使用 `data-ticker` 和 `data-counter` 的页面动画正常；reduced-motion 下直接显示终值

### Task 2.4: prototype-interactions.js 注入 CSS 迁移 `[S]`
- **验收**: 所有动态注入的 CSS 样式迁移到独立 CSS 文件，prototype-interactions.js 不再包含 `<style>` 注入
- **文件**:
  - `shared/prototype-interactions.css` — 新文件，包含 confidence-track/fill、flow-bar/segment、tab active、filter-chip pressed、tooltip、bullet graph 样式
  - `shared/prototype-interactions.js` — 移除 lines 2404-2431 的 `<style>` 注入代码
  - 所有 `page-*.html` — 添加 `<link rel="stylesheet" href="shared/prototype-interactions.css">`
- **测试**: confidence bar、flow bar、tooltip、bullet graph、tab 切换视觉效果无回退

### Task 2.5: Variable Font 升级 `[S]`
- **验收**: Inter 和 Geist Sans 迁移到 Variable Font 版本，@font-face 声明从 11 个减少到 4-5 个
- **文件**:
  - `shared/fonts.css` — 重写为 Variable Font 声明
- **方案**:
  - Inter: 1 个 variable @font-face (wght 400-600) 替代 6 个静态声明
  - Geist Sans: 1 个 variable @font-face 替代 3 个静态声明
  - JetBrains Mono: 保持静态（只有 400/500 两个权重，variable 版本不一定可用）
  - Geist Mono: 保持静态
  - 验证 Fontsource 是否提供 variable woff2 文件
- **测试**: 所有页面字体渲染无变化；文件体积减少

---

## Phase 3 — Polish (P3)

### Task 3.1: Rail Tooltip `[S]`
- **验收**: Rail 导航图标 hover 时显示页面名称 tooltip
- **文件**:
  - `shared/layout-base.css` — `.shell-rail-item` 添加 tooltip 样式（右侧弹出）
  - 所有 `page-*.html` — Rail items 添加 `data-tooltip` 属性（利用已有 TooltipSystem）
- **方案**: 复用 prototype-interactions.js 的 TooltipSystem，在 Rail items 上添加 `data-tooltip="首页"` 等属性。Tooltip 方向固定为右侧弹出
- **测试**: 所有 5 个 Rail 导航项 hover 时显示正确的中文页面名

### Task 3.2: 空状态引导 CTA `[M]`
- **验收**: 每个页面的空状态（State Gallery 中的 empty variant）包含一个 primary CTA 按钮
- **文件**:
  - `page-home.html` — 空状态的 context panels 添加 CTA
  - `page-watchlist.html` — 空表格添加"添加第一只股票"按钮
  - `page-strategy-list.html` — 空列表添加"创建第一个策略"按钮
  - `page-backtest-list.html` — 空列表添加"运行第一次回测"按钮
  - `page-signals-inbox.html` — 空列表添加描述文字
  - `page-factor-list.html` — 空列表添加"创建第一个因子"按钮
  - 其他有 empty state 的页面按需添加
- **方案**: 在每个 `.state-empty` 内的现有图标+文案下方，添加一个 `.overlay-btn-primary` 风格的 CTA 按钮
- **测试**: 验证所有页面的 State Gallery empty variant 包含可操作的 CTA

### Task 3.3: 暗色主题边界定义增强 `[S]`
- **验收**: Overlay 和 Modal 在暗色主题下有明确的边界线（而非仅靠 surface 色差）
- **文件**:
  - `shared/layout-overlay.css`（拆分后）或 `shared/layout-base.css` — `.overlay-surface` 添加 `box-shadow: 0 0 0 1px var(--border-subtle)`
  - `.surface-panel-elevated` 在嵌套使用时添加 `border: 1px solid var(--border-subtle)`
- **测试**: Modal 和 Drawer 在暗色背景下有清晰的视觉边界

### Task 3.4: 页面过渡动画 `[S]`
- **验收**: 三区切换（Default View ↔ States Gallery ↔ Overlays Gallery）时有 sub-200ms 的淡入淡出过渡
- **文件**:
  - `shared/layout-base.css` — 添加 `.proto-section { opacity: 0; transition: opacity 150ms ease-out; }` + `.proto-section.active { opacity: 1; }`
  - `shared/prototype-interactions.js` — zone 切换时添加 opacity 过渡（如果 CSS-only 的 `:has()` 可以驱动则不需要 JS）
- **方案**: 纯 CSS 方案：利用 `:has(#view-default:checked)` + `transition: opacity 150ms` 实现三区切换时的淡入效果
- **测试**: 三区切换时有平滑的 opacity 过渡，reduced-motion 下跳过

---

## 执行顺序

```
Phase 1 (P1 视觉品质) — 并行中部分串行
  1.1 CVD 修复       ← 独立，先做
  1.4 数据新鲜度     ← 独立，先做
  1.5 Overlay 堆叠   ← 独立，先做
  1.2 Light Theme    ← 需要 1.1 完成后验证对比度
  1.3 渐进式披露     ← 最复杂，放最后

Phase 2 (P2 工程健康) — 可并行
  2.2 ScreenerWorkflow 提取  ← 独立
  2.4 注入 CSS 迁移         ← 独立
  2.5 Variable Font         ← 独立
  2.3 NumberTicker 合并     ← 需要 2.4 完成后（CSS 已迁移）
  2.1 CSS 拆分              ← 需要 2.3 + 2.4 完成后（所有模块稳定后拆分）

Phase 3 (P3 Polish) — 可并行
  3.1-3.4 全部可并行

总计: 13 个任务 | S:5 M:6 L:1 | 预估 ~3 个工作日
```

## 验证门禁

每个 Phase 完成后运行：
1. `bun run test:run scripts/prototype-design-consistency.test.ts scripts/page-*-prototype.test.ts` — 原型门禁
2. 目视检查 VP-STANDARD 和 VP-COMPACT contact sheet
3. Light Theme 切换检查（Phase 1 后）

全部完成后：
4. `bun run check` — 工程检查
5. 更新 `.edition-manifest.json` 的审计记录
