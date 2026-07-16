# Part 4: 语义化视觉突变 + 综合改进路线图

---

## 1. 语义化视觉突变（Semantic Visual Cues）

### 1.1 当前缺失

当前原型在以下场景缺乏语义化的视觉反馈：

| 场景 | 当前处理 | 应有处理 | 优先级 |
|------|---------|---------|--------|
| **数据值变化** | 无反馈 | 数字滚动/高亮闪烁 | P1 |
| **状态变更**（running → success/failed） | 文字变化 | 颜色+图标+微动画 | P1 |
| **风险等级突变** | 静态颜色块 | 脉冲/呼吸动画 + 颜色渐变 | P0 |
| **选中对象联动** | 无反馈 | 联动区域边框高亮/脉冲 | P1 |
| **阈值穿越** | 无反馈 | 穿越瞬间闪烁 + 状态栏提示 | P2 |
| **列表项增删** | 瞬间出现/消失 | 滑入/滑出动画 | P2 |
| **排序变化** | 瞬间重排 | FLIP 动画 | P2 |
| **加载中 → 完成** | 无过渡 | 骨架屏 → 内容淡入 | P1 |

### 1.2 推荐的语义化突变设计

#### 类别 1: 数值变化动画

```
场景：因子暴露度从 0.45 变为 0.62
效果：
  1. 数字滚动动画（旧值 → 新值，300ms）
  2. 变化方向色彩（正=绿，负=红，300ms 后消退）
  3. 变化幅度指示（大变化=更强烈的颜色/更长持续时间）

实现：
  CSS: 数字用 tabular-nums 防布局抖动
  JS: requestAnimationFrame 计数动画（60fps）
  React: <AnimatedNumber> 组件
```

#### 类别 2: 状态突变

```
场景：回测从 running → success
效果：
  1. 状态图标旋转动画停止 → 变为 ✓ 图标
  2. 背景色从 surface-panel-base → 微妙的 success tint（300ms fade）
  3. 状态栏更新为绿色 success 标签

场景：策略从 active → critical（风控触发）
效果：
  1. 状态标签颜色突变为 danger
  2. 行项目背景闪烁一次（amber pulse，500ms）
  3. 如果影响全局：header context strip 出现 alert banner

实现原则：
  - 越严重的变化，动画越不可忽略
  - 但仍然克制（Graphite Studio：不花哨，不喧闹）
  - 脉冲动画仅用于需要用户注意的变化
```

#### 类别 3: 阈值穿越

```
场景：VaR 从 85%（warning zone）穿越到 95%（critical zone）
效果：
  1. 数值高亮闪烁（critical 色脉冲，200ms × 2 次）
  2. 进度条/仪表盘颜色过渡（warning amber → critical red）
  3. 如果首次穿越：状态栏添加 alert item

实现：
  CSS: @keyframes threshold-pulse
  JS: 检测穿越条件 → 添加 .threshold-crossed class（500ms 后自动移除）
```

#### 类别 4: 选中对象联动

```
场景：用户在表格中选中一行，右侧 Inspector 更新
效果：
  1. Inspector 面板边框短暂高亮（200ms pulse）
  2. 内容淡入更新（200ms crossfade）
  3. 新数据中的关键数值有 subtle 高亮

实现：
  CSS: @keyframes link-pulse { 0% { border-color: var(--brand-500); } 100% { border-color: var(--border-subtle); } }
  React: CSS transition + key prop 触发重渲染动画
```

### 1.3 动画体系设计

基于交互状态规范的反馈五级分级（L1-L5），设计对应的动画层级：

| 反馈级别 | 动画强度 | 持续时间 | 举例 |
|---------|---------|---------|------|
| L1 微反馈 | 极弱（opacity 0.8→1） | 150ms | hover、copy |
| L2 操作反馈 | 弱（背景色闪现） | 300ms | save 成功、delete 完成 |
| L3 运行反馈 | 中（进度动画） | 持续 | backtest running、agent 执行中 |
| L4 风险反馈 | 强（脉冲+色变） | 500ms | 阈值接近突破、模型退化 |
| L5 阻断反馈 | 最强（全屏遮罩） | 持续到处理 | 订单被拒、系统不可用 |

**动画 Token 建议**（补充到 design-tokens）：

