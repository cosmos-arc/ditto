# Home Round 2 创意蓝图

> **日期**：2026-04-01
> **基于**：Round 1 评分 7.0/10（从 3.0 提升 +4.0）
> **策略**：定向精炼 — 聚焦最低维度（品牌方向 6.5、高级感 6.8）和最大影响项（My Workspace -1.5）
> **目标**：9.0+/10，等级 best

---

## 0. 标杆调研摘要

### Linear Dashboards
Linear 的 dashboard 模式：**自定义 widget 面板**，用户将不同数据源拖入同一视图。关键模式：
- widget 以紧凑卡片呈现，无冗余装饰
- "Add widget" 入口极克制（仅空态时显示引导线）
- 每个 widget 内部信息密度高，外部间距大

### Bloomberg Launchpad
Bloomberg 的 Launchpad 模式：**用户自定义面板排列**。关键模式：
- 面板间用极细分割线（1px）区分，不靠色彩区分
- 快捷操作以"command bar"形态存在，不占据视觉权重
- 面板可折叠，默认只显示摘要数字

### 提炼的可借鉴模式
1. **Widget = 紧凑信息块**：标题 + 1-2 个关键数据 + 1 个动作，不超过 3 行
2. **编辑入口不常驻**：hover 才显示"编辑工作台"，保持阅读态的洁净
3. **视觉重量梯度**：My Workspace 区段整体视觉重量低于上方 Decision Banner 和 Priority Items，作为"收尾带"而非"信息中心"

---

## 1. My Workspace 设计方案

### 1.1 定位与约束

```
位置：main-primary 底部，Decision Banner + Priority Items 之下
角色：快捷跳转面板，不是信息展示面板
视觉重量：最轻（surface-panel-base + 极简分割线，无 noise layer）
CTA：编辑工作台（主 CTA，但视觉上不抢 Decision Banner 的 primary CTA）
```

### 1.2 布局结构

```
┌─────────────────────────────────────────────────────────┐
│  My Workspace                      [编辑工作台]         │
│  ─────────────────────────────────────────────────────  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 常用策略  │ │ 观察列表  │ │ 回测任务  │ │ 快速建仓  │   │
│  │          │ │          │ │          │ │          │   │
│  │ 3 个活跃  │ │ 8 只标的  │ │ 2 个进行中│ │ 立即下单  │   │
│  │ > 查看    │ │ > 查看    │ │ > 查看    │ │ > 进入    │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 1.3 四个 Widget 详细规格

#### Widget 1: 常用策略
- **数据**：3 个活跃策略名称 + 运行状态指示灯
- **内容**：
  - 标题："常用策略"
  - 摘要行：策略名 + 状态点（绿色=运行中 / 灰色=暂停）
    - "Alpha v3 动量" + green dot
    - "价值因子增强" + green dot
    - "行业轮动 v2" + gray dot（暂停）
  - 底部："3 个活跃 →"
- **跳转**：点击 → Trading/策略管理
- **约束**：不显示策略详细指标（那是策略页的事）

#### Widget 2: 观察列表
- **数据**：观察列表名称 + 标的数量 + 最后更新时间
- **内容**：
  - 标题："观察列表"
  - 摘要行：
    - "重点跟踪" — 8 只标的
    - "财报季窗口" — 5 只标的
  - 底部："8 只标的 →"
- **跳转**：点击 → Markets/Watchlist
- **约束**：不显示具体标的名称和价格（那是 Watchlist 页的事）

#### Widget 3: 回测任务
- **数据**：进行中/最近完成的回测
- **内容**：
  - 标题："回测任务"
  - 摘要行：
    - "价值因子 2026 Q1" — ✓ 完成（对应 Priority Items 中已有）
    - "行业轮动参数优化" — ⟳ 运行中 (67%)
  - 底部："2 个进行中 →"
- **跳转**：点击 → Research/回测中心
- **约束**：不显示 Sharpe 等指标摘要（避免与 Priority Items 重复）

#### Widget 4: 快速建仓
- **数据**：一个快捷操作入口
- **内容**：
  - 标题："快速操作"
  - 摘要行：
    - "新建模拟组合"
    - "批量下单"
    - "策略回测"
  - 底部：无摘要行，整个 widget 可点击
- **跳转**：点击展开 action menu（不是导航到新页面）
- **约束**：这是唯一的"动作型"widget，其他三个是"浏览型"

### 1.4 CSS 实现规范

```
.workspace-panel
  ├── 面板背景：var(--surface-panel-base)
  ├── 边框：1px solid var(--border-subtle)
  ├── 圆角：var(--radius-8)
  ├── 与上方 Priority Items 的间距：var(--density-section-gap)
  └── 内部布局：grid 4 columns, gap var(--density-gutter)

