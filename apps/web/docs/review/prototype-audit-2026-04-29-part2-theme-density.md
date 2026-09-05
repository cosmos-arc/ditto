# Part 2: 主题/密度切换审计 + 业界最佳实践对比

---

## 1. 当前架构分析

### 1.1 主题切换现状

| 维度 | 当前实现 | 业界最佳实践 | 差距 |
|------|---------|-------------|------|
| **策略** | `data-theme` HTML 属性 | Tailwind v4 `@custom-variant dark` + class 或 data 属性 | 兼容，但未用 Tailwind 原生 dark: |
| **选项** | dark / light（两态） | dark / light / system（三态） | **缺 system 选项** |
| **默认** | dark（无属性） | 跟随系统偏好或用户上次选择 | 硬编码 dark |
| **持久化** | localStorage | localStorage + prefers-color-scheme 监听 | 缺系统偏好监听 |
| **过渡动画** | 无（瞬间切换） | `transition-colors duration-300` 全页面平滑 | **无过渡** |
| **FOUC 防护** | 无 | `<head>` 内联阻塞脚本 | 无（SPA 场景影响较小） |
| **切换入口** | View Preferences 下拉（27 页）/ Inline switcher（2 页） | Settings / Profile 菜单 | 入口位置合理，但 UI 不统一 |

### 1.2 密度切换现状

| 维度 | 当前实现 | 业界最佳实践 | 差距 |
|------|---------|-------------|------|
| **策略** | `data-density` HTML 属性 | CSS 变量 + data 属性 | 一致 |
| **档位** | dense / compact / comfortable | compact / default / comfortable（M3 模式） | 命名语义错位 |
| **影响范围** | 12 个 CSS 变量（padding, gap, height, strip, chart） | spacing 系属性（不改字号/圆角） | **dense 档改了字号（-1 delta）** |
| **入口** | View Preferences 下拉 | Settings / 全局控制 | 合理 |
| **表格密度** | 部分页面绕过 density 变量 | 全组件统一消费 density token | **4 页面绕过** |

### 1.3 密度档位命名问题详解

```
当前:
  Prototype UI 标签: "紧" / "标" / "松"
  data-density 值:   "dense" / "compact" / "comfortable"
  React Zustand:     "dense" / "default" / "comfortable"

问题:
  1. "标" = compact, 但 React "default" = 不设属性 = :root 默认值 = 也等于 compact
  2. "dense" 在英文语境中表示"密集"，对应中文"紧"，语义一致
  3. 但 "compact" 在英文中也表示"紧凑"，与 "dense" 语义重叠
  4. 用户选择"标"期望的是"标准密度"，而非"紧凑密度"

业界对照:
  VSCode:        默认(normal) / 紧凑(compact) -- 两档
  Material 3:    Default / Comfortable / Compact -- 三档
  Linear:        默认 / 紧凑 -- 两档（紧凑在设置中）

推荐:
  重命名档位为 "compact" / "default" / "comfortable"
  - compact: 当前 dense 的值（最紧凑，字号 -1）
  - default: 当前 compact 的值（中等密度，不改字号）
  - comfortable: 当前 comfortable 的值（最宽松）
  React 和 Prototype UI 标签同步更新
```

---

## 2. 业界最佳实践详细对比

### 2.1 主题切换

#### 三态模式（推荐）

```
                 ┌──────────────┐
                 │   用户选择    │
                 └──────┬───────┘
                        │
           ┌────────────┼────────────┐
           ▼            ▼            ▼
       ┌───────┐   ┌───────┐   ┌────────┐
       │ Dark  │   │ Light │   │ System │
       └───────┘   └───────┘   └───┬────┘
                                   │
                          ┌────────┼────────┐
                          ▼                 ▼
                    ┌──────────┐      ┌──────────┐
                    │ prefers- │      │ prefers- │
                    │ dark     │      │ light    │
                    └──────────┘      └──────────┘
```

**实现要点**：
1. `localStorage` 存储用户偏好（优先级最高）
2. `window.matchMedia('(prefers-color-scheme: dark)')` 监听系统变化
3. 渲染前阻塞脚本读取偏好，防 FOUC
4. `data-theme` 属性驱动 CSS 变量切换

**代码示例（适合 Ditto 的实现）**：

```typescript
// use-ui-preferences.ts 扩展
type Theme = "dark" | "light" | "system";

// 计算实际主题
function getEffectiveTheme(theme: Theme): "dark" | "light" {
  if (theme !== "system") return theme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

// 应用到 DOM
function applyTheme(theme: Theme) {
  const effective = getEffectiveTheme(theme);
  if (effective === "dark") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", "light");
  }
}

// 监听系统偏好变化（仅 system 模式下生效）
useEffect(() => {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const handler = () => {
    if (preferences.theme === "system") applyTheme("system");
  };
  mq.addEventListener("change", handler);
  return () => mq.removeEventListener("change", handler);
}, [preferences.theme]);
```

#### FOUC 防护（SPA 场景）