```css
:root {
  /* 动画时长 */
  --duration-instant: 100ms;    /* L1 hover/focus */
  --duration-fast: 200ms;       /* L2 操作反馈 */
  --duration-normal: 300ms;     /* 标准过渡 */
  --duration-slow: 500ms;       /* L4 风险反馈 */

  /* 缓动函数 */
  --ease-standard: cubic-bezier(0.4, 0, 0.2, 1);     /* 标准 */
  --ease-decelerate: cubic-bezier(0, 0, 0.2, 1);     /* 进入 */
  --ease-accelerate: cubic-bezier(0.4, 0, 1, 1);     /* 退出 */
  --ease-spring: cubic-bezier(0.175, 0.885, 0.32, 1.275); /* 弹性 */

  /* 脉冲 */
  --pulse-opacity: 0.6;
  --pulse-duration: 1.5s;
}
```

---

## 2. 弹层风格对齐方案

### 2.1 Graphite Studio 弹层设计原则

| 原则 | 说明 |
|------|------|
| **克制** | 不用夸张阴影，用 border + 微妙背景区分 |
| **一致** | 所有弹层共享同一设计语言 |
| **从属** | 弹层属于页面，不是浮在页面上方的独立窗口 |
| **动画** | 入场有方向感（Drawer 从右滑入，Sheet 从下微升，Modal 从锚点 scale） |

### 2.2 统一弹层规范

```
弹层 Surface:
  background: var(--surface-panel-elevated)   -- 保持略高于 base
  border: 1px solid var(--border-default)      -- 统一边框
  border-radius: var(--radius-12)              -- 统一圆角
  box-shadow: 0 8px 32px oklch(0 0 0 / 0.25)  -- 克制的阴影

遮罩层:
  background: oklch(0 0 0 / 0.4)              -- 40% 黑色遮罩
  backdrop-filter: blur(4px)                   -- 4px 模糊

入场动画:
  Drawer: translateX(100%) → translateX(0), 300ms ease-decelerate
  Sheet: translateY(20px) + opacity(0) → translateY(0) + opacity(1), 200ms ease-decelerate
  Modal: scale(0.95) + opacity(0) → scale(1) + opacity(1), 200ms ease-decelerate
  Popover: scale(0.96) + opacity(0) → scale(1) + opacity(1), 150ms ease-decelerate

出场动画:
  所有类型: 反向动画，duration × 0.6（退出比进入快 40%）
```

### 2.3 Drawer vs Sheet vs Modal 使用场景重申

| 组件 | 场景 | 大小 | 遮罩 | 动画方向 |
|------|------|------|------|---------|
| **Drawer** | 对象详情、比较、参数审查、快速检查 | 宽 360-480px | 半遮罩 | 从右滑入 |
| **Sheet** | 设置面板、筛选配置、多步操作 | 宽 480-640px | 半遮罩 | 从中心微升 |
| **Modal** | 确认、警告、破坏性操作、发布确认 | 宽 400-480px | 全遮罩 | 从锚点缩放 |
| **Popover** | 小范围设置、列配置、快速预览 | 宽 240-320px | 无遮罩 | 从锚点缩放 |
| **Bottom Tray** | 日志、trace、dry run | 全宽，高可调 | 无遮罩 | 从底部展开 |

---

## 3. 综合改进路线图

### Phase 1: 紧急修复（1-2 天）— 消除对齐障碍

| # | 任务 | 影响 |
|---|------|------|
| 1.1 | 提取 shell-hub / shell-agent 到 layout-base.css | P0-1 |
| 1.2 | 提取弹层子组件 CSS 到共享层 | P0-2 |
| 1.3 | 修复 `.data-table` 密度变量绕过（4 页面） | P0-3 |
| 1.4 | 补充 `.overlay-modal` CSS 定义 | P0-4 |
| 1.5 | 统一 portfolio 弹层命名为 overlay-* | P0-5 |

### Phase 2: 设计系统统一（2-3 天）— 提升一致性

| # | 任务 | 影响 |
|---|------|------|
| 2.1 | 统一 Button 体系到 layout-base.css | P1-2 |
| 2.2 | 统一折叠/展开机制（一种实现方式） | P1-7 |
| 2.3 | 统一 Toast 组件 | P1-8 |
| 2.4 | 删除页面级 `.panel` / `.data-table` 重写 | P1-4 |
| 2.5 | 统一 token 导入模板 | P1-5 |
| 2.6 | AI 两页迁移到新式 View Preferences | P1-3 |
| 2.7 | 补齐 portfolio 的 noise/ambient | P2-7 |

