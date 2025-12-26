# 开发检查清单

> 每个开发任务必须按此清单执行，不得跳过任何步骤

---

## 一、任务启动

### 1.1 选择任务

- [ ] 从当前 Sprint 文件（`docs/sprints/sprint-XX-*.md`）选择任务
- [ ] 确认任务优先级（P0 必须 / P1 应该）
- [ ] 确认任务依赖已满足

### 1.2 设计细化（Superpowers 自动介入）

当你描述需求时，`brainstorming` skill 会自动激活：

- [ ] 需求已充分讨论
- [ ] 设计方案已确认
- [ ] 边界条件已明确

### 1.3 创建开发分支

```bash
git checkout main
git pull origin main
git checkout -b feat/task-name
```

- [ ] 已从最新 main 创建分支
- [ ] 分支命名符合规范：`feat/` | `fix/` | `refactor/` | `docs/` | `test/` | `ci/`
- [ ] **确认不在 main 分支上**

### 1.4 更新任务状态

- [ ] `docs/sprints/current.md` 已更新，标记为进行中

---

## 二、计划与执行

### 2.1 生成实施计划（Superpowers 自动介入）

`writing-plans` skill 会生成适合执行的任务列表：

- [ ] 计划已生成
- [ ] 计划强调 TDD、YAGNI、DRY
- [ ] 用户已确认计划

### 2.2 执行任务（Superpowers 自动介入）

`executing-plans` 和 `test-driven-development` 会自动激活：

- [ ] 按 TDD 模式执行：红 → 绿 → 重构
- [ ] 每个子任务完成后有 code review
- [ ] 代码基本能运行

### 2.3 持续验证

```bash
# 开发过程中定期运行
pixi run -e dev lint
pixi run -e dev typecheck
pixi run -e dev test-unit
```

---

## 三、Polishing 阶段

> AI 生成的代码必须经过精修才能合入

### 3.1 代码审美检查

- [ ] **命名规范**：变量/函数命名符合项目词汇表
- [ ] **函数长度**：单函数 ≤50 行
- [ ] **嵌套深度**：≤3 层
- [ ] **无冗余代码**：清理 AI 生成的重复/无用代码
- [ ] **模块解耦**：逻辑没有污染其他层级

### 3.2 规范检查

**数据处理**：
- [ ] 使用 Polars，**不是** Pandas
- [ ] 使用 LazyFrame，最后 `.collect()`
- [ ] rolling 操作指定了 `closed="left"`

**PIT 安全**（如涉及数据）：
- [ ] 财务数据使用 `knowledge_date` 过滤
- [ ] 信号生成使用 T-1 数据
- [ ] as-of join 使用 `strategy="backward"`

**类型注解**：
- [ ] 所有公开函数有完整类型注解
- [ ] 返回值类型明确

**可观测性**：
- [ ] 日志从 `ditto_foundation` 导入
- [ ] 日志包含 `event` 字段
- [ ] span 名称符合 `{domain}.{operation}` 格式

---

## 四、提交前检查

### 4.1 完整质量检查

```bash
# 必须全部通过，0 错误！
pixi run -e dev ci-check
```

- [ ] lint 通过（0 错误）
- [ ] format 通过（0 错误）
- [ ] typecheck 通过（0 错误）
- [ ] security 通过（0 高危）
- [ ] test-unit 通过

### 4.2 覆盖率检查

| 模块 | 要求 | 实际 |
|------|------|------|
| 整体 | ≥80% | ___% |
| 风控模块 | 100% | ___% |

### 4.3 Pre-commit 检查

```bash
pre-commit run --all-files
```

- [ ] 所有 hooks 通过

### 4.4 文档更新检查

- [ ] 是否需要更新模块 README.md？

---

## 五、🛡️ Definition of Done

> **必须全部勾选，才能创建 PR**

### 工程质量 ✅
- [ ] `pixi run -e dev ci-check` 全部通过
- [ ] 测试覆盖 ≥80%（风控模块 100%）
- [ ] 类型注解完整，MyPy 0 错误
- [ ] 无安全漏洞（Bandit 通过）

