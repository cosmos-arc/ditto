# Sidebar 交互重设计调研

> 2026-04-03 · Tier 3 调研项
> 范围: page-markets-screener (320px) + page-instrument-hub (340px) 右侧面板

---

## 1. 现状分析

### 1.1 Screener 右侧面板 (`.catalog-detail`, 320px)

| Section | 内容 | 高度估算 | 问题 |
|---------|------|---------|------|
| 结果去向 | 3 个 action 按钮 | ~80px | OK，固定在顶部 |
| 筛选预设 | 3 张 preset 卡片 | ~200px | 低频操作占大量空间 |
| 多维评分 | 雷达图 + 5 行评分条 | ~300px | 核心信息，但雷达图占位大 |
| 对比篮 | 3 个 compare item + CTA | ~180px | 需要始终可见 |

**核心矛盾**: 760px 内容压缩在 ~600px 可视区域内（1080px - header - toolbar），必须滚动才能看完。

### 1.2 Hub 右侧面板 (`.hub-sidebar`, 340px)

| Section | 内容 | 高度估算 | 问题 |
|---------|------|---------|------|
| 相关信号 | 3 条 signal item | ~240px | 跨 tab 共享，但非每个 tab 都相关 |
| 关联研究 | 2 条 research item | ~160px | 低频查看 |
| 备注 | textarea + 1 条 note | ~180px | 交互频率高但初始状态空 |

**核心矛盾**: 3 个 section 跨所有 tab 共享，但内容相关性因 tab 不同而异（如"图表"tab 不需要"关联研究"，"新闻"tab 更需要"相关信号"）。

---

## 2. 设计原则

1. **渐进式披露** — 默认展示高频核心信息，低频信息通过交互展开
2. **上下文适配** — 内容随主区域选中项/tab 动态调整
3. **空间经济学** — 320px 内每个像素都要有存在理由
4. **零学习成本** — 交互模式遵循 OS/Dark-theme 常见约定

---

## 3. Screener 方案: 折叠式面板 + 粘性锚点

### 3.1 结构重组

```
┌─────────────────────────┐
│ ⚡ 结果去向              │  ← sticky, always visible
│ [观察] [标的池] [研究]    │
├─────────────────────────┤
│ ▼ 多维评分 (默认展开)     │  ← 折叠式, 核心信息
│   雷达图 + 评分条         │
├─────────────────────────┤
│ ▶ 筛选预设 (默认折叠)     │  ← 折叠式, 低频
├─────────────────────────┤
│ ▼ 对比篮 (默认展开)       │  ← 折叠式, 高频
│   3 items + CTA          │
└─────────────────────────┘
```

### 3.2 交互规格

| Section | 默认状态 | 折叠行为 | 触发 |
|---------|---------|---------|------|
| 结果去向 | 始终展开 | 不折叠 | — (sticky) |
| 多维评分 | 展开 | 折叠只保留标题 | 点击标题栏 |
| 筛选预设 | **折叠** | 展开显示卡片 | 点击标题栏 |
| 对比篮 | 展开 | 折叠只保留计数 | 点击标题栏 |

### 3.3 CSS 实现模式 (纯 CSS)

```html
<!-- 折叠使用 <details>/<summary> — 无需 JS -->
<details open class="sidebar-section">
  <summary class="sidebar-section__header">
    多维评分
  </summary>
  <div class="sidebar-section__body">
    <!-- radar + score rows -->
  </div>
</details>

<details class="sidebar-section"> <!-- 默认折叠，无 open -->
  <summary class="sidebar-section__header">
    筛选预设
  </summary>
  <div class="sidebar-section__body">
    <!-- preset cards -->
  </div>
</details>
```

```css
.sidebar-section__header {
  display: flex;
  align-items: center;
  gap: var(--space-6);
  padding: var(--space-6) var(--space-10);
  font-size: var(--font-size-12);
  font-weight: var(--font-weight-semibold);
  color: var(--text-secondary);
  cursor: pointer;
  border-bottom: 1px solid var(--border-subtle);
  list-style: none; /* remove default marker */
}

.sidebar-section__header::before {
  content: '▶';
  font-size: 8px;
  transition: transform 0.15s ease;
}

.sidebar-section[open] > .sidebar-section__header::before {
  transform: rotate(90deg);
}

.sidebar-section__body {
  padding: var(--space-8) var(--space-10);
}
```

### 3.4 信息密度优化

- **雷达图** → 精简为 5 行 inline score bar（省 ~120px）
  - 评分条一行显示: `价值 78 ████████░░`
  - 雷达图作为 hover/click 详情弹层保留
- **筛选预设** → 折叠后只占一行标题 + 计数
- **对比篮** → 空状态时折叠，有内容时自动展开

