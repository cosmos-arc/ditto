# Ditto 项目指南

## 北极星原则

> 以**卓越代码质量**为底线、以**艺术般的可读性与一致风格**为追求，持续产出**清晰、整洁、可演进的架构**与**可长期维护的工程实现**。

**不可妥协：**
- **质量**：正确性、可测试、可维护
- **风格**：一致、克制、易读
- **架构**：清晰边界、低耦合、高内聚、可演进

**遇事不决调研业界最佳实践！！！**
**胆敢偷工减料我就换掉当前模型！！！**

---

## 🎯 三条铁律（5 秒必读）

1. **先探索后编码** - 涉及 2+ 文件或架构变更 → Plan Mode
2. **理解优先于修改** - Read 文件 → Grep 模式 → Edit
3. **验证后完成** - 声明完成前 → `pixi run -e dev check`

---

## 🔄 执行决策流程

```
用户请求
  │
  ├─ 涉及代码修改？
  │   ├─ 是 → 检查 Skill
  │   │   ├─ 创意/新功能 → brainstorming
  │   │   ├─ Bug/失败 → systematic-debugging
  │   │   ├─ 有实施计划 → executing-plans
  │   │   └─ 多步骤任务 → writing-plans
  │   │
  │   ├─ 涉及 2+ 文件或架构变更？
  │   │   └─ 是 → Plan Mode（先探索后编码）
  │   │
  │   └─ Python 代码修改？
  │       └─ 是 → Read 文件 → Grep 模式 → Edit
  │
  └─ 完成前？
      └─ 运行验证 → 声明完成
```

---

## 📋 项目规范

### 代码风格
- **语言**：中文回复/文档，UTF-8 编码
- **Python**：详见 [core.md](.claude/rules/core.md)
- **类型**：禁止滥用 `# type: ignore`（详见 [noqa-ignore.md](.claude/rules/noqa-ignore.md)）
- **TDD**：RED → GREEN → REFACTOR
- **分支**：从 main 拉开发分支，PR 合并

### 测试标准
- **覆盖率**：分支覆盖率 ≥ 80%（详见 [python-test.md](.claude/rules/python-test.md)）
- **新功能**：必须有单元测试
- **API 变更**：必须有集成测试
- **测试命令**：`pixi run -e dev test`

### 架构原则
```
依赖方向: core → datahub → foundation
          apps/port → datahub → foundation
```

- **边界检查**：`pixi run -e dev arch-check`
- **重构**：完成后移除废弃代码，无需向后兼容
- **禁止循环依赖**：必须重构架构，禁止 `TYPE_CHECKING` 延迟导入

详细分层规范：
- Infra → [packages/infra/CLAUDE.md](packages/infra/CLAUDE.md)
- DataHub → [packages/datahub/CLAUDE.md](packages/datahub/CLAUDE.md) | [pit.md](.claude/rules/pit.md)
- Core → [packages/core/CLAUDE.md](packages/core/CLAUDE.md)
- Port → [apps/port/CLAUDE.md](apps/port/CLAUDE.md)

### 允许的依赖（严格限制）

| 功能 | ✅ 允许 | ❌ 禁止 |
|------|--------|---------|
| 存储 | parquet / duckdb / sqlite | - |
| 数据处理 | **polars** | pandas |
| API | fastapi | - |
| 任务 | prefect | - |
| 日志 | loguru / opentelemetry | - |
| 限流重试 | tenacity / limits | - |
| 缓存 | cachebox | - |
| JSON | **orjson** | json |
| ASGI | granian | - |
| 网络 | httpx | - |
| 包管理 | **pixi** | pip/poetry/conda |

### 常用命令

```bash
# 快速验证（开发时）
pixi run -e dev check          # lint + fmt + type + test --fast

# 提交前检查
pixi run -e dev pre-commit-run # pre-commit hooks
pixi run -e dev ci             # CI 完整检查

# 测试
pixi run -e dev test              # 默认：单元测试（并行）
pixi run -e dev test --unit       # 只运行单元测试
pixi run -e dev test --integration # 只运行集成测试
pixi run -e dev test --fast       # 快速测试（跳过慢速）
pixi run -e dev test --snapshot   # 支持 inline-snapshot

# 类型检查
pixi run -e dev type          # 源码（strict）
pixi run -e dev type --tests  # 测试（basic）
pixi run -e dev type --all    # 完整检查

# 代码质量
pixi run -e dev lint          # 检查
pixi run -e dev lint --fix    # 自动修复
pixi run -e dev fmt           # 格式化
```

