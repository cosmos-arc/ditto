# Instrument Hub Design Cycle Review

**目标**: `/ditto-design-cycle page-instrument-hub.html --iterate --goal 10 --max-rounds 100 --level best`
**日期**: 2026-04-26
**对象**: `docs/designs/specs/prototypes/page-instrument-hub.html`
**结果**: 9.7 / 10（CSS 原型阶段上限区间，未标记 done）

## 结论

Instrument Hub 已从「高分但门禁不可用」推进到可稳定审查的 best 级原型：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿
- 默认视图无外链依赖、无 JS 崩溃、无 fixed status bar 遮挡
- Object Shell DOM 结构恢复，门禁可识别 shell/header/main/sidebar
- Compact 视口改为指标后优先呈现行情图，符合对象详情页的判断路径
- 弹层画廊与 State Coverage Index 对齐：6/6 overlays
- 静态审计：0 inline style、0 external script、0 duplicate id、0 `oklch()` 函数引用

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.7 | 去除外链和运行时崩溃；固定状态栏改为 shell 内 status row；无 prototype tool 污染 |
| 一致性 | 9.7 | Object Shell / contract slot / token 色彩收敛；chart 容器 ID 去重 |
| 高级感 | 9.6 | 本地图表 SVG、K 线/成交量/MA 线与品牌线融合；材质层保持克制 |
| 品牌方向 | 9.6 | 金融终端密度、状态栏、右侧信号与对象中心路径保持一致 |
| 信息效率 | 9.7 | Compact 首屏可见价格图；overlay/state 覆盖完整；关键数值截图稳定 |
| 综合气质 | 9.7 | P0/P1 为 0，CSS 原型阶段已接近天花板 |

## 关键修改

1. 修复 Rail DOM 多余闭合标签，避免浏览器把 header/meta/main 修复到 shell 外层。
2. 给根节点添加 `object-shell shell-hub`，给 sidebar 添加 `data-contract-slot="sidebar"`。
3. 将 status bar 纳入 shell grid 的 `status` 行，移除 fixed 遮挡风险。
4. 移除 `unpkg` lightweight-charts 外链，改为本地 deterministic SVG market chart。
5. 去重 `tv-chart-container` ID，改为两个稳定 chart container。
6. Compact 低高度视口下重排概览：metrics → chart → rank → flow。
7. 将 header ticker 改为静态目标值，并把 counter duration 压到 1ms，保证截图稳定。
8. 补齐 overlays gallery 中缺失的 Floating Toolbar card。
9. 收敛硬编码色值与阴影到 token / `color-mix()`。

## 验证

```bash
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-instrument-hub.html --out-dir test-results/ditto-design-cycle-gates/instrument-hub-final
```

结果：

- Status: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/instrument-hub-final/page-instrument-hub.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/instrument-hub-final/page-instrument-hub.html-VP-COMPACT.png`

三区抽查：

- `#states-gallery`: 38 cards
- `#overlays-gallery`: 6 cards

静态审计：

- inline styles: 0
- external scripts: 0
- duplicate ids: 0
- `oklch()` function refs: 0

## 未达 10 的原因

目标 10 在当前 HTML/CSS 静态原型阶段不宜虚报。剩余差距主要来自：

- 图表是静态 SVG 渲染，缺少真实十字线、拖拽缩放、指标开关等高保真交互。
- Sidebar 还未按当前 tab 做上下文联动展开/折叠。
- 真实数据刷新、stale 衰减和交易时段语义仍是 mock 层表现。

后续若进入 React 实现或增强原型交互层，才有合理空间冲击 9.8-10。

## Benchmark Notes

- TradingView Advanced Charts: chart toolbar, watchlist/details/news as chart-adjacent UI patterns.
- Linear UI refresh: information-dense products should reduce visual noise while preserving hierarchy and density.
- Bloomberg Terminal: object-centered workflows require dense, immediate access to data, analytics, and communication context.
