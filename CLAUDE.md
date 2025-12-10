# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup ⚠️
**项目使用 pixi 作为包管理工具，不要使用 pip 直接安装依赖！**

```bash
# 安装所有依赖（推荐）
pixi install

# 仅安装基础依赖（不含数据源）
pixi install --without default

# 初始化默认环境
pixi shell
```

### Package Management Structure ⚠️ **重要**

**依赖管理分离原则**：
- **pixi.toml**: 管理所有运行时依赖（Python 包、系统库）
- **pyproject.toml**: 仅用于代码质量工具配置（ruff、mypy、pytest 等）

#### 依赖分类
- **核心依赖**: Web框架、数据处理、数据库等（在 `pixi.toml` `[dependencies]`）
- **数据源依赖**: tushare、akshare（在 `pixi.toml` `[pypi-dependencies]`）
- **开发工具**: ruff、mypy、pytest（在 `pyproject.toml` 或 `pixi.toml` 开发环境）

#### 本地包引用 ⚠️ **极其重要**
**本项目使用 editable 模式安装本地包，禁止使用 sys.path 方式！**

```toml
# pixi.toml 中的正确配置
[pypi-dependencies]
ditto-core = { path = "packages/core", editable = true }
ditto-foundation = { path = "packages/foundation", editable = true }
```

**为什么必须使用 editable 模式**：
1. **开发时实时更新**：修改包内代码无需重新安装即可生效
2. **正确的导入路径**：IDE 和 type checker 能正确识别模块路径
3. **避免运行时错误**：不会出现模块找不到的问题
4. **符合 Python 最佳实践**：标准化的包管理方式

**错误的做法**：
```python
# ❌ 绝对不要这样做！
import sys
sys.path.insert(0, "path/to/package")
```

**正确的导入方式**：
```python
# ✅ 使用 editable 包后直接导入
from ditto.core.data.clients import TushareClient
from ditto_foundation.config import Settings
```

#### Feature 使用
```bash
# 安装数据源依赖
pixi install  # 自动安装所有依赖，包括数据源

# 或者只安装特定功能
pixi install --without default  # 仅基础依赖
# 然后手动安装数据源：pip install tushare akshare
```

### Code Quality Requirements ⚠️ **极其严格**
**All Python code must comply with ruff formatting AND linting standards. This is a strict requirement for all contributions.**

#### 🔴 零容忍规则：Ruff 检查必须全部通过
**在提交任何代码之前，必须确保：**
1. `pixi run ruff check .` 必须返回 "All checks passed!"
2. `pixi run ruff format .` 必须没有任何格式问题
3. `pixi run mypy packages/ apps/ scripts/ tests/` 必须通过类型检查
4. **没有任何例外！** 任何问题都必须在提交前修复

#### 🟢 编码阶段必须遵守的 Ruff Lint 规则
**在编写代码时就必须遵守以下规则，不要等到提交前修复：**

1. **导入规则 (I)**
   - 导入必须在文件顶部，按字母顺序排列
   - 禁止使用 `import *`
   - 禁止循环导入

2. **代码风格 (E, W)**
   - 行长度不超过88字符
   - 禁止使用未定义的变量
   - 禁止使用未使用的导入和变量

3. **类型注解 (ANN)**
   - 所有公共函数必须有返回类型注解
   - 参数类型注解是强制的（除了self/cls）
   - 禁止使用 `Any` 类型（特殊情况除外）

4. **代码质量 (B, PLC, PLE, PLR, PLW, RUF)**
   - 禁止使用魔法数字（应该定义为常量）
   - 函数复杂度不能过高（C901）
   - 禁止不必要的变量赋值
   - 注意：Pylint规则已细分为PLC（约定）、PLE（错误）、PLR（重构）、PLW（警告）

5. **最佳实践 (UP, SIM, PTH)**
   - 使用现代Python语法（f-string, 类型注解等）
   - 使用pathlib替代os.path
   - 简化不必要的循环和条件判断

#### ⚡ Ruff 性能优化配置
- **cache-dir**: 使用`.ruff_cache`缓存结果，提升重复检查速度
- **respect-gitignore**: 自动忽略.gitignore中的文件
- **force-exclude**: 强制排除配置中的目录，即使显式指定

Both formatting and linting issues must be resolved before code can be considered complete.

### 导入和编译问题 ⚠️ **最高优先级**
**所有 Python 代码必须能够正确导入和编译，不存在任何语法错误。这是代码可运行的基本前提。**

