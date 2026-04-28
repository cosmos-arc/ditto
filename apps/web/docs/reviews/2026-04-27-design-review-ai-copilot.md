# AI Copilot Design Cycle Review

**目标**: `/ditto-design-cycle page-ai-copilot.html --iterate --goal 10 --max-rounds 100 --level best`  
**日期**: 2026-04-27  
**对象**: `docs/designs/specs/prototypes/page-ai-copilot.html`  
**结果**: 9.6 / 10（best 级静态 Copilot Studio 收敛，未虚报 10）

## 结论

本轮将 AI Copilot 从「视觉可用但 design-cycle 门禁失败」推进到可稳定验收的 Studio 原型：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿。
- 修复 Gate P0：`.shell-copilot` 同时暴露为 `.shell-studio`，并补齐 rail/header/sessions/main/sidebar contract slots。
- 修复 Gate P0：status bar 从 fixed/sticky 遮挡层改为文档流底栏，compact 视口不再压住会话、因子表和右侧操作。
- 移除 mode tab 的静态 `.active` class，避免切换后出现双 active 视觉状态。
- 右侧三张可执行操作改为整张卡触发 overlay，不再只有局部文字或箭头可点击。
- 新增 `scripts/page-ai-copilot-prototype.test.ts`，覆盖 shell/contract、mode tab、overlay、三区切换、compact status bar 与零 inline style。
- `.edition-manifest.json` 中 ai-copilot 分数推进为 9.6，并记录本轮审查 note。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.6 | 保持四栏终端密度；修复遮挡与死点击，没有增加装饰负担 |
| 一致性 | 9.7 | Shell class、contract slot、三栏/三区门禁和 reviewed 页面口径对齐 |
| 高级感 | 9.5 | Thinking chain、置信度、证据链、结构化输出已具备 AI 研究工作台气质 |
| 品牌方向 | 9.3 | A 股因子研究语义明确，但 `/ai/copilot` 已被 v2 IA 升级为全局 Sidecar，独立页面天然折损 |
| 信息效率 | 9.7 | 首屏可扫会话、对话、因子假设、证据链和后续动作；关键动作可整卡触发 |
| 综合气质 | 9.6 | P0/P1 为 0；剩余差距来自静态 HTML 与 deprecated 独立路由上限 |

## 验证

```bash
bunx vitest run .claude/skills/ditto-design-cycle/scripts/verify-gates-core.test.mjs scripts/page-ai-copilot-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-ai-copilot.html --out-dir test-results/ditto-design-cycle-gates/ai-copilot-final
bun run check
```

结果：

- Targeted tests: 12 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/ai-copilot-final/page-ai-copilot.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/ai-copilot-final/page-ai-copilot.html-VP-COMPACT.png`
- `bun run check`: 未通过。Biome 阶段通过，阻塞在仓库既有 `src/` TypeScript 错误；本轮改动未触碰这些失败文件。代表性错误包括 Vitest 全局类型未导入、`data-table` 泛型不匹配、TanStack Router `handle` 类型不被当前类型接受、`src/types/index.ts` 重复导出和若干 API 类型命名漂移。

## Benchmark Notes

- Bloomberg Terminal Essentials: Launchpad / Worksheets 强调实时工作区与可定制布局，本轮保留四栏高密度结构并修复底部状态栏遮挡。<https://www.bloomberg.com/professional/insights/technology/bloomberg-terminal-essentials-ib-worksheets-launchpad/>
- Bloomberg Terminal UX: 复杂度应隐藏在连续工作流里，本轮将局部可点击动作改为整卡触发，减少“看起来能点但点不到”的干扰。<https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/>
- Linear UI redesign: 参考 sidebar、tabs、headers、panels 的低噪声对齐与导航密度，本轮修正 mode tab active 状态与 shell contract 一致性。<https://linear.app/blog/how-we-redesigned-the-linear-ui>
- Cursor Composer / Agent interface: 参考 AI 工作流中“产出可审阅、可继续行动”的界面模式，本轮强化结构化输出后的可执行动作闭环。<https://cursor.com/blog/2-0>

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，且 v2 IA 已明确 `/ai/copilot` 不再作为独立路由，而是升级为全局 Copilot Sidecar。剩余差距主要来自：

- 四种 Copilot mode 尚未驱动真实上下文、prompt schema、输出 schema 和路由来源。
- 对话、证据链、因子假设、发送到工作区仍是静态样本，缺少真实状态机、流式输出和失败恢复。
- 右侧行动卡不会根据当前选中消息或证据链实时联动目标工作区。
