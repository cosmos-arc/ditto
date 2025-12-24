# GitHub Actions CI/CD 说明

## 工作流概览

Ditto 项目使用分层的 CI/CD 策略，将快速反馈的单元测试与耗时的集成测试分离。

### 工作流文件

| 文件 | 触发条件 | 用途 | 耗时 |
|------|----------|------|------|
| `ci.yml` | PR 到 main, push 到 main | 单元测试 + 代码质量检查 | ~5 分钟 |
| `ci-integration.yml` | 手动触发, 定时, CI 成功后 | 集成测试（含 observability 服务） | ~15 分钟 |
| `deploy.yml` | CI 成功后, Release 发布 | 部署到 staging/production | ~10 分钟 |

---

## ci.yml - 持续集成（快速反馈）

**目标**: 在 PR 阶段提供快速反馈，确保代码质量和基础功能正常。

### 作业流程

```
changes (变更检测)
  ├── lint (Ruff)
  ├── type-check (MyPy)
  ├── security (Bandit + Gitleaks)
  ├── test-unit (单元测试, 覆盖率 70%)
  └── build (构建验证, 仅 main 分支)
       └── ci-success (状态汇总)
```

### Branch Protection 要求的检查

| 检查名称 | 说明 |
|----------|------|
| `lint` | Ruff 代码风格检查 |
| `type-check` | MyPy 类型检查 |
| `security` | Bandit 安全扫描 + Gitleaks 敏感信息检测 |
| `test-unit` | 单元测试（排除集成测试） |
| `ci-success` | 所有必需作业的汇总状态 |

### 覆盖率要求

- 单元测试覆盖率: **≥70%**
- 通过 Codecov 精细化配置管理各模块覆盖率

---

## ci-integration.yml - 集成测试（完整验证）

**目标**: 验证与外部服务（observability stack）的集成。

### 触发方式

1. **手动触发**: GitHub Actions UI → "CI - Integration Tests" → "Run workflow"
2. **定时触发**: 每天 UTC 2:00 自动运行
3. **CI 成功后**: 主 CI 完成后自动触发

### 启动的服务

使用 GitHub Actions 服务容器启动：

| 服务 | 端口 | 用途 |
|------|------|------|
| VictoriaMetrics | 8428 | 指标存储与 OTLP 接收 |
| VictoriaLogs | 9428 | 日志存储与查询 |
| Vector | 8686 | 日志采集 |
| Grafana | 3000 | 可视化仪表盘 |

### 运行的测试

```bash
pytest -m "integration" \
  --cov=packages \
  --cov=apps \
  --cov-report=xml:coverage-integration.xml \
  --junitxml=junit-integration.xml
```

---

## deploy.yml - 持续部署

### 部署流程

```
CI 成功
  ├── deploy-staging (自动部署到 staging)
  │     └── 触发 e2e 测试 (可选)
  └── deploy-production (Release 发布触发, 需审批)
        └── rollback (失败时自动回滚)
```

### 环境

| 环境 | 触发方式 | 审批 |
|------|----------|------|
| staging | 合并到 main 分支 | 无需审批 |
| production | 创建 Release tag | 需要审批 |

---

## 本地开发与测试

### 安装 pre-commit 钩子

```bash
pixi run pre-commit-install
```

### 运行单元测试

```bash
# 快速测试（排除集成/慢速测试）
pixi run test-unit

# 等价于
pytest -m "not integration and not e2e and not slow"
```

### 运行集成测试（需要 observability 服务）

**步骤 1**: 启动 observability 服务

```bash
# 使用 docker-compose
cd deploy/observability
docker-compose up -d

# 验证服务状态
docker-compose ps
```

**步骤 2**: 运行集成测试

```bash
# 运行所有集成测试
pixi run test-integration

# 或使用 pytest
pytest -m "integration" -v
```

**步骤 3**: 停止服务

```bash
docker-compose down
```

### 本地验证 CI 检查

```bash
# 完整的 CI 检查（等同于 GitHub Actions 运行）
pixi run ci-check
```

---

## 测试标记说明

| 标记 | 说明 | 运行位置 |
|------|------|----------|
| `integration` | 集成测试（需要外部服务） | 本地 + CI 集成工作流 |
| `e2e` | 端到端测试 | 本地 + CI 集成工作流 |
| `slow` | 耗时测试（>30s） | 本地 + CI 集成工作流 |
| `unit` | 单元测试（无外部依赖） | 本地 + CI 主工作流 |
| `smoke` | 冒烟测试 | 本地 + CI |
| `benchmark` | 性能测试 | 本地 |

---

## 常见问题

### Q1: 为什么 CI 中不运行集成测试？

**A**: 集成测试需要启动多个 Docker 服务，耗时较长（~15 分钟）。将它们分离到独立工作流可以：
- PR 阶段快速获得反馈（~5 分钟）
- 按需或定时运行完整集成测试
- 减少 CI 资源消耗

### Q2: 如何确保 PR 合并后集成测试通过？

**A**: 有三种保障机制：
1. **定时任务**: 每天自动运行，发现问题立即通知
2. **CI 成功后触发**: 主 CI 完成后自动运行集成测试
3. **手动触发**: 发布前可手动运行验证

### Q3: 本地如何运行完整的 CI 验证？

**A**:
```bash
# 1. 启动 observability 服务
cd deploy/observability && docker-compose up -d

# 2. 运行完整测试套件
cd ../..
pixi run ci-check

# 3. 清理
cd deploy/observability && docker-compose down
```

### Q4: 集成测试失败会影响合并吗？

**A**: 不会直接影响，因为 Branch Protection 只要求主 CI 的检查通过。但建议：
- 定时任务失败时应及时修复
- 发布前手动运行集成测试确认

### Q5: 如何添加新的集成测试？

**A**:
```python
# tests/integration/test_your_feature.py
import pytest

@pytest.mark.integration
class TestYourFeatureIntegration:
    def test_something(self):
        # 测试代码
        pass
```

---

## 最佳实践

### PR 工作流

1. 创建功能分支
2. 开发并编写测试
3. 本地运行 `pixi run ci-check`
4. 提交并推送
5. 等待 CI 检查通过
6. 请求代码审查
7. 合并到 main

### 发布前检查

1. 确保主 CI 通过
2. 手动触发集成测试
3. 启动 observability 服务运行本地集成测试
4. 创建 Release tag 触发部署

### 监控与告警

- 集成测试失败会创建 GitHub Issue
- Codecov 覆盖率下降会在 PR 中注释
- 安全扫描失败会阻止合并

---

## 附录: 命令速查

```bash
# === 单元测试 ===
pixi run test-unit              # 运行单元测试
pixi run test-cov               # 带覆盖率的单元测试

# === 集成测试（需要 observability 服务）===
pixi run test-integration       # 运行集成测试

# === 完整测试 ===
pixi run test                   # 运行所有测试

# === 代码质量 ===
pixi run lint                   # Ruff lint
pixi run format                 # Ruff format check
pixi run type                   # MyPy type check
pixi run security               # Bandit security scan

# === 复合任务 ===
pixi run ci-check               # 完整 CI 检查（本地）
```
