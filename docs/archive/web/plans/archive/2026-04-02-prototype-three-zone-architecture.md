# 原型三区架构设计

> 日期: 2026-04-02
> 状态: Approved
> 替代: `2026-04-02-prototype-state-completeness-design.md` 中的 CSS toggle 方案

## 问题

当前原型页面把所有交互状态（loading/empty/error 等状态变体 + modal/drawer overlay）通过 CSS toggle 机制塞在一个页面滚动流里。导致：

1. **页面不可读** — 默认状态被 `<details>` state variant 包围，视觉噪音大，无法看清页面完整设计
2. **截图质量差** — Chrome MCP 截图只能捕获一个视口，混杂了折叠的 state variant 和隐藏的 overlay
3. **Review 效率低** — Review Agent 需要从混乱 HTML 中分辨主设计与状态变体，浪费 context

### 根因

「设计可视化」与「状态覆盖文档」被混合在同一个页面滚动流中。这是两个本质不同的需求：
- 设计可视化：需要单一、干净、生产级渲染
- 状态覆盖文档：需要画廊网格 + 机器可读索引

## 方案：三区 Hash 导航架构

### 核心原则

借鉴 Figma（每个 state = 独立 frame）+ Storybook（导航切换）+ Design System 文档（画廊总览）：
- **视觉隔离** — 一次只显示一个区，截图干净
- **逻辑关联** — State Coverage Index 保持机器可读
- **Review 友好** — 每个 Review 角色对应明确的 section

### HTML 结构

```html
<body>
  <!-- [State Coverage Index comment block] — 机器可读，格式不变 -->

  <!-- View-level radio navigation -->
  <input type="radio" id="view-default" name="proto-view" checked class="sr-only">
  <input type="radio" id="view-states" name="proto-view" class="sr-only">
  <input type="radio" id="view-overlays" name="proto-view" class="sr-only">

  <!-- Navigator bar -->
  <nav class="proto-nav">
    <label for="view-default" class="proto-nav__tab">主视图</label>
    <label for="view-states" class="proto-nav__tab">状态画廊</label>
    <label for="view-overlays" class="proto-nav__tab">弹层画廊</label>
  </nav>

  <!-- Zone 1: Pure Default View -->
  <section id="default-view" class="proto-section">
    <header><!-- Shell --></header>
    <main>
      <!-- 页面默认状态的完整渲染 -->
      <!-- Tab 系统保留在此，用 radio toggle 切换 -->
      <!-- 不包含任何 state variant <details> -->
      <!-- 不包含任何 overlay checkbox -->
    </main>
  </section>

  <!-- Zone 2: States Gallery -->
  <section id="states-gallery" class="proto-section">
    <div class="gallery-header">
      <h2>状态覆盖画廊</h2>
      <p class="gallery-summary">N 组件 × M 状态变体 = 总覆盖</p>
    </div>
    <div class="gallery-grid">
      <div class="gallery-group" data-component="component-name">
        <h3 class="gallery-group__title">组件中文名</h3>
        <div class="gallery-cards">
          <div class="gallery-card">
            <span class="gallery-card__label">Loading</span>
            <div class="gallery-card__preview">
              <!-- 该状态变体的完整渲染 -->
            </div>
          </div>
          <!-- ... Empty, Failed, Stale, Selected 等 -->
        </div>
      </div>
      <!-- ...更多组件组 -->
    </div>
  </section>

  <!-- Zone 3: Overlays Gallery -->
  <section id="overlays-gallery" class="proto-section">
    <div class="gallery-header">
      <h2>弹层设计画廊</h2>
      <p class="gallery-summary">N 个弹层</p>
    </div>
    <div class="gallery-grid gallery-grid--overlays">
      <div class="gallery-card gallery-card--overlay">
        <span class="gallery-card__label">Drawer: 弹层名称</span>
        <span class="gallery-card__trigger">触发条件：xxx</span>
        <div class="gallery-card__preview gallery-card__preview--overlay">
          <!-- 弹层完整渲染，直接可见，无需 toggle -->
        </div>
      </div>
      <!-- ...更多 overlay -->
    </div>
  </section>
</body>
```

### CSS 导航机制

```css
/* 默认只显示 default-view */
.proto-section { display: none; }
:root:has(#view-default:checked) #default-view { display: block; }
:root:has(#view-states:checked) #states-gallery { display: block; }
:root:has(#view-overlays:checked) #overlays-gallery { display: block; }

/* 导航栏 active 状态 */
:root:has(#view-default:checked) [for="view-default"] { /* active style */ }
:root:has(#view-states:checked) [for="view-states"] { /* active style */ }
:root:has(#view-overlays:checked) [for="view-overlays"] { /* active style */ }
```

