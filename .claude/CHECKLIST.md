# 开发检查清单

> 每个开发任务必须按此清单执行，不得跳过任何步骤

---

## 🎯 Superpowers 工作流

> **Claude Code 必须严格遵循技能激活流程**

### 技能激活检查表

| 阶段 | 触发条件 | **必须使用的 Skill** | 检查点 |
|------|----------|---------------------|--------|
| **设计** | 用户描述需求 | `brainstorming` | ✅ 需求已充分讨论<br>✅ 设计方案已确认<br>✅ 边界条件已明确 |
| **计划** | 设计确认后 | `writing-plans` | ✅ 计划已生成<br>✅ 强调 TDD/YAGNI/DRY<br>✅ 用户已确认 |
| **执行** | 开始实施 | `executing-plans` + `test-driven-development` | ✅ RED: 测试失败<br>✅ GREEN: 最少代码通过<br>✅ REFACTOR: 优化重构<br>✅ COMMIT: 每循环提交 |
| **审查** | 任务间隙 | `requesting-code-review` | ✅ 对照计划审查<br>✅ 按严重性报告问题 |
| **完成** | 任务完成 | `finishing-a-development-branch` | ✅ 验证测试通过<br>✅ 提供 PR/合并决策 |

### 禁止行为

| 禁止 | 替代方案 |
|------|----------|
| 跳过 brainstorming 直接实现 | 使用 Skill 工具调用 brainstorming |
| 先写代码后补测试 | 遵循 TDD: RED→GREEN→REFACTOR |
| 单个大提交包含整个功能 | 每个红绿循环独立提交 |
| 声称完成前不验证 | 使用 verification-before-completion |
| 完成后不使用 finishing 技能 | 使用 Skill 工具调用 finishing-a-development-branch |

---

## 一、任务启动

### 1.1 选择任务

- [ ] 从当前 Sprint 文件（`docs/sprints/sprint-XX-*.md`）选择任务
- [ ] 确认任务优先级（P0 必须 / P1 应该）
- [ ] 确认任务依赖已满足

### 1.2 设计细化 (brainstorming)

> **MANDATORY**: 使用 Skill 工具调用 `superpowers:brainstorming`

- [ ] 需求已充分讨论
- [ ] 设计方案已确认
- [ ] 边界条件已明确
- [ ] 接口设计已定义

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

- [ ] `docs/sprints/sprint-XX-*.md` 已更新，标记为进行中

---

## 二、计划与执行

### 2.1 生成实施计划 (writing-plans)

> **MANDATORY**: 使用 Skill 工具调用 `superpowers:writing-plans`

- [ ] 计划已生成
- [ ] 计划强调 TDD、YAGNI、DRY
- [ ] 用户已确认计划
- [ ] 复杂任务已保存到 `docs/plans/`

### 2.2 执行任务 (executing-plans + test-driven-development)

> **MANDATORY**: 使用 Skill 工具调用 `superpowers:executing-plans`

> **每个子任务必须遵循 TDD: RED → GREEN → REFACTOR**

#### TDD 循环检查清单

**RED (写测试)**:
- [ ] 测试已创建，描述期望行为
- [ ] 运行测试，确认失败（观察错误信息）
- [ ] **提交**: `test(scope): add test for xxx`

**GREEN (写最少代码)**:
- [ ] 写最少代码使测试通过
- [ ] 运行测试，确认通过
- [ ] **提交**: `feat(scope): implement xxx`

**REFACTOR (优化)**:
- [ ] 清理代码，改善设计
- [ ] 运行测试，确认仍通过
- [ ] **提交**: `refactor(scope): improve xxx`

### 2.3 提交粒度规范

> **❌ 禁止**: 单个大提交包含整个功能
> **✅ 正确**: 每个 TDD 循环独立提交

#### 何时 Commit

| 场景 | 示例 | Commit Message 格式 |
|------|------|---------------------|
| 完成一个函数 | SqlEngine._register_views | `feat(sql_engine): implement _register_views` |
| 完成一个测试类 | TestSqlEngine 基础测试 | `test(sql_engine): add test skeleton` |
| RED→GREEN 完成 | 测试通过 | `feat(sql): make sql query tests pass` |
| 重构完成 | 代码改善 | `refactor(hub): simplify dependency injection` |
| 修复 Bug | 类型错误 | `fix(types): add proper type hints` |

#### ❌ 错误提交示例

| 错误示例 | 问题 |
|----------|------|
| 单个提交整个 DataHub 功能 | 粒度过粗，无法回滚特定步骤 |
| "WIP" 或 "fix all tests" | 信息不明确 |
| 混合多个不相关改动 | 违反单一职责 |

#### ✅ 正确提交序列示例