.workspace-header
  ├── flex, justify-between, align-center
  ├── 标题："My Workspace" — font-size-12, font-weight-medium, text-tertiary
  ├── CTA："编辑工作台" — decision-cta.ghost 样式（最高视觉层级为 secondary）
  └── padding: var(--space-8) var(--space-12)

.workspace-widget
  ├── 背景：var(--surface-panel-elevated)（比外层面板高半阶）
  ├── 边框：1px solid var(--border-subtle)
  ├── 圆角：var(--radius-6)
  ├── padding: var(--space-10) var(--space-12)
  ├── cursor: pointer
  ├── hover: var(--interaction-hover-subtle-bg)
  ├── transition: background var(--motion-duration-fast)
  └── 内部结构：
      ├── .widget-title — font-size-12, font-weight-medium, text-primary
      ├── .widget-body — flex column, gap var(--space-4)
      │   └── .widget-row — font-size-12, text-secondary
      │       └── .widget-status-dot — 6px 圆点
      └── .widget-footer — font-size-12, text-tertiary
          └── hover 时 color → brand-accent
```

### 1.5 品牌锚点分配

My Workspace **不新增** brand accent 锚点。保持现有 5 处：
1. Header 标题下划线
2. Rail active indicator
3. Pulse strip subtle glow
4. Decision Banner left border
5. Decision CTA primary 按钮

My Workspace 的"编辑工作台"使用 ghost 样式（无 brand accent 色），hover 时才显示 brand accent。

---

## 2. Today Pulse 五要素重构

### 2.1 当前问题

当前 Pulse Strip 只有操作状态（日期/盘态/预警/任务/连接/数据），缺少蓝图定义的五要素：
- pnl（盈亏概况）
- risk（风险概况）
- regime（市态判断）
- pending（待处理数）
- jobs（运行中任务）

### 2.2 重构方案

将 Pulse Strip 的 6 项重组为 5 项，严格对齐蓝图：

```
┌──────────────────────────────────────────────────────────────────────┐
│ 2026-03-28 · 盘中交易 │ 盈亏 +0.34% │ 风险 中等 │ 温和风险偏好 │ 3 任务 │
└──────────────────────────────────────────────────────────────────────┘
```

| # | 要素 | 内容 | 视觉 |
|---|------|------|------|
| 1 | **时间 + 状态** | "2026-03-28 · 盘中交易" | text-tertiary，无指示灯 |
| 2 | **pnl** | "盈亏 +0.34%" | market-up-fg，无 data-live |
| 3 | **risk** | "风险 中等" | risk-medium-fg 小标签 |
| 4 | **regime** | "温和风险偏好" | 带 regime-tag 胶囊（见 2.3） |
| 5 | **pending + jobs** | "2 待处理 · 3 运行中" | text-secondary |

### 2.3 Regime 视觉编码 — 克制方案

**不是整块变色**，而是通过一个极小的 regime-tag 胶囊来表达：

```css
.regime-tag {
  display: inline-flex;
  align-items: center;
  gap: var(--space-4);
  padding: 2px var(--space-6);
  border-radius: var(--radius-4);
  font-size: var(--font-size-12);      /* 与 Pulse Strip 其他项一致 */
  font-weight: var(--font-weight-medium);
}

