# 原型冻结前 Polish 整改结果

> 日期：2026-05-10
> 范围：`prototype/` active route prototypes
> 上游：`docs/plans/2026-05-10-prototype-freeze-shape-brief.md`
> 质量档位：冻结候选可交接

## 1. 设计系统对齐

本轮按 product register 执行 `impeccable polish`，优先对齐 Ditto Graphite Studio 和冻结标准，不重开视觉语言。

依据：

- `PRODUCT.md`：克制、可信、敏锐；判断先于操作。
- `DESIGN.md`：OKLCH token、L1/L2/L7 颜色语义、density preset、shell 尺寸、domain signature。
- `design/specs/00_ditto_visual_constitution.md`：主工作面、导航退后、颜色双维表达、长期稳定感。
- `design/specs/11_ditto_page_pattern_library.md`：每个 active prototype 只有一个 Primary Answer。
- `.agents/skills/impeccable/reference/product.md` 和 `.agents/skills/impeccable/reference/polish.md`：product UI 以稳定、熟悉、可扫视为优先。

Drift 处理原则：

| Drift 类型 | 本轮处理 |
|---|---|
| Missing token | `--surface-noise-opacity` 回到已批准 prototype structural token 值 `0.018` |
| One-off implementation | 表格 hover 移除装饰性 inset glow，回到背景和边界反馈 |
| Conceptual misalignment | Cross-Market pair chart trigger 不再伪装成 correlation data cell |

## 2. P0 冻结门禁

| 门禁 | 处理结果 | 文件 |
|---|---|---|
| Reduced motion 覆盖缺口 | Cross-Market `tab-reveal` 和 pair chart、Trading Overview `flow-pulse` 增加 targeted reduced-motion 覆盖 | `page-cross-market.html`, `page-trading-overview.html` |
| Non-color semantics | Cross-Market 相关矩阵的 pair chart 触发器移出 `data-corr` 数据格合同，避免被当成无符号相关系数 | `page-cross-market.html` |
| 11px operational typography | Cross-Market pill tabs、Agent batch buttons、Backtest/Portfolio benchmark selector、Portfolio exposure name 提升到 `--font-size-12` | `page-cross-market.html`, `page-agent-console-v2.html`, `page-backtest-result.html`, `page-portfolio.html` |
| Prototype structural dimension token | `--surface-noise-opacity` 与规范和测试合同对齐为 `0.018` | `tokens-style.css` |
| Decorative glow budget | 表格 hover 移除 `box-shadow` 侧向高亮，保留 tokenized hover background 与边界反馈 | `shared/layout-components.css` |
| Active prototype direct `oklch(` | Agent Console v2 source tag fallback 改为既有 `--cyan-500`、`--purple-500` token | `page-agent-console-v2.html` |
| Instrument Hub tab ARIA | Bottom tabs 补齐稳定 tab id 和 tabpanel `aria-labelledby`，消除 orphan tabpanel | `page-instrument-hub.html` |
| Tooltip / command / tab / drawer / batch action ARIA | 当前一致性合同已通过，无新增修改 | shared prototype interaction contract |

## 3. P1 / P2 Recommended Route

| 路线 | 完成状态 | 交付证据 |
|---|---|---|
| P1-A Catalog 家族任务差异化 | 完成 | Strategy、Backtest、Experiment、Factor、Watchlist、Universe 均有 task-specific summary、行内 sparkline/micro bar/heat signal、stale 标记和 sticky detail summary |
| P1-B Home 主答案收束 | 完成 | `global-pulse` 单条背景事实、唯一 `decision-card[data-primary-answer]`、`pending-actions` 默认只露出 P1/P2、data health 普通健康项降权 |
| P1-C Agent Console 透明度 | 完成 | Finding source tags、confidence bar + 数字、审批后果说明、批量操作预计敞口影响已存在并通过 P0 token 收口 |
| P1-D Trading / Portfolio 数据扫描增强 | 完成 | Trading positions 使用 price flash 和 sparklines；Portfolio 使用 PnL 曲线、benchmark line、drawdown zone、exposure heat；Backtest/Portfolio benchmark selector 统一到 12px |
| P2 Cross-Market 小步深化 | 完成 | 相关矩阵 tooltip、pair chart 展开、macro drivers bar 与 impact panel 已存在；本轮补齐 reduced motion 和数据格语义边界 |

## 4. 验证状态

已通过：

```bash
bun vitest run scripts/prototype-design-consistency.test.ts
```

结果：102 tests passed。

最终通过：

```bash
bun run check
```

结果：Biome 通过，`tsc -b` 通过，145 test files / 1768 tests passed。

补充说明：全量验证暴露 archived AI Copilot overlay close 的并发点击脆弱点，已将 3 个 overlay close 从 inline `onclick` 改为纯 label/checkbox 合同，并通过 `scripts/page-ai-copilot-prototype.test.ts`。

## 5. React 落地阶段保留项

本轮没有新增 token、新依赖、CI/CD 配置或架构边界变更。剩余工作进入 React 落地阶段：

- 将 prototype-only interaction contracts 映射到 React 状态机和组件 API。
- 将图表占位替换为正式 lightweight-charts / data-viz 实现。
- 将 panel width、column width、density preference 等专家效率合同持久化。
- 将 page contract 的 visual audit 状态从 queued 推进到 verified。
