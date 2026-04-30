# 交互体验审核报告 — 原型 Phase

> **审核日期**: 2026-04-30
> **审核范围**: `docs/designs/specs/prototypes/` 全量 27 页
> **审核维度**: 面板折叠/展开交互、图标语义质量、分区可调尺寸
> **审核等级**: Best (最严)
> **审核框架**: UI/UX Pro Max Priority 1-10 + 项目视觉验证规范
> **关联 Spec**: 04_interaction_state_spec.md, 10_ditto_shell_family_spec.md, 11_ditto_page_pattern_library.md
> **状态说明**: 评分为原始审计快照；2026-04-30 prototype remediation 进展见第六节。

---

## 一、总体评估

| 维度 | 评分 | 说明 |
|------|:----:|------|
| **布局结构** | 9.2/10 | 8 种 Shell 家族覆盖完整，grid-template 定义精确 |
| **图标语义** | 5.5/10 | 严重碰撞 + 语义弱映射，详见第二节 |
| **折叠/展开** | 6.0/10 | 有基础设施但覆盖不足、默认策略未体系化，详见第三节 |
| **可调尺寸** | 2.0/10 | 零基础设施，所有面板固定宽度，详见第四节 |

---

## 二、图标语义审核

### 2.1 碰撞问题（P0 — 会导致误操作）

| 问题 | 位置 | 影响 |
|------|------|------|
| **"提交回测"用通知铃铛** — 与头部通知按钮图标完全相同 | page-strategy-studio.html L2020 | 用户点击预期是查看通知，实际触发回测提交 |
| **"Dry Run"用播放三角** — 播放三角 = 执行/运行，而非模拟 | page-strategy-studio.html L2014 | 用户可能误以为启动了实盘交易 |
| **密度切换用汉堡菜单图标** — 三横线 = 全局菜单 | 全部 5 个审核页面 | 用户期待导航菜单，实际是密度切换 |

### 2.2 语义弱映射（P1 — 可发现性差）

| 当前图标 | 当前含义 | 用户直觉解读 | 建议替换 |
|----------|---------|-------------|---------|
| 放大镜 | Research / 研究 | "搜索" | `book-open` 或 `flask-conical` |
| 3x2 网格 | Trading / 交易 | "数据表/电子表格" | `arrow-left-right` 或自定义蜡烛图剪影 |
| 五角星 | AI Copilot | "收藏/评分/精选" | `sparkles` 或 `bot` |
| 横条 tally | 校验/Validate | "数据/表格" | `check-circle` 或 `shield-check` |
| 3x2 网格 | 事件/Events (Platform) | 与 Trading Rail 碰撞 | `zap` 或 `activity` |

### 2.3 图标复用泛滥（P2 — 视觉语言退化）

同一组 5 个 Rail 图标在以下场景中反复复用且含义不同：

- **Activity Feed**（page-home.html L1649-1705）— Signal、Research、Trading 条目复用 Rail 图标
- **Inspector Tabs**（page-strategy-studio.html L2515-2524）— Strategy Tab 复用放大镜，Performance Tab 复用趋势线
- **Factor Types**（page-strategy-studio.html L2093-2111）— 4 种因子中 3 种用完全相同的趋势线图标

后果：图标从"信息载体"退化为"装饰" — 用户无法仅凭图标区分功能。

### 2.4 无障碍缺陷（P1）

| 文件 | 问题 |
|------|------|
| page-cross-market.html L1542-1556 | Rail 图标有 `aria-label` 无 `title`，无浏览器原生 tooltip |
| page-cross-market / page-strategy-studio / page-platform | Rail 用 `<div role="button">` 而非导航链接，键盘与链接语义不一致 |
| 多个页面的 icon-only 按钮 | 仅有 `title` 无 `aria-label`（screen reader 不可靠） |
| 5 个页面间 | 标签语言不一致：部分用英文 `"Home"`，部分用中文 `"首页"`，Platform 在不同页面分别标记为 `"Platform"` / `"平台"` / `"运维"` |

### 2.5 图标改进方案

**核心策略**: 保持 Lucide（shadcn/ui 默认）+ 为领域概念创建自定义 SVG

**Rail 图标替换表**：