/* 四种 regime 状态 — 全部是极浅底色 */
.regime-tag.risk-on      { background: oklch(from var(--market-up-fg) l c h / 0.08); color: var(--market-up-fg); }
.regime-tag.risk-off     { background: oklch(from var(--market-down-fg) l c h / 0.08); color: var(--market-down-fg); }
.regime-tag.moderate     { background: var(--interaction-hover-subtle-bg); color: var(--text-secondary); }
.regime-tag.volatile     { background: oklch(from var(--risk-high-fg) l c h / 0.08); color: var(--risk-high-fg); }
```

**克制要点**：
- 底色透明度不超过 0.08（barely visible）
- 不改变 Pulse Strip 的整体背景
- 字号和字重与周围一致，不单独放大
- 在 Decision Banner 中段重复 regime-tag，形成上下呼应

### 2.4 data-live 动画语义修正

**当前问题**：pulse-value 上用 `data-live` 属性触发 dot-pulse 动画，但 pulse-value 是文本不是指示灯。

**修正方案**：
- 移除文本元素上的 `data-live` 动画
- 对"盘中交易"文本前加一个 6px 绿色实心圆点 `.status-dot.live`
- `.status-dot.live` 使用 dot-pulse 动画（表示连接状态）
- 文本本身不动画

```html
<!-- Before -->
<span class="pulse-value" data-live>盘中交易</span>

<!-- After -->
<span class="pulse-value">
  <span class="status-dot live"></span>
  盘中交易
</span>
```

---

## 3. Market Pulse 数据可视化增强

### 3.1 当前问题

Sidebar 的"市场脉搏"只有文本数字，缺少视觉层次（sparkline/趋势箭头），看起来像行情表。

### 3.2 增强方案

对沪深300和北向资金两个关键指标增加 **inline SVG sparkline**：

```
┌────────────────────────────────┐
│ 市场脉搏                        │
│ ─────────────────────────────  │
│ 沪深300  ▁▂▃▅▆▇█  3,432 +0.82%│
│ 波动率    IVIX 18.52 · -3.1%   │
│ 涨跌比    ▔▔▔▔▔▔  2.1:1       │
│ 北向资金  ▂▃▄▅▆  +12.4 亿     │
└────────────────────────────────┘
```

### 3.3 Sparkline 规格

```
尺寸：48px × 16px（使用 tokens-data-viz.css 的 --sparkline-width/height）
线宽：1.5px（--sparkline-stroke-width）
颜色：跟随涨跌色（var(--market-up-fg) / var(--market-down-fg)）
位置：pulse-metric-value 左侧，与数值对齐
实现：inline SVG <polyline>，6-8 个数据点
```

### 3.4 趋势箭头

对波动率和涨跌比使用极小的趋势箭头（不用 sparkline，因为这两个指标不适合趋势可视化）：

```
波动率 IVIX 18.52 ▼ -3.1%    （▼ 用 market-down-fg，表示波动率下降=好）
涨跌比 2.1:1                  （无箭头，纯数字）
```

---

## 4. Decision Banner Regime 视觉编码

### 4.1 当前问题

Decision Banner 中段"温和风险偏好，波动回落，北向转暖，但局部拥挤"是纯文字，缺少视觉锚定。

### 4.2 增强方案

在判断句前增加一个 **regime-tag 胶囊**，与 Pulse Strip 呼应：

```html
<div class="decision-judgment-text">
  <span class="regime-tag moderate">温和风险偏好</span>
  波动回落，北向转暖，但局部拥挤。
