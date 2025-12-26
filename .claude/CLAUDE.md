# CLAUDE.md

> Claude Code 项目指导文件 - Ditto 量化交易系统

---

## ⛔ 硬性规则（CRITICAL）

> **以下规则必须无条件遵守，不得绕过或寻找替代方案。**
> **违反时必须立即停止并告知用户。**

### 开发流程

| 必须 | 禁止 |
|------|------|
| 从 main 创建分支开发 | ❌ 在 main 分支直接修改 |
| TDD：先写测试再实现 | ❌ 先实现后补测试 |
| 通过 PR 合入 main | ❌ 直接 push 到 main |
| `pixi run -e dev ci-check` 全部通过 | ❌ 有错误时提交 |
| 正常提交流程 | ❌ 使用 `--no-verify` |
| AI 代码必须经过 Polishing | ❌ AI 粗坯直接合入 |

### 环境与工具

| 必须 | 禁止 |
|------|------|
| `pixi install` / `pixi add` | ❌ `pip install` |
| `pixi run -e dev <task>` | ❌ 省略 `-e dev` 运行开发工具 |
| editable 模式安装本地包 | ❌ `sys.path` 操作 |

### 代码规范

| 必须 | 禁止 |
|------|------|
| `import polars as pl` | ❌ `import pandas` |
| 所有公开函数有类型注解 | ❌ 省略类型注解 |
| 参数化 SQL `execute(sql, params)` | ❌ f-string 拼接 SQL |
| `from ditto_foundation import logger` | ❌ `from loguru import logger` |
| 日志包含 `event` 字段 | ❌ 缺少 event 字段 |
| 单函数 ≤50 行，嵌套 ≤3 层 | ❌ 过长函数、深层嵌套 |

### PIT 数据安全

| 必须 | 禁止 |
|------|------|
| 财务数据用 `knowledge_date` 过滤 | ❌ 用 `trade_date` 过滤 |
| `rolling_mean(n, closed="left")` | ❌ 不指定 closed 参数 |
| 信号使用 T-1 数据，T 日执行 | ❌ 当日收盘价生成当日信号 |

### 风控模块

| 必须 | 禁止 |
|------|------|
| 风控检查同步执行 | ❌ 异步跳过风控 |
| 风控模块 100% 测试覆盖 | ❌ 风控代码无测试 |
| 所有路径经过风控 | ❌ 任何绕过风控的后门 |

### 文档保护（未经授权禁止修改）

- `docs/design/*` - 设计文档
- `.pre-commit-config.yaml` - Pre-commit 配置
- `.github/workflows/*` - CI/CD 配置

### 其他规则

| 必须 | 禁止 |
|------|------|
| 使用中文与用户沟通 | ❌ 英文回复（除非用户要求） |
| 及时清理临时文件和 AI 冗余代码 | ❌ 保留临时脚本、废弃文件 |

### 违规处理

```
发现即将违规 → 立即停止 → 告知用户 → 提出合规方案 → 确认后继续
```

---

> ⚠️ **开发前请阅读 `.claude/CHECKLIST.md` 完整检查清单**

---

## 快速参考

```bash
# 环境
pixi install && pixi shell -e dev

# 代码质量（提交前必须全部通过）
pixi run -e dev ci-check

# 分支开发
git checkout main && git pull
git checkout -b feat/task-name
# ... 开发 ...
git push -u origin feat/task-name
gh pr create --base main
```

---

## 1. 开发环境

### Pixi 环境规则

| 环境 | 用途 | 命令 |
|------|------|------|
| `dev` | 开发、测试、CI | `pixi run -e dev <task>` |
| `default` | 生产部署 | `pixi run <task>` |

```bash
# 开发环境（包含 ruff, mypy, pytest, pre-commit, bandit）
pixi run -e dev lint
pixi run -e dev typecheck
pixi run -e dev test-unit
pixi run -e dev ci-check

# 生产环境
pixi run server
```

### 依赖管理

- `pixi.toml` → 依赖声明
- `pyproject.toml` → 工具配置（ruff、mypy、pytest）
- 本地包使用 editable 模式

