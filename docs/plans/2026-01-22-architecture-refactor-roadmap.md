# Ditto 架构重构中期路线图 (2026 Q1-Q2)

> **For Claude:** 本文档为综合性架构重构路线图，非单次实施计划。
> 如需执行具体任务，请使用 `superpowers:executing-plans` 逐个实施。

**目标:** 修复架构违规问题，提升代码质量和可维护性，建立长期演进基础

**架构原则:** 分层清晰、依赖单向、低耦合高内聚、可演进

**时间周期:** 2026 Q1-Q2（1-2 季度）

---

## 执行摘要

基于 2026-01-22 的全库架构审计，发现以下关键问题：

| 优先级 | 问题类别 | 数量 | 工作量 | 截止目标 |
|--------|----------|------|--------|----------|
| **P0** | 层级穿透 (Apps→Store) | 1 处 | M | Q1 第2周 |
| **P1** | 配置访问不统一 | 6 处 | S | Q1 第3周 |
| **P1** | 宽泛异常处理 | 26 处 | M | Q1 第4-5周 |
| **P2** | Any 类型过度使用 | 多处 | S | Q2 第1周 |
| **P2** | SQLite 连接管理不统一 | 1 处 | M | Q2 第2周 |
| **P2** | 空模块缺少文档 | 3 处 | XS | Q2 第1周 |

**总体工作量估算:** 约 6-8 周（含测试和文档）

---

## 架构现状

### 当前分层

```
Apps (port)
    ↓
Core (quality) + DataHub (sources/stores/accessors)
    ↓
Foundation (cache/db/observability/config)
```

### 依赖方向（正确）

```
port → datahub ✅
port → core ✅
port → foundation ✅
core → foundation ✅
datahub → foundation ✅
```

### 违反架构的依赖

```
port → datahub.stores.* ❌ (应通过 accessor/hub)
```

---

## Phase 1: P0 紧急修复 - 层级穿透 (Q1 第2周)

### 问题: ARCH-001 - Apps/Port 直接访问 DataHub Store 层

**严重程度:** Blocker - 违反核心架构设计

**位置:** `apps/port/src/ditto_port/registry/datahub.py:30-39`

**证据:**
```python
# ❌ 当前违规代码
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.calendar_store import CalendarStore
from ditto_datahub.stores.index_weight_store import IndexWeightStore
from ditto_datahub.stores.ingestion_log import IngestionLogStore
from ditto_datahub.stores.quarantine_store import QuarantineStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_datahub.stores.stock_status_store import StockStatusStore
from ditto_datahub.stores.universe_store import UniverseStore
```

### 技术方案

**方案 A (推荐): 完全移除 Store 直接访问**

通过 DataHub Facade 间接访问所有数据：

```python
# ✅ 正确方式
@app.get("/api/v1/bars")
async def get_bars(sid: int, start: str, end: str, hub: DataHub = Depends()):
    return hub.bars.get(sid, start, end)  # 通过 Accessor
```

**影响范围:**
- `apps/port/src/ditto_port/registry/datahub.py` - 移除 Store Provider 方法
- `apps/port/src/ditto_port/jobs/tasks/*.py` - 改用 hub.* accessor
- `apps/port/src/ditto_port/services/ingestion/*.py` - 改用 hub.* accessor

**工作量:** 2-3 天

**风险:** 低 - 只改变访问路径，不改变业务逻辑

---

### 实施任务清单

#### Task 1.1: 审查 Store 使用情况

**Files:**
- Read: `apps/port/src/ditto_port/registry/datahub.py`
- Grep: `apps/port/src/ditto_port --include="*.py" -e "Store"`

**步骤:**
1. 列出所有直接使用 `*Store` 的位置
2. 识别哪些使用可以通过 Accessor 替代
3. 识别哪些使用确实需要 Store（如特殊场景）

**预期输出:** Store 使用清单（约 15-20 处）

---

#### Task 1.2: 移除 DataHubProvider 中的 Store 导入和方法

**Files:**
- Modify: `apps/port/src/ditto_port/registry/datahub.py`

**Step 1: 验证当前状态**
```bash
grep -n "Store" apps/port/src/ditto_port/registry/datahub.py
```

**Step 2: 移除 Store 导入**
```python
# 删除以下行:
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
# ... 删除所有 Store 导入
```

**Step 3: 删除 Store Provider 方法**
```python
# 删除所有 @provide 装饰的 Store 方法:
# @provide
# def bars_store(...) -> BarsStore:
#     ...
```

**Step 4: 运行类型检查**
```bash
pixi run -e dev type apps/port
```