#### 全局检查要求
```bash
# 1. 检查所有 Python 文件的语法正确性
python -m py_compile packages/ apps/ scripts/ tests/  # 必须全部通过

# 2. 检查导入错误
ruff check packages/ apps/ scripts/ tests/ --select=E,F,PLC0415,PLC0414

# 3. 测试模块导入
python -c "
# pixi 会自动配置 editable packages，无需手动添加路径
# 测试所有关键模块能够正常导入
from ditto_foundation.config.settings import get_settings
from ditto.data.service import DataService
"
```

#### 解决原则
1. **零容忍**: 任何语法错误都必须立即修复，不允许进入代码库
2. **依赖检查**: 所有第三方依赖必须在 `pyproject.toml` 中明确声明
3. **导入路径**: 确保所有模块能够通过正确的 Python 路径导入
4. **实时验证**: 每次修改后必须运行编译检查确保无新错误

```bash
# Before committing, always run:
pixi run ruff check packages/ apps/ scripts/ tests/  # Check for issues
pixi run ruff format packages/ apps/ scripts/ tests/   # Format code
pixi run ruff check --fix packages/ apps/ scripts/ tests/  # Auto-fix issues

# The project uses ruff for both linting and formatting
# Configuration is in pyproject.toml

# Type checking
pixi run mypy packages/ apps/ scripts/ tests/           # Static type checking
pyright packages/ apps/ scripts/ tests/                 # VSCode integrated type checking

# Run tests
pytest                                          # Run all tests with coverage
pytest tests/test_specific.py                 # Run specific test
pytest -m "not slow"                            # Skip slow tests
pytest --cov=packages/ --cov-report=html       # Generate HTML coverage report

# Enhanced test commands
pytest --cov-report=term-missing:skip-covered   # Show only uncovered lines in terminal
pytest --cov-report=html:htmlcov               # Generate HTML report with branch coverage
pytest --durations=10                          # Show 10 slowest tests
```

### Type Checking Requirements ⚠️ **严格类型检查**
**项目使用严格的类型检查策略，确保代码的类型安全。**

#### MyPy 配置
- **strict模式**: 启用所有严格类型检查
- **show_error_codes**: 显示错误代码，便于快速定位问题
- **pydantic.mypy插件**: 提供Pydantic模型的专用类型检查
- **ignore_missing_imports**: 忽略第三方库的类型存根缺失

#### Pydantic MyPy 插件配置
```toml
[tool.pydantic-mypy]
init_forbid_extra = true      # 禁止模型接收额外字段
init_typed = true             # 强制初始化参数类型检查
warn_required_dynamic_aliases = true  # 警告必需的动态别名
```

#### Pyright 配置
- **typeCheckingMode = "strict"**: VSCode中启用严格模式
- **extraPaths**: 配置源码路径，确保正确解析
- **reportUnknownVariableType = "information"**: 对未知类型变量仅显示信息
- **reportUnknownMemberType = "information"**: 对第三方库未知成员放宽检查

### Test Configuration Enhancements
**项目配置了增强的pytest设置，提供更好的测试体验和覆盖率报告。**

#### 测试特性
- **Async测试支持**: `asyncio_mode = "auto"` 自动检测并运行异步测试
- **分支覆盖率**: 启用 `--cov-branch` 跟踪条件分支的覆盖情况
- **测试性能分析**: `--durations=10` 显示最慢的10个测试
- **严格标记**: `--strict-markers` 确保所有测试标记都已注册
- **覆盖率阈值**: 设置 `--cov-fail-under=80` 要求至少80%的代码覆盖率

#### 测试标记
- `unit`: 单元测试
- `integration`: 集成测试
- `e2e`: 端到端测试
- `slow`: 运行缓慢的测试（可使用 `-m "not slow"` 跳过）
- `smoke`: 冒烟测试

#### 覆盖率配置
- **源码目录**: `packages/` 和 `apps/`
- **排除目录**: 测试文件、迁移文件、conftest.py等
- **HTML报告**: 输出到 `htmlcov/` 目录，包含分支覆盖率详情
- **终端报告**: 仅显示未覆盖的行，跳过已完全覆盖的文件

