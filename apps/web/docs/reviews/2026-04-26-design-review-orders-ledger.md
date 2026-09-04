# Orders Ledger Design Cycle Review

**目标**: `/ditto-design-cycle page-orders-ledger.html --iterate --goal 10 --max-rounds 100 --level best`
**日期**: 2026-04-26
**对象**: `docs/designs/specs/prototypes/page-orders-ledger.html`
**结果**: 9.7 / 10（best 级结构修复 + 信息效率提升，未标记 done）

## 结论

本轮将 Orders / Execution Ledger 从「视觉基础不错但门禁与交互存在 P0」推进到可稳定验收的 best 级原型：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿。
- 修复 `.shell-ledger` 未被设计周期门禁识别的问题，补齐 gate 可识别的 shell/main/detail 语义类。
- 修复底部 `status-bar` 在 compact 视口压住表格的问题，shell 高度为状态栏预留空间。
- 修复 Orders Header 快速过滤 tab：默认只显示一个表格面板，点击可真实切换。
- 默认账本从 10 行扩展到 18 行，行高压到更像执行终端的密度。
- 主表列宽改为百分比布局，行背景与可扫视列铺满主工作面。
- 移除默认视图 `data-counter`，Playwright 视觉验收截图保持确定性。
- 新增 `scripts/page-orders-ledger-prototype.test.ts`，覆盖 shell 结构、快速过滤、状态栏遮挡、密度、列宽、截图确定性和运行时交互。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.7 | 维持 Graphite Studio 暗色终端语法，增加密度但未增加装饰噪声 |
| 一致性 | 9.7 | shell、contract slot、门禁识别口径和 manifest 指标已同步 |
| 高级感 | 9.6 | KPI strip、状态编码、滑点/费用/路由追踪形成专业执行台语境 |
| 品牌方向 | 9.7 | A 股订单生命周期、券商路由、成交/拒单状态与 trading 域一致 |
| 信息效率 | 9.8 | 首屏可同时扫视 18 笔订单、状态分布、成交效率和右侧 order trace |
| 综合气质 | 9.7 | P0/P1 为 0；剩余差距主要来自静态 HTML 阶段的真实联动上限 |

## 验证

```bash
bun run test:run scripts/page-orders-ledger-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-orders-ledger.html
```

结果：

- Targeted tests: 7 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/page-orders-ledger.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/page-orders-ledger.html-VP-COMPACT.png`

静态审计：

- inline styles: 0
- duplicate ids: 0
- default-view `data-counter` / `data-ticker`: 0
- state gallery cards: 24
- overlay gallery cards: 4
- default contract slots: 3

交互抽查：

- Orders Header 快速过滤 `全部 / 待处理 / 已成` 点击切换通过
- Status Strip `已完成 → 待提交` radio tab 切换通过
- default / states / overlays 三区 radio 切换通过
- 批量撤单 overlay 打开通过
- compact 视口 `status-bar` 与主表无重叠

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，距离真实顶级执行台还有三类差距：

- 表格行与右侧 Order Trace 仍是静态选中态，未按点击订单实时切换详情、费用、滑点和路由日志。
- 订单状态、成交进度、等待时间和券商确认状态没有真实状态机与数据老化反馈。
- 快速筛选只有本地面板切换，尚未具备真实排序、列配置、批量选择和撤单/重试后的结果回放。

## Benchmark Notes

- Interactive Brokers TWS Blotter: blotter 应在单一窗口里承载订单管理、订单状态和交易明细 drill-down。参考: https://www.interactivebrokers.co.uk/en/software/tws.bak/usersguidebook/specializedorderentry/understand_the_blotter_interface.htm
- Bloomberg EMSX Order Blotter: 执行台表格应围绕订单序列、side、type、broker 等执行字段组织。参考: https://es.mathworks.com/help/datafeed/emsx.emsxorderblotter.html
