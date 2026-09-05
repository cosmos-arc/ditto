# Markets Intelligence Design Cycle Review

**目标**: `/ditto-design-cycle page-markets-intelligence.html --iterate --goal 10 --max-rounds 100 --level best`
**日期**: 2026-04-26
**对象**: `docs/designs/specs/prototypes/page-markets-intelligence.html`
**结果**: 9.7 / 10（CSS 原型阶段上限区间，未标记 done）

## 结论

本轮将 Markets Intelligence 从「视觉高分但门禁不可评分」推进到可稳定验收的 best 级原型：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿
- Shell root 补齐 `intel-shell`，门禁可识别 grid shell
- Right Rail 与 Analysis Band 增加合同槽，结构与 page contract 语义一致
- Shell 改为 100vh 内部滚动，Compact 视口不再截断 key container
- Analysis Band 从重复 5 段收敛为趋势 / 对比 / 行动窗口 3 段
- 板块热力图补齐 Size / Color / Scope 读图规则与 5 档色阶
- 资金流向表增加 `data-flow-direction` 与 ▲ / ▼，避免涨跌判断只依赖颜色
- 默认视图移除 `data-ticker` / `data-counter`，截图数值保持确定性

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.7 | 修复布局门禁，Analysis Band 去重，热力图说明保持低噪声 |
| 一致性 | 9.7 | Shell / right rail / analysis slot 与门禁和 manifest 口径一致 |
| 高级感 | 9.6 | 热力图具备专业读图层，资金方向语义更接近终端工作台 |
| 品牌方向 | 9.7 | 保持 Graphite Studio 暗色金融终端密度和市场情报语境 |
| 信息效率 | 9.7 | 首屏可读出资金方向、板块排序、强弱色阶、关联标的与行动窗口 |
| 综合气质 | 9.7 | P0/P1 为 0，CSS 静态原型阶段已接近天花板 |

## 验证

```bash
bun run test:run scripts/page-markets-intelligence-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-markets-intelligence.html --out-dir test-results/ditto-design-cycle-gates/markets-intelligence-final
```

结果：

- `scripts/page-markets-intelligence-prototype.test.ts`: 4 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/markets-intelligence-final/page-markets-intelligence.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/markets-intelligence-final/page-markets-intelligence.html-VP-COMPACT.png`

静态审计：

- inline styles: 0
- default-view `data-ticker` / `data-counter`: 0
- duplicate ids: 0
- overlays: 5 declared, 5 covered in State Coverage Index

## Benchmark Notes

- TradingView Heatmaps: 参考 size / color / group / legend 的读图方式。<https://www.tradingview.com/support/solutions/43000766446-tradingview-heatmaps-from-global-trends-to-details/>
- Bloomberg Terminal: 参考 Launchpad / news analytics / alerting tools 形成市场监控与情报行动工作流。<https://professional.bloomberg.com/products/bloomberg-terminal/>

## R5 相关性矩阵补强

- 为 `标的相关性矩阵` 增加强相关焦点与 -1/+1 色阶。
- 自相关对角线改为中性色，避免 `1.00` 抢走真实联动信号。
- 强相关单元格增加边界和更明确的色阶，弱相关单元格保留但降噪。
- 截图输出: `test-results/correlation-matrix-polish/markets-intelligence-corr.png`
- 门禁: `bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-markets-intelligence.html --out-dir test-results/ditto-design-cycle-gates/markets-intelligence-correlation-polish` PASS

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，剩余差距主要来自：

- 热力图仍是静态 SVG 网格，缺少真实 size by / color by / group by 切换。
- 右侧 AI 摘要、筛选器和关联标的不会随主 tab 或选中情报做真实上下文联动。
- 情报详情、发送 Copilot、收藏标注仍是 mock overlay，未接入真实数据刷新和事件链路。
