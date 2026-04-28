# AI Overview Design Cycle Review

**目标**: `/ditto-design-cycle page-ai-overview.html --iterate --goal 10 --max-rounds 100 --level best`  
**日期**: 2026-04-26  
**对象**: `docs/designs/specs/prototypes/page-ai-overview.html`  
**结果**: 9.7 / 10（CSS 静态原型阶段上限区间，未标记 done）

## 结论

本轮将 AI Overview 从“视觉可用但 compact 门禁失败、关键交互有断点”推进到可稳定审查的 best 级原型：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿
- 修复 Overview tab panel 高度约束，Compact 视口下两个主 panel 不再压到状态栏外
- 将 `data-tabs` 作用域移动到 `.ai-main`，三枚 tab 与三个 panel 处在同一个交互容器内
- 顶部 Copilot / Agent CTA 从视觉按钮改为真实 toast 触发器，和底部 action card 行为一致
- 右侧 rail 从每个 section 内部微滚动改为整栏自然滚动，避免“AI 状态概览”统计卡被截断
- 新增原型回归测试，覆盖 tab 作用域、toast 触发、右栏滚动策略、状态/弹层覆盖与零 inline style

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.7 | 保持暗色终端密度，修复右栏截断后没有增加额外装饰噪声 |
| 一致性 | 9.8 | tab、toast、三区、右栏滚动与共享交互库口径一致 |
| 高级感 | 9.6 | AI pulse、confidence bar、activity timeline 和轻微材质感足够成熟 |
| 品牌方向 | 9.5 | 金融终端气质明确，但 `/ai` 独立域本身已被 v2 IA 标记为 deprecated |
| 信息效率 | 9.8 | 首屏可扫视运行中 Plan、待审批 Finding、Copilot 产出、资源用量与置信度 |
| 综合气质 | 9.7 | P0/P1 为 0，交互闭环完整，剩余差距主要来自静态原型与 deprecated 路由天花板 |

## 验证

```bash
bun run test:run scripts/page-ai-overview-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-ai-overview.html --out-dir test-results/ditto-design-cycle-gates/ai-overview-final
```

结果：

- `scripts/page-ai-overview-prototype.test.ts`: 5 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/ai-overview-final/page-ai-overview.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/ai-overview-final/page-ai-overview.html-VP-COMPACT.png`

补充浏览器交互复核：

- Overview / Models / Signals 三个 tab 均可切换并设置 `aria-selected="true"`
- Header Copilot CTA 可打开并关闭 `overlay-new-session-toast`
- Header Agent CTA 可打开并关闭 `overlay-new-plan-toast`
- Bottom action card 可打开 `overlay-new-session-toast`

## Benchmark Notes

- Bloomberg Terminal / Launchpad：参考高密度监控、alerting 和动态工作区的终端式信息组织。<https://www.bloomberg.com/company/stories/innovating-a-modern-icon-how-bloomberg-keeps-the-terminal-cutting-edge/>
- Linear UI：参考低噪声 sidebar、tabs、headers、panels 对齐和导航密度。<https://linear.app/blog/how-we-redesigned-the-linear-ui>

## 未达 10 的原因

不虚报 10。本页已经接近 HTML/CSS 静态原型上限，但仍有三类非原型层可解的问题：

- v2 IA 已将 `/ai` 标记为 deprecated，AI Overview 内容应拆到 Home Agent Findings 与 `/platform/agents`；独立 `/ai` 页面天然存在品牌方向折损。
- tab、toast、数值刷新和状态栏仍是静态演示，缺少真实数据联动与 30s polling。
- Copilot Sidecar、Agent Console、Finding 审批链路尚未接入真实路由与上下文感知。