| Rail 位置 | 当前 | 建议 | Lucide 图标名 |
|-----------|------|------|-------------|
| Home | 房子 | 保持 | `home` |
| Markets | 趋势线 | 保持 | `trending-up` |
| Research | 放大镜 | 替换 | `book-open` 或 `microscope` |
| Trading | 网格 | 替换 | `arrow-left-right` 或自定义交易图标 |
| Platform | 2x2 方格 | 替换 | `settings-2` 或 `cpu` |

**功能按钮替换表**：

| 功能按钮 | 当前 | 建议 | Lucide 图标名 |
|----------|------|------|-------------|
| Copilot | 星 | 替换 | `sparkles` |
| 密度切换 | 汉堡菜单 | 替换 | 自定义（三层矩形 + 不同间距） |
| 提交回测 | 铃铛 | 替换 | `rocket` 或 `timer` |
| Dry Run | 播放 | 替换 | `play-circle` + 虚线边框 或 `test-tube` |
| 校验 | tally 横条 | 替换 | `shield-check` |

**领域自定义图标**（Lucide 无对应）：

| 概念 | 建议设计 | 说明 |
|------|---------|------|
| Regime（市场状态） | 波形 + 眼睛 | 识别市场阶段 |
| Alpha | α 符号（希腊字母风格） | Alpha 生成 |
| Universe | 圈内散点 | 资产池 |
| Factor | 矩阵 + 权重连线 | 因子权重 |

所有自定义图标遵循现有规范：`viewBox="0 0 20 20"` / `stroke="currentColor"` / `stroke-width="1.5"` / `fill="none"`。

---

## 三、面板折叠/展开交互审核

### 3.1 现状盘点

当前有 3 种折叠机制：

| 机制 | 覆盖范围 | 交互方式 | 默认状态策略 |
|------|---------|---------|------------|
| `<details>/<summary>` | 右侧面板内部 section | 点击 header | 无统一规则，部分展开部分折叠 |
| Right Rail `.collapsed` | 仅 radar 类页面 | 按钮 `«`/`»` 切换 | 始终展开 |
| Bottom Tray 3-state | 4 个页面（platform, agent-console, strategy-studio, trading-overview） | `data-bottom-tray-toggle` | 有默认值定义但部分页面未遵守 |

2026-04-30 remediation 前的静态扫描基线：共有 50 个 `.context-section`，其中仅 3 个是 `<details class="context-section">`。也就是说，大部分右侧上下文区缺少可折叠语义与统一默认策略。

### 3.2 问题诊断

**问题 C-1：折叠默认策略未体系化**

Interaction Spec (04_interaction_state_spec.md §14) 定义了规则：

> 高频内容默认展开，低频默认折叠，空内容默认折叠

但实际原型中，右侧面板的所有 section **全部默认展开** — 即使是低频内容（如 instrument-hub 的 "Related Research"）。这导致：

- 信息过载：折叠的价值是减少认知负担，但全部展开 = 没有折叠
- 垂直空间溢出：右侧面板内容超过 viewport 高度时需要滚动

建议默认折叠的分区：

| 页面 | 分区 | 理由 | 建议默认 |
|------|------|------|---------|
| Object Hub 各页 | "Related Research" | 低频查阅 | 折叠（带 count badge） |
| Object Hub 各页 | "Historical Performance" | 依赖上下文 | 展开 |
| Catalog 各页 | Detail Panel 底部 "Actions" | 操作性，非信息性 | 展开（操作入口必须可见） |
| Analytical 各页 | Activity Stack 低优先级队列 | "Normal" 项 | 折叠（带 "+N more"） |
| Home | Pulse 底部 "Low Priority Alerts" | 低频 | 折叠 |

**问题 C-2：缺少 slide-up（上滑收起）交互**

当前所有折叠都是 `max-height` / `display:none` 的瞬间切换。对于底部面板（Bottom Tray），spec 定义了 `collapsed → peek → expanded` 三态，但原型中缺少平滑的上滑/下滑动画。

建议：

- Bottom Tray: `peek → collapsed` 用 translateY + opacity（200ms ease-out）
- Right Rail section: 展开用 `max-height` + `opacity` 过渡（150ms ease-out）
- 所有动画尊重 `prefers-reduced-motion`

