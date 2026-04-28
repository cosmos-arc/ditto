# A-Shares Design Cycle Review

**目标**: `/ditto-design-cycle page-a-shares.html --iterate --goal 10 --max-rounds 100 --level best`  
**日期**: 2026-04-26  
**对象**: `docs/designs/specs/prototypes/page-a-shares.html`  
**结果**: 9.8 / 10（best 级地图精修 + 全页风格回归 Graphite Studio，未标记 done）

## 结论

本轮聚焦 A 股总览首屏的 Market Structure Map，将 treemap / heatmap 从静态色块推进到可读、可解释、可交互的专业市场地图：

- 补齐 Size / Color / Grouping 读图规则：Size = 成交额占比，Color = 涨跌幅，Grouping = 申万一级。
- 增加 5 档涨跌色阶图例，用户不需要靠猜测理解红绿强度。
- treemap 添加 4 个行业族群标签：成长科技、防御消费、金融地产、周期制造。
- treemap / heatmap 单元统一 `data-direction` 与 `data-sector-family`，支持测试守卫与后续真实数据接入。
- 使用 ▲ / ▼ / • 方向符号，避免涨跌判断完全依赖颜色。
- 修正银行、新能源、地产、汽车、交运等单元的涨跌色阶映射，使颜色与数值方向一致。
- Enter / Space 键现在会触发可聚焦地图单元的下钻点击。
- 反馈后追加 R4：treemap 重排为 4 个父级分区，并在行业块内加入 40+ 个成分微块。
- heatmap 改为 8 列个股热力矩阵，承担全市场扫描视图，不再只是 16 个行业格。
- 反馈后追加 R5：重做地图色彩语言，tile 主体回到 graphite / charcoal，涨跌只通过低饱和 tint、方向线、角标和数值色表达，避免纯红绿整块铺底。
- 反馈后追加 R6：改为 A 股红涨绿跌主色板，按 `data-heat` 的 4 档红绿热度逐步变化，同时取消发光和行业族群杂色边线。
- 反馈后追加 R7：重新审视整页设计一致性，移除页面级氛围光、噪声纹理、signature 渐变线、mouse glow、长延迟 reveal 和面板发光 hover，让页面回到 Ditto 专业工作台语言。
- R7 同步修复 shell 滚动边界与顶部信息层 shrink 问题：Context Bar / Scope Strip 恢复固定高度，长内容被限制在 `.shell-body` 内部滚动，Prototype gates 不再出现 viewport P0。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.9 | 取消亮色 glow、页面氛围层、signature 渐变线和长 reveal，红绿主色保留但亮度受控 |
| 一致性 | 9.9 | treemap / heatmap 共用 `data-heat`、方向、分组和 4 档红绿热度色板，整页 shell / 面板 / rail 回到同一工作台语言 |
| 高级感 | 9.8 | treemap 有 nested market map 层级，heatmap 有密集个股扫描感，色板更接近真实市场热力图 |
| 品牌方向 | 9.8 | 保持 Graphite Studio 金融终端气质，并强化 A 股红涨绿跌语义 |
| 信息效率 | 9.8 | 用户可在首屏同时读出权重、涨跌方向、行业分组、成分股热度和下钻路径 |
| 综合气质 | 9.8 | 原型门禁全绿；整页风格偏差已收敛，剩余差距主要来自静态 HTML 阶段的真实交互上限 |

## Benchmark Notes

- TradingView Heatmaps: 参考其 size / color / grouping / legend / color-blind mode / tile tooltip / click drilldown 的地图读法。<https://www.tradingview.com/support/solutions/43000766446-tradingview-heatmaps-from-global-trends-to-details/>
- Finviz Maps: 参考其将 market cap、52 周高低、themes、groups heatmap 作为不同地图维度的做法。<https://finviz.com/blog/new-stock-market-maps-for-market-cap-52-week-highs-lows-themes-and-insider-trading/>
- Bloomberg Sector Performance: 参考其以行业加权表现快速形成市场概览的组织方式。<https://www.bloomberg.com/markets/sectors>

## 验证

```bash
bun run test:run scripts/page-a-shares-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-a-shares.html --out-dir test-results/ditto-design-cycle-gates/a-shares-style-unification-r7b
bun run check
```

结果：

- `scripts/page-a-shares-prototype.test.ts`: 5 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/a-shares-style-unification-r7b/page-a-shares.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/a-shares-style-unification-r7b/page-a-shares.html-VP-COMPACT.png`
- Heatmap screenshot: `test-results/ditto-design-cycle-gates/a-shares-style-unification-r7b/page-a-shares.html-HEATMAP.png`
- `bun run check`: 未通过，阻塞在既有 `src/` TypeScript 错误；本轮改动未触碰这些失败文件。

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，距离真实业界顶级地图还有三类差距：

- 缺少真实数据驱动的 size by / color by 切换、分组切换、行业下钻状态同步。
- tooltip 与点击详情仍是 mock overlay，尚未接入真实证券列表、权重贡献和时间窗口。
- heatmap 的 color-blind / monochrome 模式仍是语义预留，未做完整可切换实现。
