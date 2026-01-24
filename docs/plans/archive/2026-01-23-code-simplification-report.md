# Code Simplifier - 项目整体代码简化分析报告

## 执行摘要

经过全面分析，Ditto 项目代码质量整体优秀（⭐⭐⭐⭐⭐），发现 **15 处**可简化的代码，其中：
- **5 项**可立即清理（零风险）
- **2 项**需验证后清理（低风险）
- **1 项**架构重构（用户确认）
- **7 项**建议保持现状

---

## 一、TYPE_CHECKING 分析结果

### 发现 4 处使用

| 文件 | 用途 | 建议 |
|------|------|------|
| `webhook.py` | 可选依赖（httpx） | ⚠️ **可移除** - httpx 是核心依赖 |
| `stock_status.py` | 循环导入回避 | ⚠️ **需重构** - 用户确认统一架构 |
| `conftest.py` | 类型注解优化 | ✅ 可移除 - 直接导入即可 |
| `dishka/__init__.pyi` | 存根文件 | ✅ 保持 - 标准做法 |

### 问题 1: webhook.py 的 TYPE_CHECKING

**当前实现**:
```python
if TYPE_CHECKING:
    import httpx
else:
    try:
        import httpx
    except ImportError:
        httpx = None
```

**用户决策**: ✅ **移除 TYPE_CHECKING，直接依赖 httpx**

**原因**:
- `httpx` 在 `pixi.toml` 的 `[dependencies]` 中，是**核心依赖**
- 不是可选依赖，无需优雅降级
- 直接导入更简洁

**修改方案**:
```python
import httpx  # 直接导入
```

**同时需要移除**:
- `__init__` 中的 `ImportError` 检查
- 第 70 行的 `assert httpx is not None`

---

## 二、向后兼容代码分析结果

### 发现 6 处向后兼容代码

| 位置 | 类型 | 状态 | 建议 |
|------|------|------|------|
| `sources/__init__.py` | ingestion re-export | ✅ 可移除 | **高优先级** - 所有代码已迁移 |
| `storage.py:43` | legacy md5 注释 | ✅ 可移除 | **高优先级** - MD5 已完全移除 |
| `test_parquet_store_base_unit.py:15` | `ParquetStore` 别名 | ✅ 可移除 | **高优先级** - 仅测试 |
| `paths.py:488,550` | `_paths` 模块级变量 | ✅ 可移除 | **高优先级** - 无外部依赖 |
| `hub.py:235` | 容器外兼容注释 | ✅ 保留更新 | **中优先级** - 更新文档说明 |
| `bars/__init__.py` | Re-export | ✅ 保持 | 正常的模块组织 |

---

## 二、Notification 相关问题

### 问题 2: Telegram 通知能力

**发现**:
- `NotificationSettings` 中有 `telegram_bot_token` 和 `telegram_chat_id` 配置
- `channels/__init__.py` 只导出 `EmailSender` 和 `WebhookSender`
- 没有 `TelegramSender` 实现
- `webhook.py` 文档字符串说 "Supports Telegram, WeChat, DingTalk, Slack, and custom webhooks"

**分析**:
- 历史文档提到 `alerts/telegram_sender.py`（已在 datahub.alerts 重构中移除）
- 当前只有 `WebhookSender`，但配置中有 Telegram 专用字段
- 需要创建独立的 `TelegramSender` 来使用这些配置

**用户决策**: ✅ **两者都保留** - 创建 TelegramSender + 保留 WebhookSender

**实现方案**:

**1. 创建 `TelegramSender` 类**

