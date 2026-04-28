# Agent Console Design Cycle Review

**目标**: `/ditto-design-cycle page-agent-console.html --iterate --goal 10 --max-rounds 100 --level best`  
**日期**: 2026-04-27  
**对象**: `docs/designs/specs/prototypes/page-agent-console.html`  
**结果**: 9.7 / 10（best 级门禁修复 + 交互闭环，未伪造满分）

## 结论

本轮将 Agent Console 从「视觉上可用但 design-cycle gate 阻断」推进到可稳定验收的 best 级静态原型：

- 修复 `.shell-agent` 未被门禁识别的问题，为页面根 shell 补齐 `studio-shell` family 标识。
- 为右侧 Agent Detail 面板补齐 `data-contract-slot="detail"`，让 shell 区块映射满足门禁与下游合同消费。
- 将底部状态栏从 fixed / sticky 遮挡模型改为 default-view 正常流 footer，VP-STANDARD 与 VP-COMPACT 均不再覆盖 Plan 卡片或右侧操作区。
- 修复 Plans 内状态筛选的 `data-tabs` 作用域，`全部 / 运行中 / 已完成 / 失败` 四个筛选面板现在可真实切换。
- 移除默认视图 `data-ticker` 动画数值，保证截图审查可重复、可比较。
- 追加右侧 Detail 面板精修：面板宽度调整到 368px，Header meta 改为 2 列，当前 Agent 区块完整露出，底部操作按钮统一为 28px 等宽工作区动作。
- 收敛右栏状态颜色与字体：运行态改为低饱和 brand tint + 细左边界，section title 与 Tool Trace code badge 对齐 Strategy Studio / Platform 的 12px / 10px 层级。
- 新增 `scripts/page-agent-console-prototype.test.ts`，覆盖 shell 结构、状态栏布局、筛选交互、状态/弹层覆盖、零 inline style、重复 id 审计。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.7 | 三栏 Studio 工作台保持低噪声终端密度，状态栏不再漂浮遮挡内容 |
| 一致性 | 9.8 | shell family、contract slot、三区覆盖、filter tabs 和门禁脚本口径已对齐 |
| 高级感 | 9.6 | Agent pipeline、Tool Trace、资源仪表和输出物区块形成成熟的运行工作台语法 |
| 品牌方向 | 9.7 | 符合 Platform / Agent Console 定位，呈现 quant desk 的任务、日志、审批和证据链心智 |
| 信息效率 | 9.8 | 首屏可同时扫视 Plan 队列、执行阶段、右侧 Agent 状态、资源占用、Tool Trace 与产出物 |
| 综合气质 | 9.7 | P0/P1 为 0；剩余差距主要来自静态 HTML 阶段缺少真实状态机和数据联动 |

## 验证

```bash
bunx vitest run .claude/skills/ditto-design-cycle/scripts/verify-gates-core.test.mjs scripts/page-agent-console-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-agent-console.html --out-dir test-results/ditto-design-cycle-gates/agent-console-right-panel-final
bun run check
```

结果：

- Targeted tests: 17 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/agent-console-right-panel-final/page-agent-console.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/agent-console-right-panel-final/page-agent-console.html-VP-COMPACT.png`
- `bun run check`: 未通过；`biome check .` 已通过，失败发生在 `tsc -b`，错误来自仓库既有 TypeScript 问题（例如 `src/components/chart/chart-components.test.tsx`、`src/components/data/data-table/data-table.test.tsx`、`src/routes/*`、`src/types/*`），本轮未修改这些文件。

静态审计：

- inline styles: 0
- duplicate ids: 0
- default-view `data-ticker` / `data-counter`: 0
- state gallery cards: 19
- overlay gallery cards: 4

交互抽查：

- Plans 主 tab 与 Runs / Findings / Approvals radio tab 切换规则保持可用。
- Plans 内 `全部 / 运行中 / 已完成 / 失败` 筛选通过 Playwright 实测。
- Compact 视口下右侧当前 Agent 三个状态块完整可见，无分区内裁切。
- 右侧底部 `暂停 / 重跑 / 查看产出` 三个动作按钮为 28px、12px 字号、等宽居中，无文字溢出。
- 新建 Plan、审批确认、重跑、Tool Trace 四个 overlay 的触发器与 checkbox id 对应完整。
- default / states / overlays 三区 radio 切换结构完整。

## Benchmark Notes

- Bloomberg Terminal UX 参考点：复杂工作流用多 panel / tabbed workspace 承载，避免把复杂性堆成单一大面板。<https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/>
- Linear UI 参考点：通过降低视觉噪声、统一 header / tabs / panels、提升导航层级密度来增强可扫视性。<https://linear.app/blog/how-we-redesigned-the-linear-ui>

## 未达 10 的原因

不虚报 10。当前 HTML/CSS 原型已经通过结构、交互和视口门禁，但距离真实满分仍有静态介质无法兑现的部分：

- Agent Plan / Run / Finding / Approval 仍是 mock 数据，缺少真实状态机、轮询和错误回放。
- Detail 面板尚未根据选中 Plan / Run / Finding 做真实上下文联动。
- Tool Trace、资源占用、Confidence 和审批生成 Signal 的链路仍是静态展示，真实产品阶段需要接入数据源与路由反馈。
