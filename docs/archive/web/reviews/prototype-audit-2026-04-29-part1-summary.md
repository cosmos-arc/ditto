# Prototype 全量审计报告 (2026-04-29)

> 审计范围：`docs/designs/specs/prototypes/` 全部 29 个 HTML + 7 个共享文件
> 审计标准：UI/UX Pro Max 最高级别 + 项目既有规范体系交叉验证

---

## 执行摘要

### 评级总览

| 维度 | 评级 | 说明 |
|------|:----:|------|
| Shell 结构一致性 | B+ | 8 种 shell 模式，5 种已共享化，3 种各自内联 |
| 组件 CSS 一致性 | C | `.panel` `.data-table` `.btn` 被多页重写覆盖 |
| 主题切换完整性 | B- | 27/29 页统一，缺 system 选项，light mode 覆盖率 25% |
| 密度切换完整性 | B | token 架构完善，但部分页面绕过 density 变量 |
| 弹层/Overlay 一致性 | C- | 子组件 CSS 全部内联，命名、值、动画均不统一 |
| 折叠/展开交互 | C+ | 三种实现方式并存，无过渡动画 |
| 可调整面板 | N/A | 当前无此功能，spec 未定义 |
| 无障碍 (a11y) | B- | focus-visible 覆盖不均，portfolio 为 0 |

### 关键数字

- **29** 个原型页面
- **7** 个共享文件（layout-base.css, theme-switcher.css/js, prototype-toggles.css 等）
- **P0 问题**: 5 个（阻碍 React 对齐）
- **P1 问题**: 9 个（设计系统一致性）
- **P2 问题**: 7 个（品质提升）
- **弹层 CSS 重复**: ~27 页 × 6-16 条规则 = 估计 300+ 条重复 CSS

---

## P0 问题清单（必须修复）

### P0-1: shell-hub / shell-agent 未进入共享 CSS

**现状**: `page-strategies-detail`、`page-factor-analysis`、`page-backtest-result` 三页使用 `.shell-hub` 布局，`page-agent-console` 使用 `.shell-agent`，但这两个 shell 模式仅在各自 `<style>` 块中定义，未提取到 `layout-base.css`。

**影响**:
- 同一 shell 模式有 3 套不同 grid 定义（4 行 vs 5 行 vs 6 行）
- noise texture、ambient light bar、frosted header 在每个页面重复实现
- React 对齐时无法确定哪套 grid 定义是标准

**建议**: 提取 `shell-hub`、`shell-agent` 到 `layout-base.css`，统一 grid 定义。

---

### P0-2: 弹层子组件 CSS 全部内联且值不一致

**现状**: `.overlay-header`、`.overlay-title`、`.overlay-body`、`.overlay-actions`、`.overlay-btn` 等子组件的 CSS 在 27/29 页各自内联。核心不一致：

| 属性 | page-home | 其他多数 | page-backtest-result |
|------|-----------|---------|---------------------|
| `overlay-btn` padding | `space-4 space-10` | `space-2 space-10` | 使用 component token |
| header padding | `space-12` | `space-12` | `space-10` |

**影响**: React 实现时无法确定标准值。

**建议**: 提取弹层子组件 CSS 到 `layout-base.css` 或新建 `shared/overlay-components.css`。

---

### P0-3: `.data-table` 重写导致密度切换失效

**现状**: portfolio、strategies-detail、factor-analysis、backtest-result 各自重写 `.data-table` 的 `th`/`td` padding，使用硬编码 `var(--space-6)` 等值，绕过了 `var(--density-cell-padding-y/x)` 变量。

**影响**: 密度切换在这 4 个页面的表格区域不生效。

**建议**: 删除页面级 `.data-table` 重写，统一使用 `layout-base.css` 中的 density-aware 定义。

---

### P0-4: `overlay-modal` 类被使用但无 CSS 定义

**现状**: backtest-result、factor-analysis、markets-calendar、strategies-detail 4 个页面使用 `.overlay-modal` 类，但没有对应的 CSS 规则。只有 `prototype-toggles.css` 中的 `.overlay-surface--modal`。

**影响**: Modal 内容可能缺少宽高约束，渲染结果不可预测。

**建议**: 在共享 CSS 中补充 `.overlay-modal` 定义，或统一使用 `.overlay-surface--modal`。

---

### P0-5: page-portfolio 使用独立弹层命名体系

**现状**: portfolio 使用 `modal-header/modal-title/modal-close/modal-body/modal-actions/modal-btn` 命名，而其他所有页面使用 `overlay-*` 体系。

**影响**: 两套命名体系造成 React 组件设计歧义。

**建议**: 统一为 `overlay-*` 命名体系。

---

## P1 问题清单（设计系统一致性）

### P1-1: Light mode 覆盖率仅 25%

仅 home (10 条) 和 trading-overview (4 条) 有 `[data-theme="light"]` CSS 覆盖。其余 27 页完全依赖 token 层自动切换。

对于使用 atmosphere 层（ambient 灯光、noise texture）的页面，token 自动切换不够——ambient opacity、noise-layer 可见度等需要显式 light/dark 区分。

