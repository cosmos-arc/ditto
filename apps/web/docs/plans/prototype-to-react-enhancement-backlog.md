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

---

## 维护说明

- 每次原型迭代完成后，AD 标注的"需 React 实现"项应追加到此文档
- 完成 React 实现后，对应项标记为 `[done]` 并注明 commit hash
- 文档按页面分组，通用项放末尾
