
## ⚠️ 核心约束（必须!!重要!!）

- **语言**: 中文（回复/文档/Commit/PR）
- **分支**: 从 main 拉取开发分支，PR 合并
- **TDD**: RED → GREEN → REFACTOR
- **依赖**:
    - **存储**: parquet / duckdb / sqlite
    - **数据处理**: polars（禁止 pandas）
    - **API**: fastapi
    - **任务处理**: prefect
    - **日志监控**: loguru / opentelemetry
    - **限流、重试**: tenacity / limits
    - **本地缓存**: cachebox
    - **Json序列化**: orjson
    - **ASGI**: granian
    - **网络请求**: httpx
- **包管理**: 只用 pixi（禁止 pip/poetry/conda）
- **文档**: 文档驱动开发，保持 LiveDocument，及时更新
    - 新建/修改模块 → 更新 `**/**/README.md`
    - Sprint 计划变更 → 更新 `docs/sprints/sprint-XX.md`
    - 规划计划变更 → 更新 `docs/plans/YYYY-MM-DD-name.md`
    - 重大架构决策 → 更新 `docs/adr/NNNN-title.md`
- **测试**: 分支覆盖率 >= 80%
    - **Marker 规范**: 必须为测试添加 @pytest.mark.* 装饰器
      - 单元测试: `@pytest.mark.unit`
      - 集成测试: `@pytest.mark.integration`
      - 可观测性: `@pytest.mark.observability`
      - 外部 API: `@pytest.mark.external`
    - **覆盖率阈值**: CI 和本地统一为 80%
      - CI: `.github/workflows/ci.yml` (`--cov-fail-under=80`)
      - 本地: `pixi.toml` test-cov-xml (`--cov-fail-under=80`)
    - 假测试检测：无 `assert True` 等无效断言（检查: `grep -r "assert True" tests/`）
    - 技术债务追踪：新增 `# HACK/# TODO` 必须创建 issue 追踪（存储至 `docs/issues/`）
    - 文档同步：代码变更时必须更新相关 README/ADR
    - 验证流程：任务完成后运行 `pixi run -e dev pre-commit-run` 和覆盖率检查
- **工具**:
    - **文件读写**：**必须使用**内置工具而非 Bash 命令
        - 读文件 → `Read` 工具，不要用 `cat`
        - 写文件 → `Write` 工具，不要用 `cat >` 或 `echo >`
        - 编辑文件 → `Edit` 工具，不要用 `sed`
        - 创建目录 → 可以用 `mkdir`
    - **代码智能分析**：**必须使用** LSP 工具而非 grep/ripgrep/glob
        - 查找函数/类定义 → `goToDefinition`
        - 查找引用位置 → `findReferences`
        - 理解类型信息 → `hover`
        - 了解文件结构 → `documentSymbol`
        - 编辑后检查错误 → `getDiagnostics`
    - **工具选择优先级**（LSP 优先）：
        - 查找定义：`goToDefinition` → `Grep "class Foo"` → `Glob "**/*foo*.py"`
        - 理解结构：`documentSymbol` → `Read` 工具
        - 搜索引用：`findReferences` → `Grep "def bar\(|bar\("`
- **重构**: 所有重构完成**必须移除**旧代码，非数据格式兼容外，**必须移除**留兼容代码
- **其他**: 非本次修改引入的 Lint 检查问题也**必须**解决，避免日积月累

## 绝对禁止

- `import pandas`
- `rolling_mean(20)` 不指定 `closed="left"`
- 跳过风控检查
- 直接提交 main
- 文件读写改操作使用 Bash 中的 `cat`、`cat >`、`echo >`、`sed`
- 禁止在无合理原因下，绕过或忽略相关 mypy、ruff、precommit 检测

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

## 常用命令

```bash
# 检查
pixi run -e dev quick-check     # 开发时
pixi run -e dev pre-commit-run  # 提交前
pixi run -e dev ci-check        # CI 完整

# 测试
pixi run -e dev pytest          # 全部
pixi run -e dev pytest -m unit  # 单元测试
pixi run -e dev pytest -m pit   # PIT 测试
pixi run -e dev pytest -m integration  # 集成测试
```

