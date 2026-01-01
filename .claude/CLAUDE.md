
## ⚠️ 核心约束（必须!!重要!!）

- **语言**: 中文（回复/文档/Commit/PR）
- **分支**: 从 main 拉取开发分支，PR 合并
- **TDD**: RED → GREEN → REFACTOR
- **依赖**:
    - **存储**: parquet / duckdb / sqlite
    - **数据处理**: polars
    - **API**: fastapi
    - **任务处理**: prefect
    - **日志监控**: loguru / opentelemetry
    - **限流、重试**: tenacity / limits
    - **本地换成**：cachebox
    - **Json序列化**: orjson
    - **ASGI**: granian
    - **网络请求**: httpx
- **包管理**: 只用 pixi（禁止 pip/poetry/conda）
- **文档**: 文档驱动开发，保持LiveDocument，及时更新
- **测试**: 分支覆盖率>=80%
- **工具**:
    - **文件读写**：优先使用内置工具而非 Bash 命令
        - 读文件 → `Read` 工具，不要用 `cat`
        - 写文件 → `Write` 工具，不要用 `cat >` 或 `echo >`
        - 编辑文件 → `Edit` 工具，不要用 `sed`
        - 创建目录 → 可以用 `mkdir`
    - **代码智能分析**：项目已配置 LSP。在以下场景优先使用 LSP 工具而非 grep/ripgrep/glob，LSP 结果更精确，优先信任 LSP 的类型和诊断信息。
        - 查找函数/类定义 → `goToDefinition`
        - 查找引用位置 → `findReferences`
        - 理解类型信息 → `hover`
        - 了解文件结构 → `documentSymbol`
        - 编辑后检查错误 → `getDiagnostics`

## 绝对禁止

- `import pandas`
- `rolling_mean(20)` 不指定 `closed="left"`
- 跳过风控检查
- 直接提交 main
- 文件读写改操作使用Bash中的 `cat`、 `cat >` 、 `echo >`、`sed`

## 常用命令

```bash
pixi run -e dev quick-check     # 开发时快速检查
pixi run -e dev pre-commit-run  # 提交前检查
pixi run -e dev ci-check        # CI 完整检查
```

## 文档更新

| 触发 | 更新 |
|------|------|
| 新建/修改模块 | `**/**/README.md` |
| Sprint计划及任务状态变更 | `docs/sprints/sprint-XX.md` |
| 规划计划变更及规划详细任务项状态变更 | `docs/plans/YYYY-MM-DD-name.md` |
| 重大架构决策 | `docs/adr/NNNN-title.md` |

## 项目架构

### 包结构与依赖
```
ditto/
├── packages/           # 核心包
│   ├── foundation/    # 基础设施
│   │   └── config, observability, util
│   ├── datahub/       # 数据访问层
│   │   └── stores, repositories, dq, runtime
│   └── core/          # 核心引擎
│       └── engine, portfolio, strategy
├── apps/              # 应用
│   ├── server/        # Server 应用
│   │   └── api, ingestion, scheduler
│   └── web/           # Web 应用
└── docs/              # 文档
    ├── design/        # 架构设计
    ├── adr/           # 架构决策
    └── sprints/       # Sprint 规划

依赖方向: core → datahub → foundation
          apps/server → datahub → foundation
```

### 分层职责

| 层级 | 职责 | 示例 |
|------|------|------|
| Foundation | 基础能力 | 配置、日志、追踪 |
| DataHub | 数据访问 | Store/Repository/DQ |
| Core | 核心引擎 | 引擎、组合、策略 |
| Server | 应用服务 | FastAPI、Prefect 调度 |

## 开发工作流

| 任务类型 | 工作流 |
|----------|--------|
| 新功能 | plan → TDD → pre-commit-run → 文档 |
| 修改 DQ | 编辑 YAML → pytest → 更新 design doc |
| 数据摄入 | 查游标 → 查日志 → 修复 → 重试 |
| API 路由 | Pydantic Model → @app.get → 测试 |

### 常用命令
```bash
# 检查
pixi run -e dev quick-check     # 开发时
pixi run -e dev pre-commit-run  # 提交前

# 测试
pixi run -e dev pytest          # 全部
pixi run -e dev pytest -m unit   # PIT 测试
pixi run -e dev pytest -m pit   # PIT 测试
pixi run -e dev pytest -m integration  # 集成测试

```

## ⚠️ SKILLS执行规则（必须!!重要!!

