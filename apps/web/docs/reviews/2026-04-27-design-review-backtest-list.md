# Backtest List Design Cycle Review

**目标**: `/ditto-design-cycle page-backtest-list.html --iterate --goal 10 --max-rounds 100 --level best`
**日期**: 2026-04-27
**对象**: `docs/designs/specs/prototypes/page-backtest-list.html`
**结果**: 9.7 / 10（best 级 Backtest Catalog 精修，已标记 reviewed，未虚报 10）

## 结论

本轮将 Backtest List 从基础轻量列表推进到可稳定验收的回测目录工作台：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿。
- 修复 Gate P0：补齐 `.catalog-shell`，让 shell root、header、main、detail 被设计周期门禁识别。
- 修复 Gate P0：补齐 skip-link 默认隐藏规则，原型辅助 UI 不再污染默认产品视图。
- Filter Bar 下沉为 `data-contract-slot="header"`，新增回测运行摘要并接入 catalog shell 网格。
- 默认表格从 7 行扩展到 10 行，补齐「操作」列、行级查看/对比入口、样本说明和 `▲/▼` 方向符号。
- 右侧预览升级为 KPI、净值 sparkline、回撤诊断和双动作区，compact 视口无重叠。
- 回测对比从静态画廊预览升级为 default-view CSS-only Drawer，支持打开、关闭和三区切换。
- 状态画廊补齐 filter-bar 与 backtest-table 覆盖，共 10 张状态卡；弹层画廊覆盖 1 个 Drawer。
- 新增 `scripts/page-backtest-list-prototype.test.ts`，覆盖 shell、密度、方向符号、无 inline style、状态覆盖和运行时 Drawer 交互。
- `.edition-manifest.json` 中 backtest-list 状态推进为 `reviewed`，score 更新为 9.7。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.8 | 保持 Graphite Studio 暗色终端语言，新增内容均服务于回测筛选、诊断或对比 |
| 一致性 | 9.7 | Catalog shell、contract slot、三区结构、overlay 模式与同类 reviewed 列表页一致 |
| 高级感 | 9.6 | 摘要条、右侧净值曲线、回撤条和 frosted header 提升专业质感，但仍是静态原型 |
| 品牌方向 | 9.7 | 回测历史、Sharpe/MDD、Engine 同步和对比路径符合量化研究终端气质 |
| 信息效率 | 9.8 | 首屏可扫视 10 次回测、策略、区间、核心绩效、状态、完成时间和行操作 |
| 综合气质 | 9.7 | P0/P1/P2 为 0；剩余差距来自真实排序、筛选状态机、详情联动和动态图表上限 |

## 验证

```bash
bunx vitest run .claude/skills/ditto-design-cycle/scripts/verify-gates-core.test.mjs scripts/page-backtest-list-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-backtest-list.html --out-dir test-results/ditto-design-cycle-gates/backtest-list-final
bun run check
```

结果：

- Targeted tests: 13 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/backtest-list-final/page-backtest-list.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/backtest-list-final/page-backtest-list.html-VP-COMPACT.png`
- Runtime interaction check: backtest compare drawer open/close PASS, states gallery switch PASS, overlays gallery switch PASS
- Static audit: inline styles 0, state gallery cards 10, overlay gallery cards 1, manifest status `reviewed`
- `bun run check`: 未通过。Biome 阶段通过，阻塞在仓库既有 `src/` TypeScript 错误；本轮改动未触碰这些失败文件。代表性错误包括 Vitest 全局类型未导入、`data-table` 泛型不匹配、TanStack Router `handle` 类型不被当前类型接受、`src/types/index.ts` 重复导出、若干 API 类型命名漂移和 mock fixture 类型不匹配。

## Benchmark Notes

- Bloomberg Terminal UX: 参考复杂性隐藏、信息密度可调整和专业用户不中断工作流的原则。<https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/>
- Enterprise Data Tables: 参考高密度表格中谨慎暴露行操作、hover/selected 状态和扫描效率的模式。<https://www.pencilandpaper.io/articles/ux-pattern-analysis-enterprise-data-tables/>
- Linear UI refresh: 参考高信息密度产品中降低噪声、保持状态覆盖和焦点一致性的界面语言。<https://linear.app/blog/how-we-redesigned-the-linear-ui>

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，距离真实业界顶级回测中心还有三类差距：

- 行选中不会真实驱动右侧预览、净值曲线、回撤诊断和动作状态。
- 筛选、排序、对比选择、查看结果尚未接入真实状态机、URL 和 Backtest Engine API。
- 净值曲线、回撤条、Engine 同步和运行中状态仍是静态视觉样本，尚未体现异步进度、失败恢复和数据老化后的真实变化。
