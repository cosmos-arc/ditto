# Part 3: 弹层/Overlay + 折叠交互 + 可调整面板

---

## 1. 弹层一致性审计

### 1.1 当前弹层类型与分布

| 类型 | CSS 类 | 页面数 | 触发方式 |
|------|--------|:------:|---------|
| Sheet（居中面板） | `.overlay-surface--sheet` | 27/29 | checkbox `:has()` |
| Drawer（右侧抽屉） | `.overlay-surface--drawer` | 20/29 | checkbox `:has()` |
| Modal（小对话框） | `.overlay-surface--modal` | 4/29 | checkbox `:has()` |
| Toast | `.toast-card` | 2/29 | checkbox `:has()` |
| Fullscreen | `.overlay-fullscreen` | 1/29 | checkbox `:has()` |

### 1.2 共享 vs 内联分布

```
共享层 (prototype-toggles.css):
  ✅ .overlay-backdrop          — 遮罩层（背景模糊、定位、z-index）
  ✅ .overlay-surface           — 通用表面容器（border, radius, bg, shadow）
  ✅ .overlay-surface--drawer   — 右侧抽屉（宽度、高度）
  ✅ .overlay-surface--sheet    — 居中面板（宽度、max-height）
  ✅ .overlay-surface--modal    — 小对话框（宽度、max-height）
  ✅ .overlay-close             — 关闭按钮
  ❌ .overlay-header            — 全部内联
  ❌ .overlay-title             — 全部内联
  ❌ .overlay-body              — 全部内联
  ❌ .overlay-actions           — 全部内联
  ❌ .overlay-btn               — 全部内联
  ❌ .overlay-btn-primary       — 全部内联
  ❌ .overlay-btn-secondary     — 全部内联
  ❌ .overlay-btn-danger        — 全部内联
  ❌ .overlay-field             — 全部内联
  ❌ .overlay-field-label       — 全部内联
  ❌ .overlay-field-value       — 全部内联
  ❌ .overlay-confirm-box       — 全部内联
  ❌ .overlay-fullscreen        — 仅 1 页内联定义
  ❌ .toast-card                — 2 页各自不同实现
```

### 1.3 核心不一致详情

#### 不一致 1: 弹层按钮 padding

```css
/* page-home.html */
.overlay-btn { padding: var(--space-4) var(--space-10); }

/* 其他多数页面 */
.overlay-btn { padding: var(--space-2) var(--space-10); }

/* page-backtest-result.html */
.overlay-btn { height: var(--btn-height); padding: 0 var(--btn-padding-x); }
```

**3 种不同的按钮尺寸策略**。

#### 不一致 2: 弹层 header padding

```css
/* 大多数页面 */
.overlay-header { padding: var(--space-12) var(--space-16); }

/* page-backtest-result.html */
.overlay-header { padding: var(--space-10); }
```

#### 不一致 3: 弹层命名体系

```css
/* 27 页使用 overlay-* */
.overlay-header / .overlay-title / .overlay-body / .overlay-actions / .overlay-btn

/* page-portfolio 使用 modal-* */
.modal-header / .modal-title / .modal-close / .modal-body / .modal-actions / .modal-btn
```

#### 不一致 4: Toast

```
page-ai-overview:
  - 自定义 toast-overlay-backdrop + toast-card
  - 320px 宽度，icon + title + desc + close
  - 独立 CSS 约 40 行

page-backtest-result:
  - overlay-backdrop--toast + 简单 toast-card
  - 仅一行文本
  - CSS 约 15 行
```

### 1.4 弹层与整体风格差异分析

用户反馈"弹层的风格和整体还是有差异"。具体差异：

| 维度 | 整体设计（Shell/Panel） | 弹层设计 | 差异 |
|------|----------------------|---------|------|
| 背景 | `var(--surface-panel-base)` 或 `surface-app` | `var(--surface-panel-elevated)` | 弹层使用更高亮度的 surface |
| 边框 | 细微 `var(--border-subtle)` | `1px solid var(--border-default)` | 弹层边框更明显 |
| 圆角 | `var(--radius-8)` 或 `var(--radius-12)` | `var(--radius-8)` | 基本一致 |
| 阴影 | 大多无阴影（flat design） | `box-shadow` 明显投影 | **弹层有阴影，整体无** |
| 毛玻璃 | Shell header 使用 frosted glass | 遮罩层使用 `backdrop-filter: blur(2px)` | 遮罩 blur 程度不同 |
| 动画 | 无 | 无 | 一致（都无动画） |