### Python Format Standards
- **Line Length**: 88 characters maximum
- **Quotes**: Double quotes for strings
- **Import Style**: isort format with one import per line
- **Trailing Commas**: Required in multi-line structures
- **Indentation**: 4 spaces (no tabs)
- **Type Hints**: Required for all function parameters and return values
- **Docstrings**: Google-style or NumPy-style required for all modules and public functions
- **Naming Conventions**:
  - Variables and functions: snake_case
  - Classes: PascalCase
  - Constants: UPPER_SNAKE_CASE
  - Private members: prefix with underscore

### Pre-commit Workflow ⚠️ **自动化强制执行**
**Pre-commit hooks会在每次提交时自动运行，任何违反ruff规则的代码都无法提交！**

#### 自动检查内容：
1. **基础检查** - 文件尾空行、YAML/TOML格式、大文件检测、合并冲突等
2. **Ruff Lint** - 检查所有代码质量问题（零容忍），自动修复可修复的问题
3. **Ruff Format** - 自动格式化代码（不符合格式的提交会被阻止）
4. **Mypy** - 严格类型检查，配合Pydantic插件确保类型安全
5. **可选 pytest** - 可配置在push阶段运行快速测试套件

#### 关键配置说明：
- **--exit-non-zero-on-fix**: 如果ruff自动修复了问题，会返回非零退出码，提醒你重新git add修复的文件
- **check-toml**: 自动检查pyproject.toml、pixi.toml等TOML文件的格式正确性
- **mypy插件**: 集成pydantic.mypy插件，提供更好的Pydantic模型类型检查

#### 🚫 **绝对禁止绕过 Pre-commit 检测** ⚠️ **极其严格**
**任何情况下都不得绕过、禁用或跳过 pre-commit 检查！这是项目代码质量的最后防线。**

**禁止的绕过方式**：
```bash
# ❌ 绝对禁止使用这些命令！
git commit --no-verify          # 跳过 pre-commit hooks
git commit -n                   # --no-verify 的简写，同样禁止
git config core.hooksPath /dev/null  # 禁用所有 hooks
SKIP=ruff git commit            # 跳过特定检查（通过环境变量）
pre-commit uninstall            # 卸载 pre-commit
pre-commit run --all-files --no-color  # 修改 pre-commit 行为
```

**违反的后果**：
1. **代码将被立即回滚**：任何通过绕过检查提交的代码都会被立即回滚
2. **提交权限撤销**：违反者将被撤销项目的提交权限
3. **记录在案**：违规行为将被记录并影响项目参与权限

**为什么必须遵守**：
- **质量保证**：Pre-commit 是防止低质量代码进入代码库的唯一有效机制
- **团队协作**：绕过检查会影响整个团队的开发效率
- **技术债务**：未经检查的代码会产生大量技术债务
- **CI 一致性**：Pre-commit 检查与 CI 检查保持一致，绕过毫无意义

#### 🚫 **绝对禁止未经授权修改 CI/CD 配置** ⚠️ **极其严格**
**任何对 pre-commit、CI/CD 配置的修改都必须获得用户明确授权！**

**严重违规记录**：
- 日期：2025-12-10
- 违规行为：未经用户允许，擅自修改 .pre-commit-config.yaml，禁用了 mypy 和 pytest 检查
- 影响：绕过了项目的代码质量检查机制
- 处理：已恢复配置，违规行为已记录

**禁止的行为**：
- 修改 .pre-commit-config.yaml
- 修改 GitHub Actions 工作流文件
- 修改任何自动化检查配置
- 修改 pyproject.toml 中的检查配置（除非是修复明确的技术问题）

**正确做法**：
```bash
# ✅ 遇到检查失败时的正确处理流程
# 1. 分析错误原因
# 2. 修复代码问题
# 3. 如果是配置问题，请示用户是否允许修改
# 4. 获得明确授权后再进行配置修改
```

**正确的做法**：
```bash
# ✅ 遇到检查失败时的正确处理流程
# 1. 运行检查并自动修复
pixi run ruff check . --fix
pixi run ruff format .

# 2. 重新添加修复后的文件
git add .

# 3. 再次尝试提交（让 pre-commit 正常运行）
git commit -m "fix: 修复代码质量问题"

# 4. 如果仍有问题，逐一修复直至所有检查通过
```

#### 🚫 **任务完成后的强制检查规则** ⚠️ **极其严格**
**每次完成所有任务后，必须运行全量 precommit 检查并通过！**

