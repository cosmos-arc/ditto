# Ditto 原型设计一致性审查报告

**日期**：2026-04-27  
**范围**：`docs/designs/specs/prototypes/` 29 个 route prototype、`docs/designs/specs/*`、`docs/contracts/pages/*`、`.arch-manifest.json`  
**边界**：只审查原型设计与设计契约，不评价 React 功能实现质量。

---

## 1. 总体结论

当前 Edition v1 的原型视觉完成度高：29 个 route prototype 已经统一加载 Graphite Studio token、共享 shell/overlay/toggle 基础层，并且全部具备 `view-default / view-states / view-overlays` 三段式原型视图。页面第一眼的专业工作台气质成立，主工作面、右侧辅助区、底部分析/状态区的语法也总体稳定。

但如果从“候选原型到功能完整落地”的角度看，当前仍不建议直接批量推进。主要问题不是单页好不好看，而是**原型真实结构、蓝图、contract、manifest 的登记口径不一致**：

1. Shell Family 有 3 个关键 drift：`/markets`、`/platform/agents`、`/research/experiments`。
2. Overlay 在原型中已经普遍可触发，但 manifest 仍把 19 个有 overlay 的页面标为 `overlayStatus: none`，contract 只登记了 6 个 overlay。
3. AI Overview / AI Copilot 已在 `.arch-manifest.json` 标为 deprecated，但 edition manifest 仍放在 reviewed route page 队列中。
4. Typography / token 文档口径分裂：`DESIGN.md` 与实际 `tokens-base.css` 是 9 级字号，`15_ditto_token_stabilization_spec.md` 仍写 R1 精简为 6 级。
5. 弹层组件类名和画廊预览方式仍有页面局部变体，后续应统一为 Registry 驱动。

**结论**：原型视觉层可以保留为主方向；落地前必须先修正 manifest / contract / overlay registry，让候选原型的“页面骨架、状态、弹层”变成可消费的设计合同。

---

## 2. 量化快检

| 项目 | 当前结果 | 判定 |
|---|---:|---|
| route prototypes | 29 | 通过 |
| 三段式原型视图 | 29/29 | 通过 |
| 实际 `style="..."` 属性 | 0 | 通过 |
| 原型 overlay id | 98 | 需进入 registry |
| contract 已登记 overlays | 6 | 不达标 |
| `overlayStatus: none` 但实际有 overlay 的页面 | 19 | 不达标 |
| 使用 `--font-size-11/18/20/28` 的 route pages | 22 | 文档口径冲突 |
| 负 `letter-spacing` 的 route pages | 11 | 建议收敛 |
| 直接 `rgba()` 的 route pages | 3 | 应 token 化 |
| 直接非相对 `oklch()` 的 route pages | 10 | 应分级处理 |

> 注：`token-showcase` 是 token specimen，不应按 route prototype gate 评价。

---

## 3. P1 不达标项

### P1-1：Shell Family 真源漂移

| 页面 | 蓝图 / spec | 实际 prototype | edition / contract | 判定 |
|---|---|---|---|---|
| `/markets` | `shellFamily: radar` | `shell-radar` | `analytical` | contract/manifest 错 |
| `/platform/agents` | `shellFamily: studio` | `shell-agent studio-shell` | `ops-console` | contract/manifest 错 |
| `/research/experiments` | `shellFamily: catalog` | `shell-catalog catalog-shell` | `ops-console` | contract/manifest 错 |

影响：视觉原型本身选型是对的，但 contract 会把页面落到错误 layout 家族，导致后续实现按错误 slot、错误 responsive 行为、错误组件语气落地。

更优选择：

- `/markets` 维持 Radar，和 `/markets/a-shares` 同族。
- Agent Console 维持 Studio，而不是 Ops Console。它的核心是 Plan / Run / Finding / Tool Trace 的构建与编排，不是纯运维处置台。
- Experiment List 维持 Catalog。它是实验对象列表与详情 drawer，不是告警/任务排障控制台。

### P1-2：Overlay Registry 没有跟上原型真实状态