**核心矛盾**: 整体设计走的是 Graphite Studio flat 风格（克制、低噪声），但弹层的 `box-shadow` + `surface-panel-elevated` 背景 + 更明显的边框让弹层看起来像是"浮在另一个产品上"。

**建议**: 弹层应沿用 Graphite Studio 的克制风格：
- 降低阴影强度（用更微妙的 `box-shadow` 或改用 border + 略深背景区分）
- 统一 surface 层级（Sheet 用 `surface-panel-base` + border，而非 `surface-panel-elevated`）
- 添加入场动画（slide-in / scale-in），让弹层感觉是从页面"生长"出来的，而非"砸"上来的

---

## 2. 折叠/展开交互审计

### 2.1 当前三种实现方式

#### 方式 1: JS onclick toggle（3 页）

```html
<!-- page-a-shares, page-cross-market, page-markets-intelligence -->
<button onclick="document.querySelector('.right-rail').classList.toggle('collapsed')">
  Toggle
</button>
```
- 无动画（瞬间切换）
- 代码在 3 页完全重复（约 200 字符）
- 选择器不统一（`.right-rail` vs `.intel-right-rail`）

#### 方式 2: HTML `<details>/<summary>`（2 页）

```html
<!-- page-instrument-hub, page-markets-screener -->
<details open class="context-section">
  <summary>Section Title</summary>
  <!-- content -->
</details>
```
- 无动画（浏览器原生行为）
- 箭头用 `::before { content: '▶'; transform: rotate(90deg) }` 实现
- 有折叠计数 badge 模式

#### 方式 3: data-bottom-tray-state（4 页）

```html
<!-- page-agent-console, page-platform, page-trading-overview, page-strategy-studio -->
<div data-bottom-tray data-bottom-tray-state="peek">
  <div data-bottom-tray-toggle>...</div>
  <div data-bottom-tray-content>...</div>
</div>
```
- 无动画（瞬间切换）
- 三态定义清晰（collapsed/peek/expanded）
- CSS 在 layout-base.css 中共享（良好）

### 2.2 是否应该使用侧滑/上划交互收起

**分析**:

| 交互方式 | 适用场景 | 当前使用 | 建议 |
|---------|---------|---------|------|
| **就地折叠** | 内容区域，accordion 风格 | `<details>/<summary>` | 统一为此模式 |
| **侧滑抽屉** | 辅助面板（inspector、detail、config） | checkbox `:has()` + `overlay-surface--drawer` | 保留，但补充动画 |
| **上划面板** | 底部日志/状态/trace | `data-bottom-tray` | 保留，补充动画 |
| **可折叠面板** | 非核心信息区域 | 无统一实现 | 新增统一机制 |

### 2.3 默认展开/折叠决策建议

基于组件规范中的"5 秒测试原则"和"空间预算约束"（1080px viewport 下 <= 500px 可见内容）：

| 区域类型 | 默认状态 | 依据 |
|---------|---------|------|
| **主工作面**（表格、图表、编辑器） | 始终展开 | 核心任务数据 |
| **Context Section（右侧栏）** | 首次展开 | 辅助理解 |
| **Bottom Tray** | 按 Pattern 区分 | |
| — Ops Console | collapsed | 低风险常态 |
| — Studio | peek | 显示最新状态 |
| — Trading | collapsed | 聚焦主工作面 |
| **Config/Settings 区域** | 首次折叠 | 低频信息 |
| **Related/History 标签组** | 首次折叠 | 1 次点击可达 |
| **高级选项/Filter** | 首次折叠 | 渐进披露 |

---

## 3. 可调整面板（Resizable Panels）

### 3.1 当前状态

当前规范中**没有可调整面板**的显式定义。面板尺寸是设计时决定的固定比例（如 70/30、60/40）。

### 3.2 是否应该引入

**支持的论点**:
1. 量化工具用户通常是专业用户，需要自定义工作空间
2. VSCode / Bloomberg Terminal / TradingView 都支持面板调整
3. 不同数据集需要不同的显示比例（宽表 vs 窄表）
4. 提升专家效率

**反对的论点**:
1. 增加实现复杂度
2. 可能破坏设计一致性
3. 用户自定义后可能产生难以调试的布局问题

**结论**: **应该引入，但有限制**。