### 禁止事项

| ❌ 禁止 | 原因/替代 |
|---------|-----------|
| `import pandas` | 使用 polars |
| `rolling_mean(20)` 无 `closed="left"` | 数据泄漏（详见 pit.md） |
| 直接提交 main | 必须通过 PR |
| 绕过 pre-commit/pyright/ruff | 必须通过检测 |
| 文件操作用 Bash cat/sed/echo | 必须用 Read/Edit/Write |
| SRC 内大量 `# noqa`/`# type:ignore` | 优先重构代码 |
| `TYPE_CHECKING` 延迟导入 | 重构架构解决循环依赖 |

---

## 🚀 执行优先级

### 1. Skills 第一（处理前必查）

**历史数据警告**：2,978 个会话分析，不调用 Skills → 失败率 40-50%，返工时间 3-5 倍

| 场景 | 必须调用 | 后果 |
|------|---------|------|
| 创意/新功能 | `brainstorming` | 设计不完整，频繁重构 |
| Bug/测试失败 | `systematic-debugging` | 盲目重试，80% 失败率 |
| 实现功能 | `test-driven-development` | 引入 bug，破坏功能 |
| 多步骤任务 | `writing-plans` | 遗漏边界情况 |
| 完成任务 | `verification-before-completion` | 提交未验证代码 |

**流程**：用户请求 → 检查 Skill → 立即调用 → 再开始工作

### 2. Read ≥ 2x Edit

| 任务类型 | 最低 Read/Edit 比 |
|---------|-------------------|
| 简单修改 | 2.0 |
| 中等修改 | 3.0 |
| 重构任务 | 5.0 |

**标准流程**：
```bash
Read <file>        # 理解当前实现
Read <test_file>   # 理解预期行为
Grep "<pattern>"   # 查找相关代码
Edit <file>        # 现在才修改
```

**禁止模式**：
| ❌ 禁止 | ✅ 正确 |
|---------|---------|
| 连续 Edit | Read → Edit |
| Edit 失败后直接重试 | 调用 systematic-debugging |
| 不读代码直接改 | 先理解再修改 |
| TYPE_CHECKING解决循环引用 | 重构解决 |

---

## ✅ 完成前验证

声明任务完成前，**必须**运行：

```bash
pixi run -e dev check    # lint + fmt + type + test --fast
```

**分支门禁**：
- [ ] basedpyright 类型检查通过
- [ ] ruff 检查通过
- [ ] 测试通过
- [ ] 分支覆盖率 ≥ 80%

---

## 附录：详细参考

### 项目架构

```
ditto/
├── packages/           # 核心包
│   ├── foundation/    # 基础设施
│   ├── datahub/       # 数据访问层
│   └── core/          # 核心引擎
├── apps/              # 应用
│   ├── port/          # Server 应用
│   └── web/           # Web 应用
├── config/            # 环境配置（按环境分组）
│   ├── development/
│   ├── testing/
│   └── production/
└── docs/              # 文档
```

### 环境配置规范

**双层环境架构**：

| 层级 | 变量 | 有效值 | 说明 |
|------|------|--------|------|
| Pixi 环境 | 选择环境 | `default`, `dev` | 依赖管理层 |
| 运行时环境 | `ENVIRONMENT` | `development`, `testing`, `production` | 行为控制层 |

**使用场景**：

| 场景 | Pixi 环境 | ENVIRONMENT | 命令 |
|------|-----------|-------------|------|
| 本地开发 | `dev` | `development` | `pixi run -e dev pytest` |
| 测试执行 | `dev` | `testing` | `pixi run -e dev pytest` |
| 生产部署 | `default` | `production` | `pixi run server` |

> **注意**：`DITTO_ENV` 已弃用，请使用 `ENVIRONMENT`。代码中应使用 `get_environment()` 统一入口获取环境。