**建议**: 定义 `shared/atmosphere-overrides.css`，统一处理 light mode 下 atmosphere 层的适配。

---

### P1-2: Button 系统碎片化为 3 套

| 体系 | class 模式 | 使用页面 |
|------|-----------|---------|
| layout-base `.btn` | `.btn .btn-primary/.btn-ghost/.btn-danger` | strategies-detail, factor-analysis, backtest-result |
| 自定义 `.btn-cta` | `.btn-cta .btn-cta-sm .btn-ghost` | agent-console, risk-center |
| `.decision-cta` | `.decision-cta` | home |

**建议**: 在 `layout-base.css` 中统一按钮体系，涵盖所有使用场景。

---

### P1-3: AI 两页面使用旧式主题/密度切换 UI

`page-ai-overview.html` 和 `page-ai-copilot.html` 使用 inline switcher（直接放在 header 区域），缺少 system 主题选项，UI 与其他 27 页不一致。

**建议**: 迁移到 View Preferences 下拉面板模式。

---

### P1-4: `.panel` 被 4 个页面重定义

home、strategies-detail、factor-analysis、backtest-result 各自在 `<style>` 中重写 `.panel`。backtest-result 使用 `var(--card-radius)` 而非 `var(--radius-8)`。

**建议**: 删除页面级 `.panel` 重写，统一使用 `layout-base.css` 定义。如需变体，使用 `.panel--variant` 修饰符。

---

### P1-5: Token 导入顺序不一致

| 文件 | 缺失 |
|------|------|
| strategies-detail | `tokens-shell.css` + `tokens-data-viz.css` |
| agent-console | `tokens-shell.css` + `tokens-data-viz.css` |

导入顺序也不统一（data-viz 在 shell 前后都有）。

**建议**: 定义标准导入模板，确保所有页面使用相同的 token 导入顺序。

---

### P1-6: 主题切换缺少 system 选项和过渡动画

当前只有 dark/light 两态，没有跟随系统偏好的 system 选项。切换是瞬间的，没有过渡动画。

**建议**: 参照业界三态模式（dark/light/system），添加 `prefers-color-scheme` 跟踪和全页面 `transition-colors` 过渡。

---

### P1-7: 折叠/展开三种实现方式并存

| 方式 | 技术 | 动画 | 使用场景 |
|------|------|------|---------|
| JS onclick toggle | `classList.toggle` | 无 | sidebar rail (3 页) |
| HTML `<details>/<summary>` | 原生 | 无 | context-section (2 页) |
| data-bottom-tray-state | CSS 三态属性 | 无 | bottom tray (4 页) |

全部无过渡动画。

**建议**: 统一折叠机制，添加 `max-height` transition。

---

### P1-8: Toast 实现完全不统一

仅 2 个页面有 toast，且结构、样式、定位完全不同：
- ai-overview: 自定义 toast-overlay-backdrop + toast-card，320px 宽度，完整 icon/title/desc
- backtest-result: overlay-backdrop--toast + 简单 toast-card，一行文本

**建议**: 定义统一 toast 组件到 `layout-base.css`。

---

### P1-9: 密度档位命名语义错位

React 端 Zustand store 定义 `"dense" | "default" | "comfortable"`，但 `default` 实际等同于 `compact`（`:root` 默认值）。Prototype UI 中标签为"紧/标/松"，但 `data-density` 值为 `dense/compact/comfortable`。

用户选择"标"→ 实际设为 `compact`，但 React 端 "default" = 不设属性 = 也等于 compact。语义混乱。

**建议**: 统一命名。推荐: `"compact" | "default" | "comfortable"`，其中 `default` = 中等密度（当前 `compact` 的值适当放宽）。

---

## P2 问题清单（品质提升）

| # | 问题 | 建议 |
|---|------|------|
| 1 | 硬编码 `border-radius: Npx` (总计 41 处) | 统一为 `var(--radius-N)` token |
| 2 | `skip-link` 在所有 8 个审计页面重复定义 | 删除页面级定义，仅保留 `layout-base.css` |
| 3 | `.sr-only` 在 2 个页面重复定义 | 同上 |
| 4 | Sidebar 折叠 JS 代码 3 页各自内联且完全相同 | 提取到共享 JS |
| 5 | `collapse-count` 双 badge 模式仅 instrument-hub 使用 | 提取到 `layout-base.css` 共享 |
| 6 | Disclosure 箭头样式 3 种混用（▶ + rotate / ▾ / 纯文本） | 统一为一种 |
| 7 | portfolio 缺少 noise texture 和 ambient light bar | 补齐 Graphite Studio 特征 |

---

## 详细报告索引

| 部分 | 文件 |
|------|------|
| Part 1: 总览 + P0/P1/P2 问题清单 | `prototype-audit-2026-04-29-part1-summary.md` |
| Part 2: 主题/密度切换 + 业界最佳实践对比 | `prototype-audit-2026-04-29-part2-theme-density.md` |
| Part 3: 弹层/Overlay + 折叠交互 + 可调整面板 | `prototype-audit-2026-04-29-part3-overlay-panels.md` |
| Part 4: 语义化视觉突变 + 改进路线图 | `prototype-audit-2026-04-29-part4-recommendations.md` |