`.arch-manifest.json` 写着 overlay registry 已 “contract-driven”，但当前事实是：

- 29 个 route prototype 中共有 98 个 overlay id。
- 19 个实际有 overlay 的页面仍登记为 `overlayStatus: none`。
- `docs/contracts/pages/*` 只登记了 6 个 overlays。

这会让后续落地无法判断某个弹层是：

- 必须进入默认工作流的真实交互；
- 只作为画廊 specimen；
- 还是 deprecated / archived 的展示资产。

统一口径：

| 层级 | 作用 | 是否进入功能落地 |
|---|---|---|
| `#default-view` | 产品默认工作流，必须包含真实 trigger 与隐藏的 overlay shell | 是 |
| `#states-gallery` | 组件状态样本：loading / empty / failed / stale / selected / bulk | 否，作为验收样本 |
| `#overlays-gallery` | 弹层视觉 specimen，展示 modal / sheet / drawer / toast 的最终样式 | 否，作为视觉样本 |
| page contract `overlays[]` | 每个必需 overlay 的机器可读登记：id / kind / trigger / selector / requiredInDefaultFlow | 是 |

结论：弹窗画廊应统一保留在独立 `view-overlays` tab；默认页只保留真实工作流触发与实际 overlay shell。不要把画廊卡片混进页面主工作面，也不要只有画廊没有默认触发。

### P1-3：AI deprecated prototype 没有从候选 route 池分离

`.arch-manifest.json` 已声明 `deprecatedPrototypePages: ["ai-overview", "ai-copilot"]`，这与 IA v2.0 的方向一致：AI 不是一级域，Copilot 是全局 Sidecar，Agent Console 迁入 Platform。

但 `.edition-manifest.json` 仍把 `ai-overview`、`ai-copilot` 作为 reviewed route page 参与评分与覆盖统计。

更优选择：

- 保留 HTML 作为 `archived specimen`，用于复用交互/AI 组件语法。
- 从候选 route prototype 统计中分离，不再进入 29 route page 主队列。
- 全局 Copilot Sidecar 作为 shell-level overlay 另建 contract，而不是 route page。

### P1-4：Typography 规范与实际 token 冲突

当前 `DESIGN.md` 和 `src/styles/design-tokens/tokens-base.css` 均使用 9 级字号：10 / 11 / 12 / 13 / 14 / 16 / 18 / 20 / 24。  
`15_ditto_token_stabilization_spec.md` 仍写 R1 精简为 6 级，并将 11 / 18 / 20 标为 deprecated。

实际 prototype 中 22 个 route pages 使用了 11 / 18 / 20，说明 6 级方案并没有成为真实约束。

更优选择：

- 采用 9 级字号作为当前 Edition v1 的正式设计事实。
- `--font-size-11` 只用于 tight contexts，例如极窄表格元数据、图例、右栏辅助值。
- `--font-size-20` 只用于少量关键数字或对象级标题，不进入普通 panel 标题。
- 把负 `letter-spacing` 收敛为 0；数字清晰度用 `tabular-nums / slashed-zero / font-family-numeric` 解决。

### P1-5：弹层组件命名仍有局部变体

当前页面中同时存在：

- `overlay-sheet`
- `overlay-drawer`
- `overlay-modal`
- `drawer-sheet`
- `modal-sheet`
- 页面级 `overlay-btn` / `modal-btn` / `drawer-field`

视觉上大多可用，但作为原型到功能的中间合同不够稳定。

更优选择：

```text
overlay-backdrop
overlay-surface
overlay-surface--drawer
overlay-surface--sheet
overlay-surface--modal
overlay-surface--toast
overlay-header
overlay-title
overlay-close
overlay-body
overlay-actions
overlay-field
```

Drawer / Sheet / Modal 的差异由 modifier 和 contract `kind` 表达，不再靠每个页面自己发明一套类名。

---

## 4. P2 质量建议

### P2-1：页面局部 CSS 过多，应逐步沉淀共享原型语法