**预期:** 类型检查失败（显示缺失的 Store 依赖）

---

#### Task 1.3: 更新 Job Tasks 使用 Accessor

**Files:**
- Modify: `apps/port/src/ditto_port/jobs/tasks/dq_batch.py`
- Modify: `apps/port/src/ditto_port/jobs/tasks/monitoring.py`

**Step 1: 注入 DataHub 而非 Store**
```python
# 修改前
def process_task(bars_store: BarsStore):
    df = bars_store.get(...)

# 修改后
def process_task(hub: DataHub):
    df = hub.bars.get(...)
```

**Step 2: 更新 DI 配置**
```python
# 在 registry/core.py 中
@provide
def dq_batch_service(hub: DataHub) -> DQBatchService:
    return DQBatchService(datahub=hub)
```

**Step 3: 运行测试**
```bash
pixi run -e dev test apps/port/tests/jobs/tasks/test_dq_batch.py -v
```

---

#### Task 1.4: 更新 Ingestion Services 使用 Accessor

**Files:**
- Modify: `apps/port/src/ditto_port/services/ingestion/coordinator.py`
- Modify: `apps/port/src/ditto_port/services/ingestion/quality/*.py`

**Step 1: 替换直接 Store 调用**
```python
# 修改前
async def ingest_data(security_store: SecurityStore, ...):
    sid = security_store.get_sid(...)

# 修改后
async def ingest_data(hub: DataHub, ...):
    sid = hub.securities.resolve_sid(...)
```

**Step 2: 更新测试 Mock**
```python
# 测试中 mock hub accessor
def test_ingestion():
    mock_hub = Mock(spec=DataHub)
    mock_hub.bars.get.return_value = test_df
```

**Step 3: 运行集成测试**
```bash
pixi run -e dev test apps/port/tests/services --integration -v
```

---

#### Task 1.5: 验证和清理

**Files:**
- Grep: `apps/port --include="*.py" -e "from ditto_datahub.stores"`

**Step 1: 确认无残留 Store 导入**
```bash
# 应该返回空结果
grep -r "from ditto_datahub.stores" apps/port/src --include="*.py"
```

**Step 2: 运行完整测试套件**
```bash
pixi run -e dev test apps/port -v
```

**Step 3: 运行 CI 检查**
```bash
pixi run -e dev ci
```

**Step 4: 提交变更**
```bash
git add apps/port/src/ditto_port/registry/datahub.py
git add apps/port/src/ditto_port/jobs/tasks/
git add apps/port/src/ditto_port/services/ingestion/
git commit -m "refactor(port): remove direct Store access, use DataHub accessors

- Remove all Store imports from registry/datahub.py
- Update job tasks to use hub.* accessors
- Update ingestion services to use hub facade
- Fixes ARCH-001 layer violation"
```

---

### 回滚策略

```bash
# 如果出现问题，快速回滚
git revert HEAD

# 或切换到修复前的分支
git checkout feature/before-layer-fix
```

---

## Phase 2: P1 工程改进 (Q1 第3-5周)

### Task 2.1: 统一配置访问模式

**问题:** ENG-001 - 6 处直接 `os.environ` 调用

**位置:**
- `packages/foundation/src/ditto_foundation/config/settings.py:88`
- `packages/foundation/src/ditto_foundation/config/paths.py`
- `packages/foundation/src/ditto_foundation/observability/config.py`
- `packages/datahub/src/ditto_datahub/alerts/email.py:36-40`
- `packages/datahub/src/ditto_datahub/alerts/telegram.py:38`
- `packages/datahub/src/ditto_datahub/alerts/wechat.py:37`

#### Step 1: 创建 AlertSettings 类

**Files:**
- Create: `packages/datahub/src/ditto_datahub/config/alert.py`

```python
"""Alert configuration settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AlertSettings(BaseSettings):
    """Alert notification settings."""

    model_config = SettingsConfigDict(
        env_prefix="ALERT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Email settings
    email_smtp_host: str = Field(default="localhost", description="SMTP server host")
    email_smtp_port: int = Field(default=587, description="SMTP server port")
    email_username: str | None = Field(default=None, description="SMTP username")
    email_password: str | None = Field(default=None, description="SMTP password")
    email_from: str = Field(default="noreply@ditto.local", description="From address")
    email_to: str = Field(default="", description="To addresses (comma-separated)")

    # Telegram settings
    telegram_bot_token: str | None = Field(default=None, description="Telegram bot token")
    telegram_chat_id: str | None = Field(default=None, description="Telegram chat ID")

    # WeChat settings
    wechat_webhook_url: str | None = Field(default=None, description="WeChat webhook URL")
    wechat_corp_id: str | None = Field(default=None, description="WeChat corp ID")
    wechat_agent_id: str | None = Field(default=None, description="WeChat agent ID")

    # DingTalk settings
    dingtalk_webhook_url: str | None = Field(default=None, description="DingTalk webhook URL")
    dingtalk_secret: str | None = Field(default=None, description="DingTalk secret")


__all__ = ["AlertSettings"]
```

