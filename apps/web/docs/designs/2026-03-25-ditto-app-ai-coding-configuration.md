# Ditto App AI 编码配置体系设计

> 为 ditto-app 独立仓库设计 Claude Code 配置体系，镜像现有 ditto monorepo 的命名规范和结构模式。
> 基于 [AI 设计工作流调研](../research/2026-03-22-ai-design-workflow-for-solo-developers.md) 和现有 `.claude/` 配置审计。
>
> 状态：待实施
> 决策日期：2026-03-25

---

## 1. 背景与决策

### 1.1 问题

Ditto monorepo 的 Claude Code 配置完全围绕 Python 后端设计。随着前端项目启动，存在以下问题：

- 根 `CLAUDE.md` 验证命令只有 `pixi run -e dev check`，前端代码无门禁
- `py_gate.py` hook 对前端文件变更直接放行
- `py_after_write.py` hook 仅在 `.py` 文件写入后触发
- 无前端 rules、commands、hooks
- settings.json 无前端工具权限

### 1.2 仓库结构决策：前端独立仓库

| 维度 | Monorepo（否决） | 独立仓库（采纳） |
|------|-----------------|-----------------|
| 上下文隔离 | 靠 `paths:` + 懒加载控制 | 天然隔离 |
| settings.json | 不向上遍历（#12962），只能从根目录加载 | 各自独立 |
| MCP servers | 前后端互相污染 | 各自配置 |
| Hooks | 需要分发脚本按路径判断 | 各自独立 |
| 工具链重叠 | pixi vs bun, ruff vs biome, pytest vs vitest — 零重叠 | 不存在问题 |

**共享类型方案**：前端通过 FastAPI OpenAPI schema + `openapi-typescript` 生成 TypeScript 类型，不需要共享包。

### 1.3 现有 ditto 配置命名规范（镜像基准）

| 类别 | 命名规范 | 示例 |
|------|---------|------|
| 命令 | `ditto-{action}.md` | `ditto-plan.md`, `ditto-dev.md` |
| Hook | `py_{purpose}.py` | `py_after_write.py`, `py_gate.py` |
| Rule | `{topic}.md` + `paths:` frontmatter | `core.md`, `python-test.md` |
| Checklist | `{topic}.md` | `debug.md`, `code-change.md` |
| 命令 frontmatter | `name: ditto-{action}`, `description: {中文}` | 一致 |
| 内容语言 | 全中文 | 节标题、描述、文档字符串 |
| Section 分隔 | `---` 水平线 | 一致 |

---

## 2. 目录结构

```
ditto-app/
├── CLAUDE.md                             # 主指令文件（< 200 行）
├── .claude/
│   ├── settings.json                     # 权限 + 插件（提交到 git）
│   ├── settings.local.json               # hooks + MCP + 个人 allow（gitignore）
│   ├── commands/
│   │   ├── ditto-app-plan.md             # /ditto-app-plan — 结构化规划
│   │   ├── ditto-app-dev.md              # /ditto-app-dev — TDD 开发
│   │   ├── ditto-app-review.md           # /ditto-app-review — 代码审查
│   │   └── ditto-app-architecture-audit.md  # 架构审计
│   ├── hooks/
│   │   ├── fe_after_write.sh             # PostToolUse: biome format/lint
│   │   └── fe_gate.sh                    # Stop: lint + type + test 门禁
│   ├── rules/
│   │   ├── core.md                       # paths: ["src/**/*.ts", "src/**/*.tsx"]
│   │   ├── architecture.md               # paths: ["src/**"]
│   │   ├── tailwind.md                   # paths: ["src/**/*.css", "src/**/*.tsx"]
│   │   ├── components.md                 # paths: ["src/components/**"]
│   │   ├── react-test.md                 # paths: ["src/**/*.test.*", "src/**/*.spec.*"]
│   │   ├── no-any-ignore.md              # paths: ["src/**/*.ts", "src/**/*.tsx"]
│   │   ├── design-tokens.md              # paths: ["src/styles/**"]
│   │   └── workflow.md                   # paths: ["src/**"]
│   └── checklists/
│       ├── debug.md                      # 调试检查清单
│       └── code-change.md                # 代码变更检查清单
```

