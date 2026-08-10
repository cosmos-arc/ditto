# Ditto App

Ditto 量化平台前端 — 单页应用（SPA），与 ditto 后端 API 交互。

## 技术栈

| 功能 | 技术 |
|------|------|
| 语言 | TypeScript (strict) |
| UI 框架 | React |
| 包管理 | bun |
| 构建 | Vite + Rolldown |
| 样式 | Tailwind CSS v4 + Design Tokens (OKLCH) |
| UI 组件 | shadcn/ui |
| 状态管理 | TanStack Query + Zustand |
| 路由 | TanStack Router |
| 表单 | react-hook-form + zod |
| 测试 | Vitest + React Testing Library |
| 部署 | Cloudflare Pages |

## 快速开始

```bash
# 安装依赖
bun install

# 启动开发服务器
bun dev

# 验证
bun run check   # lint + type + unit + architecture + harness
```

## 项目结构

```
ditto-app/
├── src/
│   ├── features/       # 业务功能模块（Feature-based）
│   │   └── {name}/
│   │       ├── components/
│   │       ├── hooks/
│   │       └── types.ts
│   ├── components/ui/  # 共享 UI 组件（shadcn/ui）
│   ├── lib/            # 工具函数 + API 层
│   ├── styles/         # Design Tokens + 全局样式
│   │   ├── design-tokens/  # 唯一真理源
│   │   ├── themes/         # 主题覆盖
│   │   ├── globals.css     # 共享 token + @theme 映射
│   │   └── fonts.css       # 字体声明
│   └── routes/         # 路由定义
├── docs/               # 文档 + Prototype
└── public/             # 静态资源
```

## 测试

```bash
bun run test:unit          # 单元测试（不需要浏览器）
bun run test:prototype     # Prototype/Playwright 合同测试
bun run test:coverage      # src 覆盖率门
```

## 常用命令

| 命令 | 说明 |
|------|------|
| `bun run check` | 快速、无浏览器完成门 |
| `bun run ci` | 覆盖率 + Prototype/Playwright + 构建 |
| `bun run harness:check` | 双宿主 harness 静态验收 |
| `bunx tsc --noEmit` | 类型检查 |
| `bunx biome check .` | lint + format |
| `bunx biome check --write .` | 自动修复 |

## 详细规范

详见 [AGENTS.md](AGENTS.md)、[Agent Harness](docs/engineering/agent-harness.md) 与 [Frontend Architecture](docs/engineering/frontend-architecture.md)。
