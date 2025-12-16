# 开发工作流规范

> 通用工作流程，适用于所有开发任务

## TDD 流程（必须遵守）

```
1. 规划 → 2. 写测试 → 3. 实现 → 4. 重构 → 5. 提交 → 6. CI/Review
```

每个功能必须完整走完此流程，不得跳过测试步骤。

## Commit 规范

### 格式

```
<type>(<scope>): <task-id> <description>

# 示例
feat(data): P0-005 implement DuckDB initialization
fix(api): P0-022 resolve import error in main.py
test(engine): P0-041 add unit tests for RegimeEngine
refactor(core): P0-033 extract common validation logic
```

### Type 类型

| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `test` | 测试相关 |
| `refactor` | 重构（不改变行为） |
| `perf` | 性能优化 |
| `docs` | 文档 |
| `style` | 代码格式（不影响逻辑） |
| `chore` | 构建、依赖等杂项 |
| `ci` | CI/CD 配置 |

### 破坏性变更

在 type 后加 `!`：

```
feat!: P0-100 change API response format
```

## 分支策略

```
main
  └── feature/<task-id>-<short-desc>
      例: feature/P0-005-duckdb-init
```

## 代码质量检查

### 提交前必须执行

```bash
# 一键检查（推荐）
pre-commit run --all-files

# 或分步执行
pixi run ruff check .
pixi run ruff format .
pixi run mypy packages/ apps/ scripts/ tests/
pytest
```

### 检查标准

| 检查项 | 命令 | 要求 |
|--------|------|------|
| Lint | `ruff check .` | 0 errors |
| Format | `ruff format --check .` | 0 issues |
| Type | `mypy packages/ apps/` | 0 errors |
| Test | `pytest` | 100% pass |

## 任务管理

### 文档位置

- 任务跟踪：`docs/tasks/phase0.md`
- 工作规划：`docs/plans/*.md`
- 设计文档：`docs/design/*`（只读，勿修改）

### 状态标记

| 标记 | 含义 |
|------|------|
| ✅ | 完成 |
| ⚠️ | 部分完成 |
| 🔄 | 进行中 |
| ❌ | 未开始 |

### 完成流程

1. 功能开发完成
2. 测试通过
3. 更新任务文档状态
4. 确定下一步计划

## Superpower Skills

| 场景 | Skill |
|------|-------|
| 新功能开发 | `superpowers:test-driven-development` |
| 复杂问题设计 | `superpowers:brainstorming` |
| Bug 排查 | `superpowers:systematic-debugging` |
| 任务完成前 | `superpowers:verification-before-completion` |
| 代码审查 | `superpowers:requesting-code-review` |
| 并行任务 | `superpowers:subagent-driven-development` |

## 禁止操作

- ❌ 使用 `--no-verify` 跳过 pre-commit
- ❌ 直接 push 到 main 分支
- ❌ 修改 `docs/design/` 下的设计文档
- ❌ 修改 CI 配置文件（除非明确授权）
- ❌ 保留临时文件、废弃代码
