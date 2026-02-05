# AGENTS.md

## Project Overview

Ditto 是一个量化交易系统，采用严格的代码质量和架构标准。

**北极星原则**：以卓越代码质量为底线、以艺术般的可读性与一致风格为追求，持续产出清晰、整洁、可演进的架构与可长期维护的工程实现。

**不可妥协**：质量（正确性、可测试、可维护）| 风格（一致、克制、易读）| 架构（清晰边界、低耦合、高内聚、可演进）

---

## Setup Commands

```bash
# 安装依赖
pixi install

# 开发环境（自动设置 DITTO_ENV=development）
pixi run -e dev pytest

# 完整检查（format + lint + type + test）
pixi run -e dev ci

# 快速验证（开发时）
pixi run -e dev check

# 提交前检查
pixi run -e dev pre-commit-run
```

**注意**：代码格式（ruff format）和风格（ruff lint）通过 pre-commit hooks 和 CI 自动 enforce，Agent 生成的代码会自动被修正。

---

## Tech Stack & Constraints

### 包管理
**只用 pixi**（禁止 pip/poetry/conda）

### 依赖限制（无法自动检测，需严格遵守）

| 类别 | ✅ 允许 | 🚫 禁止 |
|------|---------|---------|
| **存储** | parquet, duckdb, sqlite | - |
| **数据处理** | **polars** | pandas |
| **API** | fastapi | - |
| **任务处理** | prefect | - |
| **日志监控** | loguru, opentelemetry | - |
| **限流重试** | tenacity, limits | - |
| **本地缓存** | cachebox | - |
| **Json序列化** | **orjson** | json |
| **ASGI** | granian | - |
| **网络请求** | httpx | - |

**原因**：技术栈一致性直接影响可维护性，混用会导致依赖膨胀、行为不一致、性能问题。

---

## Architecture

### 项目结构

```
ditto/
├── packages/           # 核心包
│   ├── foundation/    # 基础设施（最底层）
│   ├── datahub/       # 数据访问层（依赖 foundation）
│   └── core/          # 核心引擎（依赖 datahub）
├── apps/              # 应用
│   ├── port/          # Server 应用
│   └── web/           # Web 应用
└── config/            # 环境配置（按环境分组）
    ├── development/
    ├── testing/
    └── production/
```

### 依赖方向

```
core → datahub → foundation
apps/port → datahub → foundation
```

**规则**：
- 禁止循环依赖
- 禁止跨层导入（如 core 直接导入 foundation）
- 详细规范：[.claude/rules/architecture.md](.claude/rules/architecture.md)

---

## Testing

### 覆盖率要求
- **分支覆盖率**：≥80%（通过 pytest-cov enforce）
- **类型检查**：0 errors（通过 basedpyright enforce）

### 运行测试

```bash
# 默认：单元测试（并行）
pixi run -e dev test

# 只运行单元测试
pixi run -e dev test --unit

# 只运行集成测试（串行）
pixi run -e dev test --integration

# 快速测试（跳过慢速）
pixi run -e dev test --fast

# 支持 inline-snapshot（串行）
pixi run -e dev test --snapshot
```

### TDD 流程
**强制流程**：RED（写失败测试）→ GREEN（最小实现）→ REFACTOR（重构代码）

详细测试规范：[.claude/rules/python-test.md](.claude/rules/python-test.md)

---

## Workflow

### 强制流程

**每次代码修改前**：
1. 理解阶段：Read 实现文件 → Read 测试文件 → Grep 相关模式 → LSP refs（重构必须）
2. 实现阶段：RED → GREEN → REFACTOR
3. 验证阶段：verification-before-completion

**调试时**：遇到错误必须调用 systematic-debugging Skill，禁止盲目重试

**完成前**：必须调用 verification-before-completion Skill，运行 `pixi run -e dev ci` 确认通过

详细工作流：[.claude/rules/workflow.md](.claude/rules/workflow.md)

---

## Python Development Standards

### 代码规模限制（自动 enforce）

| 指标 | 限制 | enforce 方式 |
|------|------|-------------|
| 单文件行数 | ≤ 800 | `scripts/check_code_size.py` |
| 函数长度 | ≤50 行 | ruff (max-statements) |
| 参数个数 | ≤7 个 | ruff (max-args) |
| 复杂度 | ≤10 (C90) | ruff (max-complexity) |
| 行长度 | ≤88 | ruff |