```python
# packages/foundation/src/ditto_foundation/notification/channels/telegram.py

"""Telegram notification channel."""

import httpx
from loguru import logger

from ditto_foundation.notification.config import NotificationSettings
from ditto_foundation.notification.sender import NotificationSender


class TelegramSender(NotificationSender):
    """
    Telegram Bot API notification sender.

    Uses Telegram Bot API to send messages directly (not via webhook).
    Requires bot_token and chat_id in NotificationSettings.
    """

    def __init__(self, settings: NotificationSettings) -> None:
        """
        Initialize Telegram sender with settings.

        Args:
            settings: Notification settings with telegram configuration.

        Raises:
            ValueError: If telegram_bot_token or telegram_chat_id is not configured.
        """
        if not settings.telegram_bot_token:
            raise ValueError("telegram_bot_token is required for TelegramSender")
        if not settings.telegram_chat_id:
            raise ValueError("telegram_chat_id is required for TelegramSender")

        self._settings = settings
        self._api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    @property
    def channel_name(self) -> str:
        """Get channel identifier."""
        return "telegram"

    def send(self, rendered_content: str) -> bool:
        """
        Send rendered content via Telegram Bot API.

        Args:
            rendered_content: Rendered content (plain text or Markdown) to send.

        Returns:
            True if send was successful, False otherwise.
        """
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    f"{self._api_url}/sendMessage",
                    json={
                        "chat_id": self._settings.telegram_chat_id,
                        "text": rendered_content,
                        "parse_mode": "Markdown",  # or "HTML"
                    },
                )
                response.raise_for_status()

            logger.info(
                "Telegram message sent successfully",
                event="telegram_sent",
                chat_id=self._settings.telegram_chat_id,
            )
            return True

        except Exception as e:
            logger.error(
                "Telegram send failed",
                event="telegram_error",
                error=str(e),
            )
            return False
```

**2. 更新 `channels/__init__.py`**

```python
"""Notification channel senders."""

from ditto_foundation.notification.channels.email import EmailSender
from ditto_foundation.notification.channels.telegram import TelegramSender
from ditto_foundation.notification.channels.webhook import WebhookSender

__all__ = [
    "EmailSender",
    "TelegramSender",
    "WebhookSender",
]
```

**3. 更新 `webhook.py` 文档字符串**

```python
class WebhookSender(NotificationSender):
    """
    Generic webhook notification sender via HTTP POST.

    Supports custom webhooks for:
    - WeChat (企业微信)
    - DingTalk (钉钉)
    - Slack
    - Custom endpoints

    Note: For Telegram, use TelegramSender for direct Bot API integration,
    or use WebhookSender with a Telegram webhook URL if you have a proxy service.
    """
```

**4. 创建单元测试**

```python
# packages/foundation/tests/unit/notification/test_telegram_sender_unit.py
```

---

### 问题 3: DataHub.close() 兼容代码与单元测试策略

**用户关切**: 单元测试不依赖测试容器，如何去除 `DataHub.close()` 兼容代码？

**当前状态分析**:

```python
# test_hub_unit.py 第 130 行
@pytest.fixture
def datahub_with_dependencies(tmp_path: Path) -> Generator[DataHub, None, None]:
    # ... 手动构造所有依赖 ...
    sqlite_pool = SQLitePool(str(db_path), schema_path=_SCHEMA_PATH)
    # ... 手动注入所有依赖 ...
    hub = DataHub(...)
    yield hub
    sqlite_pool.close()  # 手动清理
```

**根本问题分析**:

```
DataHub 接收 sqlite_pool 作为依赖注入  ←  符合 DI 原则
         ↓
DataHub.close() 负责关闭 sqlite_pool   ←  违反"谁创建谁销毁"原则
```

这导致了**责任模糊**：
- `sqlite_pool` 是外部传入的，但销毁责任在 `DataHub`
- 在容器环境中，Provider 也要负责销毁（yield 后调用 `sqlite_pool.close()`）
- 单元测试中，fixture 也要负责销毁（yield 后调用 `sqlite_pool.close()`）

**不同场景的生命周期**:

| 场景 | sqlite_pool 来源 | 谁应该负责销毁？ |
|------|-----------------|-----------------|
| dishka 容器 | Provider 创建 | **Provider** (yield 后) |
| 单元测试 | Fixture 创建 | **Fixture** (yield 后) |
| 直接使用（罕见） | 用户手动创建 | **用户** |

**解决方案: 移除 close() 方法，使用独立 sqlite_pool fixture**:

**1. DataHub 移除 close() 相关代码**