### 3.3 推荐方案: react-resizable-panels

| 特性 | 说明 |
|------|------|
| **库** | `react-resizable-panels` (5KB gzipped, 3K+ stars) |
| **核心 API** | `PanelGroup` + `Panel` + `PanelResizeHandle` |
| **持久化** | 内置 `autoSaveId`（localStorage） |
| **约束** | `minSize` / `maxSize` / `collapsible` |
| **嵌套** | 支持水平和垂直嵌套 |
| **无障碍** | 键盘操作（方向键调整大小） |

### 3.4 哪些页面/区域应该支持可调整

| 页面 Pattern | 可调整区域 | 方向 | 约束 |
|-------------|-----------|------|------|
| **Analytical Overview** | Main Content ↔ Context Rail | 水平 | 主区 min 50%, 右栏 min 15% |
| **Market Radar** | Main Stage ↔ Right Rail | 水平 | 70/30 默认, 可调 50-80/20-50 |
| **Catalog/Screener** | Main Table ↔ Preview/Inspector | 水平 | 表格 min 40%, 预览 min 20% |
| **Object Hub** | Main Panels ↔ Related/History | 水平 | 主区 min 50% |
| **Studio 三栏** | Sources ↔ Main ↔ Inspector | 水平×2 | 中间 min 30%, 两侧各 min 15% |
| **Studio 双栏** | Editor ↔ Inspector | 水平 | 编辑器 min 40% |
| **所有带 Bottom Tray** | Main Content ↔ Bottom Tray | 垂直 | 主区 min 50%, tray min 10% |

**不应支持可调整的区域**:
- Shell Rail（固定 56px）
- Shell Header（固定 68px）
- Status Strip / Decision Banner（固定高度）
- Context Bar（固定高度）

### 3.5 Prototype 层如何体现

在 Prototype 中不需要实现完整的拖拽调整，但需要：
1. 定义 `minSize` / `maxSize` / `defaultSize` 约束
2. 在页面合同中记录这些约束
3. 实现双击分割条折叠/展开的交互原型

```html
<!-- Prototype 中的可折叠分割条示例 -->
<div class="panel-resize-handle"
     data-resize-min="15%"
     data-resize-max="40%"
     data-resize-default="30%"
     data-resize-collapsible="true"
     ondblclick="this.previousElementSibling.classList.toggle('collapsed')">
  <div class="resize-handle-line"></div>
</div>
```

### 3.6 技术实现注意事项

```tsx
// React 实现示例
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

<PanelGroup direction="horizontal" autoSaveId="analytical-overview">
  <Panel defaultSize={70} minSize={50}>
    <MainContent />
  </Panel>

  <PanelResizeHandle className="group flex w-1 items-center justify-center">
    <div className="h-8 w-0.5 rounded-full bg-border
                    group-hover:bg-primary
                    group-active:bg-primary
                    transition-colors duration-150" />
  </PanelResizeHandle>

  <Panel defaultSize={30} minSize={15} maxSize={40} collapsible>
    <ContextRail />
  </Panel>
</PanelGroup>
```

**关键细节**:
- 分割条宽度 1-4px，hover 时变色提示可拖拽
- 双击分割条折叠面板（`collapsible` 属性）
- `autoSaveId` 按页面 + 布局区域命名（如 `"home-main"`）
- 键盘支持：聚焦分割条后方向键调整 ±5%

---

## 4. 改进优先级

| 优先级 | 改进项 | 工作量 | 影响 |
|--------|--------|--------|------|
| **P0** | 弹层子组件 CSS 提升到共享层 | 1 天 | 消除 300+ 条重复 CSS |
| **P0** | 统一弹层命名体系（消除 modal-* / overlay-* 分裂） | 0.5 天 | React 对齐 |
| **P1** | 弹层入场/出场动画 | 1 天 | 体验提升显著 |
| **P1** | 弹层视觉对齐 Graphite Studio 风格 | 0.5 天 | 消除风格差异感 |
| **P1** | 统一折叠/展开机制 | 1 天 | 三种→一种 |
| **P1** | 添加折叠/展开过渡动画 | 0.5 天 | 体验提升 |
| **P2** | Toast 组件统一 | 0.5 天 | 消除 2 套实现 |
| **P2** | 引入 react-resizable-panels | 2 天 | 专家效率提升 |
| **P2** | Bottom Tray 添加拖拽调整高度 | 1 天 | 灵活度 |
