# Strategies Detail Design Cycle Review

**目标**: `/ditto-design-cycle page-strategies-detail.html --iterate --goal 10 --max-rounds 100 --level best`
**日期**: 2026-04-26
**对象**: `docs/designs/specs/prototypes/page-strategies-detail.html`
**结果**: 9.7 / 10（best 级 Object Hub 精修，已保持 reviewed，未标记 done）

## 结论

本轮把 Strategy Detail 从 9.2 的高分静态原型推进到可稳定复审的 Object Hub：

- 修复 Gate P0：恢复 shell DOM 结构，`shell-hub` 重新包住 rail/header/meta/tabs/main/bottom。
- 补齐门禁识别：根节点加入 `object-shell`，main/sidebar contract slot 下沉到真实可见区域。
- 将 tab group 接入 shell grid，主工作面贴合 bottom strip，标准视口不再留下大块空白。
- 收紧概览布局：策略状态保持紧凑，净值图承接多余高度，近期回测 3 行在 compact 视口完整可见。
- 移除 KPI `data-ticker` 截图动画，默认指标值稳定为最终数值。
- 图表坐标文字改为 tokenized CSS 类，消除硬编码 `font-size`，并修复 HS300 标签裁切。
- 新增 `scripts/page-strategies-detail-prototype.test.ts`，覆盖 shell、contract slot、无 inline style、截图稳定性、compact 裁切和图表标签边界。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.8 | 仍保持零 inline style、暗色终端克制语言，只修复信息型布局与可读性问题 |
| 一致性 | 9.7 | Object Hub shell、contract slot、tab grid、manifest 口径与 Instrument Hub / Backtest Result 对齐 |
| 高级感 | 9.7 | 净值图、KPI、右侧 context rail 和 frosted header 更稳定，视觉噪声低 |
| 品牌方向 | 9.7 | Research 策略对象中心路径清晰，Bloomberg/quant desk 信息密度与 Linear 式克制并存 |
| 信息效率 | 9.8 | 首屏稳定呈现 KPI、状态、净值趋势、Top3 回测、Universe/信号/风控上下文 |
| 综合气质 | 9.7 | P0/P1/P2 为 0；未虚报 10，剩余差距来自静态原型交互上限 |

## 验证

```bash
bunx vitest run scripts/page-strategies-detail-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-strategies-detail.html --out-dir test-results/ditto-design-cycle-gates/strategies-detail-final
bun run check
```

结果：

- Targeted tests: 9 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/strategies-detail-final/page-strategies-detail.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/strategies-detail-final/page-strategies-detail.html-VP-COMPACT.png`
- `bun run check`: 未通过，阻塞在既有 `src/` TypeScript 错误；本轮改动未触碰这些失败文件。

静态审计：

- inline styles: 0
- default-view `data-ticker` / `data-counter`: 0
- SVG text hard-coded `font-size`: 0
- gate-recognizable shell: PASS
- manifest status: `reviewed`, score `9.7`

## Benchmark Notes

- Bloomberg Terminal UX: 参考“隐藏复杂性”、避免 workflow disruption，同时允许用户看到更多/更少数据行列的密度策略。<https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/>
- Bloomberg design ethos: 参考让用户快速找到并解析信息的金融终端价值取向。<https://www.bloomberg.com/company/stories/bloombergs-customer-centric-design-ethos/>
- Linear UI refresh: 参考高信息密度产品中降低视觉噪声、保持 alignment、提升导航层级密度的做法。<https://linear.app/blog/how-we-redesigned-the-linear-ui>
- Linear latest refresh: 参考信息密集界面中“不是所有元素都应有同等视觉重量”的分层原则。<https://linear.app/now/behind-the-latest-design-refresh>

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，离真实顶级策略对象页还差三类能力：

- Tab 内数据不会真实联动：版本选择、回测对比、信号跳转和右侧上下文仍是静态样本。
- 净值图没有真实十字线、缩放、hover tooltip、数据刷新和 stale 衰减。
- 编辑、提交回测、复制、删除等动作未接入 React 状态机、API、权限和异步反馈。

进入 React 实现或增强交互原型后，才有合理空间冲击 9.8-10。
