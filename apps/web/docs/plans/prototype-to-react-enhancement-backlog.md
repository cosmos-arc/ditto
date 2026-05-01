# Prototype → React 增强待办

> **来源**: 原型迭代审查（`/ditto-design-cycle --iterate`）中 AD 明确标注为"静态原型天花板"的改进项。
> **原则**: 这些优化无法在 HTML 原型中表达，需要在 React 实现阶段落地。

---

## Home 首页

### 1. Tooltip 系统
- 原型中使用 `data-tooltip` 属性标注，但无实际渲染
- React 端需实现：hover 触发、定位逻辑、`prefers-reduced-motion` 兼容
- 涉及元素：pulse-metric-label、pulse-metric-value、queue-item 标签、health-gauge

### 2. 真实 Sparkline 数据渲染
- 原型中 inline SVG 为静态 mock
- React 端需接入真实数据源，支持动态更新 + 动画过渡
- 涉及：Decision Banner PnL sparkline、Context Rail 4 个市场脉搏指标

### 3. Status Dot 动态状态
- 原型中 dot-pulse / dot-critical-pulse 为纯 CSS 动画
- React 端需根据实际系统状态切换动画模式（live / running / paused / error）
- 涉及：Today Pulse 状态条、Alerts 严重度指示、Data Health 状态

### 4. `.decision-cta.secondary` opacity 替换
- 原型中使用 `opacity: 0.7` 实现视觉层级
- React 端应使用语义化的 `--text-quaternary` 或专用组件 token
- 当前无 `--text-quaternary` token，需评估是否新增

### 5. `findings-feed-subtitle` opacity 替换
- 同上，`opacity: 0.7` → 语义化 token
- 与 `.decision-cta.secondary` 合并处理

### 6. Workspace Placeholder 替换 emoji
- 原型中使用 `🧩` emoji 作为占位图标
- React 端应替换为项目 SVG 图标（与 queue-item category icons 保持一致）
- 依赖：Workspace 模块的实际实现

---

## 通用（跨页面）

### 7. 数据新鲜度视觉指示
- 产品规格要求：stale ≥ 5s 需要视觉指示器
- 需使用 `--data-freshness-*` token
- 涉及所有实时数据区块（pulse metrics、alerts、signals）

### 8. 响应式断点行为
- 原型仅验证 VP-STANDARD (1536×1080) 和 VP-COMPACT (1366×768)
- React 端需补充：中间断点、Rail 折叠、Context Rail 抽屉化

### 9. 交互状态完整实现
- 原型 overlay gallery 为静态渲染
- React 端需实现：Drawer / Modal / Confirm Dialog 的动画过渡 + 焦点管理 + ESC 关闭

### 10. Prototype Interaction UX 2026-04-30
- 来源：`docs/designs/specs/20_interaction_ux_audit.md` 与 `docs/plans/2026-04-30-prototype-interaction-ux-remediation-plan.md`
- React Rail 需使用 TanStack Router links，不延续 prototype 中的静态 `href`
- 建立 typed icon registry：domain icons、header utilities、local action icons 分层管理
- 将 prototype inline SVG 替换为 Lucide/custom icon components，并保证同一图标不跨语义复用
- 实现 `ContextDisclosureSection`：`aria-expanded`、`aria-controls`、默认展开策略、count 与 summary
- 折叠偏好、Bottom Tray 状态、面板尺寸偏好进入 `use-ui-preferences`、Zustand/localStorage 或 library storage 持久化
- Bottom Tray 需要 React 状态机：`collapsed | peek | expanded`，并覆盖键盘与 reduced-motion 行为
- 评估并申请批准后再安装 `react-resizable-panels`
- 2026-04-30 查询当前包版本为 `react-resizable-panels@4.10.0`，实施前需重新确认版本与 API
- 若依赖获批，先落地 Catalog 与 Studio shell 的 resizable panel group
- 面板 resize 需覆盖 `role="separator"`、方向键、Enter collapse/restore、双击重置、24px hit area
- 补 Playwright/RTL 测试：Rail 导航语义、Disclosure 键盘行为、Bottom Tray 三态、Resizable separator 键盘调整

### 11. Expert Efficiency Contracts 2026-05-01
- 表格列宽持久化：按 route + table id 保存列宽，恢复时校验最小宽度与可见列集合
- 冻结列：Catalog / Queue / Ops 表格支持首列或关键列冻结，并覆盖横向滚动、键盘导航与窄屏降级
- 完整 Command Palette：读取 `data-command-scope` 与 `data-command-context-actions`，按选中对象、route、权限和状态过滤动作
- 选中对象驱动跨区域状态：列表选中项同步主表、详情、证据、日志、批量栏与 command context
- React Modal / Drawer 焦点管理：实现 focus trap、ESC 关闭、返回焦点，并让 overlay 背景 inert

---

## 维护说明

- 每次原型迭代完成后，AD 标注的"需 React 实现"项应追加到此文档
- 完成 React 实现后，对应项标记为 `[done]` 并注明 commit hash
- 文档按页面分组，通用项放末尾
