# ditto-port 架构修复设计

**版本：v1.0**

**日期：2026-02-12**

---

## 1. 概述

### 1.1 背景

基于架构审计发现以下问题需要修复：

| 问题 | 严重度 | 类型 |
|------|--------|------|
| P1-1 backfill 参数名不一致 | P1 | 运行时 Bug |
| P1-2 DQ 返回契约不一致 | P1 | 运行时 Bug |
| P1-3 组合根边界冲突 | P1 | 架构债务 |
| P1-4 配置契约分裂 | P1 | 运行时 Bug |
| P2-1 request_id 未闭环 | P2 | 可观测性 |
| P2-2 backfill 并发注释不一致 | P2 | 语义不一致 |

### 1.2 设计目标

1. 修复所有 P1 运行时 Bug
2. 简化 DI 架构为单一组合根
3. 统一环境变量处理
4. 提升可观测性

---

## 2. 修复范围与优先级

### 2.1 修复清单

| 序号 | 问题 | 严重度 | 修复策略 |
|------|------|--------|----------|
| 1 | P1-1 backfill 参数名不一致 | P1 | 统一为 `config` |
| 2 | P1-2 DQ 返回契约不一致 | P1 | 返回模型添加 `issues` 字段 |
| 3 | P1-3 组合根边界冲突 | P1 | 移除 DomainServiceProvider，合并到 DataHubProvider |
| 4 | P1-4 配置契约分裂 | P1 | 统一环境变量为 `ENVIRONMENT`，CLI `--data-root` 透传 |
| 5 | P2-1 request_id 未闭环 | P2 | 在 middleware 中存储到 `request.state` |
| 6 | P2-2 backfill 并发注释不一致 | P2 | 修正注释，明确实际并发语义 |

### 2.2 执行顺序

```
阶段 1：P1 运行时 Bug 修复
├── 1.1 统一环境变量为 ENVIRONMENT
├── 1.2 修复 backfill 参数名
├── 1.3 修复 DQ 返回契约
└── 1.4 CLI --data-root 透传

阶段 2：P1 架构整理
├── 2.1 移除 DomainServiceProvider
├── 2.2 清理 DataHubProvider 重复绑定
└── 2.3 更新 main.py 和 CLI context 的 Provider 注册

阶段 3：P2 可观测性与语义修正
├── 3.1 request_id 全链路闭环
└── 3.2 修正 backfill 并发注释
```

---

## 3. 阶段 1 详细设计：P1 运行时 Bug 修复

### 3.1 统一环境变量处理

**决策**：使用 `ENVIRONMENT`（不带应用前缀，符合业界惯例）

**理由**：
1. 更符合通用惯例 - `NODE_ENV`、`RAILS_ENV` 都不带应用前缀
2. 语义清晰 - 直接表达"当前环境"
3. Foundation 可提供统一方法 - 避免上层重复实现

**变更文件**：

#### 3.1.1 Foundation 层新增统一方法

文件：`packages/foundation/src/ditto_foundation/config/environment.py`

```python
import os

def get_environment() -> Environment:
    """
    获取当前运行环境（统一入口）。

    读取顺序：
    1. 环境变量 ENVIRONMENT
    2. 默认值 development

    Returns:
        Environment 枚举值
    """
    env_str = os.getenv("ENVIRONMENT", "development")
    return Environment.from_str(env_str)
```

#### 3.1.2 Port 层调用统一方法

文件：`apps/port/src/ditto_port/registry/config.py`

```python
# 修改前
@provide
def environment(self) -> Environment:
    """提供运行环境枚举。"""
    env_str = os.getenv("ENVIRONMENT", "development")
    return Environment.from_str(env_str)

# 修改后
from ditto_foundation.config import get_environment

@provide
def environment(self) -> Environment:
    """提供运行环境枚举。"""
    return get_environment()
```

### 3.2 修复 backfill 参数名

**问题**：deploy.py 使用 `backfill_config`，但 flow 签名是 `config`

**变更文件**：`apps/port/src/ditto_port/jobs/flows/deploy.py`

```python
# 第 124 行：backfill_config → config
FlowDeploymentConfig(
    flow=lambda: _get_flow("backfill_flow"),
    deployment_name="backfill-prod",
    description="全量数据回补流程",
    parameters={
        "config": {  # 修改前：backfill_config
            "dataset": "stock_daily",
            "start_date": "2020-01-01",
            "end_date": "2024-12-31",
        }
    },
    tags=["production", "backfill", "manual"],
),
```

### 3.3 修复 DQ 返回契约

**问题**：L3BatchService 返回不含 `issues` 字段，导致 dq_batch.py 中 `all_issues` 永远为空

**变更文件**：`apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py`

