# Risk Center Design Cycle Review

**目标**: `/ditto-design-cycle page-risk-center.html --iterate --goal 10 --max-rounds 100 --level best`  
**日期**: 2026-04-26  
**对象**: `docs/designs/specs/prototypes/page-risk-center.html`  
**结果**: 9.7 / 10（CSS 原型阶段上限区间，未标记 done）

## 结论

本轮将 Risk Center 从「视觉高分但结构门禁失败」推进到可稳定验收的 best 级原型：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿
- `risk-gauges`、tabs、panel、status bar 全部进入 shell grid，避免自动布局漂移
- 右侧活动栈补齐 `data-contract-slot="right-rail"`，合同槽与门禁语义一致
- status bar 从 fixed 改为 shell 内状态行，不再覆盖内容
- 默认 summary panel 填满可用视口，主图区域获得更稳定的信息密度
- 首屏 ticker/counter 动画移除，截图数值保持确定性
- 静态审计：0 inline style、0 duplicate id、状态画廊 20 cards、弹层画廊 3 cards

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.7 | 去除 fixed 遮挡与底部漂移；图表/热力图/仪表带保持低噪声密度 |
| 一致性 | 9.7 | Shell grid、contract slot、manifest 与门禁脚本识别口径一致 |
| 高级感 | 9.6 | 风险仪表、趋势图、热力矩阵形成专业终端语境，动效回归确定性 |
| 品牌方向 | 9.7 | Graphite Studio 暗色金融终端、A 股风控语义与 trading 域保持一致 |
| 信息效率 | 9.7 | Compact 首屏可见关键 VaR/回撤/集中度路径，右侧风险状态持续可扫视 |
| 综合气质 | 9.7 | P0/P1 为 0，CSS 静态原型阶段已接近天花板 |

## 关键修改

1. 修复 shell secondary 门禁：给活动栈添加 `data-contract-slot="right-rail"`。
2. 扩展 risk-center shell grid：新增 `gauges` 与 `status` 行。
3. 将 status bar 移入 `.shell-analytical`，由 fixed 改为 grid flow 内相对定位。
4. 将 `risk-gauges` 绑定到独立 grid area，避免被自动布局挤到页面底部。
5. 将 `.tab-panels` 改为可滚动区域，并重置 tab panel 内部 `main-content` / `analysis-band` 的 inherited grid-area。
6. 默认 summary panel 改为主图 + analysis band 两行布局，提升标准视口空间利用率。
7. 移除首屏 `data-ticker` 与压力测试 `data-counter`，保证截图不会捕捉动画中间值。
8. 同步 `.edition-manifest.json` 中 risk-center 的 score、JS module 计数与 note。

## 验证

```bash
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-risk-center.html --out-dir test-results/ditto-design-cycle-gates/risk-center-final
```

结果：

- Status: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/risk-center-final/page-risk-center.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/risk-center-final/page-risk-center.html-VP-COMPACT.png`

静态审计：

- inline styles: 0
- duplicate ids: 0
- default contract slots: 6
- state gallery cards: 20
- overlay gallery cards: 3
- default-view `data-ticker` / `data-counter`: 0

## 未达 10 的原因

目标 10 在当前 HTML/CSS 静态原型阶段不宜虚报。剩余差距主要来自：

- 图表仍是 CSS/SVG 静态表达，缺少真实十字线、缩放、序列切换和风险阈值编辑反馈。
- 右侧活动栈是局部 tab，不会随主 tab 与事件选中状态做真实上下文联动。
- 风险模型刷新、实时数据老化、组合切换后的重算仍是 mock 层语义。

## Benchmark Notes

- Bloomberg PORT / Portfolio Analytics: 风险分析应支持自定义 dashboard、并行组合视图和高效多组合分析。
- TradingView Heatmaps: 热力图适合以大小、分组与颜色快速表达趋势、波动或风险贡献。
