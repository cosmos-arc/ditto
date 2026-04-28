# Markets Screener Design Cycle Review

**目标**: `/ditto-design-cycle page-markets-screener.html --iterate --goal 10 --max-rounds 100 --level best`  
**日期**: 2026-04-26  
**对象**: `docs/designs/specs/prototypes/page-markets-screener.html`  
**结果**: 9.7 / 10（best 级 Catalog/Screener 精修，未标记 done）

## 结论

本轮将 Markets Screener 从旧版高分但门禁不可评分的 Catalog 页面，推进到可稳定验收的专业筛选器原型：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿。
- Shell root 补齐 `catalog-shell`，主工作区、结果表、过滤区、右侧 detail slot 均可被门禁识别。
- Shell 网格改为 Header / Filter / Insight / Mode / Table 五层，修复表头 sticky 与模式切换按钮重叠。
- 反馈修复：`data-tabs` 提升到包含三块 panel 的 shell，排序 / 筛选 / 对比 tab 恢复运行时切换。
- 反馈修复：共享 `FilterChips` 交互补齐筛选按钮 active / `aria-pressed` 反馈。
- 反馈修复：多维评分从 donut + radar 改为紧凑五指标 grid，Compact 视口下不再压住对比篮。
- 反馈修复：默认筛选 tab 补齐条件堆栈、条件构建、应用筛选、执行结果四段状态，筛选动作可触发并回写读图条与结果计数。
- 反馈修复：排序项改为可点击规则，应用后回写 Rank、表头 sorted 状态；结果表补齐“+ 对比”操作列并同步右侧对比篮计数。
- 将折叠式板块热力占位改为常驻 Screener Reading Strip，明确 Scope / Rank / Color / Filters / Destination 读图规则。
- 结果表扩展到 22 行首屏样本，减少标准视口下的空白，符合高密金融工作台扫描习惯。
- 表格行补齐 `data-direction` 与 ▲ / ▼ 方向符号，避免涨跌判断只依赖颜色。
- 默认视图移除 `data-ticker` / `data-counter`，截图数值保持确定性。
- 移除旧版 `data-mouse-glow`、noise texture 和 bottom ambient glow，让页面回到克制的 Graphite Studio 工作台语言。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.8 | 去除页面级噪声、固定氛围线和 mouse glow，保留表格密度与低噪声状态表达 |
| 一致性 | 9.7 | Catalog shell、contract slot、deterministic screenshot 与近期 Markets 页面门禁口径一致 |
| 高级感 | 9.7 | Reading Strip 补齐筛选读法，表格密度和右侧 action rail 更接近专业终端 |
| 品牌方向 | 9.7 | 保持 Graphite Studio 暗色金融终端气质，红涨绿跌符合 A 股语义 |
| 信息效率 | 9.8 | 首屏可同时读出筛选范围、排序逻辑、涨跌强度、活跃过滤、结果去向和 22 行候选 |
| 综合气质 | 9.7 | P0/P1 为 0；剩余差距来自静态 HTML 原型阶段的真实交互上限 |

## 验证

```bash
bun run test:run scripts/page-markets-screener-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-markets-screener.html --out-dir test-results/ditto-design-cycle-gates/markets-screener-workflow-r2
bun run check
```

结果：

- `scripts/page-markets-screener-prototype.test.ts`: 10 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/markets-screener-workflow-r2/page-markets-screener.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/markets-screener-workflow-r2/page-markets-screener.html-VP-COMPACT.png`
- Runtime interaction check: 中证500 filter chip active feedback PASS, 添加条件 PASS, 应用筛选 PASS, 应用排序 PASS, 结果行加入对比 PASS, compare overlay open PASS
- `bun run check`: 未通过，阻塞在既有 `src/` TypeScript 错误；本轮改动未触碰这些失败文件。

静态审计：

- inline styles: 0
- default-view `data-ticker` / `data-counter`: 0
- default-view `data-mouse-glow`: 0
- overlays: 5 declared, 5 covered in State Coverage Index

## Benchmark Notes

- TradingView Stock Screener: 参考 filters、saved screens、column sets，以及 Overview / Performance / Valuation 等列组的筛选工作流。<https://www.tradingview.com/support/solutions/43000718866-tradingview-stock-screener-trade-smarter-not-harder/>
- TradingView Heatmaps: 参考 scope、size/color、legend 与 screener/heatmap 协同读法。<https://www.tradingview.com/support/solutions/43000766446-tradingview-heatmaps-from-global-trends-to-details/>
- Koyfin Stock Screener: 参考大规模筛选条件、保存为 watchlist、CSV 导出和模板化筛选。<https://www.koyfin.com/features/stock-screener/>
- Finviz Maps + Screener: 参考 map/screener 联动、market cap / 52-week / themes 等多维市场扫描。<https://finviz.com/blog/new-stock-market-maps-for-market-cap-52-week-highs-lows-themes-and-insider-trading/>

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，距离真实业界顶级 screener 还有三类差距：

- 过滤条件、排序列和对比篮已有可见原型交互，但不会驱动真实查询 API、持久化列组或 saved screen。
- Compare Drawer、结果去向、发送研究和生成标的池仍是 mock overlay，未接入真实对象与状态链路。
- Reading Strip 只是静态解释层，尚未与市场范围、活跃筛选和当前排序状态实时联动。
