# GitHub Actions 工作流

## 概述

Ditto 项目使用 GitHub Actions 实现持续集成和持续部署，集成 Codecov 进行覆盖率管理。

## 工作流文件

### ci.yml - 持续集成

**文件路径**: `.github/workflows/ci.yml`

**触发条件**:
- Pull request 到 `main` 分支
- Push 到 `main` 分支

**作业流程**:
```
changes (变更检测)
  ├── lint (Ruff)
  ├── type-check (MyPy)
  ├── security (Bandit + Gitleaks)
  ├── test-unit (单元测试, 覆盖率80%)
  │   └── test-integration (集成测试, 覆盖率追加)
  └── build (构建验证，仅 main)
```

**覆盖率要求**:
- 整体: 80% (通过 codecov.yml 精细化配置)
- 单元测试: `--cov-fail-under=80`
- Codecov 集成: 自动上传并生成 PR 注释

**必需检查** (对应 Branch Protection):
- `lint` - Ruff 代码检查
- `type-check` - MyPy 类型检查
- `security` - 安全扫描
- `test-unit` - 单元测试
- `ci-success` - 汇总状态

### deploy.yml - 持续部署

**文件路径**: `.github/workflows/deploy.yml`

**触发条件**:
- CI 成功后自动部署到 staging
- Release 发布部署到 production
- 手动触发 (workflow_dispatch)

**环境配置**:

| 环境 | 审批要求 | 限制分支 | 说明 |
|------|----------|----------|------|
| staging | 无需审批 | main | CI 成功后自动部署 |
| production | 需要审批 | refs/tags/v* | Release 发布时触发 |

**部署流程**:
1. **prepare** - 确定部署目标和版本
2. **deploy-staging** - 部署到 staging 环境
3. **deploy-production** - 部署到 production 环境 (需审批)
4. **rollback** - production 失败时自动回滚

## 使用说明

### 本地验证

提交代码前必须运行:

```bash
# 安装 pre-commit 钩子
pixi run pre-commit-install

# 运行所有检查
pre-commit run --all-files

# 或使用 pixi 任务
pixi run ci-check
```

### 查看 CI 状态

访问: https://github.com/[username]/ditto/actions

### Codecov 覆盖率报告

- PR 中自动显示覆盖率变化
- 访问: https://codecov.io/gh/[username]/ditto

### 触发部署

**Staging**: 合并到 `main` 分支自动触发

**Production**: 创建 Release tag
```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

## 覆盖率要求

基于 `codecov.yml` 的精细化配置:

| 模块 | 目标 | 说明 |
|------|------|------|
| 整体 | 80% | 默认要求 |
| 补丁 (patch) | 80% | 新增代码必须达到 |
| core-strategy | 90% | 策略核心逻辑 |
| core-engine | 85% | 核心引擎 |
| datahub | 85% | 数据访问层 |
| foundation | 80% | 基础设施 |
| server | 80% | API 服务 |

## 故障排查

### 常见问题

**问题**: MyPy 检查失败
```bash
# 本地查看详细错误
pixi run type
```

**问题**: 覆盖率不足
```bash
# 本地查看 HTML 报告
pixi run test-cov
# 报告生成在 htmlcov/ 目录
```

**问题**: Codecov 未显示报告
- 检查 `CODECOV_TOKEN` 是否配置在 GitHub Secrets
- 检查 workflow 是否成功完成

**问题**: Pre-commit 钩子运行缓慢
- 首次运行需要下载依赖，请耐心等待
- 后续运行会使用缓存，速度会快很多

## 配置验证

### Branch Protection 验证

确保 main 分支的 Branch Protection 规则配置以下必需检查:

- [x] `lint`
- [x] `type-check`
- [x] `security`
- [x] `test-unit`
- [x] `ci-success`

### Environment 验证

**staging**:
- [x] 无需审批
- [x] 限制部署分支: `main`

**production**:
- [x] Required reviewers: 需要添加审批人
- [x] Wait timer: 5 分钟 (可选)
- [x] 限制部署分支: `refs/tags/v*`

## Secrets 配置

以下 Secrets 需要在 GitHub 仓库设置中配置:

| Secret | 用途 | 必需 |
|--------|------|------|
| `CODECOV_TOKEN` | Codecov 上传覆盖率 | 是 |
| `STAGING_HOST` | Staging 服务器地址 | 部署时 |
| `STAGING_USER` | Staging 服务器用户 | 部署时 |
| `STAGING_SSH_KEY` | Staging SSH 密钥 | 部署时 |
| `PROD_HOST` | Production 服务器地址 | 部署时 |
| `PROD_USER` | Production 服务器用户 | 部署时 |
| `PROD_SSH_KEY` | Production SSH 密钥 | 部署时 |
| `OBSERVABILITY_WEBHOOK` | 部署通知 Webhook | 可选 |

## 相关文档

- [主 README](../../README.md)
- [开发者指南](../../docs/development.md)
- [Codecov 配置](../../codecov.yml)