```python
# 移除以下内容：
# - close() 方法
# - _closed 标志
# - atexit.register(_cleanup_on_exit)
# - __exit__ 方法
# - _cleanup_on_exit() 方法
```

**2. 单元测试使用独立 sqlite_pool fixture（推荐）**

```python
@pytest.fixture
def sqlite_pool(tmp_path: Path) -> Generator[SQLitePool, None, None]:
    """SQLite 连接池 fixture（单元测试专用）."""
    db_path = tmp_path / "meta" / "hub.sqlite"
    schema_path = _SCHEMA_PATH

    pool = SQLitePool(str(db_path), schema_path=schema_path)
    pool.init_schema()

    yield pool
    # fixture cleanup 会自动清理
    pool.close()

@pytest.fixture
def datahub_with_dependencies(
    sqlite_pool: SQLitePool,  # 依赖注入
    # ... 其他依赖
) -> Generator[DataHub, None, None]:
    """DataHub with all dependencies（单元测试专用）."""
    hub = DataHub(
        data_root=data_root,
        sqlite_pool=sqlite_pool,  # 直接使用
        # ...
    )
    yield hub
    # 不需要手动清理，sqlite_pool fixture 会负责
```

**收益**:

1. ✅ **职责清晰**: DataHub 只是使用者，不拥有 sqlite_pool
2. ✅ **符合 DI 原则**: 谁创建，谁销毁
3. ✅ **符合 pytest 最佳实践**: 独立 fixture 管理资源生命周期
4. ✅ **可复用**: sqlite_pool fixture 可被其他测试复用
5. ✅ **简化代码**: 移除 close()、atexit、_closed 等复杂性
6. ✅ **一致性**: 所有场景（容器/测试/直接使用）都遵循"创建者负责销毁"原则

**用户确认**: ✅ **移除 close() 方法**

---

## 三、注释代码和未使用导入分析结果

### 1. TODO 注释（2 处）

| 位置 | 问题 | 建议 |
|------|------|------|
| `dq_batch.py:176` | 告警发送未实现 | 集成现有 `notification` 模块或移除 TODO |
| `l3_batch_service.py:220` | 重复的 TODO | 同上 |

### 2. 空 `__all__` 声明（2 处）

| 位置 | 建议 |
|------|------|
| `jobs/__init__.py:3` | 移除 `__all__ = []`（Python 默认行为） |
| `scripts/__init__.py:8` | 同上 |

### 3. 未使用导入

✅ **通过 ruff F401 检测，未发现问题**

---

## 四、深入分析结果

### 1. stock_status.py 架构问题

**用户决策**: ✅ **统一架构，所有适配器支持 TushareClient 注入**

**重构方案**:
1. **修改 `BaseTushareAdapter`** 支持两种初始化方式：
   - 传入 `token` + `settings` → 创建新 client（当前行为）
   - 传入 `_client` → 使用已有 client（新增）

2. **让 `StockStatusAdapter` 继承 `BaseTushareAdapter`**
   - 消除 TYPE_CHECKING
   - 架构统一

**具体实现**:

```python
# base.py 修改
class BaseTushareAdapter:
    def __init__(
        self,
        token: str | None = None,
        settings: DataSourceSettings | None = None,
        *,
        _client: TushareClient | None = None,  # 内部使用，命名参数
    ) -> None:
        """
        Initialize Tushare adapter.

        Args:
            token: API token. Reads from keyring if None.
            settings: 数据源配置.
            _client: 已存在的 client（用于依赖注入）.

        """
        if _client is not None:
            self._client = _client
        else:
            self._client = TushareClient(token=token, settings=settings)
```

```python
# stock_status.py 修改
class StockStatusAdapter(BaseTushareAdapter):
    def __init__(self, *, client: TushareClient) -> None:
        """
        初始化 StockStatusAdapter.

        Args:
            client: Tushare API 客户端实例（必须传入）.

        """
        super().__init__(_client=client)  # 使用命名参数传入 client
```

**收益**:
- ✅ 架构统一，所有适配器继承自 BaseTushareAdapter
- ✅ 消除 TYPE_CHECKING
- ✅ 更灵活的依赖注入模式