Ditto 是 SPA（Vite），FOUC 风险低于 SSR。但仍建议在 `index.html` 的 `<head>` 中加入：

```html
<script>
  (function() {
    var theme = localStorage.getItem("ditto-theme");
    if (theme === "light") {
      document.documentElement.setAttribute("data-theme", "light");
    }
  })();
</script>
```

#### 过渡动画

```css
/* 主题切换过渡 — 仅颜色属性 */
html {
  transition:
    background-color 300ms ease-in-out,
    color 300ms ease-in-out;
}

/* 尊重用户偏好 */
@media (prefers-reduced-motion: reduce) {
  html {
    transition-duration: 0ms;
  }
}
```

**重要**: 不要用 `transition: all`——会影响 width/height/transform 造成性能问题。限定为 `background-color` 和 `color`。

### 2.2 密度切换

#### 影响范围矩阵（业界共识）

| 属性 | 低密度 | 标准 | 高密度 | 改不改？ |
|------|--------|------|--------|---------|
| padding | 16px | 12px | 8px | 改 |
| margin/gap | 12px | 8px | 4px | 改 |
| 行高 line-height | 1.75 | 1.5 | 1.25 | 改 |
| 组件高度 | auto | auto | auto | 不改（内容决定） |
| 字号 | 不变 | 不变 | **不变**（业界共识） | **不改** |
| 圆角 | 不变 | 不变 | 不变 | **不改** |
| 图标尺寸 | 20px | 18px | 16px | 可选改 |
| 触控目标 | >= 44px | >= 44px | >= 44px | **不改**（a11y 硬要求） |

**关键发现**: Ditto 当前 `dense` 档使用 `--density-font-delta: -1` 来减小字号，这违反了业界共识。Material Design 3 明确规定密度切换不改字号（保持可读性）。

**建议**: 移除 `--density-font-delta`，改用间距/行高调整来控制密度。

#### 密度切换 UI 最佳实践

**VSCode 模式**（推荐参考）：
- 不直接暴露"密度切换"UI
- 而是通过多个细粒度选项间接控制（Activity Bar 紧凑、树形缩进、行高等）
- 对 Ditto 而言：3 档预设是更好的选择（VSCode 的细粒度对量化工具过于复杂）

**Linear 模式**：
- 设置页面一个开关：紧凑模式（on/off）
- 简洁但不够灵活

**Ditto 推荐方案**：保持 3 档预设，但重命名 + 修正影响范围：

| 档位 | 新名称 | 标签 | 影响 |
|------|--------|------|------|
| compact | compact | 紧凑 | 最小间距，高信息密度 |
| default | default | 标准 | 适中间距（**推荐默认**） |
| comfortable | comfortable | 宽松 | 大间距，阅读舒适 |

### 2.3 当前设计"太繁琐"的问题分析

用户反馈"主题/密度的切换目前的设计太繁琐"。分析原因：

**问题 1: View Preferences 下拉面板过重**

当前设计：点击头像 → 弹出 View Preferences 下拉面板 → 内含两个分组（主题 + 密度）→ 每组 3 个按钮 + 描述文字。

这比业界做法更复杂：
- VSCode: 设置 > Color Theme（独立页面，带搜索）
- Linear: 头像菜单 > Theme（3 个图标按钮，一行）
- Notion: 设置 > Appearance（两个 switch）

**问题 2: 弹出层视觉与整体风格差异**

View Preferences 下拉面板使用 `.overlay-surface--sheet` 样式（居中面板 + 遮罩），但实际上它只是一个轻量的偏好选择器。用居中弹层来切换主题/密度在视觉上过于"正式"。

**推荐改进方案**:

```
方案 A: 简化为 Popover（推荐）
  - 点击头像 → 弹出小型 Popover（无遮罩，锚定到头像）
  - 内含两个 radio group（主题 + 密度）
  - 点击外部即关闭
  - 视觉轻量，不打断工作流

方案 B: 合并到 Command Palette
  - Ctrl+K 打开命令面板
  - 输入 "theme" 或 "density" 直接切换
  - 无需额外 UI

方案 C: 状态栏快捷入口
  - 在 header 右侧放一个小图标
  - hover 展示当前主题/密度
  - 点击弹出 Popover 切换
```

---

## 3. 改进优先级

| 优先级 | 改进项 | 工作量 | 影响 |
|--------|--------|--------|------|
| **P0** | 添加 system 主题选项 | 0.5 天 | 跟随系统偏好 |
| **P0** | 密度档位重命名（消除语义错位） | 0.5 天 | React 对齐无歧义 |
| **P1** | 主题切换过渡动画 | 0.5 天 | 体验提升明显 |
| **P1** | View Preferences 简化为 Popover | 1 天 | 降低"繁琐感" |
| **P1** | 移除 `--density-font-delta`（dense 不改字号） | 0.5 天 | 遵循业界共识 |
| **P2** | AI 两页迁移到新式 View Preferences | 0.5 天 | 统一 UI |
| **P2** | FOUC 防护脚本 | 0.5 天 | 防闪烁 |