```python
# 第 106-112 行：新增 issues 字段
return {
    "dataset": dataset,
    "trade_date": trade_date,
    "passed": result.passed,
    "issue_count": len(result.issues),
    "alert_count": result.alert_count,
    "issues": result.issues,  # 新增：原始 issues 列表
}
```

### 3.4 CLI --data-root 透传

**问题**：CLI `--data-root` 参数未透传到容器，实际写入路径可能不一致

**方案**：通过环境变量透传

#### 3.4.1 CLI main.py 设置环境变量

文件：`apps/port/src/ditto_port/cli/main.py`

```python
@app.callback()
def main(
    ctx: typer.Context,
    data_root: str = typer.Option(None, "--data-root", "-d", help="数据根目录"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细输出模式"),
) -> None:
    """初始化 CLI 上下文."""
    ctx.ensure_object(dict)

    # 新增：透传 data_root 到环境变量
    if data_root:
        os.environ["DITTO_DATA_ROOT"] = data_root

    ctx.obj["data_root"] = data_root
    ctx.obj["verbose"] = verbose
```

#### 3.4.2 ConfigProvider 支持环境变量覆盖

文件：`apps/port/src/ditto_port/registry/config.py`

```python
@provide
def data_root_config(self, config_loader: ConfigLoader) -> DataRootConfig:
    """加载数据根目录配置。"""
    data_store_values = load_env_file(config_loader, "data_store")

    # 新增：支持 CLI 透传的环境变量覆盖
    if override := os.getenv("DITTO_DATA_ROOT"):
        data_store_values["data_root"] = override

    return DataRootConfig.model_validate(data_store_values)
```

---

## 4. 阶段 2 详细设计：P1 架构整理

### 4.1 移除 DomainServiceProvider

**决策**：完全移除 DomainServiceProvider，所有组件合并到 DataHubProvider

**理由**：
1. 简化架构，单一组合根更易维护
2. 避免依赖解析来源不透明
3. 消除重复绑定问题

**变更文件**：

#### 4.1.1 删除 DomainServiceProvider

- 删除 `apps/port/src/ditto_port/registry/domain.py`

#### 4.1.2 更新 registry/__init__.py

```python
# 移除 DomainServiceProvider 导出
from ditto_port.registry.config import ConfigProvider
from ditto_port.registry.core import CoreProvider
from ditto_port.registry.datahub import DataHubProvider
from ditto_port.registry.notification import NotificationProvider
from ditto_port.registry.sources import DataSourcesProvider

__all__ = [
    "ConfigProvider",
    "CoreProvider",
    "DataHubProvider",
    "DataSourcesProvider",
    "NotificationProvider",
]
```

### 4.2 DataHubProvider 重构

**重构后职责**：

```
DataHubProvider（单一组合根）
├── Runtime Layer
│   ├── SQLitePool
│   ├── SQLiteClient
│   ├── FileLockManager
│   ├── DataCache
│   └── InstrumentIdAllocator
├── Store Layer（所有 CQRS Reader/Writer）
│   ├── Metadata Stores
│   ├── Market Stores
│   ├── Fundamental Stores
│   ├── Capital Stores
│   ├── Macro Stores
│   ├── Features Stores
│   ├── Factors Stores
│   └── Runtime Stores
└── Domain Services
    ├── MetadataService
    ├── MarketService
    ├── FundamentalService
    ├── CapitalService
    ├── MacroService
    ├── FeatureService
    ├── FactorService
    ├── SourceService
    ├── IngestionLogService
    └── QualityRecordService
```

**变更内容**：

1. 从 DomainServiceProvider 合并所有 Store 创建方法
2. 移除 `data_root` 重复绑定（已在 ConfigProvider 提供）
3. 移除 `sources` 重复绑定（已在 DataSourcesProvider 提供）

### 4.3 更新 Provider 注册

#### 4.3.1 main.py（API 入口）

文件：`apps/port/src/ditto_port/main.py`

```python
# 修改前
container = make_async_container(
    ConfigProvider(),
    CoreProvider(),
    DomainServiceProvider(),  # 移除
    DataHubProvider(),
    DataSourcesProvider(),
)

# 修改后
container = make_async_container(
    ConfigProvider(),
    CoreProvider(),
    DataHubProvider(),
    DataSourcesProvider(),
)
```

#### 4.3.2 cli/context.py（CLI 入口）

文件：`apps/port/src/ditto_port/cli/context.py`

```python
# 修改前
container = make_container(
    ConfigProvider(),
    CoreProvider(),
    DomainServiceProvider(),  # 移除
    DataHubProvider(),
    DataSourcesProvider(),
)

# 修改后
container = make_container(
    ConfigProvider(),
    CoreProvider(),
    DataHubProvider(),
    DataSourcesProvider(),
)
```

---

## 5. 阶段 3 详细设计：P2 可观测性与语义修正

### 5.1 request_id 全链路闭环

