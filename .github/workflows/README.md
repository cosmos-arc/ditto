# GitHub Actions CI/CD

Ditto 项目使用 GitHub Actions 实现持续集成和持续部署，集成 Codecov 进行覆盖率管理。

## 概述

```
┌─────────────────────────────────────────────────────────────────┐
│                        GitHub Actions CI/CD                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Push/PR to main                                                │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    CI Workflow                           │   │
│  │  .github/workflows/ci.yml                                │   │
│  │                                                           │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │   │
│  │  │   lint   │  │type-check│  │ security │  │test-unit │ │   │
│  │  │  (Ruff)  │  │ (MyPy)   │  │(Bandit)  │  │(pytest)  │ │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘ │   │
│  │       │             │             │             │        │   │
│  │       └─────────────┴─────────────┴─────────────┘        │   │
│  │                          │                                │   │
│  │                          ▼                                │   │
│  │                   ┌───────────┐                           │   │
│  │                   │ci-success │  ← Branch Protection     │   │
│  │                   └───────────┘                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │                                                         │
│       ▼ (All checks passed)                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  Merge to main                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  CD Workflow                             │   │
│  │  .github/workflows/deploy.yml                            │   │
│  │                                                           │   │
│  │  ┌─────────────────┐    ┌─────────────────┐              │   │
│  │  │ Deploy Staging  │    │ Deploy Production│              │   │
│  │  │ (auto on merge) │    │ (manual trigger) │              │   │
│  │  │ Environment:    │    │ Environment:      │              │   │
│  │  │ staging         │    │ production        │              │   │
│  │  └─────────────────┘    └─────────────────┘              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 工作流文件

### ci.yml - 持续集成

**触发条件**:
- Pull request 到 `main` 分支
- Push 到 `main` 分支

**作业流程**:

```
changes (变更检测)
  ├── lint (Ruff 代码检查)
  ├── type-check (MyPy 类型检查)
  ├── security (Bandit + Gitleaks 安全扫描)
  ├── test-unit (单元测试, 覆盖率 ≥80%)
  │   └── codecov (上传覆盖率报告)
  └── ci-success (状态汇总)
```

**Branch Protection 必需检查**:

| 检查名称 | 说明 | 必需 |
|----------|------|------|
| `lint` | Ruff lint + format | ✅ |
| `type-check` | MyPy 类型检查 | ✅ |
| `security` | Bandit + Gitleaks | ✅ |
| `test-unit` | 单元测试 + 覆盖率 | ✅ |
| `ci-success` | CI 状态汇总 | ✅ |

### ci-integration.yml - 集成测试

**触发条件**:
- 手动触发 (workflow_dispatch)
- 定时任务 (每天 02:00 UTC)
- CI 成功后自动运行 (workflow_run)

**作业流程**:

```
Start observability services (docker compose)
  ├── VictoriaMetrics :8428
  ├── VictoriaLogs    :9428
  ├── Vector          :8686
  └── Grafana         :3000
         │
         ▼
Run integration tests (pytest -m integration)
  ├── test_victoriametrics_health
  ├── test_victorialogs_health
  ├── test_vector_health
  ├── test_grafana_health
  └── test_metrics_export
         │
         ▼
Upload coverage to Codecov (flags: integration)
```

**注意**: 集成测试覆盖率检查已禁用 (`--cov-fail-under=0`)，因为端到端测试覆盖率较低（~25%）是正常的。

### deploy.yml - 持续部署

**触发条件**:
- CI 成功后自动部署到 staging
- Release 发布部署到 production
- 手动触发部署

**环境**:
- **staging**: 自动部署，无需审批
- **production**: 需要审批，仅限 tags (`refs/tags/v*`)

---

## 覆盖率要求

### Codecov 精细化配置 (codecov.yml)

| 模块 | 目标覆盖率 | 容差 |
|------|-----------|------|
| 整体默认 | 80% | ±2% |
| 补丁 (patch) | 80% | 0% |
| core-strategy | 90% | - |
| core-engine | 85% | - |
| datahub | 85% | - |
| foundation | 80% | - |
| server | 80% | - |

### CI 中的覆盖率配置

```yaml
# 单元测试 - 80% 覆盖率要求
pytest --cov=packages --cov=apps --cov-fail-under=80 ...

# 集成测试 - 无覆盖率要求
pytest --cov=packages --cov=apps --cov-fail-under=0 ...
```

---

## 使用说明

### 本地验证（提交前）

```bash
# 完整检查（推荐）
pixi run -e dev ci-check

