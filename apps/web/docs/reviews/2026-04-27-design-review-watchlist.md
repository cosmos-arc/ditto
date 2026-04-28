# Watchlist Design Cycle Review

**目标**: `/ditto-design-cycle page-watchlist.html --iterate --goal 10 --max-rounds 100 --level best`  
**日期**: 2026-04-27  
**对象**: `docs/designs/specs/prototypes/page-watchlist.html`  
**结果**: 9.7 / 10（best 级 Catalog Watchlist 精修，已标记 reviewed，未虚报 10）

## 结论

本轮将 Watchlist 从基础 `created` 原型推进到可稳定验收的专业观察列表工作台：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿。
- 修复 Gate P0：补齐 `.catalog-shell`，让 shell root、header、main、detail 能被设计周期门禁识别。
- 修复 Gate P0：补齐 skip-link 默认隐藏规则，原型辅助 UI 不再污染默认产品视图。
- 新增 Watchlist Summary：列表范围、信号结构、组合日变动、最强标的、数据老化一屏可扫。
- 表格补齐批量选择、8 行 deterministic 数据、行操作、stale 标记和 `▲/▼` 方向符号，避免只靠颜色表达涨跌。
- 右侧详情升级为价格、趋势 sparkline、IC/IR/胜率条、观察记录和动作区，compact 视口无重叠。
- 修复 compact 视口右侧栏底部遮挡：操作区底部从 768px 回收至 692px，观察记录不再被挤压裁切。
- 添加标的与批量删除从静态画廊预览升级为 default-view CSS-only Drawer/Modal，支持打开、关闭和三区切换。
- 状态画廊补齐 `search-bar` default/failed 状态；Watchlist Table 共 7 张状态卡，Overlay Gallery 共 2 张。
- 新增 `scripts/page-watchlist-prototype.test.ts`，覆盖 shell、表格密度、方向符号、状态覆盖、无 inline style 和运行时 overlay 交互。
- `.edition-manifest.json` 中 watchlist 状态推进为 `reviewed`，score 更新为 9.7。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.7 | 保持 Graphite Studio 暗色终端语言，新增表达均服务于信息效率 |
| 一致性 | 9.7 | Catalog shell、contract slot、overlay、状态画廊与 reviewed 目录页口径一致 |
| 高级感 | 9.6 | 摘要条、右侧 sparkline、信号条和 frosted header 提升专业感，但仍是静态原型 |
| 品牌方向 | 9.7 | A 股观察列表、红涨绿跌、信号置信度和 stale 数据语义符合量化终端气质 |
| 信息效率 | 9.8 | 首屏可扫视 8 只标的、方向、信号、备注、行操作与右侧当前标的上下文 |
| 综合气质 | 9.7 | P0/P1/P2 为 0；剩余差距来自真实筛选、排序、详情联动和数据刷新上限 |

## 验证

```bash
bunx vitest run .claude/skills/ditto-design-cycle/scripts/verify-gates-core.test.mjs scripts/page-watchlist-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-watchlist.html --out-dir test-results/ditto-design-cycle-gates/watchlist-final
bun run check
```

结果：

- Targeted tests: 14 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/watchlist-final/page-watchlist.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/watchlist-bottom-fix/page-watchlist.html-VP-COMPACT.png`
- Runtime interaction check: add-instrument drawer open/close PASS, bulk-delete modal open/close PASS, states gallery switch PASS, overlays gallery switch PASS
- Compact right rail geometry: action bottom 692px / viewport 768px, clipped sections 0
- Static audit: inline styles 0, `any` / `@ts-ignore` / `@ts-expect-error` 0, state gallery cards 9, overlay gallery cards 2
- `bun run check`: 未通过。Biome 阶段通过，阻塞在仓库既有 `src/` TypeScript 错误；本轮改动未触碰这些失败文件。代表性错误包括 Vitest 全局类型未导入、`data-table` 泛型不匹配、TanStack Router `handle` 类型不被当前类型接受、`src/types/index.ts` 重复导出和若干 API 类型命名漂移。

## Benchmark Notes

- TradingView Watchlists: 参考自定义列表、分组、可排序指标、右侧 Symbol Details 和 Advanced View 汇总能力。<https://www.tradingview.com/support/solutions/43000745825/>
- TradingView Watchlist API: 参考多 watchlist、section divider、列表持久化和可程序化管理模型。<https://www.tradingview.com/charting-library-docs/latest/trading_terminal/Watch-List>
- Koyfin Watchlists: 参考 summary rows、notes、alerts、column configurations 和自定义 dashboard 中的高密度观察列表。<https://www.koyfin.com/features/watchlists/>

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，距离真实顶级 watchlist 还有三类差距：

- 表格行选中不会真实驱动右侧详情、趋势图、观察记录和动作状态。
- 搜索、排序、列配置、批量删除与添加标的尚未接入真实状态机、API 和持久化偏好。
- 信号置信度、stale 数据和价格趋势仍是静态视觉样本，尚未体现异步刷新、失败恢复和实时行情订阅。
