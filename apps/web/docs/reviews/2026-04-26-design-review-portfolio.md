# Portfolio Design Cycle Review

**目标**: `/ditto-design-cycle page-portfolio.html --iterate --goal 10 --max-rounds 100 --level best`

**日期**: 2026-04-26

**对象**: `docs/designs/specs/prototypes/page-portfolio.html`

**结果**: 9.7 / 10（CSS 原型阶段上限区间，未标记 done）

## 结论

Portfolio 已从 created 状态推进到可稳定验收的 best 级原型：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿
- 修复 analytical shell 嵌套导致的 right-rail / secondary 门禁缺失
- 默认视图无 prototype tool 污染，0 inline style，0 duplicate id，0 external script
- 持仓、交易、归因 tab 可切换；Position / Trade drawer 与 Confirm modal 均可打开和关闭
- 右侧 PnL 从占位柱图升级为累计曲线、基准线、回撤线和关键统计
- 底部风险带补齐组合风险、行业集中度热区与 A 股交易约束

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.7 | 视觉表达收敛在 shell、曲线、热区和指标卡，未引入高噪声装饰 |
| 一致性 | 9.7 | shell grid、contract slot、tab、overlay、状态画廊与 Edition 口径一致 |
| 高级感 | 9.6 | PnL 曲线、回撤语义、集中度热区形成组合工作台的专业记忆点 |
| 品牌方向 | 9.7 | Graphite Studio 暗色金融终端、Trading 域风险/执行语义保持统一 |
| 信息效率 | 9.7 | Compact 下仍可扫视 Summary、持仓表、PnL 与风险带；交互入口 ≥24px |
| 综合气质 | 9.7 | P0/P1 为 0，CSS 静态原型阶段已接近天花板 |

## 关键修改

1. 隐藏默认视图中的 `.skip-link`，仅在 focus 时显示。
2. 将 `.shell-body` 改为 `display: contents`，恢复 analytical shell 直接 grid 子项布局。
3. 将右侧 PnL 面板标记为 `data-contract-slot="right-rail"`。
4. 补齐 Position / Trade / Confirm 三个 overlay 的 CSS-only 打开规则。
5. 在持仓表和成交表增加可见 drawer 触发入口。
6. 将所有新增交互入口拉齐到 12px 字号与 ≥24px 点击高度。
7. 用 SVG PnL 曲线替换旧柱状占位图，并删除死 CSS。
8. 重构 analysis band：组合风险 + 行业集中度热区 + A 股交易约束。
9. 同步 `.edition-manifest.json` 中 portfolio 的 status、score、rounds 和 note。

## 验证

```bash
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-portfolio.html --out-dir test-results/ditto-design-cycle-gates/portfolio-final
```

结果：

- Status: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/portfolio-final/page-portfolio.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/portfolio-final/page-portfolio.html-VP-COMPACT.png`

交互抽查：

- tabs: 持仓 / 交易 / 归因全部可切换
- overlays: Position Detail / Trade Detail / Confirm Close All 均可打开和关闭

静态审计：

- inline styles: 0
- duplicate ids: 0
- external scripts: 0
- `oklch()` function refs: 0
- state gallery cards: 20
- overlay gallery cards: 3

工程门禁：

- `bun run check`: biome passed；`tsc -b` 在既有 TypeScript/test 类型问题处失败，未进入 vitest。本轮未修改 TS/TSX 文件。

## 未达 10 的原因

目标 10 在当前 HTML/CSS 静态原型阶段不宜虚报。剩余差距主要来自：

- PnL 曲线仍是静态 SVG，缺少真实 hover 十字线、缩放、区间选择和标的贡献联动。
- 表格行只通过代表性入口触发 drawer，尚未做到整行键鼠一致的高保真交互。
- 风险、归因与交易约束仍是 mock 层语义，未与真实组合数据刷新和 Risk Center 上下文联动。

## Benchmark Notes

- Bloomberg Portfolio & Risk Analytics: 组合页应强调风险管理、绩效归因、组合报告和可定制 dashboard。参考: https://www.bloomberg.com/professional/product/portfolio-risk-analytics/
- TradingView Heatmaps: 热区适合用面积/颜色快速识别权重、趋势和相对贡献。参考: https://www.tradingview.com/support/solutions/43000766446-tradingview-heatmaps-from-global-trends-to-details/