**问题**：middleware 生成 request_id 但未存储到 `request.state`，异常处理器无法获取

**变更文件**：`apps/port/src/ditto_port/main.py`

```python
@app.middleware("http")
async def log_requests(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Log incoming requests and outgoing responses."""
    request_id = str(uuid.uuid4())

    # 新增：存储到 request.state，供异常处理器使用
    request.state.request_id = request_id

    # ... 其余逻辑不变
```

**效果**：
- 异常日志中包含 `request_id`
- 错误响应中包含 `X-Request-ID` header
- 支持跨日志追踪

### 5.2 修正 backfill 并发注释

**问题**：注释说"年内串行"，但代码实际上对所有日期并行提交

**变更文件**：`apps/port/src/ditto_port/services/ingestion/backfill.py`

```python
# 修改前（第 82 行注释）
# 年份级并行，年内串行（避免文件锁冲突）

# 修改后
# 按年份分组，并发度上限为 min(parallel, 年份数)
# 注意：同一年内的日期仍会并行执行，依赖 FileLockManager 避免冲突
```

---

## 6. 文档更新

### 6.1 项目规范文档

| 文件 | 更新内容 |
|------|----------|
| `.claude/CLAUDE.md` | 环境配置规范：明确 `ENVIRONMENT` 为统一环境变量，新增 `DITTO_DATA_ROOT` |
| `.claude/rules/server.md` | DI 架构：更新 Provider 层级说明，移除 DomainServiceProvider |
| `docs/design/11_port_architecture.md` | 目录结构：更新 registry 目录，架构图更新 |

### 6.2 环境配置规范更新

CLAUDE.md 环境配置规范章节修订：

```markdown
### 环境配置规范

**双层环境架构**：

| 层级 | 变量 | 有效值 | 说明 |
|------|------|--------|------|
| Pixi 环境 | 选择环境 | `default`, `dev` | 依赖管理层 |
| 运行时环境 | `ENVIRONMENT` | `development`, `testing`, `production` | 行为控制层 |
| CLI 覆盖 | `DITTO_DATA_ROOT` | 任意路径 | CLI --data-root 透传 |

**统一获取方法**：
```python
from ditto_foundation.config import get_environment

env = get_environment()  # 从 ENVIRONMENT 环境变量读取
```
```

### 6.3 DI 架构更新

server.md 新增章节：

```markdown
## 依赖注入架构

Provider 层级（单一组合根）：

```
ConfigProvider      → 配置加载（Settings, DataRoot, Environment）
CoreProvider        → DQ 引擎、规范加载
DataHubProvider     → 所有 Store + Domain Services（单一组合根）
DataSourcesProvider → 外部数据源（Tushare）
```

**禁止**：
- 创建多个 Provider 提供相同类型
- Store 在 Provider 外部直接实例化
```

---

## 7. 测试策略

### 7.1 新增测试

| 测试文件 | 测试内容 |
|----------|----------|
| `tests/unit/foundation/test_environment_unit.py` | 验证 `get_environment()` 函数 |
| `tests/unit/jobs/flows/test_deploy_unit.py` | deployment 参数契约测试 |
| `tests/unit/services/quality/test_l3_batch_unit.py` | DQ 返回契约测试（含 `issues` 字段） |
| `tests/integration/cli/test_cli_data_root.py` | CLI `--data-root` 生效测试 |

### 7.2 回归测试

```bash
pixi run -e dev test --unit        # 确保单元测试通过
pixi run -e dev test --integration # 确保集成测试通过
pixi run -e dev check              # 完整检查
```

---

## 8. 实施检查清单

### 阶段 1：P1 运行时 Bug 修复
- [ ] Foundation: 新增 `get_environment()` 函数
- [ ] Port: ConfigProvider 调用 `get_environment()`
- [ ] Port: 修复 backfill 参数名 `backfill_config` → `config`
- [ ] Port: L3BatchService 返回添加 `issues` 字段
- [ ] Port: CLI `--data-root` 透传支持
- [ ] 更新 CLAUDE.md 环境配置规范

### 阶段 2：P1 架构整理
- [ ] 删除 DomainServiceProvider
- [ ] 合并所有 Store 到 DataHubProvider
- [ ] 移除重复绑定（data_root, sources）
- [ ] 更新 main.py 和 cli/context.py 的 Provider 注册
- [ ] 更新 server.md DI 架构说明
- [ ] 更新 11_port_architecture.md

### 阶段 3：P2 可观测性与语义修正
- [ ] main.py: 存储 request_id 到 `request.state`
- [ ] backfill.py: 修正并发注释

---

## 9. 参考资料

- 架构审计报告：`docs/reviews/2026-02-09-architecture-audit.md`
- 12-Factor App Config: https://12factor.net/config
- Dagster - Best Practices for Python Env Variables: https://dagster.io/blog/python-environment-variables