**在执行任何任务前，必须先检查并调用相关的 skills。违反此规则被视为严重错误。**

### 执行流程

```
用户请求 → 检查是否涉及任何 skill → 如果有，立即调用 Skill 工具 → 再开始工作
```

### 当前已加载的 Skills 及使用时机

#### 🟢 Plugin Skills（通用能力）

**流程控制类（最高优先级）：**

| Skill | 使用时机 | 强制级别 |
|-------|---------|---------|
| `superpowers:brainstorming` | 任何创意工作、创建功能、构建组件、添加功能、修改行为 | ⭐⭐⭐ 必须 1%概率就调用 |
| `superpowers:systematic-debugging` | 遇到任何 bug、测试失败、异常行为 | ⭐⭐⭐ 必须，先调试后修复 |
| `superpowers:test-driven-development` | 实现任何功能或 bugfix，写实现代码前 | ⭐⭐⭐ 必须 TDD 流程 |
| `superpowers:verification-before-completion` | 准备声明工作完成、修复或通过，提交/PR前 | ⭐⭐⭐ 必须，证据先于断言 |

**任务管理类：**

| Skill | 使用时机 | 强制级别 |
|-------|---------|---------|
| `superpowers:writing-plans` | 有规范或需求的多步骤任务，在写代码前 | ⭐⭐⭐ 必须 |
| `superpowers:executing-plans` | 有书面实施计划在单独会话执行 | ⭐⭐ 推荐 |
| `superpowers:subagent-driven-development` | 执行有独立任务的当前会话中的实施计划 | ⭐⭐⭐ 必须  |
| `superpowers:dispatching-parallel-agents` | 面对 2+ 个无共享状态/顺序依赖的独立任务 | ⭐ 谨慎选择 |

**Git 工作流类：**

| Skill | 使用时机 | 强制级别 |
|-------|---------|---------|
| `superpowers:finishing-a-development-branch` | 实现完成，所有测试通过，决定如何集成工作 | ⭐⭐ 推荐 |

**代码审查类：**

| Skill | 使用时机 | 强制级别 |
|-------|---------|---------|
| `superpowers:requesting-code-review` | 完成任务、实现主要功能、合并前 | ⭐⭐⭐ 必须 |
| `superpowers:receiving-code-review` | 收到代码审查反馈，实现建议前 | ⭐⭐⭐ 必须 |

**Python 专项类：**

| Skill | 使用时机 | 强制级别 |
|-------|---------|---------|
| `python-development:python-pro` | Python 3.11+ 现代/async/性能优化 | ⭐⭐⭐ 必须 |
| `python-development:python-testing-patterns` | 写 Python 测试，设置测试套件 | ⭐⭐⭐ 必须 |
| `python-development:python-performance-optimization` | 调试慢代码，优化瓶颈 | ⭐⭐ 主动使用 |
| `python-development:async-python-patterns` | 构建 async API，并发系统，I/O 密集 | ⭐⭐ 主动使用 |
| `python-development:fastapi-pro` | FastAPI 开发，async APIs，WebSockets | ⭐⭐ 主动使用 |

**测试与调试专项类：**

| Skill | 使用时机 | 强制级别 |
|-------|---------|---------|
| `unit-testing:debugger` | 任何错误、测试失败、意外行为 | ⭐⭐⭐ 必须，主动使用 |
| `unit-testing:test-automator` | 测试自动化，质量工程，CI 集成 | ⭐⭐ 主动使用 |

### 危险信号（不要陷入这些想法）

| 你的想法 | 现实 | 行动 |
|---------|------|------|
| "这只是一个简单问题" | 问题就是任务 | 检查 skills |
| "我需要更多上下文" | Skill 告诉你如何收集 | 先调用 skill |
| "我先探索代码库" | Skills 告诉你如何探索 | 先调用 skill |
| "我可以快速检查文件" | 文件缺少对话上下文 | 先调用 skill |
| "让我先收集信息" | Skills 告诉你如何收集 | 先调用 skill |
| "这个不需要 formal skill" | 如果 skill 存在，就使用它 | 立即调用 |
| "我记得这个 skill" | Skills 会演进 | 重新读取 |
| "这不算是任务" | 行动 = 任务 | 检查 skills |

### 调用优先级

当多个 skills 可能适用时：

1. **Process skills first** (brainstorming, debugging) - 确定如何处理任务
2. **Implementation skills second** - 引导执行
