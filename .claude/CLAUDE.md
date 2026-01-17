## 北极星原则
> 以**卓越代码质量**为底线、以**艺术般的可读性与一致风格**为追求，持续产出**清晰、整洁、可演进的架构**与**可长期维护的工程实现**。

**不可妥协：**
- **质量**：正确性、可测试、可维护
- **风格**：一致、克制、易读
- **架构**：清晰边界、低耦合、高内聚、可演进

**遇事不决调研业界最佳实践！！！**

## ⚠️ 核心约束

- **语言**: 中文（回复/文档/Commit/PR）
- **分支**: 从 main 拉取开发分支，PR 合并
- **TDD**: RED → GREEN → REFACTOR
- **依赖**: **严格禁止**使用非以下功能分类中的其他功能库
    - **存储**: parquet / duckdb / sqlite
    - **数据处理**: polars（禁止 pandas）
    - **API**: fastapi
    - **任务处理**: prefect
    - **日志监控**: loguru / opentelemetry
    - **限流、重试**: tenacity / limits
    - **本地缓存**: cachebox
    - **Json序列化**: orjson（禁止 json）
    - **ASGI**: granian
    - **网络请求**: httpx
- **包管理**: 只用 pixi（禁止 pip/poetry/conda）
- **文档**: 文档驱动开发，及时更新 README/Sprint/Plan/ADR
- **开发**:
    - **Python核心规范**：详见 [core.md](.claude/rules/core.md)
    - **noqa/type:ignore 规范**：详见 [noqa-ignore.md](.claude/rules/noqa-ignore.md)
- **测试**: 遵循测试依赖，分支覆盖率 >= 80% （详见 [python-test.md](.claude/rules/python-test.md)）
- **质量**：必须通过 pyright、ruff检测
- **重构**: 数据存储、API协议格式的兼容考量外，无需考虑向后兼容性，所有包均项目内使用，重构完成必须移除废弃代码和配置

## 工具使用规范

### 文件读写（必须使用内置工具）

| 操作 | ✅ 正确 | ❌ 错误 |
|------|---------|---------|
| 读文件 | `Read` 工具 | `cat` |
| 写文件 | `Write` 工具 | `cat >` / `echo >` |
| 编辑文件 | `Edit` 工具 | `sed` |
| 创建目录 | `mkdir` | - |

### 代码智能分析（LSP 优先）- 类、方法引用查找(**重构必须使用**)

| 操作 | LSP 工具 | 降级方案 |
|------|----------|----------|
| 查找定义 | `goToDefinition` | `Grep "class Foo"` → `Glob "**/*foo*.py"` |
| 查找引用 | `findReferences` | `Grep "def bar\|bar\("` |
| 理解结构 | `documentSymbol` | `Read` 工具 |
| 类型信息 | `hover` | - |
| 错误检查 | `getDiagnostics` | - |

## 绝对禁止

- `import pandas`
- `rolling_mean(20)` 不指定 `closed="left"` （详见 [pit.md](.claude/rules/pit.md)）
- 跳过风控检查
- 直接提交 main
- 文件读写改操作使用 Bash 命令
- SRC源码内大量使用#naqa、#type:ignore, 新增代码优先重构避免
- 绕过或忽略 pyright、ruff、precommit 检测（例如修改相关配置，使用--no verify提交）
- 循环依赖，以及使用`TYPE_CHECKING`的延迟导入方式解决循环依赖（必须重构代码及架构解决），非必要`禁止延迟导入`

## 项目架构

```
ditto/
├── packages/           # 核心包
│   ├── foundation/    # 基础设施
│   ├── datahub/       # 数据访问层
│   └── core/          # 核心引擎
├── apps/              # 应用
│   ├── port/        # Server 应用
│   └── web/           # Web 应用
├── config/            # 环境配置（按环境分组）
│   ├── development/   # 开发环境配置
│   ├── testing/       # 测试环境配置
│   └── production/    # 生产环境配置
└── docs/              # 文档

依赖方向: core → datahub → foundation
          apps/port → datahub → foundation
```

### 环境配置规范

