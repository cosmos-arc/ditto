# Ditto App 项目指南

## 北极星原则

> 以**卓越代码质量**为底线、以**艺术般的可读性与一致风格**为追求，持续产出**清晰、整洁、可演进的架构**与**可长期维护的工程实现**。

**不可妥协：**
- **质量**：正确性、可测试、可维护
- **风格**：一致、克制、易读
- **架构**：清晰边界、低耦合、高内聚、可演进

**遇事不决调研业界最佳实践！！！**
**胆敢偷工减料我就换掉当前模型！！！**

---

## 🎯 三条铁律（5 秒必读）

1. **先探索后编码** - 涉及 2+ 文件或架构变更 → Plan Mode
2. **理解优先于修改** - Read 文件 → Grep 模式 → Edit
3. **验证后完成** - 声明完成前 → `bun run check`

---

## 🔄 执行决策流程

```
用户请求
  │
  ├─ 涉及代码修改？
  │   ├─ 是 → 检查 Skill
  │   │   ├─ 创意/新功能 → brainstorming
  │   │   ├─ Bug/失败 → systematic-debugging
  │   │   ├─ 有实施计划 → executing-plans
  │   │   └─ 多步骤任务 → writing-plans
  │   │
  │   ├─ 涉及 2+ 文件或架构变更？
  │   │   └─ 是 → Plan Mode（先探索后编码）
  │   │
  │   └─ TypeScript/TSX 代码修改？
  │       └─ 是 → Read 文件 → Grep 模式 → Edit
  │
  └─ 完成前？
      └─ 运行验证 → 声明完成
```

---

## 📋 项目规范

### 代码风格 — TypeScript strict + Biome
- **语言**：中文回复/文档，UTF-8 编码
- **TypeScript**：详见 [core.md](.claude/rules/core.md)
- **类型**：禁止 `any` / `@ts-ignore` / `@ts-expect-error`（详见 [no-any-ignore.md](.claude/rules/no-any-ignore.md)）
- **TDD**：RED → GREEN → REFACTOR
- **分支**：从 main 拉开发分支，PR 合并

### 测试标准 — Vitest + React Testing Library
- **覆盖率**：分支覆盖率 ≥ 80%（详见 [react-test.md](.claude/rules/react-test.md)）
- **新功能**：必须有单元测试
- **API 变更**：必须有集成测试
- **测试命令**：`bun run test`

### 架构原则 — Feature-based 目录结构
```
src/
├── features/        # 业务功能模块
│   └── {name}/
│       ├── components/
│       ├── hooks/
│       └── types.ts
├── components/ui/   # 共享 UI 组件（shadcn）
├── lib/api.ts       # 集中式 API 层（typed）
└── styles/          # Design Tokens + 全局样式
```

- **状态管理**：TanStack Query（服务端状态）+ Zustand（客户端状态）
- **路由**：TanStack Router，文件路由约定
- **禁止跨 feature 直接导入组件**（通过 barrel export）

### 允许的依赖（严格限制）

| 功能 | ✅ 允许 | ❌ 禁止 |
|------|--------|---------|
| 包管理 | **bun** | npm/yarn/pnpm |
| 构建 | Vite + Rolldown | webpack |
| 样式 | Tailwind CSS v4 | CSS Modules / styled-components |
| UI 组件 | shadcn/ui | antd / MUI |
| 状态 | TanStack Query + Zustand | Redux / MobX |
| 路由 | TanStack Router | react-router-dom |
| 表单 | react-hook-form + zod | formik |
| API 类型 | openapi-typescript | 手写类型 |
| 测试 | Vitest + RTL | Jest |
| API Mock | MSW | json-server |

### 常用命令

```bash
# 快速验证（开发时）
bun run check              # lint + type + test

# 测试
bun run test               # 默认：vitest
bun run test --coverage    # 测试 + 覆盖率

# 类型检查
bunx tsc --noEmit          # strict 类型检查

# 代码质量
bunx biome check .         # lint + format 检查
bunx biome check --write . # lint + format 自动修复
```

### 禁止事项

| ❌ 禁止 | 原因/替代 |
|---------|-----------|
| `any` 类型 | 使用 `unknown` + type guard |
| `@ts-ignore` / `@ts-expect-error` | 修正类型（详见 no-any-ignore.md） |
| inline styles | 使用 Tailwind CSS / CSS class（详见 no-inline-style.md） |
| `@apply`（非 globals.css/shadcn） | 使用 utility classes |
| 直接提交 main | 必须通过 PR |
| 绕过 biome/tsc/vitest | 必须通过检测 |
| 文件操作用 Bash cat/sed/echo | 必须用 Read/Edit/Write |
| 跨 feature 直接导入组件 | 通过 barrel export |
| npm/yarn/pnpm | 必须用 bun |