### Phase 3: 主题/密度增强（1-2 天）— 跟上业界标准

| # | 任务 | 影响 |
|---|------|------|
| 3.1 | 添加 system 主题选项（三态） | P1-6 |
| 3.2 | 主题切换过渡动画 | P1-6 |
| 3.3 | 密度档位重命名（消除语义错位） | P1-9 |
| 3.4 | 移除 dense 档的 font-delta | 密度 |
| 3.5 | View Preferences 简化为 Popover | 繁琐 |
| 3.6 | Light mode atmosphere 统一覆盖 | P1-1 |

### Phase 4: 交互增强（3-4 天）— 提升专家体验

| # | 任务 | 影响 |
|---|------|------|
| 4.1 | 弹层入场/出场动画 | P1 |
| 4.2 | 折叠/展开过渡动画 | P1 |
| 4.3 | 弹层视觉对齐 Graphite Studio | P1 |
| 4.4 | 数值变化动画（AnimatedNumber） | 语义 |
| 4.5 | 状态突变视觉反馈 | 语义 |
| 4.6 | 选中对象联动高亮 | 语义 |

### Phase 5: 高级功能（2-3 天）— 可调整面板

| # | 任务 | 影响 |
|---|------|------|
| 5.1 | 引入 react-resizable-panels | 可调整 |
| 5.2 | Analytical Overview 面板可调整 | 可调整 |
| 5.3 | Studio 三栏可调整 | 可调整 |
| 5.4 | Bottom Tray 高度可拖拽调整 | 可调整 |
| 5.5 | 面板布局持久化 | 可调整 |

### Phase 6: 品质打磨（1-2 天）— P2 清理

| # | 任务 | 影响 |
|---|------|------|
| 6.1 | 硬编码 border-radius → token | P2-1 |
| 6.2 | 删除重复 skip-link / sr-only 定义 | P2-2/3 |
| 6.3 | Sidebar 折叠 JS 提取到共享 | P2-4 |
| 6.4 | collapse-count 模式共享化 | P2-5 |
| 6.5 | Disclosure 箭头样式统一 | P2-6 |
| 6.6 | 动画 Token 定义 | 基础设施 |

**总工作量估算**: 10-16 天（单人），可并行压缩到 5-8 天

---

## 4. 依赖关系图

```
Phase 1 (紧急修复)
  ↓
Phase 2 (设计系统统一) ←→ Phase 3 (主题/密度增强)
  ↓                           ↓
Phase 4 (交互增强)       Phase 5 (可调整面板)
  ↓
Phase 6 (品质打磨)
```

- Phase 1 是所有后续工作的基础（必须先完成）
- Phase 2 和 Phase 3 可以并行
- Phase 4 依赖 Phase 2（弹层统一后才能加动画）
- Phase 5 独立于 Phase 4，可并行
- Phase 6 最后做

---

## 5. 与现有规范的对齐检查

### 5.1 Shell Chrome Contract 对齐

| 合同条款 | 当前状态 | 建议 |
|---------|---------|------|
| Theme/Density 是视图偏好，放 account 菜单 | 27/29 页一致 | 修复 AI 2 页 |
| Rail 不承载 theme/density | 一致 | 保持 |
| Header 三段式 | 一致 | 保持 |
| 动作归属矩阵 | 基本一致 | 保持 |
| 专家入口合同 | 部分页面满足 | 补齐 |

### 5.2 组件规范对齐

| 规范条款 | 当前状态 | 建议 |
|---------|---------|------|
| Panel 6 类分类 | 部分页面混合使用 | 统一 panel 类型语义 |
| 反馈 6 级分级 | 有定义但动画缺失 | Phase 4 补齐 |
| Drawer vs Side Sheet 区分 | 使用但无动画 | Phase 4 补齐 |
| AI/Agent 语气 | agent-console 已遵循 | 保持 |
| 跨页共享组件合同 | Bottom Tray 有定义 | 补齐其他共享组件 |

### 5.3 交互状态规范对齐

| 规范条款 | 当前状态 | 建议 |
|---------|---------|------|
| 15 种状态 | 有定义但视觉反馈不完整 | Phase 4 补齐 |
| 反馈五级分级 | 有定义但无动画 | Phase 4 补齐 |
| 折叠面板空间预算 | Bottom Tray 有实现 | 其他折叠面板补齐 |
| Bottom Tray 三态 | 4 页实现 | 保持并统一 |
| 高风险确认 | 部分页面有实现 | 补齐 |
