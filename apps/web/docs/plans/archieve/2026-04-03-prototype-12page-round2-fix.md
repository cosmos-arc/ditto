# 原型 12 页面第二轮修复计划

> 创建: 2026-04-03
> 触发: 三区架构迁移 + 第一轮 P0 修复后的遗留样式/交互问题
> 前置: 2026-04-03-prototype-5page-fix.md（P0 阻断已修复）

## 概述

12 个页面存在样式扭曲、画廊无样式、tab 不可切换、布局遮挡、面板过窄等问题。
分为三个 Tier：系统性修复 → 页面级修复 → 调研项（侧边栏交互重设计）。

## 技术方案

### 发现的系统性根因

1. **Gallery group title CSS class mismatch** — `prototype-toggles.css` 定义 `.gallery-group__title`，但所有 HTML 文件使用 `.gallery-group__label`，导致全部画廊分组标题条无样式
2. **Tab 使用 JS 依赖模式** — 部分 tab 用 class-based `.active` 切换，需转为纯 CSS radio + `:has()` 模式
3. **侧边栏信息密度** — 320px 面板内信息过多需要滚动，需产品层面重新规划（单独调研）

---

## 任务清单

### Tier 0: 浏览器逐页确认 `[M]`

- [ ] Task: 用 Chrome DevTools 逐页截图确认 12 个问题的当前状态
  - 验收: 每个问题有截图 + 精准定位（CSS 选择器 / HTML 行号）
  - 文件: 全部 12 个 HTML + `shared/prototype-toggles.css`

---

### Tier 1: 系统性修复（影响所有画廊页面）

- [ ] Task: 修复 gallery group title CSS class mismatch `[S]`
  - 验收: 所有页面的状态画廊/弹层画廊分组标题条有深色背景、padding、底边框
  - 文件: `shared/prototype-toggles.css` line 151
  - 修改: `.gallery-group__title` → `.gallery-group__label`

---

### Tier 2: 页面级修复

#### T2-1: page-platform — tushare 进度条渐变化 `[S]`

- [ ] Task: resource-bar-fill 改为渐变填充与 quota-bar-fill 一致 `[S]`
  - 验收: 资源条（API 配额/CPU/Memory/Disk）显示渐变填充；critical 状态有轻量脉冲/饱和度提示
  - 文件: `page-platform.html` CSS lines ~562-564
  - 修改: `.resource-bar-fill.{ok,warn,critical}` 改为 `linear-gradient()` 填充

#### T2-2: page-instrument-hub — 底部 tab 不可切换 `[M]`

- [ ] Task: 底部 tab 转为 radio + `:has()` 纯 CSS 模式 `[M]`
  - 验收: 底部三个 tab（最近事件/公告/关联研究）可点击切换，对应内容面板显示
  - 文件: `page-instrument-hub.html` CSS ~L1122, HTML ~L2492
  - 修改:
    1. `.bottom-tabs` 内添加 3 个 `<input type="radio" name="bottom-tab">`
    2. `<div class="bottom-tab">` → `<label for="...">`
    3. 添加 `:has()` 激活规则替换 `.bottom-tab.active`
    4. `.bottom-content` 拆分为 3 个 `data-panel` div

#### T2-3: page-research — 底部 bar 遮挡 + tab + 右侧遮挡 `[L]`

- [ ] Task: 修复 analysis band tab 切换 + 布局遮挡 `[L]`
  - 验收:
    - 分析 band 内 4 个 tab（IC 分析/宽度/相关性/笔记）可切换
    - 底部分析 band 不遮挡主内容区
    - 右侧 bar 底部内容完整可滚动
  - 文件: `page-research.html` CSS ~L638, HTML ~L1620
  - 修改:
    1. 分析 band tab（`<span>`）转为 radio + `<label>` + `:has()` 模式
    2. 检查 `shell-analytical` grid row 分配，确认 main 有 `1fr` 充分空间
    3. 确认右侧 activity stack `overflow-y: auto` + `max-height` 计算

#### T2-4: page-markets-intelligence — 大片空白 + tab 无效 `[M]`

- [ ] Task: 修复右侧 rail 不拉伸 + tab 激活验证 `[M]`
  - 验收:
    - 无大面积空白区域
    - 5 个分类 tab（资金面/宏观/基本面/新闻/资金流）可切换
    - 右侧 rail 内容完整
  - 文件: `page-markets-intelligence.html` CSS ~L392
  - 修改:
    1. `.intel-right-rail` 移除 `align-self: start`（改为 `stretch` 或移除）
    2. 验证 tab `:has()` 激活规则完整性（已用 radio 模式，可能只需 CSS 调整）
    3. 确保 `.intel-workspace` 高度约束正确

#### T2-5: page-ai-copilot — 对话框不可见 `[M]`

- [ ] Task: 修复对话区域不可见/不可滚动 `[M]`
  - 验收: 对话区域显示完整消息线程，可向下滚动查看历史
  - 文件: `page-ai-copilot.html`
  - 修改:
    1. 检查 `.copilot-conversation` 高度约束和 overflow 设置
    2. 确保 `.conversation-body` 有 `flex: 1; overflow-y: auto; min-height: 0;`
    3. 检查 shell grid 行分配，确保 conversation 区域获得 `1fr` 空间

#### T2-6: page-agent-console — 布局扭曲 + hover 异常 `[M]`

