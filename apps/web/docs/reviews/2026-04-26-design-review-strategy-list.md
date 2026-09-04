# Strategy List Design Cycle Review

**目标**: `/ditto-design-cycle page-strategy-list.html --iterate --goal 10 --max-rounds 100 --level best`
**日期**: 2026-04-26
**对象**: `docs/designs/specs/prototypes/page-strategy-list.html`
**结果**: 9.7 / 10（best 级 Catalog/Screener 精修，已标记 reviewed，未标记 done）

## 结论

本轮将 Strategy List 从基础 `created` 原型推进到可稳定验收的专业策略目录工作台：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿。
- 修复 Gate P0：补齐 `catalog-shell`，让 shell root、header、main、detail 能被设计周期门禁识别。
- 修复 Gate P0：补齐 skip-link 默认隐藏规则，原型辅助 UI 不再污染默认产品视图。
- Shell 网格调整为 Header / Filter / Performance Summary / Table 四层，绩效摘要回到表格上方，不再掉到底部。
- 默认表格从 6 行扩展到 12 行，并补齐 MDD 与行操作列，减少标准视口空白，提高策略目录扫描效率。
- 策略名称增加版本、因子、调仓语义；收益列增加 `▲` 方向符号，避免正向表现只依赖颜色。
- 右侧详情从稀疏字段升级为策略净值曲线、关键指标、运行上下文和操作区，compact 视口下标题与曲线不再压缩。
- 克隆 / 删除从静态按钮升级为 CSS-only 可触发 Modal，支持打开、关闭和默认/状态/弹层三区切换。
- 状态画廊补齐 filter-bar、perf-summary、strategy-table 三类组件，共 12 张状态卡；弹层画廊覆盖 2 个 Modal。
- 新增 `scripts/page-strategy-list-prototype.test.ts`，覆盖 shell、密度、方向符号、无 inline style、状态覆盖和运行时弹层交互。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.8 | 保持 Graphite Studio 暗色终端语言，只增加信息型密度与低噪声状态表达 |
| 一致性 | 9.7 | Catalog shell、contract slot、三区结构、overlay 模式与近期 reviewed 页面口径一致 |
| 高级感 | 9.6 | 右侧净值曲线、KPI grid、frosted header 与细线分割提升专业感，但仍是静态原型 |
| 品牌方向 | 9.7 | Research / Strategies 的量化研究语境明确，红涨绿跌与 A 股语义一致 |
| 信息效率 | 9.8 | 首屏可扫视 12 个策略、运行状态、Sharpe、年化、MDD、最近运行和行操作 |
| 综合气质 | 9.7 | P0/P1/P2 为 0；未虚报 10，剩余差距来自真实数据与交互联动上限 |

## 验证

```bash
bunx vitest run scripts/page-strategy-list-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-strategy-list.html --out-dir test-results/ditto-design-cycle-gates/strategy-list-final
bun run check
```

结果：

- Targeted tests: 6 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/strategy-list-final/page-strategy-list.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/strategy-list-final/page-strategy-list.html-VP-COMPACT.png`
- Runtime interaction check: clone overlay open/close PASS, delete overlay open/close PASS, states gallery switch PASS, overlays gallery switch PASS
- `bun run check`: 未通过，阻塞在既有 `src/` TypeScript 错误；本轮改动未触碰这些失败文件。

静态审计：

- inline styles: 0
- default-view prototype tool UI leakage: 0
- state gallery cards: 12
- overlay gallery cards: 2
- manifest status: `reviewed`

## Benchmark Notes

- Bloomberg Terminal / Launchpad: 参考可定制的多窗口监控、动态证券监视器和专业金融终端的信息密度。<https://www.bloomberg.com/company/stories/innovating-a-modern-icon-how-bloomberg-keeps-the-terminal-cutting-edge/>
- Bloomberg Terminal UX: 参考“复杂性隐藏在可调整密度和表格行列中”的终端设计思路。<https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/>
- TradingView Stock Screener: 参考筛选器、指标列组、Table view 与多维过滤的目录型工作流。<https://www.tradingview.com/support/solutions/43000718866-what-is-the-stock-screener/>
- Linear design refresh: 参考保持高信息密度同时降低边框噪声、统一 header/action 区的克制界面语言。<https://linear.app/now/behind-the-latest-design-refresh>

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，距离真实业界顶级策略目录还有三类差距：

- 表格行选中不会真实驱动右侧详情、回测上下文和策略版本链路。
- 筛选、排序、批量操作与新建策略尚未接入真实状态机、API 和持久化偏好。
- 策略净值曲线与绩效摘要是静态视觉样本，尚未体现数据老化、异步刷新和失败恢复后的真实变化。
