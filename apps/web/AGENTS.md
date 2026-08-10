# Ditto App Agent Guide

Ditto App 是 Ditto A 股 ETF 量化平台的 React SPA。它负责研究、市场、交易和平台操作界面；后端 API 与运行时领域规则属于相邻 `ditto` 仓库。

## 事实优先级

冲突时按以下顺序处理，并显式报告不能自行化解的冲突：

1. 源码与机器配置：`src/`、`package.json`、`biome.json`、`tsconfig*.json`、`vitest.config.ts`。
2. 机器合同：`docs/contracts/pages/`、`.arch-manifest.json`、`.discovery-manifest.json`。
3. 产品与设计事实：`PRODUCT.md`、`DESIGN.md`、`src/styles/design-tokens/`。
4. 设计规格与工程文档：`docs/designs/specs/`、`docs/engineering/`。
5. 历史计划和评审仅提供背景，不能覆盖当前源码或合同。

## 架构地图

- `src/routes/`：TanStack Router 文件路由；`src/routeTree.gen.ts` 自动生成且不提交。
- `src/features/`：业务能力；页面、hooks、API adapter 和 feature 状态在各自能力内聚。
- `src/features/shell/`、`src/features/navigation/`：跨页面 shell/navigation 提供者。
- `src/components/ui/`：无业务语义的基础组件；不得依赖 feature。
- `src/components/{data,domain,indicator,status,chart}/`：跨 feature 展示能力。
- `src/lib/`：API client、错误边界和纯工具；不得依赖 feature。
- `src/styles/design-tokens/`：颜色、密度、交互、组件 token 的唯一值源。
- `src/types/generated/api.d.ts`：后端 OpenAPI 生成类型，不手写复制 API schema。

## 项目 Skills

- `ditto-product-discovery`：新产品方向、新页面定位、竞品/领域调研、假设注册。
- `ditto-product-arch`：信息架构、页面蓝图、用户流程、状态矩阵和产品架构审计。
- `ditto-design-cycle`：HTML prototype 创建、设计评审、跨视口迭代和 edition 管理。
- `ditto-page-contract`：页面合同创建、验证、提升、度量刷新和生成物同步。
- `ditto-app-dev`：合同驱动的 React 页面/组件实现、交互打磨和视觉验证。

通用 planning、debugging、review、worktree 和并行编排使用宿主原生能力，不包装成项目 skill。

## 风险与测试

| 等级 | 示例 | 要求 |
|---|---|---|
| 普通 | 文档、格式、机械重命名 | 保持链接和格式有效；可豁免 RED |
| 行为 | 组件交互、hook、store、API adapter、路由 | 先观察相关测试 RED，再做最小 GREEN |
| 高风险 | 交易确认、风控展示、可访问性、公共组件契约、页面合同 | RED 必须覆盖用户可见行为或合同失败 |
| 发布/真实系统 | 依赖、环境、部署、真实后端写操作 | 先取得批准，保留发布证据和恢复方式 |

测试优先适用于 bug、行为变化、公共契约、可访问性、交易/风控语义和页面合同。纯文档、格式化、纯移动与机械重命名豁免。不要用只验证实现细节的 mock 替代可观察失败。

## 验证矩阵

| 变更 | 最低验证 |
|---|---|
| Harness/agent 配置 | `bun run harness:check` |
| 测试文件 | 目标 `vitest run <files>` + `bun run type` |
| TS/TSX/路由/API | `bun run check` |
| Design Token/主题/CSS | `bun run check && bun run audit:tokens && bun run build:tokens:check` |
| 页面合同 | 合同 validator/generator + 消费方目标测试 |
| 发布候选 | `bun run ci`；prototype 测试需要 Chromium |

`check` 是快速、可重复、无浏览器门；`ci` 才包含 coverage、prototype/Playwright 和构建。

## 不可妥协项

- 只使用 Bun；不要引入 npm/yarn/pnpm lockfile。
- 生产 TypeScript 保持 strict；禁止 `any`、`@ts-ignore` 和 `@ts-expect-error`。
- 服务端状态使用 TanStack Query；跨页面客户端偏好使用 Zustand；局部 UI 状态保持局部。
- 基础 UI 与 `src/lib` 不得导入 feature。跨 feature 依赖优先公共 barrel；深层依赖需有明确能力契约。
- 静态视觉值使用 Tailwind/Design Token。仅数据驱动几何可使用 inline style，且不得嵌入静态品牌色。
- 数据界面覆盖 loading、empty、error、stale；破坏性操作必须显式确认。
- 页面路由必须先运行 `bun run routes:generate`，不要编辑生成的 route tree。
- Biome 是格式与 lint 事实源；不要通过扩大 ignore 绕过失败。

## 审批边界

修改依赖/锁文件、环境变量契约、CI/部署、Design Token 文件架构、页面合同 schema、生成 API 流程、真实后端写操作或发布前必须取得用户批准。读取、搜索、目标测试、静态检查和仓库内可恢复编辑无需额外批准。禁止直接在 `main` commit/push、force push、hard reset、`--no-verify` 和递归强制删除。

## 常用入口

```bash
bun install --frozen-lockfile
bun run check
bun run ci
bun run harness:check
bun run check:changed
```