#### Step 2: 更新 AlertSender 实现

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/alerts/email.py`
- Modify: `packages/datahub/src/ditto_datahub/alerts/telegram.py`
- Modify: `packages/datahub/src/ditto_datahub/alerts/wechat.py`

```python
# email.py 修改
from ditto_datahub.config.alert import AlertSettings

class EmailAlertSender(AlertSender):
    def __init__(self, settings: AlertSettings | None = None) -> None:
        self._settings = settings or AlertSettings()
        self._from_addr = self._settings.email_from
        self._to_addrs = self._settings.email_to.split(",") if self._settings.email_to else []
        # ... 其他配置

    @property
    def name(self) -> str:
        return "email"
```

#### Step 3: 更新 DI 配置

**Files:**
- Modify: `apps/port/src/ditto_port/registry/datahub.py`

```python
from ditto_datahub.config.alert import AlertSettings
from ditto_datahub.alerts.email import EmailAlertSender
from ditto_datahub.alerts.telegram import TelegramAlertSender
from ditto_datahub.alerts.wechat import WeChatAlertSender

@provide
def alert_settings() -> AlertSettings:
    """Alert settings."""
    return AlertSettings()

@provide
def email_sender(alert_settings: AlertSettings) -> EmailAlertSender:
    """Email alert sender."""
    return EmailAlertSender(alert_settings)
```

#### Step 4: 验证配置加载

**测试文件:** `packages/datahub/tests/alerts/test_config.py`

```python
import os
import pytest
from ditto_datahub.config.alert import AlertSettings

def test_alert_settings_defaults():
    settings = AlertSettings()
    assert settings.email_smtp_host == "localhost"
    assert settings.email_smtp_port == 587

