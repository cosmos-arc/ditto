# 原型 5 页面 P0 修复计划

> 审查日期: 2026-04-03
> 触发: 全量三区架构迁移后发现多个页面样式损坏

## 审查范围

page-regime-monitor / page-strategy-studio / page-signals-inbox / page-risk-center / page-ai-overview

## P0 阻断性问题（主内容不可见）

### 1. page-regime-monitor.html

**症状**: 主内容区域 + 右侧栏完全黑色空白，仅 rail/header/scope-strip/tab-bar/status-bar 可见

**根因 A — grid-area 未分配**:
- `shell-regime` 使用 named grid areas: `rail / header / strip / main / activity`
- 但 `regime-tab-bar` 和 `tab-panels` 作为 shell-regime 的直接子元素，没有声明 `grid-area`
- 浏览器 auto-placement 将 tab-bar 放入 main area（但内容为空）、tab-panels 放入错误位置

**根因 B — `:has()` 选择器路径错误**:
- CSS 写的是 `.tab-group:has(#regime-status:checked) [data-panel="regime-status"] { display: block }`
- 但 `.tab-group`（含 radios + labels）和 `[data-panel]`（在 tab-panels 内）是 **兄弟关系**
- `:has()` 无法匹配兄弟的后代，所有 tab-panel 保持 `display: none`

**修复方案**:
- 方案 A: 将 tab radios + labels + panels 放入同一个 `.tab-group` 容器（推荐，与其他页面一致）
- 方案 B: 改用 `.shell-regime:has(#regime-status:checked) [data-panel="regime-status"]` 选择器
- 确保 main-content / activity-stack 是 shell-regime 的直接 grid child

**涉及行**: HTML ~L800-1200, CSS ~L650-710

---

### 2. page-risk-center.html

**症状**: 主内容区域完全空白

**根因 A — DOM 嵌套错误**:
- proto-nav（zone navigation radios + nav + default-view section）被嵌套在第一个 `rail-icon[title="Home"]` 的 div 内
- `<section id="default-view">` 开在第 ~812 行（rail-icon div 内），但 `</section>` 在第 ~1638 行（rail-icon 早已关闭）
- 导致 DOM 结构严重错乱

**根因 B — grid 子元素嵌套过深**:
- `main-content` 嵌套在 `tab-panels > tab-panel > main-content` 中
- `activity-stack` 嵌套在 `tab-panel > main-content > risk-main-layout > activity-stack`
- `analysis-band` 也在 tab-panel 内
- CSS `.shell-analytical .main-content { grid-area: main }` 无效，因为 grid-area 只对 grid container 的直接子元素生效

**修复方案**:
1. 将 proto-nav + zone radios + default-view section 从 rail-icon div 中提取出来，放到 shell-analytical 的正确层级
2. 将 main-content / activity-stack / analysis-band 提升为 shell-analytical 的直接子元素
3. tab-panels 只包含内容，不包含需要 grid-area 的布局元素

**涉及行**: HTML ~L800-820 (嵌套), ~L950-1200 (grid 子元素), CSS ~L600-680

---

### 3. page-signals-inbox.html

**症状**: Shell 三栏变为近似等分（37/749/750），数据表格溢出 485px

**根因 A — 缺失 CSS token 文件**:
- `<head>` 中未加载 `tokens-shell.css`（或 `--shell-signals-detail-width` 未定义）
- `.shell-signals { grid-template-columns: var(--shell-rail-width) 1fr var(--shell-signals-detail-width) }`
- 第三个值解析为空字符串 → 整个 `grid-template-columns` 属性无效 → 回退 `none`

**根因 B — tab-panel flex-direction 错误**:
- `tab-panel` 使用 `flex-direction: row`，将 signals-header（434px）与 table-wrap 并排放置
- table-wrap 宽度收缩为 0，但内部 `data-table` 仍渲染 800px
- 修复: `flex-direction: column`

**修复方案**:
1. 在 `<head>` tokens 层添加 `shared/tokens-shell.css`，或为 `--shell-signals-detail-width` 添加 fallback `var(--shell-signals-detail-width, 380px)`
2. 修正 `tab-panel` 的 `flex-direction: column`
3. `data-table` 添加 `table-layout: fixed; width: 100%`

**涉及行**: HTML `<head>` tokens 层, CSS ~L700-750

---

## P1 建议修复（非阻断但影响体验）

| 页面 | 问题 | 修复 |
|------|------|------|
| regime-monitor | Overlays 仅 1 个 | 补充 Regime 切换通知 Toast、策略调整确认 Dialog |
| strategy-studio | Tab Panel 缺 `display: none` 兜底 | 给 `.tab-panel:not(:first-child)` 或非默认 panel 添加显式隐藏 |
| strategy-studio | Stale 状态用 inline style | 抽取 `.state-stale` 共享 class |
| signals-inbox | Scope Tab 无激活态 | 检查 `:has()` 选择器或添加 `.active` class |
| signals-inbox | Gallery 卡片单列布局 | 修正 `grid-template-columns: repeat(auto-fill, minmax(296px, 1fr))` |
| signals-inbox | Overlay 预览缺关闭按钮 | 补充 `.overlay-close` 到 gallery 预览中 |
| risk-center | 5 个空白占位 div 未清理 | 删除 State Variants 注释后的空 div |
| ai-overview | 44 处 inline style | 分批抽取为语义 class |
| ai-overview | Actions Bar 窄视口截断 | 添加 `min-width` 或 `overflow: hidden` |

## 执行优先级

1. **P0 #1** — regime-monitor（grid-area + `:has()` 选择器）
2. **P0 #2** — risk-center（DOM 嵌套 + grid 子元素提升）
3. **P0 #3** — signals-inbox（缺失 token + flex-direction）
4. P1 批量修复