```bash
# SqlEngine 实现的提交序列
git commit -m "test(sql_engine): add test skeleton for SqlEngine"                    # RED
git commit -m "feat(sql_engine): implement SqlEngine.__init__ and _setup"            # GREEN
git commit -m "feat(sql_engine): implement _register_views for Parquet datasets"     # GREEN
git commit -m "feat(sql_engine): implement adjustment macros (qfq, qfq_now)"         # GREEN
git commit -m "refactor(sql_engine): extract view registration to separate method"   # REFACTOR

# DataHub 实现的提交序列
git commit -m "test(hub): add test skeleton for DataHub"                             # RED
git commit -m "feat(hub): implement DataHub.__init__ with cached_property"           # GREEN
git commit -m "feat(hub): implement runtime layer properties"                         # GREEN
git commit -m "feat(hub): implement store layer properties"                           # GREEN
git commit -m "feat(hub): implement repository layer properties"                     # GREEN
git commit -m "refactor(hub): simplify dependency injection pattern"                 # REFACTOR
```

### 2.4 代码审查 (requesting-code-review)

> **MANDATORY**: 任务间隙使用 Skill 工具调用 `superpowers:requesting-code-review`

- [ ] 对照计划审查实现
- [ ] 按严重性报告问题（阻塞性/重要/建议）
- [ ] 问题已修复

### 2.5 持续验证

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
- [ ] 使用 `cast()` 处理复杂类型

**可观测性**：
- [ ] 日志从 `ditto_foundation` 导入
- [ ] 日志包含 `event` 字段
- [ ] span 名称符合 `{domain}.{operation}` 格式

---

## 四、提交前检查

### 4.1 完成前验证 (verification-before-completion)

> **MANDATORY**: 声称完成前必须验证

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
- [ ] Sprint 文件状态已更新

---

## 五、🛡️ Definition of Done

> **必须全部勾选，才能进入完成阶段**

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

### Git 提交 ✅
- [ ] 提交粒度合理（每个 TDD 循环独立提交）
- [ ] Commit Message 符合规范
- [ ] 没有 "WIP" 或 "fix tests" 提交
- [ ] 提交数量 ≥ 子任务数（每个功能点独立提交）

### 文档 ✅
- [ ] README.md 已更新（如有接口变更）
- [ ] `docs/sprints/sprint-XX-*.md` 状态已更新

---

## 六、完成分支 (finishing-a-development-branch)

> **MANDATORY**: 使用 Skill 工具调用 `superpowers:finishing-a-development-branch`

### 6.1 决策点

**请选择**:
- [ ] **创建 PR** → 适用于功能完整、需要 Review 的代码
- [ ] **本地合并** → 适用于小型工具函数、实验性功能
- [ ] **保留分支** → 适用于未完成的工作、后续继续开发
- [ ] **丢弃分支** → 适用于实验失败、废弃的代码

### 6.2 创建 PR（如选择）

```bash
git push -u origin feat/task-name
gh pr create --base main --title "feat: description" --body "## 变更类型
- [x] feat: 新功能

## 变更描述
...

## DoD 检查
- [x] ci-check 通过
- [x] 测试覆盖达标
"
```

### 6.3 等待 CI

- [ ] GitHub Actions CI 全部通过
- [ ] Codecov 覆盖率达标

### 6.4 合并

- [ ] 使用 Squash and merge
- [ ] 确认 Commit Message 清晰

---

## 七、合并后清理

### 7.1 本地清理

```bash
git checkout main
git pull origin main
git branch -d feat/task-name
```

### 7.2 文档更新

- [ ] Sprint 文件中的任务状态已更新（checkbox → ✅）
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
| 单个提交包含整个功能 | 拆分为多个小提交，每个 TDD 循环独立 |
| 没有使用 brainstorming | 使用 Skill 工具调用 brainstorming |
| 没有使用 test-driven-development | 使用 Skill 工具调用 test-driven-development |
| 声称完成但未验证 | 使用 verification-before-completion |
| 完成后未使用 finishing 技能 | 使用 Skill 工具调用 finishing-a-development-branch |

---

## 领域规范速查

| Domain | Rules 文件 |
|--------|-----------|
| 引擎基类 | `.claude/rules/domain/engines/base.md` |
| 因子计算 | `.claude/rules/domain/engines/factor.md` |
| 策略 | `.claude/rules/domain/strategy.md` |
| 回测 | `.claude/rules/domain/engines/backtest.md` |
| 风控 | `.claude/rules/domain/risk.md` |
| 市场状态 | `.claude/rules/domain/engines/regime.md` |
| 数据安全 | `.claude/rules/domain/pit-safety.md` |
| Polars | `.claude/rules/backend/polars.md` |
| 测试 | `.claude/rules/backend/python-test.md` |
| API | `.claude/rules/backend/fastapi.md` |
| 可观测性 | `.claude/rules/backend/observability.md` |
| Git 工作流 | `.claude/rules/git-workflow.md` |
