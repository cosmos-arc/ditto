# CLAUDE.md

> Claude Code 项目指导文件 - Ditto 量化交易系统

## 快速参考

```bash
# 环境设置
pixi install && pixi shell

# 代码质量检查（提交前必须全部通过）
pixi run lint
pixi run format
pixi run mypy packages/ apps/ scripts/ tests/
pixi run test

# 完整预提交检查
pre-commit run --all-files
```

---

## 1. 开发环境

### 包管理（使用 pixi，不要用 pip）

```bash
pixi install          # 安装所有依赖
pixi shell            # 激活环境
```

**依赖管理分离**：
- `pixi.toml` → 运行时依赖（Python 包、系统库）
  - 优先使用 `dependencies`, 无法解析依赖时使用 `pypi-dependencies`
- `pyproject.toml` → 代码质量工具配置（ruff、mypy、pytest）

**本地包使用 editable 模式**：
```toml
# pixi.toml
[pypi-dependencies]
ditto-core = { path = "packages/core", editable = true }
ditto-foundation = { path = "packages/foundation", editable = true }
```

---

## 2、代码质量检查清单

提交前必须执行：

```bash
# 方法1：一键检查（推荐）
pre-commit run --all-files

# 方法2：分步检查
pixi run lint .    # Lint
pixi run format .  # Format
pixi run type      # Type check
pixi run pytest    # Tests
```

**规则**: 每次提交前必须通过所有检查，不得使用 `--no-verify` 绕过。
**以上问题必须通过！！！！无法容忍任何的哪怕部分小问题和格式问题**

---

## 3. 开发工作流

### 规划 + TDD 流程 + CI以及CodeReview（**必须遵守**）

1.规划任务
2.建立开发分支
3.执行编码任务
```
4. 编写测试 → 2. 实现功能 → 3. 重构优化 → 4. 提交代码 → 5. CI/CD + AI-CODEREVIEW
执行以上流程至流程通过
```
5.更新文档
6.提交PR

### 代码实现
**必须**优先参考设计文档中的代码实现及伪代码

### Commit 规范（Conventional Commits）

```
<type>(<scope>): <task-id> <description>

# 示例
feat(data): P0-005 implement DuckDB initialization - TDD
fix(api): P0-022 resolve import error in main.py
test(engine): P0-041 add unit tests for RegimeEngine
```

**Type 类型**：`feat` | `fix` | `docs` | `style` | `refactor` | `perf` | `test` | `chore` | `ci` | `build`

**破坏性变更**：在 type 后加 `!`，如 `feat!: breaking change`

### 项目管理
- 项目管理文档：`docs/progress/{sprint*}.md`
- 状态标记：✅ 已完成 | 🔴 阻塞中 | 📝 未开始 | 🔄 进行中
- 完成功能后立即更新任务状态

### 工作规划管理
- 从`sprint`中选择需要完成的Task
- 构建Task工作规划文档：`docs/plans/{sprint*}/{date}-{task*}.md`
- 梳理详细拆解任务项`TaskItem`列表
- 状态标记：✅ 已完成 | 🔴 阻塞中 | 📝 未开始 | 🔄 进行中
- 制定执行优先级
- 确立完成标准
- 开始基于开发流程进行开发
- 完成功能后立即更新任务项状态

### Superpower Skills 使用

| 场景 | 推荐 Skill |
|------|-----------|
| 新功能开发 | `superpowers:test-driven-development` |
| 复杂问题设计 | `superpowers:brainstorming` |
| Bug 排查 | `superpowers:systematic-debugging` |
| 任务完成前 | `superpowers:verification-before-completion` |
| 代码审查 | `superpowers:requesting-code-review` |
| 并行开发 | `superpowers:subagent-driven-development` |

### 文档同步清单

实现完成后需要更新的文档：

| 文档 | 用途 |
|------|------|
| `docs/sprints/sprint-*.md` | 更新任务完成状态 |
| `docs/plans/YYYY-MM-DD-sprint*-task*.md` | 更新实施状态和验收标准 |
| `docs/design/*.md` | 同步命名变更、接口变更 |

### 模块文档更新规则

**任何源码文件变更后，必须判断是否需要更新对应的 `@README.PACKAGE.md` 文件。**

#### 需要更新 @README.PACKAGE.md 的场景

| 变更类型 | 说明 | 示例 |
|----------|------|------|
| 新增类/函数 | 添加新的公开类或函数 | 在 `stores/` 中新增 `FooStore` |
| 修改接口 | 函数签名变更、参数增减 | `connect()` 方法增加 `timeout` 参数 |
| 删除功能 | 移除公开类或函数 | 废弃 `LegacyStore` 类 |
| 架构调整 | 模块职责变化、依赖关系变更 | `stores/` 不再依赖 `runtime/` |

#### 不需要更新的场景

| 变更类型 | 说明 |
|----------|------|
| 私有实现 | 仅修改 `_private_method()` 等私有成员 |
| Bug 修复 | 不改变接口的行为修复 |
| 内部重构 | 代码结构优化但接口不变 |
| 测试代码 | 仅修改 `tests/` 下的文件 |

#### @README.PACKAGE.md 文件位置