---

## 3. 命名映射对照表

| 类别 | Ditto (Python 后端) | ditto-app (React 前端) |
|------|---------------------|----------------------|
| 命令 | `ditto-plan.md` | `ditto-app-plan.md` |
| 命令 | `ditto-dev.md` | `ditto-app-dev.md` |
| 命令 | `ditto-review.md` | `ditto-app-review.md` |
| 命令 | `ditto-architecture-audit.md` | `ditto-app-architecture-audit.md` |
| Hook | `py_after_write.py` | `fe_after_write.sh` |
| Hook | `py_gate.py` | `fe_gate.sh` |
| Rule | `core.md` (paths: `.py`) | `core.md` (paths: `.ts/.tsx`) |
| Rule | `architecture.md` (paths: `.py`) | `architecture.md` (paths: `src/**`) |
| Rule | `python-test.md` (paths: `tests/**/*.py`) | `react-test.md` (paths: `src/**/*.test.*`) |
| Rule | `noqa-ignore.md` (paths: `.py`) | `no-any-ignore.md` (paths: `.ts/.tsx`) |
| Rule | `polars.md` (paths: `.py`) | `tailwind.md` (paths: `.css`, `.tsx`) |
| Rule | `pit.md` (paths: `datahub/**/*.py`) | `design-tokens.md` (paths: `src/styles/**`) |
| Rule | `workflow.md` (paths: `**/*.py`) | `workflow.md` (paths: `src/**`) |
| Rule | — | `components.md` (paths: `src/components/**`) |
| Checklist | `debug.md` | `debug.md` |
| Checklist | `code-change.md` | `code-change.md` |

---

## 4. CLAUDE.md 主指令设计

镜像 ditto `CLAUDE.md` 的结构风格，内容针对前端技术栈：

```
# Ditto App 项目指南

## 北极星原则
（镜像 ditto 的哲学声明，针对前端质量）

## 🎯 三条铁律（5 秒必读）
1. 先探索后编码
2. 理解优先于修改
3. 验证后完成（bun run check）

## 🔄 执行决策流程
（镜像 ditto 的流程图，工具替换为 bun/biome/vitest）

## 📋 项目规范
### 代码风格 — TypeScript strict + Biome
### 测试标准 — Vitest + React Testing Library，覆盖率 ≥ 80%
### 架构原则 — Feature-based 目录结构
### 允许的依赖（严格限制）
### 常用命令 — bun run dev/check/test/lint/type
### 禁止事项

## 🚀 执行优先级
### 1. Skills 第一
### 2. Read >= 2x Edit

## ✅ 完成前验证
bun run check

## Boundaries
### ✅ Always do
### ⚠️ Ask first
### 🚫 Never do
```

---

## 5. Settings 配置

### 5.1 settings.json（提交到 git）

```json
{
  "permissions": {
    "allow": [
      "Read(**)",
      "Write(**)",
      "Edit(**)",
      "LSP(**)",
      "Skill(**)",
      "Glob(**)",
      "Grep(**)",
      "Task(**)",
      "TodoWrite(**)",
      "AskUserQuestion(**)",
      "Bash(bun *)",
      "Bash(git *)",
      "Bash(gh *)"
    ],
    "deny": [
      "Bash(rm -rf *)",
      "Bash(sudo *)",
      "Bash(chmod 777 *)",
      "Bash(git push --force *)",
      "Bash(git reset --hard *)"
    ]
  },
  "enabledPlugins": {
    "superpowers@superpowers-marketplace": true,
    "code-simplifier@claude-plugins-official": true,
    "code-review@claude-plugins-official": true
  }
}
```

**与 ditto 的差异**：
- Bash allow: `bun *` 替代 `pixi *`
- 移除 Python 相关插件：`python-development`、`unit-testing`、`quantitative-trading`、`pyright-lsp`
- 保留通用插件：`superpowers`、`code-simplifier`、`code-review`

### 5.2 settings.local.json（gitignore）

