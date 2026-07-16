# Prototype Best Review Remediation Results

> 对应计划：`docs/plans/2026-05-01-prototype-best-review-remediation-plan.md`

## 结果摘要

`docs/designs/specs/prototypes/` 已从可演示状态推进到 Best 级冻结候选。整改策略是先补机器门禁，再逐层修复共享交互、token 对比度、响应式 Shell、Primary Answer、Catalog 任务分化、专家效率与性能可维护性。

当前 active route prototypes 保持 27/27 覆盖；最终剩余风险已转入 React backlog 或标记为 prototype-only 例外。

## 原始 P0 / P1 问题

| 等级 | 问题 | 处理结果 |
|---|---|---|
| P0 | 19 个 active prototype 缺少语义 `<h1>`，style label 被辅助技术读取 | 已补语义 heading 与 `aria-hidden` 门禁 |
| P0 | `[role="button"]` 缺少键盘激活，tabs ARIA wiring 不完整 | 已由 shared interaction 与契约测试覆盖 |
| P0 | focus ring、reduced motion、CSS hygiene 缺少稳定门禁 | 已补 `:focus-visible`、reduced-motion、`100vh`、`transition: all`、tiny text 等 gate |
| P0 | contrast audit 存在 operational / data-critical fail | 已按 usage tier 修复，gating pairs 0 fail |
| P0 | active pages 缺少单一 Primary Answer 或主动作无法 drill down | 已覆盖每页单一 Primary Answer、动作目标与 visible text binding |
| P1 | Home 首屏缺少明确决策面 | 已改为 `global-pulse` + 唯一 `decision-card` |
| P1 | Catalog 家族 summary / inspector 同质化 | 已区分 Strategy、Backtest、Experiment、Universe、Factor、Watchlist 等子型 |
| P1 | A 股 Light Mode 热力图复用 Dark Mode 大色块基底 | 已改为页面本地 light scale，并保留 non-color marker |
| P1 | Catalog / Studio / Ops 缺少专家效率合同 | 已补 resizable persistence、table hooks、bulk bar、active filters、command context actions |
| P1 | shared JS / CSS 存在性能与维护性风险 | 已补 CSS var cache、MouseGlow RAF、DOM text node 构造、shell-scoped resize suppression、comfortable density |

## 主要变更文件

- `scripts/prototype-design-consistency.test.ts`
- `scripts/prototype-interaction-ux-contract.test.ts`
- `scripts/audit-wcag-contrast.mjs`
- `docs/designs/specs/prototypes/shared/layout-base.css`
- `docs/designs/specs/prototypes/shared/prototype-interactions.js`
- `docs/designs/specs/prototypes/tokens-style.css`
- active `docs/designs/specs/prototypes/page-*.html`
- `docs/designs/specs/04_interaction_state_spec.md`
- `docs/designs/specs/10_ditto_shell_family_spec.md`
- `docs/designs/specs/11_ditto_page_pattern_library.md`
- `docs/designs/specs/12_ditto_data_views_spec.md`
- `docs/designs/specs/14_ditto_token_naming_layering_spec.md`
- `docs/designs/specs/20_interaction_ux_audit.md`
- `docs/plans/prototype-to-react-enhancement-backlog.md`

## 验证证据

| Command | Result |
|---|---|
| `bun run audit:tokens:contrast` | 175 pairs checked; 135 pass, 29 metadata warn, 0 failed pairs, 0 unresolved, 11 decorative reports |
| `bun run build:tokens:check` | 354 tokens parsed from 9 layers; validation passed |
| `bun run prototype:interaction` | 29 tests passed |
| `bun run prototype:gates` | every active route prototype PASS |
| `bun run audit:routes` | 27 IA routes covered |
| `bun run check` | Biome + `tsc -b` + Vitest passed; 141 test files / 1599 tests |

## React Backlog Deferrals

Deferred implementation remains intentionally outside prototype scope and is recorded in `docs/plans/prototype-to-react-enhancement-backlog.md`:

- persisted table columns.
- frozen columns.
- full command palette implementation.
- selected object driven cross-region state.
- modal / drawer focus trap, ESC return focus, and inert overlay background.
- React resizable panel implementation pending dependency approval.

## Remaining Risks

- Table freeze / column persistence / command context are prototype contracts plus representative coverage; React needs real component tests for state, permission, keyboard and overflow behavior.
- Prototype-only Light Mode data-viz scale is a documented local exception until product token layers accept dedicated light data-viz scale.
- `prototype:gates` verifies professional desktop viewports, not a phone IA; mobile product shape remains out of scope for this plan.
