# Pro Max Findings Triage

> 日期：2026-04-29
> 范围：`docs/designs/specs/prototypes/.edition-manifest.json`、27 个活跃 `page-*.html`、`shared/layout-base.css`
> 目的：把 2026-04-28 Pro Max Review 中仍然有效的结论校准为当前分支事实，避免沿用旧页数和旧缺口。

## 当前样本

| 指标 | 当前值 |
|------|-------:|
| manifest 页面总数 | 30 |
| 活跃原型 | 27 |
| reviewed 原型 | 27 |
| 已排除归档页 | `ai-overview`、`ai-copilot` |

Shell 分布：

| Shell | 页面数 |
|-------|-------:|
| radar | 2 |
| ops-console | 4 |
| command-center | 1 |
| catalog | 8 |
| analytical | 6 |
| object-hub | 4 |
| studio | 2 |

## 处理结论

| Pro Max 结论 | 当前状态 | 处理 |
|--------------|----------|------|
| 活跃页数量按 29 页统计 | 已过时 | 当前以 manifest 的 27 个 reviewed 活跃原型为准。 |
| `.filter-select::after` 后存在游离 CSS 声明 | 已确认 | 修复在 `shared/layout-base.css`，并加入结构测试。 |
| `layout-base.css` 有未解析 token | 已确认 | 低风险 prototype-local token 已补齐：`--shell-rail-radar-width`、`--brand-signature-glow`、`--risk-warning-fg`、`--surface-secondary`、`--radius-full`、`--space-1`。 |
| `oklch(from...)` 与 `color-mix()` 混用 | 已确认 | 活跃原型与共享 CSS 已收敛；归档 AI 原型仍保留旧写法，不纳入本轮活跃门禁。 |
| 多数页面缺少 Zone / proto-nav | 已过时 | 27 个活跃原型均由 `prototype-design-consistency.test.ts` 检查 `proto-nav`、`#default-view`、`#states-gallery`、`#overlays-gallery`。 |
| reduced-motion 基线不足 | 已确认 | 共享层补充 `prefers-reduced-motion: reduce` fallback，页面级已有 fallback 继续保留。 |
| title / viewport / skip-link / heading 缺口 | 已确认 | 已补齐当前扫描命中的缺口，并纳入活跃页基线测试。 |
| 图表依赖颜色 | 已确认 | A Shares、Cross Market、Risk Center、Regime Monitor、Factor Analysis、Backtest Result 增加 legend / sign / threshold / selected markers。 |
| Bottom Tray 遮挡风险 | 已确认 | Strategy Studio、Agent Console、Platform、Trading Overview 增加 `data-bottom-tray` 三态合同。 |
| Catalog 右栏与危险动作链路弱 | 已确认 | Catalog 家族增加 sticky summary、selected marker、batch bar；危险确认增加影响、确认、取消、恢复提示。 |
| Light mode 缺少视觉矩阵 | 已确认 | 新增 `bun run prototype:visual-matrix`，生成 7 类 Shell × 4 偏好截图。 |
| z-index / line-height / letter-spacing 系统治理 | 部分确认 | 本轮把 `oklch(from...)`、负字距 fallback 和契约缺口纳入门禁；更大规模 CSS token 语义重构延后。 |

## 需要 Design Token 批准的事项

本轮没有新增产品级 semantic token。已新增或补齐的变量限定在 prototype shared scope，用于修复共享 CSS 引用和原型几何：

- `--shell-rail-radar-width`
- `--brand-signature-glow`
- `--risk-warning-fg`
- `--surface-secondary`
- `--radius-full`
- `--space-1`

若后续要把这些提升为产品 token，必须同步 `14_ditto_token_naming_layering_spec.md` 并单独评审。

## 延后事项

| 事项 | 原因 |
|------|------|
| 全量移动端 / 窄屏重构 | 当前原型目标仍是桌面专业工作台；本轮只覆盖 1366x768 与 light/density 矩阵。 |
| 归档 AI 原型 CSS 收敛 | `ai-overview`、`ai-copilot` 不属于当前 27 个活跃 reviewed 页面。 |
| manifest schema 扩展 | `reviewNotes` 可能影响现有消费方；本轮评分说明写入文档和技能参考，不改 manifest schema。 |

## 复核命令

```bash
node -e "const m=require('./docs/designs/specs/prototypes/.edition-manifest.json'); console.log(m.pages.filter(p=>p.status==='reviewed').length)"
rg "oklch\\(from|role=\"button\"|prefers-reduced-motion|proto-nav|data-contract-slot" docs/designs/specs/prototypes
bun test scripts/prototype-design-consistency.test.ts
```
