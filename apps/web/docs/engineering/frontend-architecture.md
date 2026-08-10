# Frontend Architecture

本文件解释机器门禁背后的架构意图。当前源码和配置优先于历史审计；`.arch-manifest.json`、页面合同、`PRODUCT.md`、`DESIGN.md` 与 token 源分别承担产品、页面和视觉事实。

## 依赖方向

```text
routes → features → shared domain/data/chart components → components/ui + lib
```

`src/components/ui` 和 `src/lib` 是低层能力，不能导入 `src/features`。Feature 间优先通过稳定 public barrel 或明确的共享能力交互，避免依赖另一 feature 的页面私有组件。现有仓库尚未消除全部跨 feature 深层导入，因此机器门当前只强制低层依赖方向；扩大约束前应先形成迁移计划和基线证据。

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

`src/styles/design-tokens/` 是静态视觉值的唯一源。主题映射应完整，语义命名优先于页面名或裸色名；生产 TS/TSX 不写硬编码十六进制品牌色。

Inline style 不是一律禁止：图表坐标、虚拟列表尺寸、拖拽位移等运行时几何可以使用，但静态颜色、字号、间距、圆角和阴影应来自 Tailwind/token。检查 light/dark、compact/comfortable、色觉无障碍与非颜色编码。

## 审查清单

- 低层模块是否反向依赖 feature，feature 深层依赖是否有稳定契约。
- 组件是否同时承担数据、编排、布局和展示，是否出现循环或无边界共享。
- Query/Zustand/local state 的所有权是否匹配生命周期。
- API 类型是否生成，错误/loading/empty/stale 是否完整。
- token、主题、对比度、focus、键盘操作和响应式是否有证据。
- 高风险发现是否带具体文件位置、影响、复现和最低修复建议。

机器入口是 `bun run arch:check`；全库只读评审还应结合 `bun run check`、coverage、token audit 与针对性的源码检查，不自动写审计报告。
