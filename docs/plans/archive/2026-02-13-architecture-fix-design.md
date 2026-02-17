# 架构修复计划

**日期**: 2026-02-13
**状态**: Completed
**关联审计**: [2026-02-13-architecture-audit.md](../reviews/2026-02-13-architecture-audit.md)

---

## 执行摘要

基于代码审查和架构分析，本计划识别出 **2 个 Blocker**、**4 个 High**、**4 个 Medium** 优先级问题。

**核心风险**：
- ENG-001: `futures_position` 数据写入静默丢失
- ENG-004: 生产环境自动删表存在数据丢失风险
- ARCH-001: 跨层依赖侵蚀架构边界

**总工时估算**: 约 3 小时

---

## P0: 必须立即修复

### ENG-001: futures_position 数据丢写

**严重度**: 🔴 Blocker
**类别**: 数据完整性
**位置**: [data_writer.py:457-482](apps/port/src/ditto_port/services/ingestion/data_writer.py#L457-L482)

#### 问题分析

```
┌─────────────────────────────────────────────────────────────┐
│                    数据写入流程                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  write_data("futures_position", df, ...)                    │
│       │                                                     │
│       ▼                                                     │
│  handlers[Dataset.FUTURES_POSITION]()                       │
│       │                                                     │
│       ▼                                                     │
│  _write_capital(dataset, dataset_enum, df, year)            │
│       │                                                     │
│       ▼                                                     │
│  capital_dataset = "futures_position"  ← cast() 不验证值    │
│       │                                                     │
│       ▼                                                     │
│  if/elif/else 匹配                                          │
│       ├── "valuation_metrics" → save_valuation_metrics() ✅ │
│       ├── "margin_trading" → save_margin_trading() ✅       │
│       ├── "pledge_ratio" → save_pledge_ratio() ✅           │
│       └── else → records_written = 0 ❌ ← futures 走这里    │
│                                                             │
│  结果：数据被静默丢弃，返回 rows_written=0                   │
└─────────────────────────────────────────────────────────────┘
```

**根因代码**:

```python
# data_writer.py:464-476
def _write_capital(self, ...):
    capital_dataset = cast(
        Literal["valuation_metrics", "margin_trading", "pledge_ratio"],  # ← 缺少 futures_position
        dataset_enum.value,
    )
    if capital_dataset == "valuation_metrics":
        records_written = self._capital_service.save_valuation_metrics(df)
    elif capital_dataset == "margin_trading":
        records_written = self._capital_service.save_margin_trading(df)
    elif capital_dataset == "pledge_ratio":
        records_written = self._capital_service.save_pledge_ratio(df)
    else:
        records_written = 0  # ← futures_position 走到这里，静默丢失
```

**验证**: `CapitalService.save_futures()` 方法已存在且正常工作。

```python
# capital_service.py:210-221
def save_futures(self, df: pl.DataFrame) -> int:
    """Save futures data."""
    return self._futures_writer.write(df)
```

#### 修复方案

```python
def _write_capital(self, ...):
    capital_dataset = cast(
        Literal["valuation_metrics", "margin_trading", "pledge_ratio", "futures_position"],
        dataset_enum.value,
    )
    if capital_dataset == "valuation_metrics":
        records_written = self._capital_service.save_valuation_metrics(df)
    elif capital_dataset == "margin_trading":
        records_written = self._capital_service.save_margin_trading(df)
    elif capital_dataset == "pledge_ratio":
        records_written = self._capital_service.save_pledge_ratio(df)
    elif capital_dataset == "futures_position":
        records_written = self._capital_service.save_futures(df)  # ← 新增
    else:
        records_written = 0
```

#### 改动清单

| 文件 | 改动 |
|------|------|
| `data_writer.py` | 添加 `futures_position` 分支，更新 Literal 类型 |
| `test_data_writer_unit.py` | 新增 futures_position 写入测试 |

#### 风险评估

| 维度 | 评估 |
|------|------|
| 改动范围 | 单文件 |
| 风险 | 低 |
| 回滚 | 简单（单文件回退） |
| 工时 | 15 分钟 |

---

### ARCH-004: 主应用路由未挂载

**严重度**: 🟠 High（从 Blocker 降级）
**类别**: 功能可达性
**位置**: [main.py:170-173](apps/port/src/ditto_port/main.py#L170-L173)

#### 问题分析

```python
# main.py - 当前挂载
app.include_router(market.router, prefix="/api/v1")
app.include_router(metadata.router, prefix="/api/v1")
app.include_router(ingestion.router, prefix="/api/v1")
app.include_router(portfolio.router, prefix="/api/v1")

# routes/__init__.py - 存在但未挂载
from ditto_port.api.routes import (
    capital,      # ← 未挂载
    fundamental,  # ← 未挂载
    macro,        # ← 未挂载
    ...
)
```

**决策**: 立即挂载（代码和测试已存在）

#### 修复方案

```python
# main.py
from ditto_port.api.routes import (
    capital,
    fundamental,
    ingestion,
    macro,
    market,
    metadata,
    portfolio,
)

# 挂载所有业务路由
app.include_router(market.router, prefix="/api/v1")
app.include_router(metadata.router, prefix="/api/v1")
app.include_router(ingestion.router, prefix="/api/v1")
app.include_router(portfolio.router, prefix="/api/v1")
app.include_router(capital.router, prefix="/api/v1")       # ← 新增
app.include_router(fundamental.router, prefix="/api/v1")   # ← 新增
app.include_router(macro.router, prefix="/api/v1")         # ← 新增
```

#### 改动清单

| 文件 | 改动 |
|------|------|
| `main.py` | 添加 3 个路由挂载 |
| `test_main_routes_integration.py` | 新增装配级测试 |

#### 风险评估

| 维度 | 评估 |
|------|------|
| 改动范围 | 单文件 |
| 风险 | 低 |
| 回滚 | 撤销 include_router |
| 工时 | 10 分钟 |

---

### ARCH-001: 跨层依赖例外

**严重度**: 🟡 Medium
**类别**: 架构边界
**位置**: [service.py:9](apps/port/src/ditto_port/services/ingestion/quality/service.py#L9), [.importlinter:96](.importlinter#L96)

#### 问题分析

```python
# service.py (Port 层)
from ditto_datahub.stores.runtime.quality import QuarantineWriter  # ← 直接依赖 Store

class QualityService:
    def __init__(
        self,
        engine: QualityEngine,
        quarantine_writer: QuarantineWriter | None = None,  # ← 直接依赖 Store 实现
    ) -> None:
        ...
```

**架构违规**:
- `ditto_port.services` 直接依赖 `ditto_datahub.stores`
- 违反 `Port → DataHub Service → DataHub Store` 分层原则
- 通过 `.importlinter:96` 的 `ignore_imports` 绕过检查

**已有解决方案**: `QualityRecordService` 已封装 `QuarantineWriter`

```python
# quality_record_service.py (DataHub 层)
class QualityRecordService:
    def save_failed_data(
        self,
        dataset: str,
        rule_id: str,
        severity: str,
        failed_data: pl.DataFrame,
        trade_date: str | None = None,
    ) -> int:
        return self._quarantine_writer.save_failed_data(...)  # ← 封装 Store
```

**关键发现**: `QualityRecordService.save_failed_data()` 签名与 `QuarantineWriter.save_failed_data()` 完全一致！

#### 修复方案

```python
# Before
from ditto_datahub.stores.runtime.quality import QuarantineWriter

class QualityService:
    def __init__(
        self,
        engine: QualityEngine,
        quarantine_writer: QuarantineWriter | None = None
    ) -> None:
        self._quarantine_writer = quarantine_writer

# After
from ditto_datahub.services import QualityRecordService

class QualityService:
    def __init__(
        self,
        engine: QualityEngine,
        quarantine_service: QualityRecordService | None = None
    ) -> None:
        self._quarantine_writer = quarantine_service  # 内部变量名保持不变
```

#### 改动清单

| 文件 | 改动 |
|------|------|
| `service.py` | import 改为 QualityRecordService，类型注解更新 |
| `.importlinter` | 移除 ignore 规则 |

#### 风险评估

| 维度 | 评估 |
|------|------|
| 改动范围 | 2 文件 |
| 风险 | 零（接口完全兼容） |
| 回滚 | 简单 |
| 工时 | 15 分钟 |

---

## P1: 应该修复

### ENG-003: Tushare Client 多实例

**严重度**: 🟡 Medium
**类别**: 资源管理 / 限流准确性
**位置**: [tushare_source.py:47-53](packages/datahub/src/ditto_datahub/sources/tushare/tushare_source.py#L47-L53)

#### 问题分析

```
┌─────────────────────────────────────────────────────────────┐
│              当前架构：多 Client 多限流器                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TushareSource                                              │
│       │                                                     │
│       ├── CalendarAdapter ──► TushareClient ──► Limiter #1  │
│       ├── StockAdapter ─────► TushareClient ──► Limiter #2  │
│       ├── ETFAdapter ───────► TushareClient ──► Limiter #3  │
│       ├── IndexAdapter ─────► TushareClient ──► Limiter #4  │
│       ├── CapitalAdapter ───► TushareClient ──► Limiter #5  │
│       ├── FundamentalAdap ──► TushareClient ──► Limiter #6  │
│       └── MacroAdapter ─────► TushareClient ──► Limiter #7  │
│                                                             │
│  问题：7 个独立限流器 = 实际请求可能是限额的 7 倍！          │
└─────────────────────────────────────────────────────────────┘
```

**Tushare 限流规则**:

| 账户类型 | 每分钟限制 | 并发限制 |
|---------|-----------|---------|
| 免费 | 200 次/分钟 | 单线程 |
| 基础 | 500 次/分钟 | 单线程 |
| 高级 | 2000 次/分钟 | 3 并发 |

**关键洞察**: Tushare 限流是 **按账户**，不是按客户端实例。

**影响评估**:

| 场景 | 风险 |
|------|------|
| 单用户 CLI | 低（串行执行，不易触发） |
| 并发摄入 | 高（多任务并行，易超限） |
| 生产环境 | 高（被限流会导致任务失败） |

#### 修复方案

```python
# tushare_source.py
class TushareSource(DataSource):
    def __init__(
        self,
        settings: DataSourceSettings,
        token: str | None = None,
    ) -> None:
        # 创建单例 client
        client = TushareClient(token=token, settings=settings)

        # 注入所有 adapter（BaseTushareAdapter 已支持 _client 参数）
        self._calendar = CalendarTushareAdapter(_client=client)
        self._stock = StockTushareAdapter(_client=client)
        self._etf = ETFTushareAdapter(_client=client)
        self._index = IndexTushareAdapter(_client=client)
        self._capital = CapitalTushareAdapter(_client=client)
        self._fundamental = FundamentalTushareAdapter(_client=client)
        self._macro = MacroTushareAdapter(_client=client)

        self._client = client  # 保留引用用于关闭

    def close(self) -> None:
        """释放资源"""
        self._client.close()
```

```python
# sources.py (Provider)
@provide
def tushare_source(
    settings: DataSourceSettings,
) -> Iterator[TushareSource]:
    source = TushareSource(settings=settings)
    yield source
    source.close()  # ← 生命周期结束时会自动调用
```

#### 改动清单

| 文件 | 改动 |
|------|------|
| `tushare_source.py` | 创建单例 client，注入 adapter，新增 close() |
| `sources.py` | Provider 改为 Iterator，添加 yield/finally |

#### 风险评估

| 维度 | 评估 |
|------|------|
| 改动范围 | 2 文件 |
| 风险 | 中（需验证所有 adapter 的 _client 注入路径） |
| 回滚 | 保留旧构造路径切换 |
| 工时 | 30 分钟 |

---

### ENG-004: 生产环境自动删表

**严重度**: 🟠 High
**类别**: 数据安全
**位置**: [sqlite_pool.py:174-175](packages/infra/src/ditto_infra/foundation/db/sqlite_pool.py#L174-L175)

#### 问题分析

```python
# sqlite_pool.py
if self._needs_schema_rebuild(conn):
    self._reset_all_user_tables(conn)  # ← 自动删表
```

**量化系统特殊性**: 对数据完整性要求极高，任何误删都会影响回测和实盘。

#### 修复方案

1. **短期**: 添加环境变量开关 `DITTO_ALLOW_SCHEMA_REBUILD=1`
2. **默认行为**: 检测到 legacy schema 时 fail-fast，而非自动删除
3. **删除时间线**: 2026-07-31 后移除自动删表路径

```python
# sqlite_pool.py
def _handle_legacy_schema(self, conn: sqlite3.Connection) -> None:
    if self._needs_schema_rebuild(conn):
        if os.getenv("DITTO_ALLOW_SCHEMA_REBUILD") == "1":
            logger.warning("Legacy schema detected, rebuilding with explicit permission")
            self._reset_all_user_tables(conn)
        else:
            raise LegacySchemaError(
                "Legacy schema detected. Set DITTO_ALLOW_SCHEMA_REBUILD=1 to allow rebuild, "
                "or manually migrate the database."
            )
```

#### 改动清单

| 文件 | 改动 |
|------|------|
| `sqlite_pool.py` | 添加环境变量开关，fail-fast 逻辑 |
| `test_sqlite_pool_unit.py` | 新增开关行为测试 |

#### 风险评估

| 维度 | 评估 |
|------|------|
| 改动范围 | 单文件 |
| 风险 | 中（旧库可能因 schema 不兼容启动失败） |
| 回滚 | 临时开启兼容开关恢复旧行为 |
| 工时 | 30 分钟 |

---

### ENG-002: 测试盲区

**严重度**: 🟡 Medium
**类别**: 测试质量
**位置**: `apps/port/tests/`

#### 问题分析

现有"集成"测试是路由局部装配，无法发现 main.py 漏挂路由这类装配级错误。

```python
# test_capital_router_unit.py
app = FastAPI()  # ← 新建 app，而非使用 ditto_port.main.app
app.include_router(router, prefix="/api/v1")
```

#### 修复方案

新增 `test_main_routes_integration.py`，直接验证 `ditto_port.main.app` 的路由表：

```python
def test_all_routes_registered():
    """验证所有 routes/__init__.py 导出的路由都已挂载"""
    from ditto_port.api.routes import __all__ as expected_routes
    from ditto_port.main import app

    registered = {r.name for r in app.routes if hasattr(r, 'name')}

    for route_name in expected_routes:
        assert route_name in registered, f"Route {route_name} not registered"
```

#### 改动清单

| 文件 | 改动 |
|------|------|
| `test_main_routes_integration.py` | 新增 |

#### 风险评估

| 维度 | 评估 |
|------|------|
| 改动范围 | 新增测试文件 |
| 风险 | 零 |
| 工时 | 30 分钟 |

---

### ARCH-003: async 阻塞

**严重度**: 🟡 Medium
**类别**: 性能
**位置**: [market.py](apps/port/src/ditto_port/api/routes/market.py)

#### 问题分析

```python
@router.post("/bars")
async def post_bars(...):
    df = service.find_bars(service_query)  # ← 同步调用阻塞事件循环
```

#### 修复方案

采用方案 1：将路由改为 `def`（FastAPI 自动线程池执行）

```python
# Before
@router.post("/bars")
async def post_bars(...):

# After
@router.post("/bars")
def post_bars(...):  # FastAPI 自动使用线程池
```

#### 风险评估

| 维度 | 评估 |
|------|------|
| 改动范围 | 路由文件 |
| 风险 | 中 |
| 回滚 | 路由逐文件回退 |
| 工时 | 20 分钟 |

---

## P2: 可延后

### ENG-005: 环境变量统一

**严重度**: Low
**类别**: 配置一致性
**建议**: 统一 `DITTO_ENV`，`ENVIRONMENT` 作为兼容别名并打 warning

### ENG-006: 日志脱敏

**严重度**: Low
**类别**: 安全合规
**建议**: 日志字段脱敏（hash/last4）+ 按环境禁用测试端点

### ENG-007: PIT 占位字段

**严重度**: Low
**类别**: 数据质量
**建议**: 缺 `report_date/knowledge_date` 时改为 null + blocked

### ENG-008: 配置漂移清理

**严重度**: Low
**类别**: 代码治理
**建议**: 抽象重复逻辑，清理残留路径

---

## 执行计划

### Phase 1: P0 修复（本周）

| 顺序 | Issue | 工时 | 风险 |
|------|-------|------|------|
| 1 | ENG-001 futures_position 丢写 | 15min | 低 |
| 2 | ARCH-004 路由挂载 | 10min | 低 |
| 3 | ARCH-001 依赖倒置 | 15min | 零 |
| 4 | ENG-003 Tushare 单例化 | 30min | 中 |

### Phase 2: P1 修复（下周）

| 顺序 | Issue | 工时 | 风险 |
|------|-------|------|------|
| 5 | ENG-004 删表开关 | 30min | 中 |
| 6 | ENG-002 装配测试 | 30min | 零 |
| 7 | ARCH-003 async 阻塞 | 20min | 中 |

### Phase 3: P2 优化（迭代中）

按需处理，不阻塞主流程。

---

## 验证命令

```bash
# 完整检查
pixi run -e dev check

# 架构边界检查
pixi run -e dev arch-check

# 测试覆盖率
pixi run -e dev test --unit --cov --cov-report=html

# 类型检查
pixi run -e dev type
```

---

## 风险矩阵

| Issue | 改动范围 | 风险等级 | 回滚难度 |
|-------|---------|---------|---------|
| ENG-001 | 单文件 | 低 | 简单 |
| ARCH-004 | 单文件 | 低 | 简单 |
| ARCH-001 | 2 文件 | 零 | 简单 |
| ENG-003 | 2 文件 | 中 | 中等 |
| ENG-004 | 单文件 | 中 | 简单 |
| ENG-002 | 新增文件 | 零 | N/A |
| ARCH-003 | 多文件 | 中 | 中等 |

---

## 附录：验证清单

- [x] ENG-001: futures_position 写入测试通过
- [x] ARCH-004: 3 个路由可访问
- [x] ARCH-001: import-linter 无例外
- [x] ENG-003: 单例行为测试通过
- [x] ENG-004: 开关行为测试通过
- [x] ENG-002: 装配测试通过
- [x] ARCH-003: 性能测试无退化