**强制要求**：
1. **必须运行全量检查**：`pre-commit run --all-files`
2. **必须确保所有检查通过**：包括 ruff、mypy、pytest
3. **禁止提交代码**：除非用户主动告知提交，否则只报告检查结果
4. **检查失败时必须修复**：不能带着未解决的问题结束任务

**执行流程**：
```bash
# 任务完成后必须执行的命令
pre-commit run --all-files

# 如果有失败，必须修复后再次运行，直至全部通过
```

**特别注意**：
- 这是任务完成的必要条件，不是可选步骤
- 即使代码看起来没问题，也必须运行检查验证
- 检查通过后，只需要向用户报告"所有检查已通过"
- 只有用户明确要求时才能提交代码

**为什么必须遵守**：
- **质量保证**：确保代码符合项目的所有质量标准
- **避免技术债务**：防止小问题累积成大问题
- **团队协作**：保证代码对其他开发者友好
- **专业素养**：体现对代码质量的负责态度

#### 编码阶段最佳实践：
1. **IDE集成配置**
   - 安装 ruff 扩展（VSCode: `charliermarsh.ruff`）
   - 启用"保存时格式化"功能
   - 启用实时 linting 检查
   - 配置 ruff 为默认格式化工具

2. **编码时的实时检查**
   - ✅ **写代码时立即查看lint警告**
   - ✅ **每个函数写完就添加类型注解**
   - ✅ **导入时确保按顺序排列**
   - ❌ **不要累积问题到最后一起修复**

3. **提交前的快速验证**
   ```bash
   # 快速自检（应该全部通过）
   pixi run ruff check .       # 必须返回 "All checks passed!"
   pixi run ruff format .      # 必须没有任何文件需要格式化
   pixi run mypy packages/ apps/ scripts/ tests/  # 必须通过类型检查
   ```

4. **错误处理流程**
   ```bash
   # 如果有lint错误：
   pixi run ruff check . --fix  # 自动修复能修复的问题
   # 手动修复剩余问题（通常是需要添加类型注解或重构）

   # 如果格式化问题：
   pixi run ruff format .      # 自动格式化

   # 如果有类型检查错误：
   pixi run mypy packages/ apps/ scripts/ tests/  # 查看具体类型错误
   # 修复类型注解或类型使用问题
   ```


### Data Feature
```bash
# Install data dependencies
pixi install --feature data

# Download/update market data
python -m ditto.data.update      # Update daily market data
```

## High-Level Architecture

Ditto is a quantitative investment system designed for volatile market conditions, with a focus on ETF sector rotation strategies. The system follows a layered architecture:

### System Layers
1. **Web UI Layer** (Next.js) - User interface for strategy research, backtesting, and monitoring
2. **API Layer** (FastAPI) - HTTP endpoints that orchestrate application services
3. **Application Services** - Use case-oriented services (RegimeSvc, RotationSvc, BacktestSvc, RiskSvc, etc.)
4. **Core Domain** - Business logic engines (RegimeEngine, FactorEngine, RotationEngine, BacktestEngine, RiskEngine)
5. **Infrastructure** - Data access, external integrations, scheduling

### Key Domain Concepts

**Portfolio Management:**
- `PortfolioManager` coordinates multiple strategies
- `Strategy` is the core abstraction all strategies must implement
- `Signal` and `SignalSet` represent trading intentions with confidence scores
- `RiskBudget` enforces position limits and volatility targets

**Data Architecture:**
- **Point-in-Time (PIT) Safety**: All factor data includes `knowledge_date` to prevent lookahead bias
- **Adjustment Separation**: Store only non-adjusted prices + adjustment factors, compute adjusted prices dynamically
- **Dual Storage**: DuckDB for analytics & factor data, SQLite for transactional data
- **Dual Source Validation**: Cross-validate Tushare and AkShare data

**Trading Execution:**
- `BrokerAdapter` interface abstracts broker-specific implementations
- `ExecutionManager` handles order routing and cost estimation
- Supports both paper trading (Phase 0-1) and live trading (Phase 2+)

### Module Structure

```
apps/
  server/           # FastAPI application and API endpoints
    src/
      api/          # HTTP routers
      services/     # Application services (use case orchestration)
      models/       # Pydantic models for API
      scheduler/    # APScheduler job definitions
      main.py       # FastAPI app entry point

  web/              # Next.js frontend (Phase 1+)
    src/
      app/          # Next.js page routes
      components/   # React components
      stores/       # Zustand state management
      types/        # TypeScript types shared with backend

packages/
  core/
    src/
      data/         # DataService, database adapters
      engine/       # Core business logic engines
      strategy/     # Strategy abstractions and implementations
      portfolio/    # Portfolio management and multi-strategy coordination
      config/       # Configuration models
      util/         # Common utilities

  shared/
    src/
      types/          # Shared type definitions
      contracts/      # Data contracts and validation rules
```

