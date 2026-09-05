# Testing

Ditto App 将可重复的单元门与需要浏览器的 prototype 门分开。新 checkout 不依赖已存在的 `src/routeTree.gen.ts`：类型检查、覆盖率和构建都会先执行 `bun run routes:generate`。

## 分层

| 命令 | 范围 | 浏览器 |
|---|---|---|
| `bun run test:unit` | `src/` 与 canonical skill tests | 不需要 |
| `bun run test:prototype` | `scripts/**/*.test.*` 的原型、视觉和交互合同 | 需要 Chromium |
| `bun run test:coverage` | `src/` 单元测试与覆盖率阈值 | 不需要 |
| `bun run check` | lint、type、unit、architecture、harness | 不需要 |
| `bun run ci` | check、coverage、prototype、build | 需要 Chromium |

本地第一次运行完整门前安装浏览器：

```bash
bunx playwright install chromium
bun run ci
```

## 测试优先

Bug、交互行为、公共组件契约、可访问性、交易/风控语义和页面合同先写能观察目标行为的失败测试。确认失败原因是缺失行为而不是环境、路由生成或错误断言，再做最小实现。文档、格式化、纯移动和机械重命名可豁免 RED。

优先用 React Testing Library 通过角色、标签、可见文案和用户事件验证；不要把内部 state、组件私有结构或 mock 调用次数当作主要合同。网络测试用 MSW 表达服务端行为。

## Coverage

V8 全局最低阈值是 statements 80%、branches 75%、functions 80%、lines 80%。阈值是回归底线，不替代高风险路径的行为断言。覆盖率命令只采集 `src/`，原型浏览器合同独立运行，避免环境失败污染快速反馈。

## 失败诊断

- 类型检查找不到 route tree：先运行 `bun run routes:generate`，不要手写生成文件。
- Prototype 报找不到 browser executable：运行 `bunx playwright install chromium`。
- 视觉测量不稳定：确认 viewport、字体加载、服务地址和 contract selector 一致，再判断是否重试。
- Skill 测试只从 `.agents/skills` 运行；`.claude/skills` 是镜像，不能重复收集。