---

## 2. 代码质量

### 检查命令

```bash
# 推荐：一键检查
pixi run -e dev ci-check

# 或分步
pixi run -e dev lint          # Ruff
pixi run -e dev format        # Format
pixi run -e dev typecheck     # MyPy
pixi run -e dev test-unit     # Tests
```

### 质量标准

| 检查项 | 标准 |
|--------|------|
| Lint / Format | 0 错误 |
| Type Check | 0 错误 |
| Security | 0 高危 |
| Coverage | ≥80%（风控模块 100%） |

### 代码审美标准

| 维度 | 标准 |
|------|------|
| 函数长度 | ≤50 行 |
| 嵌套深度 | ≤3 层 |
| 命名 | 符合项目词汇表 |
| AI 代码 | 必须清理冗余，重构后才能合入 |

---

## 3. Superpowers 驱动的开发工作流

### 核心理念

**Skills 自动激活，无需手动调用。** 当检测到相关任务时，对应 Skill 会自动介入。

```
用户描述需求
    ↓
brainstorming → 交互式设计细化，分块确认
    ↓
writing-plans → 创建实施计划（适合无经验工程师执行）
    ↓
用户确认 → 创建开发分支
    ↓
executing-plans → 批量执行任务（TDD 模式）
    ↓
finishing-a-development-branch → 完成分支，创建 PR
```

### Skill 自动激活表

| Skill | 激活场景 | 行为 |
|-------|----------|------|
| `brainstorming` | "让我们构建..."、"设计一个..." | 交互式设计细化，分块展示等待确认 |
| `writing-plans` | 设计确认后 | 生成清晰实施计划，强调 TDD/YAGNI/DRY |
| `executing-plans` | "开始执行"、计划确认后 | 批量执行工程任务 |
| `test-driven-development` | 实现功能时 | 强制 TDD：红→绿→重构 |
| `systematic-debugging` | 调试问题时 | 4阶段根因分析流程 |
| `verification-before-completion` | 声称完成前 | 确保真正完成，不遗漏 |
| `requesting-code-review` | 任务间隙 | 对照计划审查，按严重性报告问题 |
| `finishing-a-development-branch` | 任务完成时 | 验证测试，提供选项：PR/merge/keep/discard |
| `subagent-driven-development` | 复杂并行任务 | 子代理执行 + 两阶段审查 |

### 分支开发流程

```bash
# 1. 确保在最新 main
git checkout main
git pull origin main

# 2. 创建功能分支
git checkout -b feat/task-name

# 3. 开发（Superpowers 自动介入）
# - brainstorming 细化设计
# - writing-plans 生成计划
# - executing-plans 执行任务
# - test-driven-development 保证质量

# 4. 提交变更
git add .
git commit -m "feat(scope): description"

# 5. 推送并创建 PR
git push -u origin feat/task-name
gh pr create --base main --title "feat: description"

# 6. CI 通过后合并
# 使用 Squash and merge

# 7. 清理本地分支
git checkout main
git pull origin main
git branch -d feat/task-name
```

### 分支命名规范

```bash
feat/momentum-factor       # 功能
fix/import-error           # 修复
refactor/engine-cleanup    # 重构
docs/readme-update         # 文档
test/add-unit-tests        # 测试
ci/optimize-workflow       # CI/CD
```

### Commit 规范

```bash
# 格式：<type>(<scope>): <description>
git commit -m "feat(factor): implement momentum factor"
git commit -m "fix(api): resolve import error"
git commit -m "test(risk): add kill switch edge cases"
```

Type: `feat` | `fix` | `docs` | `refactor` | `test` | `chore` | `ci`

---

## 4. 本地任务管理

### 文档结构

```
docs/
├── sprints/
│   ├── README.md                    # 总览 + 当前状态
│   ├── sprint-01-data-layer.md      # Sprint 1 规划（Epic 级）
│   ├── sprint-02-core-engines.md    # Sprint 2 规划
│   ├── sprint-03-backtest-risk.md   # Sprint 3 规划
│   └── backlog.md                   # 想法池、技术债
└── plans/
    ├── sprint-01/                   # 按 Sprint 组织
    │   ├── task1-runtime-layer.md   # 详细任务规划
    │   └── task2-store-layer.md
    └── sprint-02/
        └── ...
```