29 个 route prototype 已做到 0 actual inline style attributes，这是好事。  
但大量重复的 overlay、button、gallery、drawer field、state card 样式仍散在 page-local `<style>` 中。

建议优先沉淀到共享层：

- overlay surface / field / actions
- state card / gallery card preview
- table selected / bulk action bar
- drawer detail row
- compact panel header

### P2-2：颜色 token 仍有可替换硬编码

目前 route pages 中仍有：

- 3 个页面使用 `rgba()`；
- 10 个页面使用直接 `oklch()`；
- 若是 `oklch(from var(...))` 这种相对 token，可接受；
- 若是裸色值、shadow 黑色、白色混入，应迁移到 semantic / overlay / chart token。

建议优先处理：

- `page-portfolio.html` 的 `rgba()` overlay/shadow；
- `page-platform-settings.html` 的 `rgba()` backdrop/shadow；
- `page-a-shares.html` 的 treemap 局部裸色；
- `page-agent-console.html` donut JSON 中的裸 `oklch()`。

### P2-3：Visual audit 状态仍是 `missing`

Edition manifest 中 29 个 route pages 的 `visualAuditStatus` 大多仍是 `missing`。这不影响当前原型静态评审，但影响候选稿进入功能后做 prototype-vs-runtime 对齐。

建议：prototype 阶段可以先不跑 React visual audit，但至少将 route prototype 的基准截图、关键 slot selector、overlay selector 固化到 contract。

---

## 5. 已做得更好的设计选择

1. **三段式原型视图是正确方向**  
   `页面设计 / 状态画廊 / 弹层画廊` 的分离让默认页保持干净，也让状态覆盖能被持续审计。

2. **Radar 不应退回 Analytical**  
   `/markets` 与 `/markets/a-shares` 的扫描、比较、下钻任务与普通 analytical 页不同。Radar 是更优选择。

3. **Catalog 列表族的收敛是正确方向**  
   Watchlist / Factor List / Strategy List / Backtest List / Universe List 等列表族使用 Catalog，比各自发明半个 dashboard 更利于落地。

4. **Agent Console 采用 Studio 语气更合理**  
   Agent 的核心不是系统告警，而是 plan / run / evidence / approval 的编排工作台。Studio 更贴近任务。

5. **高密度不是问题，缺少合同才是问题**  
   当前页面密度整体符合量化工作台定位。不要为了“统一”把页面变松、变卡片化；应该统一 slot、overlay、state 和 token 口径。

---

## 6. 建议整改顺序

1. 修正 `.edition-manifest.json` 与 `docs/contracts/pages/*` 的 3 个 Shell drift：cross-market、agent-console、experiment-list。
2. 建立 overlay registry：把 98 个 prototype overlay id 全量登记到 page contracts。
3. 更新 overlayStatus：有默认页 trigger 的页面不应继续标 `none`。
4. 将 AI Overview / AI Copilot 从 route candidate 队列移入 archived specimen。
5. 统一 Overlay class grammar，先沉淀 shared CSS，再逐页替换。
6. 对齐 Typography 文档：Edition v1 采用 9 级字号；负 letter-spacing 归零。
7. 清理裸 `rgba()` 与裸 `oklch()`，仅保留相对 token 或明确的数据可视化例外。

---

## 7. 验收标准

下一轮只聚焦原型设计时，建议用以下标准判定“可进入功能落地”：

- 29 个 route prototype 保持三段式视图一致。
- 每个 route 的 `shellFamily` 在蓝图、edition manifest、contract、HTML root class 四处一致。
- 每个 blueprint Overlay Registry 都有 contract `overlays[]` 记录。
- 每个 required overlay 在 `#default-view` 有 trigger，在 `#overlays-gallery` 有 specimen。
- 状态画廊只放状态，不放真实业务弹层。
- 弹层画廊只放 specimen，不承担产品默认工作流。
- route pages 继续保持 0 actual inline style attributes。
- 字号、间距、圆角以 `DESIGN.md` + `tokens-base.css` 当前事实为准，spec 文档同步更新。