```json
{
  "permissions": {
    "allow": [
      "Bash(biome *)",
      "Bash(tsc *)",
      "Bash(vitest *)",
      "Bash(npx *)",
      "Bash(ls *)",
      "Bash(cat *)",
      "Bash(mkdir *)",
      "Bash(cp *)",
      "Bash(mv *)",
      "Bash(rm *)"
    ],
    "additionalDirectories": ["/tmp"]
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/fe_after_write.sh",
            "timeout": 30
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/fe_gate.sh",
            "timeout": 120
          }
        ]
      }
    ]
  }
}
```

---

## 6. Hooks 设计

### 6.1 fe_after_write.sh

**触发**：`PostToolUse`，matcher: `Write|Edit`

**逻辑**：
1. 从 stdin 读取 JSON，提取 `tool_input.file_path`
2. 判断文件扩展名：
   - `.ts` / `.tsx` / `.css` / `.json` → 运行 `bunx biome check --write <file>`
   - 其他 → 跳过
3. 使用 `$CLAUDE_PROJECT_DIR` 定位项目根目录

**与 ditto `py_after_write.py` 的对应关系**：
- ditto: Python 脚本 + `pixi run -e dev lint --fix` + `pixi run -e dev fmt`
- ditto-app: Shell 脚本 + `bunx biome check --write`（biome 同时处理 lint + format）

### 6.2 fe_gate.sh

**触发**：`Stop`（Claude 即将声明完成时）

**逻辑**（顺序执行，任一失败则阻塞）：
1. `bunx biome check .` — lint + format 检查
2. `bunx tsc --noEmit` — 类型检查
3. `bunx vitest run --coverage` — 测试 + 覆盖率

**与 ditto `py_gate.py` 的对应关系**：
- ditto: `lint` → `fmt --check` → `type` → `type --tests`
- ditto-app: `biome check` → `tsc --noEmit` → `vitest run --coverage`

---

## 7. Rules 设计

### 7.1 core.md

**paths**: `["src/**/*.ts", "src/**/*.tsx"]`

内容方向：
- TypeScript strict 模式强制
- 禁止 `any` / `@ts-ignore` / `@ts-expect-error`
- 组件命名规范（PascalCase）
- Hook 命名规范（use 前缀）
- 文件命名规范（kebab-case）
- 代码行宽限制（biome 默认 80）
- 函数/组件大小限制
- 导入排序（biome 自动处理）

### 7.2 architecture.md

**paths**: `["src/**"]`

内容方向：
- Feature-based 目录结构：`src/features/{name}/components/`, `hooks/`, `types.ts`
- 共享 UI 组件：`src/components/ui/`（shadcn）
- API 层：`src/lib/api.ts`（集中式，typed）
- 状态管理：TanStack Query（服务端状态）+ Zustand（客户端状态）
- 路由：TanStack Router，文件路由约定
- 禁止跨 feature 直接导入组件（通过 barrel export）

### 7.3 tailwind.md

**paths**: `["src/**/*.css", "src/**/*.tsx"]`

内容方向：
- Tailwind CSS v4 CSS-first 配置
- 禁止 inline styles
- `@apply` 仅限 globals.css 和 shadcn 组件
- Design Token 消费模式（CSS 变量 → Tailwind utility）
- 响应式断点约定
- 暗色/亮色主题切换实现

### 7.4 components.md

**paths**: `["src/components/**"]`

内容方向：
- shadcn/ui 组件作为基础，禁止重复造轮子
- CVA (class-variance-authority) 变体模式
- `data-slot` 精确样式
- 组件 props 类型定义规范
- 可组合性优先于继承
- 受控 vs 非受控组件规范

### 7.5 react-test.md

**paths**: `["src/**/*.test.*", "src/**/*.spec.*"]`

内容方向：
- Vitest + React Testing Library
- 测试命名：`{Component}.{behavior}` 模式
- 测试文件位置：`__tests__/` 或 co-located `.test.tsx`
- Fixture 模式
- Mock 策略（MSW for API mocks）
- 覆盖率要求 ≥ 80%
- E2E: Playwright（Phase 4 引入）

### 7.6 no-any-ignore.md

**paths**: `["src/**/*.ts", "src/**/*.tsx"]`

内容方向（镜像 ditto `noqa-ignore.md` 的严格精神）：
- `any` 类型零容忍（src 内）
- `@ts-ignore` / `@ts-expect-error` 零容忍
- 允许的例外：测试文件中的 mock 类型
- 替代方案：使用 `unknown` + type guard
- ESLint `@typescript-eslint/no-explicit-any` 作为安全网