</div>
```

视觉表现：
- regime-tag 使用与 Pulse Strip 相同的克制胶囊样式
- 判断句保持 text-primary + font-weight-semibold
- 胶囊与文字 inline 排列，不换行

---

## 5. metric-sub 硬编码符号修正

### 5.1 当前问题

```html
<span class="metric-sub">+0.34% · 总权益 ¥25,432,180 · ▲ 较昨日 +¥21,400</span>
```

箭头符号 `▲` 是硬编码的，应该使用 `--indicator-up-sym` / `--indicator-down-sym` token。

### 5.2 修正方案

在 tokens-domain.css 或 tokens-semantic.css 中定义方向指示 token：

```css
:root {
  --indicator-up-sym: "▲";
  --indicator-down-sym: "▼";
  --indicator-flat-sym: "—";
}
```

HTML 中用 CSS content 方式引入（需要结构调整），或在 prototype 阶段先用语义 class：

```html
<span class="metric-sub">+0.34% · 总权益 ¥25,432,180 · <span class="indicator-up"></span> 较昨日 +¥21,400</span>
```

```css
.indicator-up::before { content: "▲"; color: var(--market-up-fg); font-size: 0.85em; }
.indicator-down::before { content: "▼"; color: var(--market-down-fg); font-size: 0.85em; }
```

---

## 6. 实施优先级与影响预估

| # | 改动 | 影响维度 | 预估分值提升 |
|---|------|---------|-------------|
| 1 | My Workspace 完整实现 | 品牌方向 +1.5, 高级感 +0.3 | **+1.8** |
| 2 | Today Pulse 五要素重构 | 信息效率 +0.5, 数据表达 +0.3 | **+0.8** |
| 3 | Regime 视觉编码 | 品牌方向 +0.3, 高级感 +0.2 | **+0.5** |
| 4 | Market Pulse sparkline | 数据表达 +0.5, 高级感 +0.3 | **+0.8** |
| 5 | data-live 语义修正 | 克制度 +0.2 | **+0.2** |
| 6 | metric-sub token 化 | 一致性 +0.2 | **+0.2** |

**预估总分**：7.0 + 4.3 = **~9.3/10**

### 实施顺序

```
Phase 1: 基础修正（不影响布局）
  ├── 5. metric-sub token 化
  └── 6. data-live 语义修正

Phase 2: Pulse 重构（影响 Pulse Strip 和 Decision Banner）
  ├── 2. Today Pulse 五要素
  └── 3. Regime 视觉编码

Phase 3: 数据可视化增强（影响 Sidebar）
  └── 4. Market Pulse sparkline

Phase 4: My Workspace（最大改动，放最后）
  └── 1. My Workspace 完整实现