### LSP 辅助工具（强制：重构时必须使用）

> GLM-4.7 无原生 LSP 能力，必须使用项目提供的 LSP 辅助脚本

```bash
# 查找定义
pixi run -e dev python .claude/scripts/lsp_pyright.py goto <file> <line> <col>

# 查找引用（重构必须）
pixi run -e dev python .claude/scripts/lsp_pyright.py refs <file> <line> <col>

# 列出符号
pixi run -e dev python .claude/scripts/lsp_pyright.py symbols <file>

# 类型信息
pixi run -e dev python .claude/scripts/lsp_pyright.py hover <file> <line> <col>

# 类型诊断
pixi run -e dev python .claude/scripts/lsp_pyright.py diagnose [file]
```

**列号定位注意事项**：`<col>` 必须指向符号名称内部，不能指向行首

### noqa/type:ignore 规范
- 新增代码优先重构避免使用
- 详见：[.claude/rules/noqa-ignore.md](.claude/rules/noqa-ignore.md)

详细 Python 规范：[.claude/rules/core.md](.claude/rules/core.md)

---

## Boundaries

### ✅ Always do（无需询问）
- 使用 `Read` 工具读文件（禁止 cat）
- 使用 `Edit` 工具编辑（禁止 sed）
- 使用 `Write` 工具写文件（禁止 echo/cat >）
- 重构前使用 LSP 查找引用
- 遵循 TDD 流程（RED → GREEN → REFACTOR）
- Python 源码处理优先使用 LSP 而非 Grep/Glob

### ⚠️ Ask first（需要人工批准）
- 数据库 schema 变更
- 添加新依赖
- CI/CD 配置修改
- 修改架构边界
- 修改环境配置文件

### 🚫 Never do（硬性禁止）
- **使用 pandas**（必须用 polars）
- **使用 json**（必须用 orjson）
- **使用 pip/poetry/conda**（必须用 pixi）
- 使用 `TYPE_CHECKING` 延迟导入解决循环依赖（必须重构代码及架构）
- 跳过 basedpyright、ruff、pre-commit 检测（禁止修改相关配置、使用 --no-verify 提交）
- 直接提交到 main 分支
- 提交 secrets
- 使用 Bash 命令进行文件读写改操作
- `rolling_mean(20)` 不指定 `closed="left"`（详见 [pit.md](.claude/rules/pit.md)）

---

## Language & Encoding

- **回复语言**：中文（文档、Commit、PR）
- **文件编码**：UTF-8
- **Commit 消息**：中文，遵循约定式提交格式

---

## Documentation

**文档驱动开发**：及时更新 README/Sprint/Plan/ADR

详细文档规范：[.claude/rules/doc.md](.claude/rules/doc.md)

---

## Quick Reference

```bash
# 开发前
git status
git branch --show-current

# 修改前（强制）
Read <file>
Read <test_file>
Grep "<pattern>"
# LSP refs（重构）

# 调试
# 调用 systematic-debugging Skill

# 完成前
# 调用 verification-before-completion Skill
pixi run -e dev ci
```

---

## Complete Specification Reference

| 规范 | 路径 |
|------|------|
| 主配置 | [.claude/CLAUDE.md](.claude/CLAUDE.md) |
| Python 核心规范 | [.claude/rules/core.md](.claude/rules/core.md) |
| 测试规范 | [.claude/rules/python-test.md](.claude/rules/python-test.md) |
| 架构规范 | [.claude/rules/architecture.md](.claude/rules/architecture.md) |
| 工作流 | [.claude/rules/workflow.md](.claude/rules/workflow.md) |
| Foundation 层规范 | [.claude/rules/foundation.md](.claude/rules/foundation.md) |
| DataHub 层规范 | [.claude/rules/datahub.md](.claude/rules/datahub.md) |
| Core 层规范 | [.claude/rules/core.md](.claude/rules/core.md) |
| Server 层规范 | [.claude/rules/server.md](.claude/rules/server.md) |
| Pitfalls 避坑指南 | [.claude/rules/pit.md](.claude/rules/pit.md) |
| noqa/type:ignore 规范 | [.claude/rules/noqa-ignore.md](.claude/rules/noqa-ignore.md) |