---

### 2. _paths 模块变量使用

**结论**: ✅ **可以安全移除**

**发现**:
- LSP 确认：`_paths` 只在 `paths.py` 内部使用，无外部引用
- Grep 确认：无任何测试文件直接访问 `_paths`
- 标准访问方式已完善：`get_paths()`, `reload_paths()`, `reset_paths_for_testing()`

**可移除的代码**:
```python
# 第 488 行
_paths: XDGPaths | None = None

# 第 550 行
# Module-level accessor for backward compatibility with tests
_paths = _PathsRegistry.instance
```

**风险等级**: 🟢 低风险 - 无外部依赖，纯清理操作

---

### 3. DataHub.close() 移除（符合 DI 原则）

**结论**: ✅ **移除 close() 方法及相关代码**

**发现**:
- `DataHub.close()` 违反了依赖注入原则（谁创建，谁销毁）
- `sqlite_pool` 是外部注入的，不应由 `DataHub` 负责销毁
- 单元测试可以使用独立的 `sqlite_pool` fixture 管理生命周期

**需要移除的代码**:
```python
# packages/datahub/src/ditto_datahub/hub.py

# 移除：
# - close() 方法（约 20 行）
# - _closed 标志
# - atexit.register(self._cleanup_on_exit)
# - __exit__ 方法
# - _cleanup_on_exit() 方法
```

**需要修改的测试**:
```python
# packages/datahub/tests/unit/test_hub_unit.py

# 新增独立的 sqlite_pool fixture
@pytest.fixture
def sqlite_pool(tmp_path: Path) -> Generator[SQLitePool, None, None]:
    """SQLite 连接池 fixture（单元测试专用）."""
    db_path = tmp_path / "meta" / "hub.sqlite"
    pool = SQLitePool(str(db_path), schema_path=_SCHEMA_PATH)
    pool.init_schema()
    yield pool
    pool.close()

# 修改 datahub_with_dependencies，依赖 sqlite_pool fixture
@pytest.fixture
def datahub_with_dependencies(
    sqlite_pool: SQLitePool,  # 依赖注入
    # ... 其他依赖
) -> Generator[DataHub, None, None]:
    hub = DataHub(..., sqlite_pool=sqlite_pool)
    yield hub
    # 移除 yield 后的手动 close()
```

**收益**:
1. ✅ **职责清晰**: DataHub 只是 sqlite_pool 的使用者，不拥有其生命周期
2. ✅ **符合 DI 原则**: 依赖注入对象的生命周期由注入方管理
3. ✅ **符合 pytest 最佳实践**: 独立 fixture 管理资源，自动清理
4. ✅ **可复用**: sqlite_pool fixture 可被其他测试复用
5. ✅ **简化代码**: 移除约 30 行复杂性代码

**风险等级**: 🟢 低风险 - 改动范围明确，测试覆盖完整

---

## 五、最终清理清单

### 第一批：立即清理（7 个文件，零风险）

```bash
# 高优先级清理
packages/datahub/src/ditto_datahub/sources/__init__.py
packages/datahub/src/ditto_datahub/models/storage.py
packages/datahub/tests/unit/stores/test_parquet_store_base_unit.py
apps/port/src/ditto_port/jobs/__init__.py
packages/datahub/src/ditto_datahub/scripts/__init__.py
packages/foundation/src/ditto_foundation/config/paths.py

# TYPE_CHECKING 清理（httpx 是核心依赖）
packages/foundation/src/ditto_foundation/notification/channels/webhook.py
```

### 第二批：文档更新（2 个文件）

```bash
# 更新文档说明
packages/foundation/tests/integration/observability/conftest.py
packages/foundation/src/ditto_foundation/notification/channels/webhook.py  # 更新文档
packages/foundation/src/ditto_foundation/notification/channels/__init__.py  # 添加 TelegramSender
```

### 第三批：新增功能（需要 TDD）

```bash
# 用户确认：创建 TelegramSender
packages/foundation/src/ditto_foundation/notification/channels/telegram.py  # 新文件
packages/foundation/tests/unit/notification/test_telegram_sender_unit.py  # 新文件
```