| 包级别 | 文件路径 |
|--------|----------|
| ditto_core | `packages/core/src/ditto_core/@README.PACKAGE.md` |
| ditto_datahub | `packages/datahub/src/ditto_datahub/@README.PACKAGE.md` |
| ditto_foundation | `packages/foundation/src/ditto_foundation/@README.PACKAGE.md` |

| 子模块级别 | 文件路径示例 |
|------------|-------------|
| stores | `packages/datahub/src/ditto_datahub/stores/@README.PACKAGE.md` |
| runtime | `packages/datahub/src/ditto_datahub/runtime/@README.PACKAGE.md` |
| config | `packages/foundation/src/ditto_foundation/config/@README.PACKAGE.md` |

#### 更新检查清单

提交代码前，确认以下检查项：

- [ ] 是否新增/修改/删除了公开类或函数？
- [ ] 是否修改了模块的依赖关系？
- [ ] 是否改变了模块的核心职责？
- [ ] 如果是，是否已更新对应的 `@README.PACKAGE.md`？

---

## 4. 项目架构

### 系统分层

```
Web UI (Next.js)
    ↓
API Layer (FastAPI)
    ↓
Application Services (RegimeSvc, RotationSvc, BacktestSvc, RiskSvc)
    ↓
Core Engine (RegimeEngine, FactorEngine, RotationEngine, BacktestEngine, RiskEngine)
    ↓
DataHub (Data Access, External Integrations)
```

### 目录结构

```
apps/
  server/           # FastAPI 后端
    src/ditto-server/
      api/          # HTTP routers
      services/     # Application services
      models/       # Pydantic models
      scheduler/    # Prefect jobs

  web/              # Next.js 前端
    src/
      app/          # Page routes
      components/   # React components
      stores/       # Zustand state

packages/
  datahub/          # 数据存储层
    src/ditto-datahub/
      repositories/ # 仓储逻辑访问
      stores/       # 物理存储访问
      runtime/      # 运行时支持类

  core/             # 核心业务逻辑
    src/ditto-core/
      engine/       # Business logic engines
      strategy/     # Strategy abstractions
      portfolio/    # Portfolio management

  foundation/       # 基础设施
    src/ditto-foundation/
      types/        # Shared types
      contracts/    # Data contracts
      config/       # Configuration
      util/         # Utilities
```

### 核心引擎

| 引擎 | 职责 |
|------|------|
| RegimeEngine | 市场状态识别（牛市/震荡/熊市） |
| FactorEngine | 因子计算（RS、Value、Vol、Crowding） |
| RotationEngine | 多因子打分和 TopN 选择 |
| BacktestEngine | 回测（快速向量化 + 生产事件驱动） |
| RiskEngine | 三级风控（回撤驱动 + 速度检测） |

### 数据架构原则

- **Point-in-Time 安全**：所有因子数据包含 `knowledge_date`，防止未来数据泄露
- **价格调整分离**：存储未复权价格 + 复权因子，动态计算复权价格
- **双存储**：DuckDB（分析/因子） + SQLite（事务）
- **双源验证**：Tushare + AkShare 交叉验证

### 关键约束

- 单机 Windows 环境（Phase 0-1）
- 日频数据（无日内需求）
- ETF 行业轮动策略为主
- 严格风控（KillSwitch 机制）
- 核心功能无云依赖

---

## 5. 重要规则

### 必须遵守

1. **Pre-commit 检查** - 每次提交前必须通过，不得绕过（`--no-verify` 禁止使用）
2. **任务完成后** - 必须运行 `pre-commit run --all-files` 确认通过
3. **TDD 开发** - 先写测试，再实现功能
4. **中文回复** - Claude 使用中文与用户沟通

### 禁止操作

1. **不要修改** `docs/design/` 目录下的设计文档（除非获得明确授权）
2. **不要修改** CI/CD 配置文件（`.pre-commit-config.yaml`、GitHub Actions）
3. **不要使用** `pip install`（使用 pixi）
4. **不要使用** `sys.path` 引入本地包（使用 editable 安装）
5. **不要保留** 临时文档（临时脚本，重构废弃文件等）

### 保留的官方文档

- `.claude/CLAUDE.md` - 项目指导
- `.claude/rules/*.md` - 项目分类别的详细规则
- `README.md` - 项目说明
- `docs/plans/*` - 任务跟踪文档
- `docs/design/*` - 设计文档
- `scripts/` 下的官方脚本

---

## 6. 测试命令

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_specific.py

# 跳过慢测试
pytest -m "not slow"

# 生成覆盖率报告
pytest --cov=packages/ --cov-report=html

# 显示最慢的 10 个测试
pytest --durations=10
```

---

## 7. 数据功能

```bash
# 安装数据依赖
pixi install --feature data

# 更新市场数据
python -m ditto.data.update
```

---

## 附录：Shell 命令跨平台参考

判断开发环境系统后选择相关Shell执行

| 操作 | Windows (PowerShell) | Linux/macOS |
|------|---------------------|-------------|
| 列出文件 | `Get-ChildItem` / `ls` | `ls` |
| 复制 | `Copy-Item` / `copy` | `cp` |
| 移动 | `Move-Item` / `move` | `mv` |
| 删除 | `Remove-Item` / `del` | `rm` |
| 创建目录 | `mkdir` | `mkdir` |
| 环境变量 | `$env:VAR` | `$VAR` |
