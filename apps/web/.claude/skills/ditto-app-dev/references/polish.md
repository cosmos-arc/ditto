# Phase 13: POLISH — 交互打磨 [opus]

> CSS transitions 基线 + Motion 按需 + 交互状态全覆盖审计。

**输入**：Phase 12 实现的组件 + 原型中的交互暗示（hover 区域、按钮、可点击元素）

---

## Step 1: Design System 对齐（使用 impeccable:normalize）

- 读取 `docs/DESIGN.md` Components 章节，确认组件 token 映射基线
- 扫描 React 实现，对照 contract slots/subSlots 的 token 消费
- 检查是否存在硬编码颜色/字号/间距（应使用 design token）
- 确保与项目 design system 一致（shadcn 组件变体、spacing scale、typography scale）
- 确保 token 使用与 DESIGN.md 一致（组件背景色、边框色、圆角等应匹配 DESIGN.md Components 章节）
- 修复所有 drift（偏离 design system 的样式）

## Step 2: 排版精修（使用 impeccable:typeset）

- 字号档位与 prototype 一致（通过 Phase 10 度量数据验证）
- 字重使用正确（text-xs/text-sm/text-base 等不塌缩）
- 行高、字距在阈值内（line-height 1.5-1.7 body，letter-spacing ±0.02em）
- 数字/数据列使用 tabular-nums
- 文本容器 max-width ≤ 65ch（正文可读性）

## Step 3: 交互状态审计（Interaction Audit）

扫描页面所有可交互元素：Button、Link、Input、Tab、Card、可点击行。
对每个元素建立状态清单：

| 元素类型 | 必需状态 | 默认行为 |
|---------|---------|---------|
| Button | default, hover, focus-visible, active, disabled | CSS transition |
| Card (可点击) | default, hover, focus-visible | 背景色 + 阴影过渡 |
| Tab | default, hover, active (selected) | 下划线/背景滑动 |
| Input | default, focus, error, disabled | focus ring 过渡 |
| 数据行 (可点击) | default, hover, selected | 行背景过渡 |
| 面板 (可展开) | collapsed, expanded, transitioning | Motion AnimatePresence |
| Modal/Drawer | hidden, entering, visible, exiting | Motion AnimatePresence |
| Tooltip | hidden, visible | CSS opacity + transform |

## Step 4: CSS Transitions 基线（零成本覆盖 ~80% 场景）

- 所有可交互元素必须添加 `transition-colors` 或 `transition-all`
- 时长使用 Tailwind token：`duration-150`（快速）、`duration-200`（标准）、`duration-300`（慢速）
- focus-visible ring 使用 `ring-offset` + `ring-2` + design token 颜色
- 禁止 `transition-all` 的无限滥用（仅在有多个属性需要过渡时使用）

## Step 5: Motion 按需引入（使用 impeccable:animate）

```
引入 Motion 的判断标准（满足任一即引入）：
├── 元素需要退出动画（CSS 无法做到 DOM 卸载动画）
├── 布局位移需要补间（面板 resize、列表排序）
├── 需要 stagger 编排（列表项依次进入）
└── 需要手势响应（drag, pinch）
```

- 动画参数使用项目 token（--duration-fast/normal/slow, --ease-default/spring）
- 每个动画组件必须 `export` 动画 variant 常量，禁止 inline magic numbers

## Step 6: 色彩精修（使用 impeccable:colorize）

- 语义色使用正确（success/error/warning/info 状态）
- accent 色应用一致（CTA、active 状态、关键数据高亮）
- 遵循 60/30/10 配色比例
- WCAG 对比度合规（4.5:1 正文，3:1 大文本）

## Step 7: 边界加固（使用 impeccable:harden）

- 文本溢出处理（ellipsis、line-clamp、word-wrap、flex min-width:0）
- 空数据 / 加载中 / 错误状态的 UI 完整性（contract states 覆盖检查）
- 长文本 / 特殊字符 / 超长列表的渲染稳定性
- 输入验证（表单字段、API 错误码映射）
- A11y 基线（keyboard nav、aria-label、focus management）

## Step 8: Micro-interactions（使用 impeccable:polish）

- 按钮 hover 微位移（translate-y -0.5px）
- 选中态的视觉权重变化
- 数据加载时的 skeleton shimmer
- 状态切换的即时反馈（颜色闪变、图标旋转）

## Step 9: 交互状态测试

- 每个交互状态至少一个测试：`fireEvent.hover()`, `fireEvent.focus()`
- `:focus-visible` 键盘导航测试
- Motion 动画的 `act()` 包裹测试
- 边界场景测试（空数据、长文本、error fallback）

**输出**：交互状态覆盖报告（元素类型 × 状态矩阵，标注已实现/已跳过及原因）