### 代码审美 ✅
- [ ] 命名符合项目约定
- [ ] 无冗余的 AI 生成代码（已清理）
- [ ] 单函数 ≤50 行
- [ ] 嵌套 ≤3 层
- [ ] 模块职责清晰，无跨层污染

### PIT 安全 ✅（如涉及数据）
- [ ] 使用 `knowledge_date` 过滤
- [ ] rolling 指定 `closed="left"`
- [ ] 信号 T-1 生成，T 日执行

### 风控模块 ✅（如涉及风控）
- [ ] 测试覆盖 100%
- [ ] 风控检查同步执行
- [ ] 无绕过风控的后门

### 文档 ✅
- [ ] README.md 已更新（如有接口变更）
- [ ] `docs/sprints/current.md` 状态已更新

---

## 六、完成分支（Superpowers 自动介入）

`finishing-a-development-branch` skill 会：
1. 验证所有测试通过
2. 提供选项：创建 PR / 本地合并 / 保留 / 丢弃

### 6.1 提交变更

```bash
git add .
git commit -m "feat(scope): description"
git push -u origin feat/task-name
```

### 6.2 创建 PR

```bash
gh pr create --base main --title "feat: description"
```

PR 描述应包含：
- 变更类型
- 变更概述
- DoD 检查结果

### 6.3 等待 CI

- [ ] GitHub Actions CI 全部通过
- [ ] Codecov 覆盖率达标

### 6.4 合并

- [ ] 使用 Squash and merge

---

## 七、合并后清理

### 7.1 本地清理

```bash
git checkout main
git pull origin main
git branch -d feat/task-name
```

### 7.2 文档更新

- [ ] Sprint 文件中的任务状态已更新（checkbox）
- [ ] 如有 Plan 文件，已更新完成状态
- [ ] Sprint README 进度已同步

---

## 快速命令参考

```bash
# 环境
pixi shell -e dev

# 质量检查
pixi run -e dev ci-check       # 完整检查（推荐）
pixi run -e dev lint           # Lint
pixi run -e dev typecheck      # Type check
pixi run -e dev test-unit      # 单元测试
pre-commit run --all-files     # Pre-commit

# Git 分支操作
git checkout main && git pull  # 更新 main
git checkout -b feat/name      # 创建分支
git push -u origin feat/name   # 推送分支
gh pr create --base main       # 创建 PR

# 测试
pytest tests/unit/             # 运行单元测试
pytest --cov=packages/ -v      # 带覆盖率
pytest -k "test_name"          # 运行特定测试
```

---

## 违规自检

如果发现以下情况，**立即停止并纠正**：

| 发现 | 行动 |
|------|------|
| 在 main 分支上编辑了代码 | `git stash` → 创建分支 → `git stash pop` |
| 先写了实现没写测试 | 停止实现 → 补写测试 → 确认测试失败 → 继续 |
| import 了 pandas | 改为 import polars |
| rolling 没有 closed 参数 | 添加 `closed="left"` |
| ci-check 有错误 | 修复所有错误，不得跳过 |
| AI 代码未经 Polishing | 回到 Polishing 阶段，清理重构 |
| DoD 未全部勾选就想合并 | 回到检查清单，逐项完成 |

---

## 领域规范速查

| Domain | Rules 文件 |
|--------|-----------|
| 引擎基类 | `.claude/rules/base.md` |
| 因子计算 | `.claude/rules/factor.md` |
| 策略 | `.claude/rules/strategy.md` |
| 回测 | `.claude/rules/backtest.md` |
| 风控 | `.claude/rules/risk.md` |
| 市场状态 | `.claude/rules/regime.md` |
| 数据安全 | `.claude/rules/pit-safety.md` |
| Polars | `.claude/rules/polars.md` |
| 测试 | `.claude/rules/python-test.md` |
| API | `.claude/rules/fastapi.md` |
| 可观测性 | `.claude/rules/observability.md` |
