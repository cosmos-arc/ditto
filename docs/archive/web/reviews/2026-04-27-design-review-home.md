# Home Design Cycle Review

**目标**: `/ditto-design-cycle page-home.html --iterate --goal 10 --max-rounds 100 --level best`
**日期**: 2026-04-27
**对象**: `docs/designs/specs/prototypes/page-home.html`
**结果**: 9.7 / 10（best 级门禁通过，未标记满分）

## 结论

本轮在既有 Graphite Studio 方向上做稳定性与可操作性精修，没有引入新的产品范围：

- 默认视图移除 `data-ticker` / `data-counter`，避免 NumberTicker/AnimatedCounter 在截图采集窗口内生成非确定数值。
- 折叠队列中的 P2/P3 项移除 `data-reveal`，避免 `<details>` 打开后仍保留 ScrollReveal 的透明/位移初始态。
- 决策横幅主 CTA「信号详情」接入既有 `overlay-signal-detail` drawer，首屏关键动作不再只是视觉按钮。
- 新增 `scripts/page-home-prototype.test.ts`，覆盖截图确定性、折叠队列可见性、零 inline style、主 CTA overlay 行为。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.7 | 延续低饱和暗色工作台，不靠新增装饰提分 |
| 一致性 | 9.8 | 默认视图截图确定性提升，状态/overlay 数量与结构保持稳定 |
| 高级感 | 9.7 | 关键数值、主 CTA、折叠内容进入更可靠的验收状态 |
| 品牌方向 | 9.7 | 保持金融终端式信息密度与 Home orient/dispatch 定位 |
| 信息效率 | 9.6 | 首屏可扫视核心风险、待办、活动流和数据健康；仍受静态原型联动上限限制 |
| 综合气质 | 9.7 | P0/P1 为 0；未伪造 10 分 |

## 验证

```bash
bunx vitest run scripts/page-home-prototype.test.ts
bunx vitest run .claude/skills/ditto-design-cycle/scripts/verify-gates-core.test.mjs scripts/page-home-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-home.html --out-dir test-results/ditto-design-cycle-gates/home-final
bun run check
```

结果：

- Home prototype tests: 4 tests passed
- Gate core + Home prototype tests: 11 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/home-final/page-home.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/home-final/page-home.html-VP-COMPACT.png`

静态审计：

- inline styles: 0
- duplicate ids: 0
- default-view `data-ticker` / `data-counter`: 0
- collapsed queue `data-reveal`: 0
- state gallery cards: 25
- overlay gallery cards: 4

全量验证状态：

- `bun run check` 已执行；Biome 阶段通过。
- `tsc -b` 仍被仓库既有 TypeScript/test 类型问题阻断，失败分布在 `src/components/chart/*`、`src/components/data/*`、`src/routes/*`、`src/types/*`、`src/mocks/*` 等非本轮原型文件。本轮未修改这些文件。

## 未达 10 的原因

不虚报 10。当前 Home 仍是 HTML/CSS 静态原型，距离真正满分还有三类上限：

- 首屏 CTA 只接入了已有 drawer，研究/风控路径仍缺少真实路由与状态迁移。
- 市场脉搏、数据健康、活动流仍是静态快照，未体现真实数据老化、推送更新和异常恢复。
- Home 与 React 实现之间的动态联动、键盘路径和审计日志还需要在 app-dev 阶段补齐。

## Benchmark Notes

- Bloomberg Terminal UX 的核心启发是“隐藏复杂性而不牺牲可操作信息密度”，本轮优先修截图与动作可靠性，而非继续堆视觉效果。参考: https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/
- Linear 的近期设计刷新强调在保持信息密度的同时降低噪音；本轮移除动态截图噪声，保留工作台密度。参考: https://linear.app/now/behind-the-latest-design-refresh