**问题 C-3：折叠后的信息密度不足**

当前 `<details>` 折叠后仅显示 title 文本。VS Code / Figma 的做法是折叠后仍保留：

- **Count badge**（"3 items"）— 部分实现（仅 instrument-hub 有 `.collapse-count`）
- **关键指标摘要**（如 "Risk: High" 或 "P&L: +2.3%"）— 完全缺失

建议折叠态增强：

```html
<details class="context-section">
  <summary class="context-section-header">
    <span class="collapse-indicator">›</span>
    <span class="section-title">Risk Metrics</span>
    <!-- 折叠后显示摘要 -->
    <span class="collapse-summary">VaR 95%: -2.1%</span>
    <span class="collapse-count">5 metrics</span>
  </summary>
  <!-- 展开内容 -->
</details>
```

### 3.3 折叠交互推荐方案

| 折叠类型 | 适用场景 | 交互 | 动画 |
|----------|---------|------|------|
| **Section Fold** | 右侧面板内 section | 点击 header 展开/折叠 | 150ms ease-out, max-height + opacity |
| **Panel Collapse** | 右侧整体面板 | Rail icon 点击 或 面板边缘按钮 | 200ms ease-out, width transition |
| **Bottom Tray** | 底部托盘 | 拖拽边缘 / 按钮切换 3 态 | 200ms ease-out, translateY |
| **Slide-in Detail** | Catalog 详情面板 | 选中行时 slide-in，ESC 关闭 | 200ms ease-out, translateX |

---

## 四、分区可调尺寸审核

### 4.1 原始现状：零基础设施

原始审计时，所有 Shell 家族的面板宽度均为固定值：

| Shell 家族 | 左侧 Rail | 主内容区 | 右侧面板 | 面板宽度 |
|-----------|:---------:|:-------:|:--------:|---------|
| analytical | 56px | 1fr | 300px | 固定 |
| catalog | 56px | 1fr | 320px | 固定 |
| hub | 56px | 1fr | — | — |
| ops | 56px | 1fr | 340px | 固定 |
| agent/studio | 56px | 1fr | 368px | 固定 |
| radar | 56px | 1fr | 可折叠 56px↔完整 | 二态切换 |

原始审计未发现 `minmax()`、`resize` CSS 属性、拖拽手柄或 resize JavaScript。2026-04-30 prototype remediation 已先在 Catalog 与 Studio/Agent P0 shell 加入 prototype-only separator 合同；React 实现仍按 backlog 推进。

### 4.2 为什么需要可调尺寸

| 用户场景 | 固定面板的问题 | 可调尺寸的收益 |
|----------|-------------|-------------|
| 回测结果分析 — 需要宽图表 + 宽详情 | 368px 详情面板挤压图表空间 | 拖拽到 200px 可让图表多显示 40% 数据 |
| 策略开发 — 代码编辑器需要全宽 | Studio 368px inspector 占 24% 宽度 | 临时折叠 inspector，编辑器全宽编码 |
| 市场筛选 — 表格列多需要空间 | 320px detail 挤压 screener 表格 | 收窄 detail 到最小值，表格多显示 3-4 列 |
| 交易监控 — 需要同时看多个面板 | 固定比例无法适配不同数据密度 | 按需调整各区域比例 |

### 4.3 推荐方案：Prototype 合同 + React 后续实现

原型层不安装 `react-resizable-panels`。Prototype remediation 先用共享 HTML/CSS/JS 建立可检查合同：`data-resizable-panel-group`、`data-resize-separator`、`role="separator"`、`aria-controls`、`aria-valuemin`、`aria-valuemax`、`aria-valuenow`、方向键调整、拖拽调整、双击重置与 min/max clamp。

React 层在产品/技术批准后再评估并安装 `react-resizable-panels`，当前记录在 `docs/plans/prototype-to-react-enhancement-backlog.md`。

| 评估项 | 结论 |
|--------|------|
| **React 候选库** | `react-resizable-panels`（版本与 API 需在实施前重新确认） |
| **体积** | ~5KB gzipped |
| **无障碍** | 内置 `role="separator"`, `aria-valuenow`, 键盘方向键调节 |
| **持久化** | `autoSaveId` 自动存 localStorage 或 `onLayoutChange` 接 Zustand |
| **双击重置** | 内置支持（恢复默认比例） |
| **React 19** | 实施前随当前版本重新验证 |

