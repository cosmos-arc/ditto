# Factor List Design Cycle Review

**目标**: `/ditto-design-cycle page-factor-list.html --iterate --goal 10 --max-rounds 100 --level best`
**日期**: 2026-04-27
**对象**: `docs/designs/specs/prototypes/page-factor-list.html`
**结果**: 9.7 / 10（best 级 Catalog/Screener 精修，已标记 reviewed，未虚报 10）

## 结论

本轮将 Factor List 从基础 `created` 原型推进到可稳定验收的专业因子目录工作台：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿。
- 修复 Gate P0：补齐 `catalog-shell`，让 shell root、header、main、detail 能被设计周期门禁识别。
- 修复 Gate P0：补齐 skip-link 默认隐藏规则，原型辅助 UI 不再污染默认产品视图。
- Filter Bar 下沉为 `data-contract-slot="header"`，Health Summary 回到表格上方并接入 catalog shell 网格。
- 默认表格从 7 行扩展到 12 行，补齐「衰减率」和「操作」列，贴合蓝图字段与对比工作流。
- IC 正负方向增加 `▲/▼` 标记，健康状态 pill 增加形状提示，避免关键判断只依赖颜色。
- 右侧详情升级为因子 KPI、60 日 IC sparkline、质量分解、关联策略和操作区，compact 视口无重叠。
- 因子对比从静态画廊预览升级为 default-view CSS-only Drawer，支持打开、关闭和三区切换。
- 状态画廊补齐 filter-bar、health-summary、factor-table 三类组件，共 12 张状态卡；弹层画廊覆盖 1 个 Drawer。
- 新增 `scripts/page-factor-list-prototype.test.ts`，覆盖 shell、密度、方向符号、无 inline style、状态覆盖和运行时 Drawer 交互。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.8 | 仍保持 Graphite Studio 暗色终端语言，新增内容以信息型密度和低噪声状态表达为主 |
| 一致性 | 9.7 | Catalog shell、contract slot、三区结构、overlay 模式与 Strategy List 等 reviewed 页面口径一致 |
| 高级感 | 9.6 | 右侧 IC sparkline、KPI grid、质量条和 frosted header 提升专业感，但仍是静态原型 |
| 品牌方向 | 9.7 | Research / Factors 的因子健康、衰减、IC/IR 工作流明确，符合量化研究终端气质 |
| 信息效率 | 9.8 | 首屏可扫视 12 个因子、家族、IC、IR、衰减、健康、关联策略和对比入口 |
| 综合气质 | 9.7 | P0/P1/P2 为 0；剩余差距来自真实筛选排序、详情联动和动态图表上限 |

## 验证

```bash
bunx vitest run .claude/skills/ditto-design-cycle/scripts/verify-gates-core.test.mjs scripts/page-factor-list-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-factor-list.html --out-dir test-results/ditto-design-cycle-gates/factor-list-final
bun run check
```

结果：

- Targeted tests: 13 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/factor-list-final/page-factor-list.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/factor-list-final/page-factor-list.html-VP-COMPACT.png`
- Runtime interaction check: factor compare drawer open/close PASS, states gallery switch PASS, overlays gallery switch PASS
- Static audit: inline styles 0, state gallery cards 12, overlay gallery cards 1, manifest status `reviewed`
- `bun run check`: 未通过，阻塞在既有 `src/` TypeScript 错误；本轮改动未触碰这些失败文件。代表性错误包括测试全局类型未导入、`data-table` 泛型不匹配、TanStack Router `handle` 类型不被当前类型接受、`src/types/index.ts` 重复导出和若干 API 类型命名漂移。

## Benchmark Notes

- Bloomberg Terminal UX: 参考复杂性隐藏在专业用户可接受的信息密度、工作流效率和可配置表格中的终端设计思路。<https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/>
- TradingView Stock Screener: 参考多筛选条件、指标表格和筛选后继续分析的目录型工作流。<https://www.tradingview.com/support/solutions/43000718866-what-is-the-stock-screener/>
- Linear UI refresh: 参考高信息密度产品中统一 header/action 区、降低噪声并提升可扫视性的克制界面语言。<https://linear.app/now/behind-the-latest-design-refresh>

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，距离真实业界顶级因子目录还有三类差距：

- 表格行选中不会真实驱动右侧详情、因子健康状态和关联策略。
- 筛选、排序、对比选择与批量操作尚未接入真实状态机、API 和持久化偏好。
- IC sparkline、衰减率和质量分解是静态视觉样本，尚未体现异步刷新、失败恢复和数据老化后的真实变化。
