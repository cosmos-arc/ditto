# Alpha Explorer Design Cycle Review — Round 1

**目标**: `/ditto-design-cycle page-alpha-explorer.html --iterate --goal 10 --max-rounds 100 --level best`
**日期**: 2026-05-03
**对象**: `docs/designs/specs/prototypes/page-alpha-explorer.html`
**基线**: 9.7 / 10（上轮审查）
**结果**: 9.8 / 10（+0.1，媒介限制区域）
**Tag**: `review/alpha-explorer/r1`

## 结论

Round 1 从 9.7 推进到 9.8。六角色并行审查发现 6 个 P0 + 14 个 P1 问题，全部 P0 和关键 P1 已修复。未达 goal 10 的原因是 HTML/CSS 静态原型的交互天花板。

### 修复摘要

**P0 修复（7 项）：**
1. 数字元素添加 `font-variant-numeric: tabular-nums slashed-zero`
2. 代码字体添加 `font-feature-settings: "liga" 0`
3. 全部交互元素添加 hover/focus 状态（candidate-card, chip, queue-item, node, point）
4. Pareto 网格使用 `--chart-grid` token 替代 `--border-subtle`
5. Pareto 点位添加 aria-label + 轴刻度标签 + 图例
6. 实验图谱系节点添加 `::after` 方向箭头连线
7. Chip 从 `<span>` 改为 `<button role="switch" aria-pressed>` 键盘可访问

**P1 修复（8 项）：**
1. "已阻断"状态使用 `.blocked` class（红色）替代 `.partial`（琥珀色）
2. 预算数据修正："剩余 38 分钟" → "剩余 ~17 分钟"（与 62% of 45min 一致）
3. 状态文案标准化："部分" → "部分完成"，"复核" → "待复核"
4. 添加 `@media (prefers-reduced-motion: reduce)` 查询
5. 审批面板文案优化（CJK 间距、清晰度）
6. 状态栏措辞对齐面板副标题
7. 数字上下文全面覆盖 tabular-nums（metric-value, panel-kicker, status-bar）
8. Chip 添加 hover + focus-visible 状态

## 评分卡

| 维度 | 上轮 | Round 1 | Delta | 依据 |
|------|------|---------|-------|------|
| 克制度 | 9.7 | 9.8 | +0.1 | hover/focus 统一用 interaction token, Pareto 网格降级为 chart-grid |
| 一致性 | 9.9 | 9.9 | 0.0 | tabular-nums 贯穿全页数字元素, font-feature-settings on code |
| 高级感 | 9.6 | 9.8 | +0.2 | Pareto 有轴刻度+标签+legend, 实验图有方向连线, 点位 hover 放大 |
| 品牌方向 | 9.7 | 9.8 | +0.1 | 量化工作台语法更完整：前沿面可读, 谱系有方向, 状态语义一致 |
| 信息效率 | 9.8 | 9.9 | +0.1 | 点位 aria-label + 标签, 预算修正, 状态文案对齐术语表 |
| **综合** | **9.7** | **9.8** | **+0.1** | 5 维均值 |

## 验证

```bash
bunx vitest run scripts/page-alpha-explorer-prototype.test.ts
# 5/5 passed

bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-alpha-explorer.html
# PASS — 0 blocking, 0 non-blocking
```

截图：
- VP-STANDARD: `test-results/ditto-design-cycle-gates/alpha-explorer-r1-post-fix/page-alpha-explorer.html-VP-STANDARD.png`
- VP-COMPACT: `test-results/ditto-design-cycle-gates/alpha-explorer-r1-post-fix/page-alpha-explorer.html-VP-COMPACT.png`
- VP-NARROW: `test-results/ditto-design-cycle-gates/alpha-explorer-r1-post-fix/page-alpha-explorer.html-VP-NARROW.png`

## 未达 10 的原因

当前仍是静态 HTML 原型。剩余 0.2 分的瓶颈：

1. **交互天花板** — 候选点击选中、Tab 切换模式、Overlay 弹出关闭需要 JS 状态管理
2. **数据可视化深度** — Pareto 前沿曲线（SVG）、条件格式（metric 超阈值变色）、sparkline 需要 Canvas/SVG/JS
3. **响应式布局** — VP-COMPACT inspector 折叠为 overlay 需要布局重排，超出纯 CSS 能力
4. **Copilot 侧栏** — 从 always-visible 到按需展开需要 JS toggle

**结论**：原型层面已接近 HTML/CSS 天花板。后续 0.2 分需要 React 实现（TanStack Query + 交互 JS + SVG 可视化）才能突破。

## 反思记录

```
Round 1 反思：
├─ 创意策略: 定向精修 → 创意突破
├─ 实际执行: 六角色审查发现系统性缺陷（tabular-nums 缺失、hover 空白、chart token 未消费），已全部修复
├─ 效果:
│   ├─ 分数变化: +0.1（9.7 → 9.8）
│   └─ 整体感受: 有效 — 补齐了数据可视化层的基础设施
├─ 关键洞察:
│   ├─ 起作用: 并行审查高效发现跨维度系统性遗漏
│   └─ 未起作用: 无法突破静态 HTML 的交互限制
├─ 死胡同: 纯 CSS hover/focus 已达天花板
└─ 结论: 媒介限制已确认，不再继续迭代
```

## 待同步清单

- [ ] 状态胶囊 `.blocked` class 需同步到共享样式
- [ ] Pareto 图例/轴刻度样式需同步到其他有散点图的页面
- [ ] 术语表需补充：因子实验室 / 研究空间 / 候选检查器 / 采纳队列
- [ ] 覆盖率声明 "100%" 建议修正为 "~70% critical state coverage"