最小/最大约束建议：

| 面板 | 最小宽度 | 默认宽度 | 最大宽度 | 可折叠 |
|------|---------|---------|---------|:-----:|
| Rail | 48px | 56px | 56px | 否（始终可见） |
| 右侧 Context/Detail | 170px | 300-340px | 40% viewport | 是 |
| Bottom Tray | 80px | peek ~60px / expanded ~240px | 50% viewport | 是 |
| 主内容区 | 40% viewport | 剩余空间 | 100% (面板全折叠时) | 否 |

### 4.4 拖拽手柄设计规范

参考 VS Code Sash 模式：

```
视觉表现:
  默认: 1px 透明分割线
  Hover: 1px 品牌强调色 (lapis hue 235°) + cursor: col-resize / row-resize
  拖拽中: 2px 强调色 + 全局 user-select: none

交互:
  Hit area: 至少 24px（视觉仅 1px，可点击区域扩大）
  双击: 恢复默认比例
  键盘: 方向键 ±5%, Shift+方向键 ±1%

动画:
  拖拽时: 无动画（1:1 跟随指针）
  程序化折叠/展开: 200ms ease-out
  prefers-reduced-motion: 无动画
```

### 4.5 实施优先级

| 优先级 | Shell 家族 | 覆盖页面 | 理由 |
|:------:|-----------|---------|------|
| **P0** | catalog | markets-screener, factor-list, strategy-list, backtest-list, experiment-list, watchlist, markets-calendar, universe-list | 表格+详情是最常见的双面板交互 |
| **P0** | agent/studio | strategy-studio, agent-console | 编辑器+inspector 布局，VS Code 核心场景 |
| **P1** | analytical | trading-overview, portfolio, risk-center, regime-monitor, markets-intelligence, research | 图表+activity stack |
| **P1** | ops | platform, signals-inbox, orders-ledger, platform-settings | 队列+detail |
| **P2** | radar | cross-market, a-shares | 已有折叠机制，可升级为可调尺寸 |
| — | hub | instrument-hub, factor-analysis, strategies-detail, backtest-result | 单栏布局，不适用 |

---

## 五、优先行动计划

### Phase 1 — 图标修复（Prototype 层，1-2 天）

1. 修复 3 个 P0 碰撞图标（提交回测、Dry Run、密度切换）
2. 替换 2 个 Rail 语义弱图标（Research 放大镜、Trading 网格）
3. 替换 Copilot 星形为 `sparkles`
4. 统一 Rail `aria-label` + `title` 为中文
5. 所有 Rail `<div role="button">` 改为 `<a href="...">` 导航链接
6. 所有 icon-only 按钮补充 `aria-label`

### Phase 2 — 折叠策略体系化（Spec + Prototype 层，1 天）

1. 定义每个 shell 家族的默认折叠/展开规则表
2. 为折叠态增加 count badge + 关键指标摘要
3. Bottom Tray 的 prototype 三态与动画已补齐；React 层继续实现状态机与持久化
4. Activity Stack 低优先级队列默认折叠

### Phase 3 — 可调尺寸基础设施（Prototype 已建合同，React 层后续 2-3 天）

1. Prototype 层已为 catalog + studio/agent P0 shell 建立 separator 合同
2. React 层经批准后再引入 `react-resizable-panels` 或等价实现
3. 在 Shell Chrome 层集成 PanelGroup
4. 先实现 catalog + studio 两种 Shell（P0 覆盖率最高）
5. Zustand 持久化面板布局偏好

---

## 六、2026-04-30 Prototype Remediation Status

### 已在 Prototype 层修复

- Rail 统一为 5 个导航链接，并统一中文 `aria-label` 与 `title`。
- Header 与 Strategy Studio 的 P0 图标碰撞已通过 `data-icon` / `data-action-icon` 合同收敛。
- 右侧上下文区已按 L1/L2/L3 折叠优先级迁移，折叠态保留 count 与摘要。
- Bottom Tray 已补齐三态合同、作用域隔离、动画与键盘/状态测试。
- Catalog 与 Studio/Agent P0 shell 已加入 prototype-only resize separator，视觉线 1px、hit area 至少 24px，并支持拖拽、方向键、Shift+方向键与双击重置。