### Core Engines

1. **RegimeEngine**: Market state identification (bull/osc/bear) with adaptive thresholds
2. **FactorEngine**: Factor calculation (RS, Value, Vol, Crowding) with health monitoring
3. **RotationEngine**: Multi-factor scoring and TopN selection for sector rotation
4. **BacktestEngine**: Dual implementation (Fast vectorized + Production event-driven) with limit-up/down filtering
5. **RiskEngine**: Drawdown-driven three-tier risk controls with velocity detection

### Data Quality Principles

- **Never silently use suspicious data** - Mark or flag inconsistencies
- **Always validate across sources** - Cross-check Tushare vs AkShare
- **Respect knowledge dates** - Only use data available at trade time
- **Version control important datasets** - Ensure backtest reproducibility

### Testing & Quality Gates

The system enforces strict quality requirements:

1. **Unit Tests**: Cover all core modules with normal, boundary, and error cases
2. **Integration Tests**: Golden datasets for regression testing
3. **Alignment Tests**: Fast vs Production backtester must match within 0.1% return difference
4. **Risk Rule Tests**: Validate KillSwitch triggers under various market scenarios

**Quality Gates**:
- Code merges require all unit tests and critical integration tests to pass
- Strategy promotion to live trading requires comprehensive validation including walk-forward analysis
- Fast/Production alignment must be maintained for all backtest logic changes

### Development Workflow

1. **Research Phase**: Use research playground for initial strategy exploration
2. **Implementation**: Implement strategy extending the base `Strategy` class
3. **Validation**: Run comprehensive backtest validation with alignment tests
4. **Paper Trading**: Deploy to paper trading environment for real-time validation
5. **Live Trading**: Gradual rollout with risk budget constraints

### Configuration

- Configuration uses Pydantic Settings for type-safe configuration
- Environment-specific settings in `.env` files
- Database paths, API keys, and risk parameters configurable
- Strategy parameters configurable without code changes

### External Dependencies

- **Data Sources**: Tushare Pro (primary), AkShare (validation)
- **Brokers**: MiniQMT adapter (Phase 2+), interface designed for extensibility
- **Notifications**: Telegram/DingTalk for heartbeat and risk alerts
- **Execution**: Local file-based storage with OS permissions for security

## Key Constraints

- Single-machine Windows environment (Phase 0-1)
- Daily data focus (no intraday requirements)
- ETF sector rotation focus, but architecture supports multi-asset expansion
- Strict risk management with KillSwitch capabilities
- No cloud dependencies for core functionality

## Claude Code 交互规范 ⚠️ **必须遵守**

### 语言和记录要求
1. **中文回复**：
   - Claude 必须使用中文回复用户的所有问题
   - 代码注释和文档可以使用英文，但解释和说明必须用中文
   - 错误信息和调试输出保留原文，但需要中文解释

2. **信息记录**：
   - 每次会话中的重要决策和变更都需要记录
   - 使用 TodoWrite 工具跟踪任务进度
   - 完成的功能必须在 phase0_tasks.md 中更新状态

3. **沟通风格**：
   - 清晰、简洁、专业
   - 主动报告进度和遇到的问题
   - 提供具体的文件路径和行号引用

## Claude Code 开发工作流规范 ⚠️ **必须遵守**

### 任务跟踪管理
1. **使用官方任务文档**：
   - Phase 0 和 Phase 0.5 的所有任务记录在 `phase0_tasks.md`
   - 每个任务有唯一ID、描述、工时估算、状态和完成日期
   - 开发过程中必须实时更新任务状态

2. **状态标记规则**：
   - ✅ 已完成：功能已实现并通过验证
   - ⚠️ 部分完成：功能已实现但需要补充或优化
   - ❌ 未开始：尚未开始的任务
   - 🔄 进行中：正在开发的任务

3. **文档更新要求**：
   - 完成任何功能后，立即在 `phase0_tasks.md` 中标记完成
   - 更新完成日期和备注
   - 阻塞其他任务时，必须在备注中说明

