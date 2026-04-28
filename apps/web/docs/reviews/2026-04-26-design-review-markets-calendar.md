# Markets Calendar Design Cycle Review

**目标**: `/ditto-design-cycle page-markets-calendar.html --iterate --goal 10 --max-rounds 100 --level best`  
**日期**: 2026-04-26  
**对象**: `docs/designs/specs/prototypes/page-markets-calendar.html`  
**结果**: 9.76 / 10（best 级 Calendar/Catalog 精修，未标记 done）

## 结论

本轮将 Markets Calendar 从旧版 9.1 的可用原型推进到可稳定验收的专业事件日历：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿。
- Shell root 补齐 `catalog-shell`，主日历区和右侧经济数据 rail 均可被门禁识别。
- 右侧时间线从被嵌套在主区中的“假侧栏”改为真正占用 catalog detail 列，消除标准视口右侧空洞。
- 新增 Calendar Reading Strip，明确窗口、影响等级、颜色语义、下一事件簇和去向。
- 月历格从单纯色点升级为事件标签，首屏可直接读出 04-17 双交割、GDP、解禁、除息等关键日。
- 事件列表和经济时间线补齐 `data-impact`、事件类型和 ▲ / ◆ 重要性符号，避免重要性判断完全依赖颜色。
- 默认视图移除 `data-ticker` / `data-counter`，截图数值保持确定性。
- 移除 page-level noise、bottom ambient glow 和 `data-mouse-glow`，回到克制的 Graphite Studio 工作台语言。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.8 | 去除页面级纹理、氛围线和 mouse glow，只保留低噪声边线、标签和重要性符号 |
| 一致性 | 9.8 | Catalog shell、contract slot、Reading Strip 与近期 Markets 页面门禁口径一致 |
| 高级感 | 9.7 | 月历具备可扫视事件标签，右侧时间线有专业数据发布节奏 |
| 品牌方向 | 9.7 | 保持暗色金融终端气质，信息密度优先于装饰 |
| 信息效率 | 9.8 | 首屏可同时读出窗口、事件簇、影响等级、日历位置、事件列表和宏观数据 |
| 综合气质 | 9.76 | P0/P1 为 0；剩余差距来自静态 HTML 原型阶段的真实筛选、提醒和数据联动上限 |

## Benchmark Notes

- TradingView Economic Calendar: 参考 importance filter、国家/类别筛选和事件流组织方式。<https://www.tradingview.com/economic-calendar/>
- TradingView Economic Calendar Help: 参考用重要性图标帮助快速判断事件影响。<https://www.tradingview.com/support/solutions/43000759911/>
- Bloomberg Economic Calendar: 参考专业宏观日历按日期、发布时间和市场影响组织事件。<https://www.bloomberg.com/markets/economic-calendar>

## 验证

```bash
bun run test:run scripts/page-markets-calendar-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-markets-calendar.html --out-dir test-results/ditto-design-cycle-gates/markets-calendar-r3-final
bun run check
```

结果：

- `scripts/page-markets-calendar-prototype.test.ts`: 6 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/markets-calendar-r3-final/page-markets-calendar.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/markets-calendar-r3-final/page-markets-calendar.html-VP-COMPACT.png`
- inline styles: 0
- `bun run check`: 未通过，Biome 已通过，阻塞在既有 `src/` TypeScript 错误（chart/data-table/dittogrid 测试、route `handle` 类型、mock fixtures、types export 等）；本轮只改 HTML 原型、manifest、review 文档和新增原型测试。

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，距离真实顶级事件日历还有三类差距：

- 筛选条件、月/列表视图切换和日期选择不会驱动真实数据查询。
- 日历提醒、事件详情和 Intelligence 跳转仍是 mock overlay，未接入真实对象状态。
- 宏观数据发布后的实际值、偏离高亮和事件老化状态仍未与时间和数据源联动。