def test_alert_settings_from_env(monkeypatch):
    monkeypatch.setenv("ALERT_EMAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("ALERT_EMAIL_SMTP_PORT", "2525")
    settings = AlertSettings()
    assert settings.email_smtp_host == "smtp.example.com"
    assert settings.email_smtp_port == 2525
```

**运行测试:**
```bash
pixi run -e dev test packages/datahub/tests/alerts/test_config.py -v
```

---

### Task 2.2: 改进异常处理精确度

**问题:** ENG-002 - 26 处宽泛 `except Exception` 捕获

**分类处理策略:**

#### A 类: 网络请求异常 (10 处)

**位置:** `packages/datahub/src/ditto_datahub/sources/tushare/*.py`

```python
# 修改前
try:
    response = httpx.get(url, timeout=30)
except Exception as e:
    logger.error("Request failed", error=str(e))

# 修改后
try:
    response = httpx.get(url, timeout=30)
except httpx.TimeoutException as e:
    logger.error("Request timeout", url=url, timeout=30)
    raise  # 重新抛出让上层处理
except httpx.NetworkError as e:
    logger.error("Network error", url=url, error=str(e))
    raise
except httpx.HTTPStatusError as e:
    logger.error("HTTP error", status=e.response.status_code, url=url)
    raise
```

#### B 类: 顶层异常处理 (8 处)

**位置:** `apps/port/src/ditto_port/main.py`, `packages/datahub/src/ditto_datahub/init_providers.py`

```python
# 修改前
except Exception as e:
    logger.error("Failed to initialize", error=str(e))

# 修改后
except Exception as e:
    logger.exception("Failed to initialize application")  # 包含完整堆栈
    raise  # 重新抛出或返回错误响应
```

#### C 类: 数据处理异常 (5 处)

**位置:** `packages/core/src/ditto_core/quality/checkers/*.py`

```python
# 修改前
except Exception as e:
    logger.error("Quality check failed", error=str(e))

# 修改后
except (pl.ComputeError, pl.SchemaError) as e:
    logger.error("Polars computation error", error=str(e))
    # 返回默认结果而非吞掉异常
    return DQResult(dataset=dataset, passed=False, issues=[...])
except ValueError as e:
    logger.error("Invalid input data", error=str(e))
    return DQResult(dataset=dataset, passed=False, issues=[...])
```

#### D 类: 资源清理 (3 处)

**位置:** `packages/foundation/src/ditto_foundation/db/sqlite_pool.py`

```python
# 修改前
try:
    conn.close()
except Exception:
    pass

# 修改后
try:
    conn.close()
except sqlite3.Error as e:
    logger.warning("Failed to close connection", error=str(e))
finally:
    # 确保资源标记为已关闭
    self._closed = True
```

**测试策略:**
```python
# 测试异常传播
def test_network_error_propagates():
    with pytest.raises(httpx.NetworkError):
        client.fetch_data()

# 测试异常转换为业务错误
def test_quality_check_handles_invalid_data():
    result = engine.check(df_with_invalid_data)
    assert not result.passed
    assert len(result.issues) > 0
```

---

## Phase 3: P2 优化改进 (Q2 第1-2周)

### Task 3.1: 减少 Any 类型使用

**问题:** ENG-004 - Cache 返回值类型不明确

**Files:**
- Modify: `packages/foundation/src/ditto_foundation/cache/core.py`

```python
# 修改前
def get(self, key: str, default: Any = None) -> Any:
    ...

# 修改后
from typing import TypeVar

T = TypeVar("T")

class DataCache:
    def get(self, key: str, default: T | None = None) -> T | None:
        """Get cached value with type inference."""
        try:
            value = self._cache[key]
            if self._enable_metrics:
                M.cache_hit.add(1, {"type": "data_cache"})
            return value
        except KeyError:
            if self._enable_metrics:
                M.cache_miss.add(1, {"type": "data_cache"})
            return default
```

**验证类型检查:**
```bash
pixi run -e dev pyright packages/foundation/src/ditto_foundation/cache/core.py
```

---

### Task 3.2: 统一 SQLite 连接管理

**问题:** ENG-005 - QuarantineStore 直接使用 sqlite3.connect()

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/stores/quarantine_store.py`

```python
# 修改前
def __init__(self, db_path: str | Path) -> None:
    self._db_path = Path(db_path)
    self._conn = sqlite3.connect(self._db_path)
    self._init_schema()

# 修改后
def __init__(self, sqlite_pool: SQLitePool) -> None:
    """Initialize quarantine store with connection pool.

    Args:
        sqlite_pool: SQLite connection pool for database access
    """
    self._pool = sqlite_pool
    # Schema initialization happens on first use
    self._initialized = False

def _ensure_schema(self) -> None:
    """Initialize schema if not already done."""
    if self._initialized:
        return

    with self._pool.get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quarantine_failed_data (...)
        """)
    self._initialized = True

def save_failed_data(self, ...) -> int:
    """Save failed data using connection pool."""
    self._ensure_schema()
    with self._pool.get_connection() as conn:
        cursor = conn.execute(...)
        conn.commit()
        return cursor.lastrowid
```

**更新 DI 配置:**
```python
# registry/datahub.py
@provide
def quarantine_store(sqlite_pool: SQLitePool) -> QuarantineStore:
    """Quarantine store with pooled connections."""
    return QuarantineStore(sqlite_pool)
```

---

### Task 3.3: 添加空模块规划文档

**问题:** ENG-003 - 空占位模块缺少说明

**Files:**
- Modify: `packages/core/src/ditto_core/strategy/__init__.py`
- Modify: `packages/core/src/ditto_core/portfolio/__init__.py`
- Modify: `packages/core/src/ditto_core/engine/__init__.py`

```python
"""
Trading Strategy Module (PLANNED)

This module is planned for v0.2.0 (Q2 2026).

TODO: Implement strategy framework
- Strategy base class with signal generation interface
- Backtesting engine integration
- Strategy performance metrics
- Multi-strategy composition

Design Doc: docs/design/06_strategy_framework.md

Status: 📋 Planned - Not yet implemented
"""

__all__: list[str] = []
```

**更新 README.md:**
```markdown
## Core Modules

| Module | Status | Description | Target Version |
|--------|--------|-------------|----------------|
| quality | ✅ Implemented | Data quality engine | v0.1.0 |
| strategy | 📋 Planned | Trading strategy framework | v0.2.0 |
| portfolio | 📋 Planned | Portfolio management | v0.2.0 |
| engine | 📋 Planned | Backtesting engine | v0.3.0 |
```

---

## Phase 4: 质量保证和文档 (持续)

### 测试策略

#### 单元测试要求
- 每个修改的函数必须有对应的单元测试
- 测试覆盖率 >= 80%（分支覆盖）
- 使用 pytest + pytest-mock

#### 集成测试要求
- DI 容器正确组装所有组件
- DataHub Facade 正确路由到 Accessor
- 配置正确加载并注入

#### 回归测试
- 所有现有测试必须通过
- 性能测试（避免引入性能退化）

---

### 文档更新

#### 架构文档
- 更新 `docs/design/02_data_design.md` - 添加 Accessor 层说明
- 更新 `.claude/rules/datahub.md` - 强化"禁止直接访问 Store"规则

#### ADR 记录
- 创建 `docs/adr/006-layer-violation-fix.md` - 记录层级穿透修复决策
- 创建 `docs/adr/007-config-unification.md` - 记录配置统一化决策

#### Changelog
- 更新 `CHANGELOG.md` 记录所有破坏性变更

---

## 风险管理

### 高风险变更

| 变更 | 风险等级 | 缓解措施 | 回滚计划 |
|------|----------|----------|----------|
| 移除 Store 直接访问 | 中 | 分批修改，每批 3-5 个文件 | Git revert |
| 异常处理重构 | 中 | 先写测试验证异常传播 | 分批提交 |
| SQLite 连接池改造 | 低 | 集成测试覆盖 | 恢复直接连接 |

### 低风险变更

| 变更 | 风险等级 | 说明 |
|------|----------|------|
| 配置访问统一 | 低 | 只改变访问方式，不改变配置值 |
| Any 类型优化 | 低 | 纯类型标注，不影响运行时 |
| 文档添加 | 无 | 仅添加注释 |

---

## 里程碑和交付节点

### Q1 里程碑 (Week 1-12)

| 周次 | 里程碑 | 交付物 | 验收标准 |
|------|--------|--------|----------|
| W2 | P0 层级穿透修复 | 移除 Store 直接访问 | 0 处 Store 导入 |
| W3 | P1 配置统一 | AlertSettings 类 | 0 处 `os.getenv` |
| W4-5 | P1 异常处理 | 精确异常类型 | 减少 80% 宽泛捕获 |
| W6-12 | 缓冲和迭代 | 处理意外问题 | CI 全部通过 |

### Q2 里程碑 (Week 13-24)

| 周次 | 里程碑 | 交付物 | 验收标准 |
|------|--------|--------|----------|
| W13 | P2 Any 类型优化 | Cache 泛型 | pyright strict 通过 |
| W14 | P2 SQLite 统一 | QuarantineStore 重构 | 无直接 sqlite3.connect |
| W15 | P2 文档完善 | 空模块说明 | README 更新 |
| W16-24 | 功能开发 | strategy/portfolio/engine | 新功能实现 |

---

## 执行检查清单

### 开始前检查

- [ ] 创建特性分支 `feature/architecture-refactor-q1-2026`
- [ ] 运行完整测试套件建立基线
- [ ] 备份当前数据库 schema
- [ ] 通知团队成员架构变更

### Phase 1 检查点

- [ ] 无 `from ditto_datahub.stores import` 导入
- [ ] 所有数据访问通过 `hub.*` accessor
- [ ] 测试覆盖率 >= 80%
- [ ] CI 检查全部通过

### Phase 2 检查点

- [ ] 0 处直接 `os.environ` 调用
- [ ] 宽泛异常处理减少 80%
- [ ] Alert 配置通过 Settings 类
- [ ] 性能测试无退化

### Phase 3 检查点

- [ ] pyright strict 模式通过
- [ ] SQLite 统一使用连接池
- [ ] 空模块有规划文档
- [ ] README 有模块状态表

### 完成检查

- [ ] 所有测试通过
- [ ] 文档更新完整
- [ ] Changelog 记录
- [ ] ADR 文件创建
- [ ] Code Review 通过
- [ ] 合并到 main

---

## 附录

### A. 相关文档

- [架构规范](.claude/rules/architecture.md)
- [DataHub 规范](.claude/rules/datahub.md)
- [工作流规范](.claude/rules/workflow.md)
- [Python 核心规范](.claude/rules/core.md)

### B. 相关 Issues/PRs

- ARCH-001: 层级穿透问题
- ENG-001: 配置访问不统一
- ENG-002: 宽泛异常处理
- ENG-003: 空模块文档
- ENG-004: Any 类型使用
- ENG-005: SQLite 连接管理

### C. 工具和命令

```bash
# 类型检查
pixi run -e dev type

# Lint 检查
pixi run -e dev lint

# 测试
pixi run -e dev test --unit
pixi run -e dev test --integration

# CI 完整检查
pixi run -e dev ci

# LSP 辅助（查找引用）
pixi run -e dev python .claude/scripts/lsp_pyright.py refs <file> <line> <col>
```

---

**文档版本:** 1.0
**创建日期:** 2026-01-22
**最后更新:** 2026-01-22
**维护者:** Ditto Team