### 临时文档管理
1. **禁止保留的文档类型**：
   - 代码质量检查报告（如 formatting_summary.md）
   - 进度跟踪文档（如 progress_*.md）
   - 临时任务记录（如 task*.md）
   - 任何由工具自动生成的报告文档

2. **必须删除的时机**：
   - 功能开发完成后立即删除相关临时文档
   - 每个会话结束前清理所有临时文件
   - 发现临时文档立即删除，不要积累

3. **保留的官方文档**：
   - `phase0_tasks.md` - 官方任务跟踪（永久保留）
   - `CLAUDE.md` - 项目指导文档（永久保留）
   - `README.md` - 项目说明（永久保留）
   - `docs/design/` 目录下的设计文档（永久保留）

### Docs 文件夹管理规范 ⚠️ **严格禁止**
1. **绝对禁止修改 docs/design/ 文件夹下的任何原有文档**
   - 所有设计文档都是项目核心资产
   - 需要修改必须获得用户明确授权
   - 包括但不限于：系统设计、路线图、数据设计、引擎设计等

2. **文档内容保护**：
   - 不得删除 docs/design/ 下的任何文件
   - 不得重命名 docs/design/ 下的任何文件
   - 不得修改 docs/design/ 下的文件内容
   - 可以读取但仅作参考，不能用于生成新内容

### Scripts 文件夹管理
1. **保留的官方脚本**：
   - `start_all.ps1` - 系统启动脚本
   - `backup.ps1` - 数据备份脚本
   - `health_check.ps1` - 健康检查脚本
   - `cleanup_logs.ps1` - 日志清理脚本
   - `init_db.py` - 数据库初始化脚本
   - `check_data_quality.py` - 数据质量检查脚本
   - `init_data_sources.py` - 数据源初始化脚本
   - `update_data.py` - 数据更新脚本

### 开发流程要求
1. **任务执行顺序**：
   - 优先处理阻塞其他任务的项
   - 修复导入错误等基础问题
   - 按照里程碑依赖关系推进

2. **TDD 开发规范 ⚠️ **必须遵守**：
   - **先写测试**：实现任何功能前，先编写测试用例
   - **测试驱动**：测试应该描述功能的期望行为
   - **小步快跑**：完成一个功能（通过测试）就立即提交
   - **重构安全**：有测试保护的前提下进行代码优化
   - **测试覆盖**：每个模块必须有对应的测试文件

   **TDD 流程**：
   ```bash
   # 1. 编写测试（先让测试失败）
   # 2. 实现最小功能（让测试通过）
   # 3. 重构优化（保持测试通过）
   # 4. 提交代码
   git commit -m "P0-005: 实现DuckDB初始化 - TDD"
   ```

3. **Superpower Skills 使用规范**：
   - **合理利用**：根据任务类型选择合适的 skill
   - **测试驱动开发**：使用 `superpowers:test-driven-development` 进行 TDD
   - **复杂任务分解**：使用 `superpowers:writing-plans` 制定实现计划
   - **代码审查**：完成功能后使用 `superpowers:requesting-code-review`
   - **系统性调试**：遇到 bug 使用 `superpowers:systematic-debugging`
   - **执行计划**：使用 `superpowers:executing-plans` 批量实现任务

   **推荐 Skills 使用场景**：
   - `superpowers:systematic-debugging`:问题排查，找根因
   - `superpowers:test-driven-development`：新功能开发
   - `superpowers:brainstorming`：设计阶段和复杂问题解决
   - `superpowers:verification-before-completion`：任务完成前验证
   - `superpowers:subagent-driven-development`：独立任务并行开发