- [ ] Task: 修复布局拥挤 + hover 布局跳动 `[M]`
  - 验收: 卡片间距均匀，hover 效果平滑无布局重排
  - 文件: `page-agent-console.html`
  - 修改:
    1. 检查 agent 卡片 grid gap/spacing
    2. 确保 hover 不改变 margin/border-width（用 box-shadow / opacity 代替）

#### T2-7: page-orders-ledger — 右侧空白 `[S]`

- [ ] Task: 修复 trace panel 右侧空白 `[S]`
  - 验收: 右侧 340px 区域显示订单追踪内容（时间线/费用/滑点/路由）
  - 文件: `page-orders-ledger.html`
  - 修改:
    1. 确认 `.order-trace` 有 `background`/`overflow-y: auto`/`min-height: 0`
    2. 检查内容是否被颜色/对比度问题隐藏

#### T2-8: page-risk-center — 图标交错 + 空白 `[S]`

- [ ] Task: 修复图标布局交错和空白区域 `[S]`
  - 验收: 图标对齐整齐，无异常空白
  - 文件: `page-risk-center.html`
  - 修改: 浏览器确认后精确定位（疑似 flex alignment 或 grid placement 问题）

#### T2-9: page-strategy-studio — 画廊验证 `[S]`

- [ ] Task: 验证 Fix 0 (gallery class) 后 strategy-studio 画廊正常 `[S]`
  - 验收: 状态画廊 6 组 21 卡片全部有样式；弹层画廊 5 卡片 overlay 渲染正确
  - 文件: `page-strategy-studio.html`
  - 修改: 如 Fix 0 后仍有问题再单独处理

#### T2-10: page-signals-inbox — 画廊验证 `[S]`

- [ ] Task: 验证 Fix 0 后 signals-inbox 画廊正常 `[S]`
  - 验收: 状态画廊 5 组 9 卡片全部有样式；弹层画廊 3 卡片正常
  - 文件: `page-signals-inbox.html`
  - 修改: 如有 inline style 残留的 state cards 需统一为标准 class

#### T2-11: page-ai-overview — 画廊验证 `[S]`

- [ ] Task: 验证 Fix 0 后 ai-overview 画廊正常 `[S]`
  - 验收: 状态画廊 3 组 9 卡片全部有样式；弹层画廊 toast 卡片渲染正确
  - 文件: `page-ai-overview.html`
  - 修改: 确认 `.toast-card` 等 CSS 定义存在（可能在 page-local `<style>` 中）

---

### Tier 3: 调研项（单独规划，不在本轮修复范围）

- [ ] Task: 调研 page-markets-screener 右侧面板交互重设计 `[XL]`
  - 问题: 320px 面板内信息密度高，需要内部滚动
  - 需要: 调研哪些信息直接展示、哪些通过交互获取
  - 输出: 独立设计文档

- [ ] Task: 调研 page-instrument-hub 右侧面板交互重设计 `[XL]`
  - 问题: 同上信息视窗过小
  - 需要: 面板内容分层和交互方式调研
  - 输出: 独立设计文档

---

## 执行优先级

| 序号 | Task | 复杂度 | 依赖 | 风险 |
|------|------|--------|------|------|
| 1 | Tier 0: 浏览器确认 | M | 无 | 低 |
| 2 | T1: Gallery class fix | S | 无 | 低 — 一行 CSS |
| 3 | T2-1: Platform 进度条 | S | Tier 0 | 低 |
| 4 | T2-7: Orders ledger 空白 | S | Tier 0 | 低 |
| 5 | T2-8: Risk center 图标 | S | Tier 0 | 中 |
| 6 | T2-9/10/11: 画廊验证 | S×3 | T1 | 低 |
| 7 | T2-2: Hub 底部 tab | M | Tier 0 | 中 — HTML 重构 |
| 8 | T2-4: Intelligence 空白 | M | Tier 0 | 中 |
| 9 | T2-5: Copilot 对话框 | M | Tier 0 | 中 |
| 10 | T2-6: Agent console | M | Tier 0 | 中 |
| 11 | T2-3: Research 多问题 | L | Tier 0 | 高 — 多处修改 |

## 关键文件

| 文件 | 修改类型 |
|------|---------|
| `shared/prototype-toggles.css` | L151: `.gallery-group__title` → `.gallery-group__label` |
| `page-platform.html` | CSS: `.resource-bar-fill` 渐变 |
| `page-instrument-hub.html` | HTML: 底部 tab radio 化 + CSS: `:has()` 规则 |
| `page-research.html` | HTML: 分析 band tab radio 化 + CSS: 布局修复 |
| `page-markets-intelligence.html` | CSS: 右侧 rail 高度 + tab 验证 |
| `page-ai-copilot.html` | CSS: 对话区 overflow/height |
| `page-agent-console.html` | CSS: 间距 + hover 效果 |
| `page-orders-ledger.html` | CSS: trace panel 渲染 |
| `page-risk-center.html` | CSS: 图标布局 |
| `page-strategy-studio.html` | 验证（依赖 T1） |
| `page-signals-inbox.html` | 验证 + 可选 inline style 清理 |
| `page-ai-overview.html` | 验证（依赖 T1） |

## 验证策略

修复完成后逐页浏览器验证：
1. 所有页面画廊分组标题正常（深色背景 + padding + 底边框）
2. 所有 tab 可点击切换（Hub 底部、Research 分析 band、Intelligence 分类）
3. 布局无遮挡、无空白、无布局跳动
4. hover 效果平滑无异常
5. 右侧面板/侧边栏内容完整可滚动
6. 进度条渐变风格统一
