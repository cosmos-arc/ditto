# Signals Inbox Design Cycle Review

**目标**: `/ditto-design-cycle page-signals-inbox.html --iterate --goal 10 --max-rounds 100 --level best`  
**日期**: 2026-04-27  
**对象**: `docs/designs/specs/prototypes/page-signals-inbox.html`  
**结果**: 9.7 / 10（best 级门禁修复 + 信息效率提升，未标记 done）

## 结论

本轮将 Signals Inbox 从「DOM 结构破裂导致门禁失败」推进到可稳定验收的 ops-console 原型：

- 修复 rail 中缺失的 AI 图标容器，避免 `</div>` 提前关闭 `.shell-signals`，header/main/detail 回到同一个 shell grid。
- 给 shell 增加 gate 可识别的 `.shell-ops` 语义类，并为底部 status bar 预留 `--shell-status-bar-height`。
- `tab-panel` 改为占满 main 区，批量操作条回到底部操作位。
- 修复状态 tab 交互：`active-by-default` 只在 `#tab-pending` 选中时显示，避免切到「已确认」后双面板同时可见。
- 待复核表格补齐 12 行，与 tab count 和 status bar 计数一致。
- 移除滚动表格行上的 `data-reveal`，避免 IntersectionObserver 让后续行保持透明。
- 移除 default-view `data-ticker` / `data-counter`，视觉验收截图保持确定性。
- 新增 `scripts/page-signals-inbox-prototype.test.ts`，覆盖 shell 结构、队列密度、ScrollReveal 回归、截图确定性、status bar 遮挡和运行时交互。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.7 | 保持 Graphite Studio 暗色终端语法，修复结构而非增加装饰 |
| 一致性 | 9.7 | shell、ops-console 语义、manifest 指标、门禁识别口径已同步 |
| 高级感 | 9.6 | 表格、风险检查、详情面板和底部 action bar 回到稳定执行台节奏 |
| 品牌方向 | 9.7 | A 股信号复核、T+1、涨跌停、两融检查与 Trading 域闭环一致 |
| 信息效率 | 9.8 | 首屏可扫视 12 条待复核信号，并保持右侧风险详情持续可见 |
| 综合气质 | 9.7 | P0/P1 为 0；剩余差距主要来自静态 HTML 阶段的真实联动上限 |

## 验证

```bash
bunx vitest run scripts/page-signals-inbox-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-signals-inbox.html --out-dir test-results/ditto-design-cycle-gates/signals-inbox-final
bun run check
```

结果：

- Targeted tests: 6 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/signals-inbox-final/page-signals-inbox.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/signals-inbox-final/page-signals-inbox.html-VP-COMPACT.png`

静态审计：

- inline styles: 0
- duplicate ids: 0
- default-view `data-ticker` / `data-counter`: 0
- data-reveal rows in pending table: 0
- pending rows: 12
- state gallery cards: 14
- overlay gallery cards: 4

全量验证状态：

- `bun run check` 已执行；Biome 阶段通过。
- `tsc -b` 仍被仓库既有 TypeScript/test 类型问题阻断，失败分布在 `src/components/chart/*`、`src/components/data/*`、`src/routes/*`、`src/types/*` 等非本轮原型文件。本轮未修改这些文件。

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，距离真实顶级信号复核台还有三类差距：

- 表格行与右侧 Signal Detail 仍是静态选中态，未按点击信号实时切换解释、风控、组合影响和动作。
- 风控检查、涨跌停、T+1 与两融状态没有真实数据老化、重算和阻断后的结果回放。
- 批量确认、AI 解读、生成订单复核虽然 overlay 可打开，但尚未具备真实提交、状态迁移和审计日志联动。

## Benchmark Notes

- Interactive Brokers TWS Blotter 将 ticket、order status、orders、trades 放在同一 blotter 窗口，强调单屏管理订单生命周期。参考: https://www.interactivebrokers.co.uk/en/software/tws.bak/usersguidebook/specializedorderentry/understand_the_blotter_interface.htm
- Bloomberg EMSX order blotter 以表格承载 order sequence、side、type、broker 等执行字段，支持订单创建后持续更新。参考: https://www.mathworks.com/help/datafeed/emsx.emsxorderblotter.html
- Bloomberg EMSX 相关集成说明强调 OMS、pre-trade risk controls 与 DMA/order routing 的组合价值。参考: https://www.bloomberg.com/company/press/rofex-integrates-bloomberg-emsx-order-routing-direct-market-access/
