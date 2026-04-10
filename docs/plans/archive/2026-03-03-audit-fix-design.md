# 架构审计问题修复设计

> 基于 2026-03-02 Architecture & Engineering Audit 的修复计划

## 概述

本文档定义了剩余审计问题的修复方案，按优先级排序执行。

### 问题状态总览

| ID | Severity | 问题 | 状态 |
|---|---|---|---|
| ENG-001 | High | 异常因果链丢失 | 待修复 |
| ARCH-002 | High | CapitalProvider 未使用 Ports 模式 | 待修复 |
| ENG-004 | Medium | 调试路由隔离不完整 | 待修复 |

---

## PR-1: 修复异常因果链丢失 (ENG-001)

### 问题描述

`coordinator.py` 中 3 处 `raise original_error from None` 主动抹除异常因果链，导致排障时丢失 root-cause 堆栈。

### 修改位置

- `apps/port/src/ditto_port/services/ingestion/coordinator.py:711`
- `apps/port/src/ditto_port/services/ingestion/coordinator.py:719`
- `apps/port/src/ditto_port/services/ingestion/coordinator.py:736`

### 修改方案

```python
# 当前代码（第 711 行）
except Exception as fetch_error:
    logger.error(...)
    raise original_error from None  # ❌ 丢失因果链

# 修改后
except Exception as fetch_error:
    logger.error(...)
    raise original_error from fetch_error  # ✅ 保留因果链
```

同样修改第 719 行（`fetch_error`）和第 736 行（`register_error`）。

### 测试验证

```python
# tests/unit/services/ingestion/test_coordinator_exception_chain.py

def test_exception_chain_preserved_on_fetch_error():
    """验证 fetch 失败时异常因果链被保留。"""
    # ... 测试 __cause__ 属性

def test_exception_chain_preserved_on_register_error():
    """验证 register 失败时异常因果链被保留。"""
    # ... 测试 __cause__ 属性
```

### 风险评估

- **风险**: 低（仅异常语义增强，行为不变）
- **回滚**: 单文件回滚

---

## PR-2: CapitalProvider 使用 Ports 模式 (ARCH-002)

### 问题描述

`CapitalService` 构造函数直接注入 8 个 Reader/Writer 参数，与 `MarketService`/`FundamentalService` 的 Ports 模式不一致。

### 修改范围

1. `packages/data/src/ditto_data/services/ports.py` - 新增 `CapitalReadPorts`/`CapitalWritePorts`
2. `packages/data/src/ditto_data/services/capital_service.py` - 重构为使用 Ports
3. `apps/port/src/ditto_port/registry/datahub/capital.py` - 使用 Ports 组装

### 设计方案

#### Step 1: 新增 CapitalPorts 定义

```python
# packages/data/src/ditto_data/services/ports.py

@dataclass
class CapitalReadPorts:
    """
    Capital 域读取端口。

    包含所有 Capital 域的 Reader 依赖，用于 CapitalService 的查询操作。

    Attributes:
        margin_trading: 融资融券读取器.
        pledge_ratio: 质押比例读取器.
        valuation_metrics: 估值指标读取器.
        index_composition: 指数成分读取器.
    """

    margin_trading: MarginTradingReader
    pledge_ratio: PledgeRatioReader
    valuation_metrics: ValuationMetricsReader
    index_composition: IndexCompositionReader


@dataclass
class CapitalWritePorts:
    """
    Capital 域写入端口。

    包含所有 Capital 域的 Writer 依赖，用于 CapitalService 的写入操作。

    Attributes:
        margin_trading: 融资融券写入器.
        pledge_ratio: 质押比例写入器.
        valuation_metrics: 估值指标写入器.
        index_composition: 指数成分写入器.
    """

    margin_trading: MarginTradingWriter
    pledge_ratio: PledgeRatioWriter
    valuation_metrics: ValuationMetricsWriter
    index_composition: IndexCompositionWriter
```

#### Step 2: 重构 CapitalService

```python
# packages/data/src/ditto_data/services/capital_service.py

from ditto_data.services.ports import CapitalReadPorts, CapitalWritePorts


class CapitalService:
    """Capital domain unified service with CQRS Ports pattern."""

    def __init__(
        self,
        read_ports: CapitalReadPorts,
        write_ports: CapitalWritePorts,
    ) -> None:
        """
        Initialize CapitalService with CQRS Ports.

        Args:
            read_ports: Capital 域读取端口.
            write_ports: Capital 域写入端口.
        """
        self._read_ports = read_ports
        self._write_ports = write_ports

        logger.debug(
            "CapitalService initialized with CQRS Ports",
            event="capital_service_init_complete",
        )
```

#### Step 3: 更新 CapitalProvider