### 7.7 design-tokens.md

**paths**: `["src/styles/**"]`

内容方向（基于 [Design Token 架构设计](2026-03-25-ditto-app-design-token-architecture.md)）：
- Primitive Token 修改规则（需与架构文档同步）
- Semantic Token 命名规范（`--color-{domain}-{variant}-{usage}`）
- 四色域分离：Market / Risk / System / Signal
- OKLCH 色彩空间约束
- 图表颜色独立体系
- 暗色/亮色映射完整性

### 7.8 workflow.md

**paths**: `["src/**"]`

内容方向（镜像 ditto `workflow.md`）：
- 代码修改流程：Read → Grep → Edit
- 调试流程：引用 `checklists/debug.md`
- 质量指标
- 引用 `checklists/code-change.md`

---

## 8. Commands 设计

### 8.1 ditto-app-plan.md

镜像 `ditto-plan.md` 的结构：
- frontmatter: `name: ditto-app-plan`, `description: 生成结构化开发任务规划`
- 输入: `$ARGUMENTS` — 任务描述
- 流程: 调用 `brainstorming` skill → 输出结构化计划文档
- 规范引用: `workflow.md`, `architecture.md`

### 8.2 ditto-app-dev.md

镜像 `ditto-dev.md` 的结构：
- frontmatter: `name: ditto-app-dev`, `description: 基于 TDD 的前端开发`
- 输入: `$ARGUMENTS` — 任务描述
- 流程: 调用 `test-driven-development` skill → RED → GREEN → REFACTOR
- 验证: `bun run check`

### 8.3 ditto-app-review.md

镜像 `ditto-review-review.md` 的结构：
- frontmatter: `name: ditto-app-review`, `description: 并行代码审查`
- 流程: 架构合规 + 代码质量 + 测试覆盖 + Design Token 合规

### 8.4 ditto-app-architecture-audit.md

镜像 `ditto-architecture-audit.md` 的结构：
- frontmatter: `name: ditto-app-architecture-audit`, `description: 全库架构审计`
- 审计维度: 分层合规、组件依赖、状态管理、Design Token 使用

---

## 9. Skills 分阶段引入

| 阶段 | Skill | 来源 | 用途 |
|------|-------|------|------|
| Phase 1 | superpowers | 已安装 | TDD / 调试 / 规划 / 头脑风暴 |
| Phase 1 | code-simplifier | 已安装 | 代码简化 |
| Phase 1 | code-review | 已安装 | 代码审查 |
| Phase 4 | Impeccable | `npx skills add pbakaus/impeccable` | 设计质量门禁 |
| Phase 4 | vercel-react-best-practices | `npx skills add vercel-labs/react-best-practices` | React 性能/模式规则 |

---

## 10. ditto monorepo 侧的清理

前端独立后，ditto monorepo 需要做以下清理：

- [ ] 移除 `ci.yml` 中 `frontend-check` job 的骨架代码
- [ ] 移除根 `CLAUDE.md` 中 `apps/web/` 的引用（如有）
- [ ] 移除 `.github/` 中引用 `apps/web` 的部署配置（如有）
- [ ] 确认 `deploy.yml` 中 `packages/foundation` 的过时引用已清理

---

## 11. 工具链对照表

| 功能 | ditto (Python) | ditto-app (React) |
|------|---------------|-------------------|
| 包管理 | pixi | bun |
| 运行时 | Python 3.12+ | Node.js (bun) |
| 类型检查 | basedpyright (strict) | tsc (strict) |
| Lint | ruff | biome |
| Format | ruff format | biome format |
| 测试框架 | pytest | vitest |
| 测试 runner | pytest (parallel) | vitest |
| 测试覆盖率 | coverage.py | @vitest/coverage-v8 |
| E2E 测试 | — | Playwright (Phase 4) |
| API mock | pytest fixtures | MSW |
| Hot reload | — | Vite HMR |
| 构建 | — | Vite + Rolldown |
| 部署 | FastAPI server | Cloudflare Pages |
| 验证命令 | `pixi run -e dev check` | `bun run check` |
