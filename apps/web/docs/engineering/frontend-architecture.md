# Frontend Architecture

本文件解释机器门禁背后的架构意图。当前源码和配置优先于历史审计；`.arch-manifest.json`、页面合同、`PRODUCT.md`、`DESIGN.md` 与 token 源分别承担产品、页面和视觉事实。

## 依赖方向

```text
routes → workflows → feature public APIs → shared domain/data/chart components → components/ui + lib
```

`src/components/ui` 和 `src/lib` 是低层能力，不能导入 `src/features`。单一 feature 页面可由 route
直接装配；涉及多个业务 feature 的取数、错误映射或交互必须进入 `src/workflows`，且 route 与
workflow 都只消费 public index。

业务 feature-to-feature 依赖默认禁止。`shell` 与 `navigation` 是显式 foundational allowlist，且它们
自身不得反向依赖业务 feature；迁移前
已经存在且仍有明确消费者的 peer capability 边在 `dependency-cruiser.config.mjs` 中逐项登记，未登记
的新边直接失败。该登记不是新增依赖的捷径：优先把跨域组合迁入 workflow，并在清除旧边时同步缩小
allowlist。

Strategy governance 是标准示例：`features/strategy` 拥有 governance controls、mutation 和显式
`StrategyReviewEvidence` props；`features/research` 提供 review packet query；
`workflows/strategy-governance` 组合两者并把 `ApiError` 归一化为结构化 evidence issue；route 只导入
workflow public index。packet 缺失、读取失败、bundle hash 非法或 hard gate 阻断时，submit/approve
必须 fail closed。

Markets 与 Instrument 页面采用同一模式：`workflows/market-pages` 组合 Markets-owned view contracts、
Instrument catalog 与 Data Product coverage；`workflows/instrument-analysis` 通过显式 renderer/dependency
contract 组合 Instrument、SelectionRun 与 certified Data Product evidence。对应 route 只导入 workflow
public index，`features/instruments` 不再依赖 `selection` 或 `data-products`，`features/markets` 不再依赖
Instrument catalog。当前唯一保留的目标域 peer edge 是 `markets → data-products`：
`fetchCurrentMarketContext` 仍是 Home 消费的既有 public API；在未把 Home 的市场脉搏编排迁到 workflow
前，删除该边会破坏现有消费者，不能以复制 Data Product adapter 或 service locator 伪装消除。

## 状态与数据

- 服务器状态、缓存和刷新交给 TanStack Query。
- 跨页面用户偏好和会话 UI 状态使用 Zustand。
- 只影响一个组件树的状态保持局部，避免无必要的全局 store。
- API schema 来自生成类型；feature adapter/hook 将传输模型转换为界面模型。
- 数据界面明确 loading、empty、error、stale，危险操作具有确认与错误恢复。

## 类型与组件

- 生产代码禁止 `any`、`@ts-ignore` 和 `@ts-expect-error`；不要扩大 lint ignore 消音。
- 组件大小不是单一失败条件。超过约 200 行时检查是否混合了数据获取、状态编排、布局和展示职责，再依据变化原因拆分。
- 复用基础交互时优先 `src/components/ui`；业务语义保留在 feature 或共享 domain/data 组件。
- 关注循环依赖、深层 prop drilling、重复 adapter 和过宽 public export。

## 样式与 Tokens

`src/styles/design-tokens/` 是静态视觉值的唯一源。主题映射应完整，语义命名优先于页面名或裸色名。机器门会扫描生产 CSS、JavaScript 和 TypeScript 中的 hex、RGB/HSL、OKLab 与 OKLCH 原语；只有 `src/styles/design-tokens/*.css` 可以定义颜色，`globals.css`、light/dark 主题、SVG 属性和 Tailwind arbitrary value 都只能消费命名 token。扫描器忽略注释、报告精确行号，其回归测试属于 `bun run arch:check`。

Inline style 不是一律禁止：图表坐标、虚拟列表尺寸、拖拽位移等运行时几何可以使用，但静态颜色、字号、间距、圆角和阴影应来自 Tailwind/token。检查 light/dark、compact/comfortable、色觉无障碍与非颜色编码。

## 审查清单

- 低层模块是否反向依赖 feature，feature 深层依赖是否有稳定契约。
- 组件是否同时承担数据、编排、布局和展示，是否出现循环或无边界共享。
- Query/Zustand/local state 的所有权是否匹配生命周期。
- API 类型是否生成，错误/loading/empty/stale 是否完整。
- token、主题、对比度、focus、键盘操作和响应式是否有证据。
- 高风险发现是否带具体文件位置、影响、复现和最低修复建议。

机器入口是 `bun run arch:check`；全库只读评审还应结合 `bun run check`、coverage、token audit 与针对性的源码检查，不自动写审计报告。
