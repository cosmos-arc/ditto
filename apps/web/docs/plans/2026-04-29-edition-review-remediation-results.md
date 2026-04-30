# Edition Review Remediation Results

> 日期：2026-04-29
> 计划：`docs/plans/2026-04-29-edition-review-remediation-plan.md`
> 范围：27 个活跃 reviewed 原型、共享 prototype CSS、规范文档、review scoring 参考、回归截图资产

## 总结

本轮完成了 2026-04-28 Edition Review 与 Pro Max Review 中无需产品决策的系统精修项：

- Pro Max 基线：共享 CSS 结构、token 引用、`oklch(from...)`、skip link / title / viewport / heading / reduced-motion 门禁。
- Bottom Tray：Strategy Studio、Agent Console、Platform、Trading Overview 接入 `collapsed / peek / expanded` 合同。
- 数据可视化：A Shares、Cross Market、Risk Center、Regime Monitor、Factor Analysis、Backtest Result 增加非颜色编码。
- Command 可发现性：全局 command 暴露 `Ctrl+K` 与 `data-command-scope="global"`，本地搜索使用 `data-local-search`。
- Light / density 视觉矩阵：7 类 Shell × 4 偏好截图，共 28 张。
- Catalog 家族：sticky summary、selected marker、batch action bar、danger confirmation。
- 高风险动作：impact summary、confirm、cancel、recovery hint、非颜色危险标记。
- 专家效率：`data-primary-answer`、`data-selected-object-region`、Studio / Agent React parity 槽位。

## 主要变更

| 区域 | 变更 |
|------|------|
| 共享 CSS | 修复 `.filter-select::after` 游离声明；补 prototype-local token；新增 Bottom Tray、Data Viz、Catalog、Danger、skip-link 基线样式。 |
| 活跃原型 | 27 页补齐 Command 语义、搜索作用域和 `oklch(from...)` 收敛；代表页补齐 Bottom Tray、非颜色编码、危险确认和专家效率标记。 |
| 测试 | 扩展 `prototype-design-consistency.test.ts`；新增 `prototype-expert-efficiency.test.ts`；新增 visual matrix 测试与脚本；修正 A Shares 测试对 `color-mix()` 的预期。 |
| 文档 | 更新 Interaction、Page Pattern、Data Views、Component、Shell Chrome、review scoring、quality levels；新增 Pro Max triage 与本结果报告。 |
| 审查资产 | 刷新 `test-results/edition-gates/*`、`test-results/edition-review/per-page/*`、standard / compact contact sheets、visual matrix。 |

## Before / After 风险表

| 风险 | Before | After |
|------|--------|-------|
| Bottom Tray 压缩主工作面 | Studio / Ops 底部日志缺少统一三态合同 | 4 个代表页具备 `data-bottom-tray`、状态、toggle、content 合同，27 页 gates 通过。 |
| 色觉依赖 | 热力图 / 矩阵部分依赖红绿或透明度 | 6 个代表页具备 legend、sign、threshold、strong / selected cell 标记。 |
| Command 作用域模糊 | icon-only command 与本地搜索可发现性不足 | 全局 command 有 `Ctrl+K` label / title / scope，本地输入有 `data-local-search`。 |
| Light mode 审计不足 | 主要审阅集中在 dark default | 新增 28 张 visual matrix 截图，覆盖 7 类 Shell 的 light / dark 与 compact / comfortable。 |
| 高风险动作缺恢复语境 | 删除、暂停、回滚等动作影响面不够结构化 | 代表页具备影响摘要、确认、取消、恢复提示和非颜色危险标记。 |
| 评分虚高 | 9.x 页面缺少专家效率扣分项 | review-scoring / quality-levels 增加 5 秒主答案、选中联动、非颜色关键状态、紧凑主流程等门槛。 |

## Pro Max 结论处置

| 结论 | 处置 |
|------|------|
| 29 页统计 | superseded：当前 manifest 为 27 个活跃 reviewed 原型。 |
| `.filter-select::after` 游离声明 | fixed：共享 CSS 修复并纳入测试。 |
| missing token references | fixed：prototype-local alias 补齐；无新增产品级 semantic token。 |
| `oklch(from...)` 活跃页使用 | fixed：活跃原型与共享 CSS 收敛为 `color-mix(in oklch, ...)`。 |
| title / viewport / skip-link / heading / aria baseline | fixed：当前扫描缺口已补齐，并有机器门禁。 |
| reduced-motion fallback | fixed：共享层补齐 fallback。 |
| Zone / contract-slot 覆盖不均 | fixed / recalibrated：以 27 页 manifest 为准重扫；Studio / Agent 专家槽位已补齐。 |
| z-index / line-height / letter-spacing 系统治理 | partially fixed：负字距与 CSS 基线纳入门禁；更大 token 语义治理延后。 |
| 全量响应式重构 | deferred：本轮只覆盖桌面工作台与 1366x768 紧凑视口。 |
| Design Token 语义新增 | requires approval：本轮没有提升为产品 token。 |

## 剩余 P2 / P3

- 角色化密度预设：Research-Heavy / Trading-Heavy / Platform-Heavy。
- Copilot 输出进入 Signals / Strategy Studio 的审批策略细化。
- Agent Finding 生命周期与 Signal 状态机边界。
- A 股扩展交易规则，例如可转债 T+0。
- 更大规模 CSS token 语义迁移与本地 CSS 去重。
- 移动 / 极窄视口另立计划。

## 验证结果

| 命令 | 结果 |
|------|------|
| `bun test scripts/prototype-design-consistency.test.ts` | PASS，29 tests。 |
| `bun test scripts/prototype-view-preferences.test.ts` | PASS，3 tests。 |
| `bun test scripts/prototype-expert-efficiency.test.ts` | PASS，6 tests。 |
| `bun test scripts/page-a-shares-prototype.test.ts` | PASS，5 tests。 |
| `bun test scripts/prototype-expert-efficiency.test.ts scripts/prototype-design-consistency.test.ts scripts/prototype-view-preferences.test.ts scripts/page-home-prototype.test.ts scripts/page-strategy-studio-prototype.test.ts scripts/page-agent-console-prototype.test.ts` | PASS，58 tests。 |
| 27 页 `bun run prototype:gates -- --prototype ...` loop | PASS，27/27；blocking 0；non-blocking 0。 |
| `bun run prototype:visual-matrix` | PASS，生成 28 张截图。 |
| `bun run check` | PASS，137 test files；1515 tests。 |