```

---

## 7. My Workspace Mock Data

```javascript
// 在 mock-data.js 中追加
const workspaceWidgets = {
  strategies: {
    title: '常用策略',
    items: [
      { name: 'Alpha v3 动量', status: 'running' },
      { name: '价值因子增强', status: 'running' },
      { name: '行业轮动 v2', status: 'paused' },
    ],
    summary: '3 个活跃',
    route: '/trading/strategies',
  },
  watchlist: {
    title: '观察列表',
    items: [
      { name: '重点跟踪', count: 8 },
      { name: '财报季窗口', count: 5 },
    ],
    summary: '8 只标的',
    route: '/markets/watchlist',
  },
  backtests: {
    title: '回测任务',
    items: [
      { name: '价值因子 2026 Q1', status: 'completed' },
      { name: '行业轮动参数优化', status: 'running', progress: 67 },
    ],
    summary: '2 个进行中',
    route: '/research/backtests',
  },
  quickActions: {
    title: '快速操作',
    items: [
      { name: '新建模拟组合' },
      { name: '批量下单' },
      { name: '策略回测' },
    ],
    route: null, // 本地 action menu
  },
};
```

---

## 8. My Workspace HTML 结构

```html
<!-- ═══ My Workspace ═══ -->
<div class="panel workspace-panel">
  <div class="workspace-header">
    <span class="panel-title">My Workspace</span>
    <button class="decision-cta ghost workspace-edit-cta" role="link">编辑工作台</button>
  </div>
  <div class="workspace-grid">
    <!-- Widget: 常用策略 -->
    <div class="workspace-widget" role="link" tabindex="0">
      <div class="widget-title">常用策略</div>
      <div class="widget-body">
        <div class="widget-row">
          <span class="widget-status-dot running"></span>
          <span>Alpha v3 动量</span>
        </div>
        <div class="widget-row">
          <span class="widget-status-dot running"></span>
          <span>价值因子增强</span>
        </div>
        <div class="widget-row">
          <span class="widget-status-dot paused"></span>
          <span>行业轮动 v2</span>
        </div>
      </div>
      <div class="widget-footer">3 个活跃 →</div>
    </div>

    <!-- Widget: 观察列表 -->
    <div class="workspace-widget" role="link" tabindex="0">
      <div class="widget-title">观察列表</div>
      <div class="widget-body">
        <div class="widget-row">
          <span>重点跟踪</span>
          <span class="widget-count">8 只</span>
        </div>
        <div class="widget-row">
          <span>财报季窗口</span>
          <span class="widget-count">5 只</span>
        </div>
      </div>
      <div class="widget-footer">8 只标的 →</div>
    </div>

    <!-- Widget: 回测任务 -->
    <div class="workspace-widget" role="link" tabindex="0">
      <div class="widget-title">回测任务</div>
      <div class="widget-body">
        <div class="widget-row">
          <span class="widget-status-dot completed"></span>
          <span>价值因子 2026 Q1</span>
        </div>
        <div class="widget-row">
          <span class="widget-status-dot running"></span>
          <span>行业轮动参数优化</span>
          <span class="widget-progress">67%</span>
        </div>
      </div>
      <div class="widget-footer">2 个进行中 →</div>
    </div>

    <!-- Widget: 快速操作 -->
    <div class="workspace-widget widget-action" role="button" tabindex="0">
      <div class="widget-title">快速操作</div>
      <div class="widget-body">
        <div class="widget-row widget-action-row">新建模拟组合</div>
        <div class="widget-row widget-action-row">批量下单</div>
        <div class="widget-row widget-action-row">策略回测</div>
      </div>
    </div>
  </div>
</div>
```

---

## 9. 不改变的事项

以下是 Round 1 已确定且 Round 2 **不改动**的部分：

1. **Shell grid 三栏结构** — rail (56px) | main | sidebar (320px)
2. **Brand accent 5 处锚点** — 不新增，不移动
3. **Noise texture layer** — opacity 0.018，不调整
4. **Ambient light bars** — top-edge + rail-right，不调整
5. **Decision Banner 三段式布局** — 5fr 4fr 3fr grid，不调整
6. **Priority Items 内容** — 5 条跨域优先事项，不调整
7. **研究进展 + Agent 洞察** — 双栏布局，不调整
8. **Typography 字体系统** — Inter + Noto Sans SC + JetBrains Mono，不调整
9. **Surface elevation 步进** — Graphite Studio oklch 步进，不调整

---

## 10. 验收标准

Round 2 完成后，需通过以下验收：

- [ ] My Workspace 有 4 个真实 widget，每个含 2-3 条真实数据
- [ ] "编辑工作台" CTA 视觉重量低于 Decision Banner 的 primary CTA
- [ ] Today Pulse 严格包含 pnl/risk/regime/pending/jobs 五要素
- [ ] Regime tag 在 Pulse Strip 和 Decision Banner 中风格一致
- [ ] Market Pulse 的沪深300有 inline SVG sparkline
- [ ] 所有文本元素上不再有 data-live 动画
- [ ] metric-sub 中的方向箭头使用语义 class
- [ ] Brand accent 锚点总数不变（5 处）
- [ ] 无新增外部依赖
- [ ] 支持暗色/亮色主题切换
- [ ] 支持三种密度（dense/compact/comfortable）
