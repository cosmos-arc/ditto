# Universe List Design Cycle Review

**目标**: `/ditto-design-cycle page-universe-list.html --iterate --goal 10 --max-rounds 100 --level best`
**日期**: 2026-04-27
**对象**: `docs/designs/specs/prototypes/page-universe-list.html`
**结果**: 9.7 / 10（best 级 Catalog/Screener 精修，已标记 reviewed，未虚报 10）

## 结论

本轮将 Universe List 从基础 `created` 原型推进到可稳定验收的股票池目录工作台：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿。
- 修复 Gate P0：补齐 `catalog-shell`，让 shell root、rail、header、main、detail 能被设计周期门禁识别。
- 修复 Gate P0：`skip-link` 默认移出视口，原型辅助 UI 不再污染默认产品视图。
- Header / Filter Bar / Main Table / Detail Panel 均对齐 Page Contract slot。
- 默认表格从 6 行扩展到 12 行，覆盖名称、标的数、来源、关联策略数、更新时间与操作入口。
- stale 与 selected 状态增加形状/文本提示，避免关键判断只依赖颜色。
- 右侧详情升级为成分分布、筛选规则、关联策略和操作区，compact 视口无重叠。
- 创建/编辑 Drawer 与删除 Modal 从静态画廊升级为 default-view CSS-only 运行态弹层。
- 状态画廊补齐 filter-bar 4 张卡与 universe-table 6 张卡；弹层画廊覆盖 2 个 overlay。
- 新增 `scripts/page-universe-list-prototype.test.ts`，覆盖 shell、密度、无 inline style、状态覆盖和运行时 overlay 交互。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.8 | 保持 Graphite Studio 暗色终端语言，新增内容以信息密度和状态清晰度为主 |
| 一致性 | 9.7 | Catalog shell、contract slot、overlay 与三 gallery 结构和同批 reviewed 页面一致 |
| 高级感 | 9.6 | 右侧分布条、规则摘要和低噪声操作区提升专业感，但仍是静态原型 |
| 品牌方向 | 9.7 | Research / Universes 的策略输入、筛选来源、刷新状态和关联策略路径明确 |
| 信息效率 | 9.8 | 首屏可扫视 12 个股票池、来源、数量、策略引用、同步状态和操作入口 |
| 综合气质 | 9.7 | P0/P1/P2 为 0；剩余差距来自真实筛选、行详情联动和批量状态机上限 |

## 验证

```bash
bunx vitest run scripts/page-universe-list-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-universe-list.html --out-dir test-results/ditto-design-cycle-gates/universe-list-final
bun run check
```

结果：

- Targeted tests: 6 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/universe-list-final/page-universe-list.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/universe-list-final/page-universe-list.html-VP-COMPACT.png`
- Runtime interaction check: create/edit drawer open/close PASS, delete modal open/backdrop close PASS, states gallery switch PASS, overlays gallery switch PASS
- Static audit: inline styles 0, state gallery cards 10, overlay gallery cards 2, manifest status `reviewed`
- `bun run check`: 未通过，阻塞在既有 `src/` TypeScript 错误；本轮改动未触碰这些失败文件。代表性错误包括测试全局类型未导入、`data-table` 泛型不匹配、TanStack Router `handle` 类型不被当前类型接受、`src/types/index.ts` 重复导出和若干 API 类型命名漂移。

## Benchmark Notes

- Bloomberg Terminal / Portfolio Analytics: 参考全局数据、组合分析、可过滤 universe 与自定义 dashboard 的高密度金融工作流。<https://professional.bloomberg.com/products/bloomberg-terminal/> / <https://professional.bloomberg.com/products/bloomberg-terminal/portfolio-analytics/>
- TradingView Stock Screener: 参考多筛选条件、可保存 screen、指标表格和筛选后继续分析的目录型工作流。<https://www.tradingview.com/support/solutions/43000718866-tradingview-stock-screener-trade-smarter-not-harder/>
- Linear interface refresh: 参考高信息密度产品中降低边界噪声、压低次级导航视觉权重、让主工作面优先的克制界面语言。<https://linear.app/now/behind-the-latest-design-refresh>

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，距离真实业界顶级股票池目录还有三类差距：

- 表格行选中尚未真实驱动右侧详情、成分分布和关联策略。
- 搜索、筛选、批量选择、删除确认尚未接入真实状态机、API 和持久化偏好。
- 数据刷新与 stale 衰减仍是静态视觉表达，未体现异步同步、失败恢复和实盘交易日变更。