4. **Conventional Commits 提交规范 ⚠️ **必须遵守**：

   **基本格式**：
   ```
   <type>[optional scope]: <description>

   [optional body]

   [optional footer(s)]
   ```

   **提交类型（Type）**：
   - `feat`: 新功能（对应 SemVer MINOR）
   - `fix`: 修复 bug（对应 SemVer PATCH）
   - `docs`: 文档变更
   - `style`: 代码格式化（不影响功能）
   - `refactor`: 重构（既不是新功能也不是修复）
   - `perf`: 性能优化
   - `test`: 添加或修改测试
   - `chore`: 构建过程或辅助工具的变动
   - `ci`: CI/CD 配置变更
   - `build`: 构建系统或依赖变更

   **破坏性变更**：
   - 在 type 后加 `!`：`feat!: breaking change`
   - 或在 footer 中添加：`BREAKING CHANGE: description`

   **Ditto 项目规范**：
   - **必须包含任务ID**：在 description 前加上任务ID
   - **TDD 标记**：使用 TDD 开发的功能添加 `- TDD` 后缀
   - **范围（Scope）**：使用模块名作为 scope（如 data, api, engine）

   **正确示例**：
   ```bash
   feat(data)!: P0-005 implement DuckDB initialization - TDD

   fix: P0-022 resolve import error in main.py

   test(engine): P0-041 add unit tests for RegimeEngine - TDD

   docs: update CLAUDE.md with development workflow

   refactor(data): P0-036 simplify DataService interface

   BREAKING CHANGE: DataService constructor now requires config parameter
   ```

   **错误示例**：
   ```bash
   # 缺少任务ID
   feat: implement DuckDB

   # 类型错误
   bugfix: P0-022 fix import error

   # 破坏变更未标记
   feat: P0-005 change DataService API
   ```

5. **会话结束检查清单**：
   - [ ] 更新 `phase0_tasks.md` 中的任务状态
   - [ ] 删除所有临时生成的文档
   - [ ] 提交已完成的功能（使用原子提交）
   - [ ] 更新 README.md 中的任务进度
   - [ ] 确保所有新功能都有对应的测试

## Python 单元测试规范 v1.0

### 总体目标
1. 建立一套统一、可执行的Python单元测试标准
2. 保证金融计算、数据时序、风控规则的正确性
3. 采用AAA模式（Arrange-Act-Assert），拥抱pytest函数式测试风格

### 测试技术栈
```bash
# 必选工具
pip install pytest pytest-cov pytest-mock

# 推荐工具（按需）
pip install pytest-benchmark faker hypothesis
```

### 目录结构
```
project_root/
├── src/
│   └── ditto/
│       ├── strategies/
│       ├── risk/
│       └── core/
└── tests/
    ├── conftest.py           # 全局共享fixtures
    ├── unit/                 # 单元测试（mock外部依赖）
    ├── integration/          # 集成测试（子系统+真DB/IO）
    ├── e2e/                  # 端到端测试
    └── fixtures/             # 测试数据文件
```

### 测试命名规范
- 文件命名：`test_<module_name>.py`
- 函数命名：`test_<被测对象>_<场景>_<预期结果>`
- 示例：
  ```python
  def test_calculate_sharpe_ratio_with_positive_returns_returns_correct_value():
      ...
  def test_kill_switch_when_drawdown_exceeds_threshold_triggers_halt():
      ...
  ```

### AAA模式（必须遵守）
```python
def test_portfolio_daily_returns():
    # Arrange - 准备输入数据
    prices = pl.DataFrame({
        "date": ["2024-01-01", "2024-01-02"],
        "close": [100.0, 105.0],
    })

    # Act - 执行被测试函数
    returns = calculate_returns(prices)

    # Assert - 验证结果
    assert returns["return"].to_list() == [0.0, 0.05]
```

### 测试隔离原则
- 每个测试必须独立，不共享可变状态
- 使用fixture而非类属性共享数据
- 所有外部依赖（网络、DB、时间）必须mock

### 浮点数比较规范
```python
# 金融金额比较（精确到分）
assert actual == pytest.approx(expected, rel=1e-5, abs=1e-2)

# 数组比较
assert np.isclose(actual, expected, rtol=1e-5, atol=1e-2)
```

### PIT数据验证
```python
def test_pit_data_integrity():
    as_of = pl.datetime(2024, 1, 1)
    data = load_pit_data(as_of)
    assert data["date"].max() <= as_of
```

### 覆盖率要求
- 整体覆盖率不低于80%
- 关键模块（风控、仓位）建议90%+
- CI配置覆盖率门槛：`--cov-fail-under=80`

### pytest配置示例
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = [
    "--cov=src/ditto",
    "--cov-report=html",
    "--cov-report=term-missing",
    "--strict-markers",
    "-v"
]
markers = [
    "slow: marks tests as slow",
    "integration: marks tests as integration tests",
    "benchmark: marks performance benchmark tests",
]
```

### 测试最佳实践
1. **使用pytest-mock**：统一使用`mocker` fixture
2. **Patch原则**：在"使用的地方"patch，而非定义的地方
3. **参数化测试**：使用`@pytest.mark.parametrize`覆盖多种场景
4. **时间/随机数**：固定seed，使用freezegun固定时间