### 文件职责

| 文件 | 职责 | 更新时机 |
|------|------|----------|
| `README.md` | 当前 Sprint 进度 | 任务状态变更时 |
| `sprint-XX-*.md` | Epic 规划，任务列表 | 规划阶段 |
| `backlog.md` | 想法池、技术债 | 随时 |
| `plans/*.md` | 任务详细拆解 | 复杂任务开始前 |

### Plan 文件使用时机

```
简单任务 (S/M)：
  → Superpowers 即时规划
  → 不需要保存 Plan 文件

复杂任务 (L) / 跨 Session：
  → 保存到 docs/plans/sprint-XX/
  → 便于恢复上下文
```

### 工作节奏

**日常（Continuous Flow）**：
1. 从当前 Sprint 文件选择任务
2. Superpowers 自动介入：brainstorm → plan → execute
3. 更新 Sprint 文件中的任务状态（checkbox）
4. 如有详细规划，更新 plans/ 文件

**每周五（30分钟回顾）**：
1. 回顾本周完成任务
2. 清理 `backlog.md` 过时想法
3. 识别技术债
4. 更新 Sprint README 进度

---

## 5. 项目架构

### 系统分层

```
Web UI (Next.js)
    ↓
API Layer (FastAPI)
    ↓
Application Services
    ↓
Core Engine (Regime, Factor, Rotation, Backtest, Risk)
    ↓
DataHub (DuckDB + SQLite)
```

### 目录结构

```
apps/
  server/              # FastAPI
  web/                 # Next.js

packages/
  core/                # 核心引擎
  datahub/             # 数据存储
  foundation/          # 基础设施
```

### 核心引擎

| 引擎 | 职责 |
|------|------|
| RegimeEngine | 市场状态识别 |
| FactorEngine | 因子计算 |
| RotationEngine | 多因子选择 |
| BacktestEngine | 策略回测 |
| RiskEngine | 三级风控 |

### 关键约束

- 单机 Windows 环境
- 日频数据
- ETF 行业轮动策略
- 严格风控（Kill Switch）
- Point-in-Time 安全

---

## 6. 领域规范索引

| 领域 | 规范文件 | 适用路径 |
|------|----------|----------|
| 引擎基类 | `base.md` | `engine/**` |
| 因子计算 | `factor.md` | `engine/factor*` |
| 策略 | `strategy.md` | `strategy/**` |
| 回测 | `backtest.md` | `engine/backtest*` |
| 风控 | `risk.md` | `risk/`, `execution/`, `portfolio/` |
| 市场状态 | `regime.md` | `engine/regime*` |
| PIT 安全 | `pit-safety.md` | `core/`, `foundation/` |
| Polars | `polars.md` | `packages/**` |
| 测试 | `python-test.md` | `tests/**` |
| API | `fastapi.md` | `apps/server/**` |
| 可观测性 | `observability.md` | `**/*.py` |

---

## 7. 测试

```bash
# 运行所有测试
pytest

# 特定测试
pytest tests/test_specific.py

# 跳过慢测试
pytest -m "not slow"

# 覆盖率
pytest --cov=packages/ --cov-report=html
```

### 覆盖率要求

| 模块 | 要求 |
|------|------|
| 整体 | ≥80% |
| core-strategy | ≥90% |
| core-engine | ≥85% |
| datahub | ≥85% |
| 风控模块 | 100% |

---

## 附录：跨平台命令

| 操作 | Windows (PowerShell) | Linux/macOS |
|------|---------------------|-------------|
| 列出文件 | `Get-ChildItem` / `ls` | `ls` |
| 复制 | `Copy-Item` / `copy` | `cp` |
| 删除 | `Remove-Item` / `del` | `rm` |
| 环境变量 | `$env:VAR` | `$VAR` |