---

## 🚀 执行优先级

### 1. Skills 第一（处理前必查）

**历史数据警告**：2,978 个会话分析，不调用 Skills → 失败率 40-50%，返工时间 3-5 倍

| 场景 | 必须调用 | 后果 |
|------|---------|------|
| 创意/新功能 | `brainstorming` | 设计不完整，频繁重构 |
| Bug/测试失败 | `systematic-debugging` | 盲目重试，80% 失败率 |
| 实现功能 | `test-driven-development` | 引入 bug，破坏功能 |
| 多步骤任务 | `writing-plans` | 遗漏边界情况 |
| 完成任务 | `verification-before-completion` | 提交未验证代码 |

**流程**：用户请求 → 检查 Skill → 立即调用 → 再开始工作

### 2. Read ≥ 2x Edit

| 任务类型 | 最低 Read/Edit 比 |
|---------|-------------------|
| 简单修改 | 2.0 |
| 中等修改 | 3.0 |
| 重构任务 | 5.0 |

**标准流程**：
```bash
Read <file>        # 理解当前实现
Read <test_file>   # 理解预期行为
Grep "<pattern>"   # 查找相关代码
Edit <file>        # 现在才修改
```

**禁止模式**：
| ❌ 禁止 | ✅ 正确 |
|---------|---------|
| 连续 Edit | Read → Edit |
| Edit 失败后直接重试 | 调用 systematic-debugging |
| 不读代码直接改 | 先理解再修改 |

---

## ✅ 完成前验证

声明任务完成前，**必须**运行：

```bash
bun run check    # lint + type + test
```

**分支门禁**：
- [ ] tsc 类型检查通过
- [ ] biome lint 检查通过
- [ ] 测试通过
- [ ] 分支覆盖率 ≥ 80%

---

## Boundaries

### ✅ Always do（无需询问）
- 使用 `Read` 工具读文件（禁止 cat）
- 使用 `Edit` 工具编辑（禁止 sed）
- 使用 `Write` 工具写文件（禁止 echo/cat >）
- 重构前使用 Grep 查找引用
- 遵循 TDD 流程（RED → GREEN → REFACTOR）

### ⚠️ Ask first（需要人工批准）
- 添加新依赖
- CI/CD 配置修改
- 修改架构边界
- 修改环境配置文件
- Design Token 新增档位（字号/间距等需先在 prototype 中定义，详见 [design-tokens.md](.claude/rules/design-tokens.md)）

### Design Token 变更规则

> Token 值的**唯一修改入口**：`src/styles/design-tokens/tokens-*.css`。修改后 Prototype 和 React 同时生效。

| 操作 | 需要审批？ | 说明 |
|------|:---:|------|
| 修改已有 token 值（如 `--brand-500` 颜色） | ❌ | 直接改 design-tokens/ |
| 新增 token 变量 | ❌ | 在 design-tokens/ 中新增 `:root` 变量 |
| 新增 @theme inline 映射 | ❌ | 在 globals.css 中新增映射行 |
| 新增字号/间距档位 | ⚠️ | 需同步更新 design-tokens.md 映射表 |
| 修改 token 文件架构（增删文件） | ✅ | 涉及架构变更 |
| 修改 @theme inline → :root 引用关系 | ✅ | 涉及 Tailwind v4 内部机制 |

### 🚫 Never do（硬性禁止）
- **使用 `any` 类型**（必须用 `unknown` + type guard）
- **使用 npm/yarn/pnpm**（必须用 bun）
- **使用 inline styles**（必须用 Tailwind CSS）
- 跳过 biome、tsc、vitest 检测
- 直接提交到 main 分支
- 提交 secrets
- 使用 Bash 命令进行文件读写改操作

---

## 附录：详细参考

### 项目架构

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
│   │   ├── design-tokens/  # ← 唯一真理源（Prototype + React 共享）
│   │   ├── themes/         # 主题覆盖（dark/light/market-intl）
│   │   ├── globals.css     # @import 共享 token + @theme inline 映射
│   │   └── fonts.css       # 字体声明
│   └── routes/         # 路由定义
├── docs/               # 文档 + Prototype
└── public/             # 静态资源
```

### 工具链

| 功能 | 工具 |
|------|------|
| 包管理 | bun |
| 运行时 | Node.js (bun) |
| 类型检查 | tsc (strict) |
| Lint + Format | biome |
| 测试 | vitest + React Testing Library |
| 覆盖率 | @vitest/coverage-v8 |
| API Mock | MSW |
| 构建 | Vite + Rolldown |
| 部署 | Cloudflare Pages |