Ditto 采用**双层环境架构**（详见 [04_deployment_topology.md](../docs/design/04_deployment_topology.md#12-环境架构)）：

| 层级 | 变量 | 有效值 | 说明 |
|------|------|--------|------|
| Pixi 环境 | 选择环境 | `default`, `dev` | 依赖管理层：default 生产依赖、dev 开发工具 |
| 运行时环境 | `DITTO_ENV` | `development`, `testing`, `production` | 行为控制层 |

**环境命名规范**：

| 类型 | 规范 | 示例 |
|------|------|------|
| Pixi 环境 | 小写，无连字符 | `default`, `dev` |
| 运行时环境 | 小写，全称 | `development`, `testing`, `production` |
| 环境变量前缀 | 大写，下划线 | `OBSERVABILITY_`, `DB_`, `API_` |

**配置文件结构**：

```
config/
├── development/
│   ├── observability.env  # OBSERVABILITY_* 前缀
│   ├── database.env       # DB_* 前缀
│   ├── api.env            # API_* 前缀
│   └── data_source.env    # 无前缀
├── testing/
│   └── ...
└── production/
    └── ...
```

**使用场景**：

| 场景 | Pixi 环境 | DITTO_ENV | 命令 |
|------|-----------|-----------|------|
| 本地开发 | `dev` | `development` | `pixi run -e dev pytest` |
| 测试执行 | `dev` | `testing` | `pixi run -e dev pytest` (自动设置) |
| 生产部署 | `default` | `production` | `pixi run server` |

**重要原则**：
- 环境值必须使用 `Environment` 枚举，禁止硬编码字符串
- 可观测性使用 OTEL 风格的**独立功能开关**，而非单一"模式"枚举
- 配置文件按 `config/{environment}/` 结构组织
- 不同 Settings 类使用不同的环境变量前缀实现隔离

| 层级 | 职责 | 详细规范 |
|------|------|----------|
| Foundation | 基础能力 | [foundation.md](.claude/rules/foundation.md) |
| DataHub | 数据访问 | [datahub.md](.claude/rules/datahub.md), [pit.md](.claude/rules/pit.md) |
| Core | 核心引擎 | [core.md](.claude/rules/core.md) |
| Server | 应用服务 | [server.md](.claude/rules/server.md) |

## 开发工作流

| 任务类型 | 工作流 |
|----------|--------|
| 新功能 | plan → TDD → 文档 |
| 修改 DQ | 编辑 YAML → pytest → 更新 design doc |
| 数据摄入 | 查游标 → 查日志 → 修复 → 重试 |
| API 路由 | Pydantic Model → @app.get → 测试 |

## 常用命令

```bash
# 快速验证（开发时）
pixi run -e dev check          # lint + fmt + type + test --fast

# 提交前检查
pixi run -e dev pre-commit-run # pre-commit hooks
pixi run -e dev ci             # CI 完整检查

# 测试
pixi run -e dev test              # 默认：单元测试（并行）
pixi run -e dev test --unit       # 只运行单元测试（并行）
pixi run -e dev test --integration # 只运行集成测试（串行）
pixi run -e dev test --fast       # 快速测试（跳过慢速）
pixi run -e dev test --snapshot   # 支持 inline-snapshot（串行）
pixi run -e dev test-pit          # PIT 测试

# 类型检查
pixi run -e dev type          # 源码类型检查（strict）
pixi run -e dev type --tests  # 测试类型检查（basic）
pixi run -e dev type --all    # 完整类型检查

# 代码质量
pixi run -e dev lint          # 代码检查
pixi run -e dev lint --fix    # 自动修复
pixi run -e dev fmt           # 格式化
pixi run -e dev fmt --check   # 只检查不修改
```

## ⚠️ SKILLS 执行规则

**在执行任何任务前，必须先检查并调用相关的 skills**

### 执行流程

```
用户请求 → 检查是否涉及任何 skill → 如果有，立即调用 Skill 工具 → 再开始工作
```

### 流程控制类（最高优先级）

| Skill | 使用时机 | 强制级别 |
|-------|---------|---------|
| `superpowers:brainstorming` | 任何创意工作、创建功能、构建组件 | ⭐⭐⭐ 必须 |
| `superpowers:systematic-debugging` | 遇到任何 bug、测试失败、异常行为 | ⭐⭐⭐ 必须 |
| `superpowers:test-driven-development` | 实现任何功能或 bugfix | ⭐⭐⭐ 必须 TDD |
| `superpowers:verification-before-completion` | 准备声明工作完成、提交/PR 前 | ⭐⭐⭐ 必须 |

### 任务管理类

| Skill | 使用时机 | 强制级别 |
|-------|---------|---------|
| `superpowers:writing-plans` | 有规范或需求的多步骤任务 | ⭐⭐⭐ 必须 |
| `superpowers:executing-plans` | 有书面实施计划在单独会话执行 | ⭐⭐⭐ 必须 |
| `superpowers:subagent-driven-development` | 执行有独立任务的当前会话计划 | ⭐⭐⭐ 必须 |
| `superpowers:dispatching-parallel-agents` | 面对 2+ 个无共享状态/顺序依赖的独立任务 | ⭐ 谨慎选择 |

### 代码审查类

| Skill | 使用时机 | 强制级别 |
|-------|---------|---------|
| `superpowers:requesting-code-review` | 完成任务、实现主要功能、合并前 | ⭐⭐⭐ 必须 |
| `superpowers:receiving-code-review` | 收到代码审查反馈，实现建议前 | ⭐⭐⭐ 必须 |

### Python 专项类

| Skill | 使用时机 | 强制级别 |
|-------|---------|---------|
| `python-development:python-pro` | Python 3.12+ 现代/async/性能优化 | ⭐⭐⭐ 必须 |
| `python-development:python-testing-patterns` | 写 Python 测试，设置测试套件 | ⭐⭐⭐ 必须 |
| `python-development:python-performance-optimization` | 调试慢代码，优化瓶颈 | ⭐⭐ 主动使用 |
| `python-development:async-python-patterns` | 构建 async API，并发系统 | ⭐⭐ 主动使用 |
| `python-development:fastapi-pro` | FastAPI 开发，async APIs | ⭐⭐ 主动使用 |

### 并行执行前检查清单

启动并行 agents 前，**必须确认**：
- [ ] 修改的文件之间无 import 依赖
- [ ] 不涉及共享状态（数据库 schema、全局配置）
- [ ] 不需要协调的测试运行
- [ ] 修改可以独立 rollback（独立 commit）

**高风险场景**（禁止并行）:
- ❌ 修改函数签名 + 更新调用方
- ❌ 重构 import + 修改被导入文件
- ❌ 更新 schema + 迁移数据

### 调用优先级

1. **Process skills first** (brainstorming, debugging) - 确定如何处理任务
2. **Implementation skills second** - 引导执行

### 无例外清单

| 场景 | 必须 | 禁止 |
|------|------|------|
| "简单查询" | 检查相关 skill | 直接搜索文件 |
| "快速修复" | 调用 TDD | 直接改代码 |
| "查查这个" | 使用 Explore agent | 直接读文件 |
| "小改动" | 写 plan | 直接实现 |

**判断标准**: **只要涉及代码，100% 检查 skill**

## 上下文管理指南

### 长对话中的上下文保持

GLM-4.7 上下文窗口有限，需主动保持上下文：

**关键检查点**（每次任务开始/结束时）:
1. 确认当前分支: `git branch --show-current`
2. 确认项目约束（重新读取本文件的"核心约束"）
3. 确认最近的决策（查看 git log -5）

**决策记录**: 重大决策应在代码注释中说明"为什么"
```python
# 使用 OnDuplicate.KEEP_FIRST 而非 ERROR
# 原因: 数据源可能有重复，我们信任首次入库的数据
def write_data(df, on_duplicate=OnDuplicate.KEEP_FIRST):
    ...
```

### 文件依赖追踪

修改文件时，必须检查：
- [ ] 导入此文件的其他文件（使用 `findReferences`）
- [ ] 此文件导入的依赖文件
- [ ] 相关的测试文件
- [ ] 相关的文档文件