## ⚠️ SKILLS 执行规则（必须!!重要!!）

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
| `superpowers:brainstorming` | 任何创意工作、创建功能、构建组件、添加功能、修改行为 | ⭐⭐⭐ 必须 1% 概率就调用 |
| `superpowers:systematic-debugging` | 遇到任何 bug、测试失败、异常行为 | ⭐⭐⭐ 必须，先调试后修复 |
| `superpowers:test-driven-development` | 实现任何功能或 bugfix，写实现代码前 | ⭐⭐⭐ 必须 TDD 流程 |
| `superpowers:verification-before-completion` | 准备声明工作完成、修复或通过，提交/PR 前 | ⭐⭐⭐ 必须，证据先于断言 |

**任务管理类：**

| Skill | 使用时机 | 强制级别 |
|-------|---------|---------|
| `superpowers:writing-plans` | 有规范或需求的多步骤任务，在写代码前 | ⭐⭐⭐ 必须 |
| `superpowers:executing-plans` | 有书面实施计划在单独会话执行 | ⭐⭐⭐ 必须 |
| `superpowers:subagent-driven-development` | 执行有独立任务的当前会话中的实施计划 | ⭐⭐⭐ 必须 |
| `superpowers:dispatching-parallel-agents` | 面对 2+ 个无共享状态/顺序依赖的独立任务 | ⭐ 谨慎选择 |

#### 并行执行前检查清单

启动并行 agents 前，**必须确认**：

- [ ] 修改的文件之间无 import 依赖
- [ ] 不涉及共享状态（如数据库 schema、全局配置）
- [ ] 不需要协调的测试运行
- [ ] 修改可以独立 rollback（独立 commit）

**判断标准**: 如果有任何不确定，顺序执行，不要并行。

**高风险场景**（禁止并行）:
- ❌ 修改函数签名 + 更新调用方（有依赖）
- ❌ 重构 import + 修改被导入文件（有依赖）
- ❌ 更新 schema + 迁移数据（需要协调）

**安全场景**（可以并行）:
- ✅ 独立模块的单元测试（无依赖）
- ✅ 不同 README 文档更新（无依赖）
- ✅ 不相关文件的 bug 修复（无依赖）

**并行后必须**:
- ✅ 使用 `ditto-review` 进行并行代码审查
- ✅ 确认所有 agents 的结果一致且无冲突

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

### 调用优先级

当多个 skills 可能适用时：

1. **Process skills first** (brainstorming, debugging) - 确定如何处理任务
2. **Implementation skills second** - 引导执行

### Skill 强制执行 - 无例外清单

以下场景 **也必须调用对应 skill**（无例外）：

| 场景 | 必须 | 禁止 |
|------|------|------|
| "简单查询" | 检查相关 skill | 直接搜索文件 |
| "快速修复" | 调用 TDD | 直接改代码 |
| "查查这个" | 使用 Explore agent | 直接读文件 |
| "小改动" | 写 plan | 直接实现 |
| "单行修改" | 先写测试 | 直接编辑 |

**判断标准**: **只要涉及代码，100% 检查 skill**

### 常见误判场景（危险信号）

| 误判想法 | 实际风险 | 正确做法 |
|---------|---------|---------|
| "这只是一个简单问题" | 问题就是任务 | 检查 skills |
| "我需要更多上下文" | Skill 告诉你如何收集 | 先调用 skill |
| "我先探索代码库" | Skills 告诉你如何探索 | 先调用 skill |
| "我可以快速检查文件" | 文件缺少对话上下文 | 先调用 skill |
| "让我先收集信息" | Skills 告诉你如何收集 | 先调用 skill |
| "这个不需要 formal skill" | 如果 skill 存在，就使用它 | 立即调用 |
| "这只是个 typo" | 可能影响其他地方 | 调用 TDD |
| "查一下就知道了" | 缺少系统性分析 | 使用 Explore agent |
| "两行代码不用测" | 累积质量下降 | RED→GREEN→REFACTOR |
| "我了解这个模块" | 可能有遗漏 | 仍然调用相关 skill |
| "这不算是任务" | 行动 = 任务 | 检查 skills |

---

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

**使用方法**: 用 `findReferences` (LSP) 查找引用，不要依赖记忆。