```python
# apps/port/src/ditto_port/registry/datahub/capital.py

from ditto_data.services.ports import CapitalReadPorts, CapitalWritePorts


class CapitalProvider(Provider):
    # ... 现有 reader/writer provider 方法保持不变 ...

    # ========================================================================
    # Capital Ports
    # ========================================================================

    @provide
    def capital_read_ports(
        self,
        margin_trading_reader: MarginTradingReader,
        pledge_ratio_reader: PledgeRatioReader,
        valuation_metrics_reader: ValuationMetricsReader,
        index_composition_reader: IndexCompositionReader,
    ) -> CapitalReadPorts:
        """Capital 域读取端口."""
        return CapitalReadPorts(
            margin_trading=margin_trading_reader,
            pledge_ratio=pledge_ratio_reader,
            valuation_metrics=valuation_metrics_reader,
            index_composition=index_composition_reader,
        )

    @provide
    def capital_write_ports(
        self,
        margin_trading_writer: MarginTradingWriter,
        pledge_ratio_writer: PledgeRatioWriter,
        valuation_metrics_writer: ValuationMetricsWriter,
        index_composition_writer: IndexCompositionWriter,
    ) -> CapitalWritePorts:
        """Capital 域写入端口."""
        return CapitalWritePorts(
            margin_trading=margin_trading_writer,
            pledge_ratio=pledge_ratio_writer,
            valuation_metrics=valuation_metrics_writer,
            index_composition=index_composition_writer,
        )

    # ========================================================================
    # Capital Service
    # ========================================================================

    @provide
    def capital_service(
        self,
        read_ports: CapitalReadPorts,
        write_ports: CapitalWritePorts,
    ) -> CapitalService:
        """Capital domain unified service."""
        return CapitalService(
            read_ports=read_ports,
            write_ports=write_ports,
        )
```

### 迁移策略

1. **内部属性访问**: 将 `self._margin_trading_reader` 改为 `self._read_ports.margin_trading`
2. **Writer 访问**: 将 `self._margin_trading_writer` 改为 `self._write_ports.margin_trading`

### 测试验证

更新现有单测，验证 Ports 注入正确工作。

### 风险评估

- **风险**: 中（涉及 DI 结构变更）
- **回滚**: 三个文件回滚

---

## PR-3: 调试路由隔离 (ENG-004)

### 问题描述

`/api/v1/logs/test` 路由在生产环境仍然注册，仅在 handler 内返回 404。存在安全面扩大问题。

### 修改位置

- `apps/port/src/ditto_port/main.py`

### 当前代码

```python
# main.py - 路由始终注册
@app.get("/api/v1/logs/test")
async def generate_test_logs() -> dict[str, str]:
    env = get_environment()
    if env.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    # ...
```

### 修改方案

```python
# main.py

# 方案 A: 条件注册（推荐）
def create_app() -> FastAPI:
    app = FastAPI(...)

    # ... 其他路由注册 ...

    # 调试路由仅在非生产环境注册
    env = get_environment()
    if not env.is_production:
        from ditto_port.api.routes.debug import debug_router

        app.include_router(debug_router, prefix="/api/v1", tags=["debug"])

    return app


# 新建 apps/port/src/ditto_port/api/routes/debug.py
from fastapi import APIRouter

debug_router = APIRouter()


@debug_router.get("/logs/test")
async def generate_test_logs() -> dict[str, str]:
    """测试日志记录功能."""
    logger.info("Test info log", test_data="example")
    logger.warning("Test warning log", test_data="example")
    logger.error("Test error log", test_data="example")
    return {"message": "Test logs generated"}
```

### 风险评估

- **风险**: 低（仅影响调试功能）
- **回滚**: 双文件回滚

---

## 执行顺序

```
Phase 1: P0 必须修
├── PR-1: ENG-001 异常因果链丢失 (30 min)
│   └── 修改 coordinator.py (3 行)
│   └── 新增单测验证
│
├── PR-2: ARCH-002 Capital Ports 模式 (2-3 hours)
│   ├── Step 1: 新增 CapitalReadPorts/WritePorts
│   ├── Step 2: 重构 CapitalService
│   └── Step 3: 更新 CapitalProvider
│
└── PR-3: ENG-004 调试路由隔离 (30 min)
    ├── Step 1: 新建 debug.py 路由模块
    └── Step 2: 条件注册路由
```

## 验收标准

- [ ] `pixi run -e dev check` 全部通过
- [ ] PR-1: 异常因果链测试通过
- [ ] PR-2: CapitalService 构造函数参数 ≤ 3
- [ ] PR-3: 生产环境 `/api/v1/logs/test` 返回 404（路由不存在）

## 参考

- [2026-03-02 Architecture Audit Report](../reviews/2026-03-02-architecture-audit.md)
- [CLAUDE.md](../../CLAUDE.md)