---

## 4. Hub 方案: 上下文感知 + Tab 内联动

### 4.1 结构重组

```
┌─────────────────────────┐
│ ⚡ 快捷操作              │  ← 新增: 跨 tab 通用操作
│ [加观察] [加标的池]       │
├─────────────────────────┤
│ ▼ 相关信号 (默认展开)     │  ← 上下文感知: 新闻/公告 tab 时自动展开
│   3 signal items         │
├─────────────────────────┤
│ ▶ 关联研究 (默认折叠)     │  ← 上下文感知: 概览 tab 时默认展开
├─────────────────────────┤
│ ▼ 备注 (默认展开)         │  ← 始终展开, 高频交互
│   textarea + notes       │
└─────────────────────────┘
```

### 4.2 上下文感知规则

| 当前 Tab | 信号 | 研究 | 备注 |
|----------|------|------|------|
| 概览 | 展开 | **展开** | 展开 |
| 图表 | 折叠 | 折叠 | 展开 |
| 资金流 | **展开** | 折叠 | 展开 |
| 基本面 | 折叠 | **展开** | 展开 |
| 公告 | **展开** | 折叠 | 展开 |
| 新闻 | **展开** | **展开** | 展开 |

> 纯 CSS 实现思路: 利用 tab radio 的 `:has()` + `details` 的 `open` 属性联动。
> 但 `<details open>` 是 HTML 属性不能被 CSS 切换，所以需要用 checkbox + `:has()` 模拟。

### 4.3 替代方案: checkbox 折叠 (纯 CSS)

```html
<div class="sidebar-section" data-section="signals">
  <input type="checkbox" id="collapse-signals" class="sr-only"
         checked><!-- checked = expanded -->
  <label for="collapse-signals" class="sidebar-section__header">
    相关信号 <span class="count-badge">3</span>
  </label>
  <div class="sidebar-section__body">
    <!-- signal items -->
  </div>
</div>
```

```css
.sidebar-section__body {
  display: none;
}

.sidebar-section:has(input:checked) .sidebar-section__body {
  display: block;
}

/* 上下文感知: 图表 tab 时自动折叠信号和研究 */
.tab-group:has(#tab-chart:checked)
  .sidebar-section[data-section="signals"] .sidebar-section__body,
.tab-group:has(#tab-chart:checked)
  .sidebar-section[data-section="research"] .sidebar-section__body {
  display: none;
}
```

### 4.4 新增: 快捷操作栏

从当前"结果去向"section 提取为独立 sticky 顶栏:

```
┌─────────────────────────┐
│ 贵州茅台 600519          │  ← 当前标的名称, sticky
│ [观察] [标的池] [研究]    │  ← 紧凑 icon 按钮
├─────────────────────────┤
```

高度约 48px，始终可见，节省了原 section 的 ~32px 冗余空间。

---

## 5. 信息分层策略

### 5.1 三层模型

| 层级 | 可见性 | 内容 | 交互 |
|------|--------|------|------|
| L1 常驻 | 始终可见 | 标的名称 + 快捷操作 | 无 |
| L2 核心上下文 | 默认展开 | 信号/评分/备注 (与当前 tab 相关) | 折叠/展开 |
| L3 补充信息 | 默认折叠 | 筛选预设/关联研究/历史 | 折叠/展开 |

### 5.2 垂直空间预算 (1080px viewport)

```
Header:     60px
Toolbar:    40px (screener) / 0 (hub)
─────────────────
Available:  980px (screener) / 1020px (hub)

L1 Sticky:  48px
L2 Core:    ~400px (2 sections × ~200px)
L3 Supplement: ~200px (1 section, default collapsed = ~32px header only)
─────────────────
Total visible: ~480px ← fits without scrolling
```

---

## 6. 推荐实施顺序

### Phase 1: 折叠式 section (最小改动)

- 用 `<details>/<summary>` 包装现有 section
- 默认展开/折叠状态按上述方案配置
- 无需新增 CSS 文件，page-local `<style>` 即可

### Phase 2: 上下文感知 (hub 专属)

- Hub sidebar section 根据 tab radio 联动展开/折叠
- 纯 CSS `:has()` 实现

### Phase 3: 信息密度优化 (可选)

- Screener: 雷达图 → inline score bars
- Hub: 研究列表 → 紧凑单行模式

---

## 7. 与现有 CSS 架构的兼容性

- `<details>/<summary>` 原生支持，无需额外 JS
- 折叠 header 复用 `.context-section-header` / `.context-section-body` 现有 class
- `sidebar-section` 是新 class，不与 `context-section` 冲突
- 所有折叠交互在 gallery 视图中不影响展示（gallery 独立渲染）
