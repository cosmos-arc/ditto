# Ditto Web

Ditto 的 React 单页应用。它是根 monorepo 的 Bun workspace，由根 uv 统一编排，
通过提交的 OpenAPI 3.1 快照与本地 FastAPI API 协作。

## 技术边界

- React 19、TypeScript 6、Vite 8、Tailwind CSS v4。
- TanStack Router/Query、Zustand、Vitest、Playwright、Biome。
- `openapi-fetch` 绑定 `src/api/generated/schema.d.ts` 中的 `paths`，并用同一快照生成的
  `src/api/generated/operation-contracts.ts` 在运行时核验 operation 状态码和响应媒体类型；feature adapter
  将 HTTP DTO 转为 view model，组件不直接消费 generated 类型。
- Bun 是唯一 JavaScript 包管理器；唯一锁文件位于仓库根 `bun.lock`。
- 正式静态制品从 `ditto-runtime-config.json` 读取无秘密运行配置，不以编译期
  `VITE_API_BASE_URL` 固化生产 API，也不默认部署到任何公共云。

依赖方向由根 `dependency-cruiser` 门禁执行：

```text
app/routes → workflows → feature public APIs → shared → ui/lib
feature api adapters → typed src/api
```

feature 间不做 deep import；跨 feature 行为进入 `src/workflows`。
例如，`workflows/market-context` 将 Data Product certification evidence 解析为 exact snapshot scope，
再调用 Markets 的显式 scope API；`workflows/home-dashboard` 将该 loader 注入 Home，Markets 页面也只在
workflow 层消费同一编排。`features/markets` 和 `features/home` 都不反向定位 workflow 实现。

## 开发与验证

从仓库根执行：

```bash
task bootstrap
task dev
task check-web
task check-contract
task test-system
```

仅开发 Web 叶子任务时，可在本目录执行：

```bash
bun run lint
bun run type
bun run test:unit
bun run test:prototype
bun run build
```

这些 Bun scripts 不定义跨栈 DAG；跨栈完成标准始终以根 uv 任务为准。

## 目录

```text
src/
├── api/             # typed transport、运行配置、generated schema
├── workflows/       # 跨 feature 用例编排
├── features/        # feature public API、adapter、view 与局部状态
├── routes/          # TanStack Router composition
├── components/      # 共享 UI/data-viz primitives
├── stores/          # 不反向依赖 feature 的全局状态
└── styles/          # OKLCH design tokens、主题和字体
scripts/             # 受独立 tooling tsconfig 管理的生成/质量叶子工具
public/              # runtime config 模板与静态资源
```

修改本目录前请阅读 [AGENTS.md](AGENTS.md)。跨 API 改动同时遵守
[契约规则](../../contracts/AGENTS.md)；仓库总体入口见
[根 README](../../README.md)。