# 或分别运行
pixi run -e dev lint          # Ruff
pixi run -e dev format-check  # Ruff format
pixi run -e dev typecheck     # MyPy
pixi run -e dev security      # Bandit
pixi run -e dev test-cov      # pytest with coverage

# Pre-commit 钩子
pre-commit run --all-files
```

### 查看 CI 状态

**GitHub Actions 页面**:
https://github.com/cosmos-arc/ditto/actions

**PR 检查状态**:
PR 页面底部显示所有必需的检查项及其状态

### Codecov 覆盖率报告

**PR 中自动显示**: 覆盖率变化报告

**详细报告**: https://codecov.io/gh/cosmos-arc/ditto

### 触发部署

**Staging**: 合并 PR 到 `main` 分支自动触发

**Production**: 创建 Release tag
```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

---

## 分支保护规则

### main 分支保护

- ✅ 需要 Pull Request 才能合并
- ✅ 至少 1 人审批
- ✅ 必须通过所有状态检查
- ✅ 必须是最新的分支（merge 前需要 update）
- ✅ 需要解决所有对话
- ✅ 推荐使用 Squash merge

### GitHub Environments

**staging**:
- 无需审批
- 限制部署分支：`main`

**production**:
- 需要审批（添加审批人）
- 限制部署分支：`refs/tags/v*`

---

## 故障排查

### CI 未触发

**可能原因**:
- 分支名称不匹配（CI 只监听 PR 到 main 和 push 到 main）
- GitHub Actions 未启用

**解决方法**: 创建 PR 到 `main` 分支触发 CI

### 作业失败

**查看日志**:
```bash
# GitHub 网页直接查看
# Actions → 选择运行 → 点击失败的作业
```

### 常见问题

| 问题 | 解决方法 |
|------|----------|
| MyPy 检查失败 | 本地运行 `pixi run -e dev typecheck` 查看详细错误 |
| 覆盖率不足 | 本地运行 `pixi run -e dev test-cov` 查看 HTML 报告 |
| Codecov 未显示 | 检查 `CODECOV_TOKEN` 是否配置在 GitHub Secrets |
| 集成测试失败 | 检查 observability 服务是否启动 |

---

## 开发工作流

### 标准开发流程

```bash
# 1. 创建功能分支
git checkout -b feat/P0-XXX-task-name

# 2. 开发 + 测试
pixi run -e dev ci-check  # 确保通过

# 3. 提交代码
git add .
git commit -m "feat(scope): P0-XXX description"

# 4. 推送分支
git push -u origin feat/P0-XXX-task-name

# 5. 创建 PR
gh pr create --base main --title "feat: P0-XXX description"

# 6. 等待 CI 通过 + 代码审查

# 7. 合并到 main (Squash merge)

# 8. 删除分支
git branch -d feat/P0-XXX-task-name
```

### 快速修复流程

```bash
# 直接在 main 分支修复（小问题）
git commit -m "fix: quick fix"
git push origin main

# 或创建 hotfix 分支（大问题）
git checkout -b hotfix/P0-XXX-issue
# ... 修复 ...
git push origin hotfix/P0-XXX-issue
gh pr create --base main
```

---

## 配置文件

| 文件 | 用途 |
|------|------|
| `.github/workflows/ci.yml` | CI 持续集成 |
| `.github/workflows/ci-integration.yml` | 集成测试 |
| `.github/workflows/deploy.yml` | CD 持续部署 |
| `.github/PULL_REQUEST_TEMPLATE.md` | PR 模板 |
| `.pre-commit-config.yaml` | Pre-commit 钩子 |
| `codecov.yml` | 覆盖率配置 |
| `pixi.toml` | Pixi 任务定义 |

---

## 附录：命令速查

```bash
# 本地完整验证
pixi run -e dev ci-check
pre-commit run --all-files

# 单独运行各检查
pixi run -e dev lint         # Ruff
pixi run -e dev format       # Ruff format
pixi run -e dev typecheck    # MyPy
pixi run -e dev security     # Bandit
pixi run -e dev test-unit    # 单元测试
pixi run -e dev test-cov     # 覆盖率

# 集成测试（本地）
docker compose -f deploy/observability/docker-compose.yml up -d
pixi run -e dev pytest -m integration

# GitHub CLI
gh pr list                    # 列出 PR
gh pr create                  # 创建 PR
gh pr merge <number>          # 合并 PR
gh run list                   # 列出 CI 运行
gh run view <id>              # 查看运行详情
```