### 第四批：架构重构（4 个文件，需要 TDD）

```bash
# 用户确认：移除 DataHub.close()，符合 DI 原则
packages/datahub/src/ditto_datahub/hub.py  # 移除 close()、_closed、atexit、__exit__、_cleanup_on_exit
packages/datahub/tests/unit/test_hub_unit.py  # 新增 sqlite_pool fixture，修改 datahub_with_dependencies

# 用户确认：统一 TushareAdapter 架构
packages/datahub/src/ditto_datahub/sources/tushare/adapters/base.py
packages/datahub/src/ditto_datahub/sources/tushare/adapters/stock_status.py
```

---

## 六、执行优先级

### 第一批：立即清理（零风险）
1. 移除 `sources/__init__.py` 的 ingestion re-export
2. 移除 `storage.py` 中的 "md5 for legacy" 注释
3. 移除测试中的 `ParquetStore` 类型别名
4. 清理空的 `__all__` 声明
5. 移除 `_paths` 模块级变量
6. **移除 `webhook.py` 的 TYPE_CHECKING** ⭐ 用户确认

### 第二批：文档更新（低风险）
7. 移除 `conftest.py` 的 TYPE_CHECKING
8. **更新 `webhook.py` 文档** ⭐ 说明与 TelegramSender 的区别
9. **更新 `channels/__init__.py`** ⭐ 导出 TelegramSender

### 第三批：新增功能（需要 TDD）
10. **创建 TelegramSender 类** ⭐ 用户确认
    - 使用 telegram_bot_token 和 telegram_chat_id 配置
    - 直接调用 Telegram Bot API
    - 创建单元测试

### 第四批：架构重构（需要 TDD）
11. **移除 DataHub.close() 方法** ⭐ 用户确认，符合 DI 原则
    - 移除 `close()`、`_closed`、`atexit.register`、`__exit__`、`_cleanup_on_exit()`
    - 新增独立的 `sqlite_pool` fixture
    - 修改 `datahub_with_dependencies` 依赖 `sqlite_pool` fixture
12. **统一 TushareAdapter 架构** ⭐ 用户确认
    - 修改 `BaseTushareAdapter` 支持 client 注入
    - 让 `StockStatusAdapter` 继承基类
    - 消除 TYPE_CHECKING

---

## 七、总结

| 类别 | 发现数量 | 可清理 | 新增功能 | 保持现状 | 需重构 |
|------|----------|--------|----------|----------|--------|
| TYPE_CHECKING | 4 | 2 | 0 | 1 | **1** ⭐ |
| 向后兼容代码 | 7 | 5 | 0 | 1 | **1** ⭐ |
| DI 原则 | 1 | 0 | 0 | 0 | **1** ⭐ |
| 通知功能 | 1 | 0 | **1** ⭐ | 0 | 0 |
| TODO 注释 | 2 | 2 | 0 | 0 | 0 |
| 空 `__all__` | 2 | 2 | 0 | 0 | 0 |
| **总计** | **17** | **11** | **1** | **1** | **3** |

**项目代码质量**: ⭐⭐⭐⭐⭐ 优秀

- ✅ 无被注释掉的死代码
- ✅ 无未使用的导入
- ✅ TYPE_CHECKING 使用优化（webhook.py 移除）
- ✅ 向后兼容代码清理后更清晰
- ⭐ **新增：TelegramSender 直接集成 Telegram Bot API**
- ⭐ **用户决策：统一 TushareAdapter 架构，消除 TYPE_CHECKING**
- ⭐ **用户决策：移除 DataHub.close()，符合 DI 原则**

---

## 八、验证步骤

执行清理前：
```bash
# 1. 确保当前代码健康
pixi run -e dev ci

# 2. 搜索引用位置
pixi run -e dev python .claude/scripts/lsp_pyright.py refs <file> <line> <col>

# 3. 清理后验证
pixi run -e dev test --unit
pixi run -e dev type
```

---

**创建时间**: 2026-01-23
**分支**: feature/dishka-migration
**状态**: ✅ 分析完成，待执行