### 延后到 React 层

- TanStack Router link 驱动的 React Rail。
- Lucide/custom icon registry 与跨语义复用治理。
- `ContextDisclosureSection` React 组件、Bottom Tray 状态机与用户偏好持久化。
- 经批准后评估并安装 `react-resizable-panels`，先覆盖 Catalog 与 Studio shell，再扩展 Analytical/Ops/Radar。

### 需要产品/设计确认

- P0 修复后的图标词汇是否作为长期 canonical vocabulary。
- L1/L2/L3 默认展开策略是否符合实际工作流优先级。
- 面板最小/默认/最大宽度、双击重置行为、未来是否支持 snap-to-collapse。

---

## 附录 A：图标审核完整问题清单

### Critical（图标误用）

| ID | 文件 | 行号 | 描述 |
|---|------|:----:|------|
| S-5 | page-strategy-studio.html | 2020 | "提交回测"用通知铃铛图标 — 与 Notifications 按钮碰撞 |
| H-2 | 全部 5 页 | varies | 密度切换用汉堡菜单图标，与全局菜单惯例冲突 |
| S-4 | page-strategy-studio.html | 2014 | "Dry Run"用播放三角，误导为实盘执行 |

### High（语义弱映射）

| ID | 文件 | 行号 | 描述 |
|---|------|:----:|------|
| R-Research | 全部 5 页 | varies | Research Rail 用放大镜 — 用户理解为"搜索" |
| R-Trading | 全部 5 页 | varies | Trading Rail 用网格 — 不传达"交易" |
| H-1 | 全部 5 页 | varies | Copilot 按钮用星形 — 歧义大 |
| S-3 | page-strategy-studio.html | 2011 | 校验用 tally 图标 — 不传达"验证" |
| P-2 | page-platform.html | 2061 | 事件图标与 Trading Rail 网格碰撞 |
| M-1 | page-strategy-studio.html | 2058 | Form Builder 图标与密度切换视觉相同 |

### Medium（无障碍缺陷）

| ID | 文件 | 行号 | 描述 |
|---|------|:----:|------|
| R-1 | 全部 5 页 | varies | 标签语言不一致（英文/中文混用） |
| R-2 | page-cross-market.html | 1542-1556 | Rail 图标缺失 `title` 属性 |
| R-3 | 3/5 页 | varies | Rail 用 `<div role="button">` 非导航链接 |
| S-2 | page-strategy-studio.html | 1998 | 删除策略按钮有 `title` 无 `aria-label` |
| P-1 | page-platform.html | 2056-2058 | 刷新按钮 `<div>` 缺 `aria-label` |
| T-1 | page-trading-overview.html | 2141 | 涨跌停状态按钮有 `title` 无 `aria-label` |

### Low（图标复用/词汇退化）

| ID | 文件 | 行号 | 描述 |
|---|------|:----:|------|
| F-1 | page-strategy-studio.html | 2093-2111 | 3/4 因子类型共享同一趋势线图标 |
| I-Tabs | page-strategy-studio.html | 2515-2524 | Inspector Tabs 复用 Rail 图标 |
| A-Feed | page-home.html | 1649-1705 | Activity Feed 复用 Rail 图标 |
| S-1 | page-strategy-studio.html | 1989 | 策略名 badge 复用 Copilot 星形 |

---

## 附录 B：业界参考

| 工具 | 面板调整方式 | 折叠方式 | 值得借鉴 |
|------|-----------|---------|---------|
| VS Code | Sash 拖拽 + 双击重置 | 侧栏 collapse/expand | 拖拽手柄交互、键盘调整 |
| Figma | 拖拽 + snap-to-collapse | 拖过最小宽度即折叠 | snap-to-collapse 行为 |
| JetBrains | Splitter 拖拽 | 双击 sash 最大化一侧 | 最大化模式 |
| TradingView | 比例拖拽 | 指标面板折叠 | 比例化调整 |
| Bloomberg | 固定 grid + tab | Tab 切换内容 | 键盘驱动导航 |