### Gallery 网格样式

```css
/* States gallery grid */
.gallery-grid {
  display: grid;
  gap: var(--space-6);
  padding: var(--space-6);
}

.gallery-group {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-8);
  overflow: hidden;
}

.gallery-group__title {
  padding: var(--space-3) var(--space-4);
  font-size: var(--font-size-12);
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.gallery-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
  padding: var(--space-4);
}

.gallery-card {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-6);
  overflow: hidden;
}

.gallery-card__label {
  display: block;
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-10);
  font-weight: var(--font-weight-600);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface-secondary);
}

.gallery-card__preview {
  padding: var(--space-4);
  min-height: 120px;
}

/* Overlay gallery — larger cards */
.gallery-grid--overlays .gallery-card__preview--overlay {
  min-height: 200px;
  position: relative;
  background: var(--surface-overlay);
}
```

## 设计决策记录

### D1: 单文件 vs 多文件

**决策**: 单文件 + hash 导航（radio 切换）

**Why**: 多文件方案会导致共享样式管理复杂、文件数量爆炸（16 页面 × 3-4 文件 = 50+ 文件）。单文件维护简单，Chrome MCP 通过 `evaluate_script` 切换 radio 即可截图不同区。

**Trade-off**: 文件较大（约 1500-2000 行），但每个 section 职责单一，结构清晰。

### D2: Tab 系统位置

**决策**: Tab 保留在 default-view 内，用 radio toggle 切换

**Why**: Tab 是页面功能导航（如行情/自选/板块），不是组件生命周期状态。概念上属于「页面设计」而非「状态变体」。放进画廊会混淆两类不同关注点。

**Review 适配**: Baseline Phase 自动检测 tab group 并逐一截图（每个 tab 一张截图）。

### D3: Default-view 纯净度

**决策**: 完全不含 state variant 和 overlay

**Why**: default-view 的唯一职责是回答"这个页面长什么样？"。任何额外元素都是噪音。Review Agent 评估视觉质量时应该看到一个与生产环境一致的渲染。

### D4: Gallery 中 Overlay 的展示

**决策**: 直接渲染，不用 checkbox toggle

**Why**: 画廊的目的是让 Review Agent 一眼看到所有 overlay 设计。checkbox toggle 需要交互才能看到，违背了画廊「一览性」的设计意图。

### D5: 迁移策略

**决策**: 全量重写 16 个页面

**Why**: 结构性变更（三区分离 vs 单页混合）无法增量迁移。一次性重写确保所有页面结构一致，避免新旧格式混存的维护负担。

## 对 Review 流程的影响

### Phase 1: BASELINE 截图策略

```
Before: 1 张截图（混乱）
After:  N 张截图
  1. evaluate_script → view-default radio checked → 截图（默认 tab）
  2. 对 default-view 中每个 tab group:
     evaluate_script → 点击 tab label → 截图
  3. evaluate_script → view-states radio checked → 截图（状态画廊）
  4. evaluate_script → view-overlays radio checked → 截图（弹层画廊）
```

### Phase 3: 6-Role Review 输入指引

| 角色 | 主要评估 Section | 辅助评估 |
|------|-----------------|---------|
| UI Designer | default-view 视觉质量 | states-gallery 卡片一致性 |
| UX Reviewer | default-view 交互流 | overlays-gallery 弹层可用性 |
| Product Manager | default-view 产品规格 | states-gallery 状态覆盖完整性 |
| IA Specialist | default-view 信息架构 | — |
| Copy Editor | 所有 section 文案 | — |
| Art Director | default-view 品牌方向 | 三区整体协调性 |

### State Coverage Report

模板适配：不再依赖 `<details>` 展开检测，改为检查 states-gallery 中 `.gallery-card` 的数量和 label 是否匹配 State Coverage Index。

## 需要修改的文件

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `prototypes/shared/prototype-toggles.css` | **重写** | 新增 view-level radio 导航；移除 details state variant 样式；新增 gallery grid 样式 |
| `.claude/commands/ditto-design-cycle.md` | **修改** | Phase 0.5 CREATE 输出结构；Phase 1 BASELINE 截图策略；Phase 3 Review 角色输入指引 |
| `.claude/design-review/iterate.md` | 微调 | REFLECT 中状态覆盖检查逻辑 |
| `.claude/design-review/roles.md` | 微调 | 各角色评估 section 指引 |
| `.claude/design-review/templates.md` | 微调 | State coverage report 模板 |
| 16 个 `page-*.html` | **全量重写** | 三区结构 |

## 不变的部分

- State Coverage Index 注释格式
- Design tokens 全套
- 5 维评分系统
- 产品规格文档
- blueprints / interaction state spec
- Edition manifest 追踪机制
