# 架构审计修复方案

> 基于 2026-03-02 架构审计报告的修复实施计划

## 概述

本文档定义了架构审计报告中识别问题的修复方案，按优先级分为 P0/P1/P2 三个阶段。

### 验证状态

| ID | 问题 | 状态 | 备注 |
|---|---|---|---|
| ARCH-001 | adapter 常量耦合 | ✅ 确认 | coordinator.py:26-30 直接导入 adapter 常量 |
| ARCH-002 | main.py 职责过载 | ⚠️ 跳过 | 323 行结构已清晰，无需拆分 |
| ARCH-003 | httpx 异常外泄 | ✅ 确认 | coordinator.py:401, 759 捕获 httpx 异常 |
| ENG-001 | 死代码 | ✅ 确认 | `_raise_fred_not_configured` 无调用 |
| ENG-002 | 过宽异常捕获 | ✅ 确认 | 11 处 `except Exception` |
| ENG-003 | keyring 导入方式 | ⚠️ 轻微 | 模块级 try-import，P2 处理 |
| ENG-004 | provider 样板重复 | ✅ 确认 | reader/writer 样板高度重复 |
| ENG-005 | 超长参数列表 | ✅ 确认 | market_service: 22 参数，fundamental_service: 14 参数 |
| ENG-006 | 审计自动化门禁 | ⚠️ 新增 | P2 处理 |

---

## P0：必须修（3 个 PR）

### PR-1：删除死代码（ENG-001）

**风险**：低

**改动范围**：
- 删除 `apps/port/src/ditto_port/services/ingestion/coordinator.py` 中的 `_raise_fred_not_configured` 方法（第 135-144 行）

**验证**：
```bash
pixi run -e dev check
```

---

### PR-2：异常分层（ENG-002 + ARCH-003）

**风险**：中

**目标**：建立清晰的异常层次，消除 `except Exception` 和 `httpx` 异常外泄。

**异常层次设计**：

```
DittoPortError (基础类)
├── DataSourceError (数据源相关)
│   ├── NetworkError (网络超时/连接失败)
│   ├── AuthError (认证失败)
│   └── DataValidationError (数据校验失败)
└── PersistenceError (持久化相关)
    └── WriteError (写入失败)
```

**文件改动**：

| 文件 | 改动 |
|---|---|
| `ditto_port/errors.py` (新) | 定义异常层次 |
| `coordinator.py` | 替换 11 处 `except Exception` + 2 处 `httpx.*` |

**异常映射**：
```python
# coordinator.py 中
except httpx.NetworkError as e:
    raise NetworkError(source=self._source_name, cause=e)
except httpx.TimeoutException as e:
    raise NetworkError(source=self._source_name, cause=e, timeout=True)
```

**测试策略**：
- 单元测试：验证异常映射正确
- 集成测试：验证错误日志包含完整上下文

---

### PR-3：常量迁移（ARCH-001）

**风险**：中

**目标**：将 adapter 常量移到 `datahub.models`，消除 port 对 `sources.adapters` 的直接依赖。

**迁移方案**：

| 常量 | 原位置 | 新位置 |
|---|---|---|
| `VIX_CODE_TO_INSTRUMENT_ID` | `sources.fred.adapters.commodity` | `datahub.models.source_codes` |
| `FX_CODE_TO_INSTRUMENT_ID` | `sources.tushare.adapters.fx` | `datahub.models.source_codes` |
| `METAL_CODE_ALIASES` | `sources.tushare.adapters.metal` | `datahub.models.source_codes` |

**文件改动**：

| 文件 | 改动 |
|---|---|---|
| `datahub/models/source_codes.py` (新) | 定义 3 个常量 |
| `datahub/models/__init__.py` | 导出常量 |
| `fred/adapters/commodity.py` | 从新位置 re-export（兼容） |
| `tushare/adapters/fx.py` | 从新位置 re-export（兼容） |
| `tushare/adapters/metal.py` | 从新位置 re-export（兼容） |
| `coordinator.py` | 改为从 `ditto_data.models` 导入 |

---

## P1：应该修（2 个 PR）

### PR-4：参数对象化（ENG-005）

**风险**：中

**目标**：将超长参数列表（22/14 个）拆分为结构化的 Ports 对象，消除 `# noqa: PLR0913`。

**Ports 对象设计**：

```python
# datahub/services/ports.py (新)
from dataclasses import dataclass

@dataclass
class MarketReadPorts:
    """Market 域读取端口。"""
    stock_bars: StockBarsReader
    stock_status: StockStatusReader
    stock_adj: StockAdjFactorReader
    etf_bars: EtfBarsReader
    etf_status: EtfStatusReader
    etf_adj: EtfAdjFactorReader
    etf_nav: EtfNavReader
    index_bars: IndexBarsReader
    index_constituent: IndexConstituentReader
    fx_bars: FxBarsReader
    commodity_bars: CommodityBarsReader
    instrument: InstrumentReader

@dataclass
class MarketWritePorts:
    """Market 域写入端口。"""
    stock_bars: StockBarsWriter
    stock_status: StockStatusWriter
    stock_adj: StockAdjFactorWriter
    etf_bars: EtfBarsWriter
    etf_status: EtfStatusWriter
    etf_adj: EtfAdjFactorWriter
    etf_nav: EtfNavWriter
    index_bars: IndexBarsWriter
    index_constituent: IndexConstituentWriter
    fx_bars: FxBarsWriter
    commodity_bars: CommodityBarsWriter
```

**Service 构造简化**：
```python
# 修改前（22 参数）
def __init__(self, stock_bars_reader, stock_bars_writer, ...): ...

# 修改后（3 参数）
def __init__(self, read_ports: MarketReadPorts, write_ports: MarketWritePorts, file_lock: FileLockManager): ...
```

**适用服务**：
- `MarketService`（22 → 3 参数）
- `FundamentalService`（14 → 3 参数）
- `CapitalService`（8 参数，可选优化）

---

### PR-5：Provider 样板抽象（ENG-004）

**风险**：中

**目标**：减少 reader/writer 样板代码，保持显式 provider 名称（便于 DI 追踪）。

**工厂函数设计（Python 3.12+ 语法）**：

```python
# registry/datahub/builders.py (新)
from collections.abc import Callable
from pathlib import Path

from ditto_data.stores.sqlite_client import SQLiteClient


def sqlite_store_pair[R, W](
    reader_cls: type[R],
    writer_cls: type[W],
) -> tuple[Callable[[SQLiteClient], R], Callable[[SQLiteClient], W]]:
    """创建 SQLite reader/writer 工厂。"""
    def make_reader(client: SQLiteClient) -> R:
        return reader_cls(client)

    def make_writer(client: SQLiteClient) -> W:
        return writer_cls(client)

    return make_reader, make_writer


def parquet_store_pair[R, W](
    reader_cls: type[R],
    writer_cls: type[W],
    subdir: str | None = None,
) -> tuple[Callable[[Path], R], Callable[[Path], W]]:
    """创建 Parquet reader/writer 工厂。"""
    def make_reader(data_root: Path) -> R:
        path = data_root / subdir if subdir else data_root
        return reader_cls(path)

    def make_writer(data_root: Path) -> W:
        path = data_root / subdir if subdir else data_root
        return writer_cls(path)

    return make_reader, make_writer
```

**Provider 简化示例**：

```python
# fundamental.py 使用工厂
_balance_r, _balance_w = sqlite_store_pair(BalanceSheetReader, BalanceSheetWriter)
_income_r, _income_w = sqlite_store_pair(IncomeStatementReader, IncomeStatementWriter)

class FundamentalProvider(Provider):
    @provide
    def balance_sheet_reader(self, client: SQLiteClient) -> BalanceSheetReader:
        return _balance_r(client)

    @provide
    def balance_sheet_writer(self, client: SQLiteClient) -> BalanceSheetWriter:
        return _balance_w(client)
```

---

## P2：可优化（2 个 PR）

### PR-6：Keyring 函数化（ENG-003）

**风险**：低

**目标**：将模块级 try-import 改为函数内延迟加载，运行时可控降级并记录日志。

**修改方案**：

```python
# 修改前（config.py 模块级）
_keyring: Any = None
keyring_available = False
try:
    import keyring as _keyring_module
    _keyring = _keyring_module
    keyring_available = True
except ImportError:
    pass

# 修改后（函数内延迟加载）
def _load_keyring_secret(service: str, key: str) -> str | None:
    """从 keyring 加载密钥（运行时降级）。"""
    try:
        import keyring
    except ImportError:
        logger.debug("keyring not available, skipping", service=service)
        return None

    try:
        return keyring.get_password(service, key)
    except Exception as e:
        logger.warning("keyring read failed", service=service, error=str(e))
        return None
```

---

### PR-7：CI 审计门禁（ENG-006）

**风险**：低

**目标**：在 CI 中增加架构审计基线 job，确保新代码符合分层规范。

**CI 配置**：

```yaml
# .github/workflows/ci.yml (新增 job)
audit:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: prefix-dev/setup-pixi@v0.8.0
    - name: Architecture check
      run: pixi run -e dev arch-check
    - name: Type check
      run: pixi run -e dev type --all
    - name: Fast tests
      run: pixi run -e dev test --fast
```

---

## 实施顺序

```
PR-1 (死代码) ─────────────────────────────────────────┐
                                                        │
PR-2 (异常分层) ───────────────────────────────────────┼─→ P0 完成
                                                        │
PR-3 (常量迁移) ───────────────────────────────────────┘

PR-4 (参数对象化) ─────────────────────────────────────┐
                                                        │
PR-5 (样板抽象) ───────────────────────────────────────┴─→ P1 完成

PR-6 (keyring) ────────────────────────────────────────┐
                                                        │
PR-7 (CI 门禁) ────────────────────────────────────────┴─→ P2 完成
```

**依赖关系**：无强依赖，各 PR 可独立实施。

---

## 回滚策略

每个 PR 保持 API 兼容（保留旧调用路径一版，记录 deprecate），出现线上问题可逐 PR 回滚。

---

## 验收标准

- [x] 所有 PR 通过 `pixi run -e dev check`
- [x] arch-check 保持 6 个约束全部 KEPT
- [x] 无新增 `# noqa` 或 `# type: ignore`

## 实施状态

> **状态**: 🟡 Phase 1 已完成，Phase 2 进行中 (2026-03-03)

### 已完成（Phase 1）

| PR | 描述 | 状态 |
|----|------|------|
| PR-1 | 删除死代码 `_raise_fred_not_configured` | ✅ 完成 |
| PR-2 | 异常分层 - 创建 `ditto_port/errors.py` | ✅ 完成 |
| PR-3 | 常量迁移到 `datahub.models.source_codes`（coordinator.py） | ✅ 完成 |
| PR-4 | 参数对象化 - `MarketReadPorts/WritePorts` | ✅ 完成 |
| PR-5 | Provider 样板抽象 - `sqlite_store_pair` | ✅ 完成 |
| PR-6 | Keyring 函数化延迟加载 | ✅ 完成 |
| PR-7 | CI 审计门禁配置 | ✅ 完成 |

### 待完成（Phase 2）

基于 2026-03-03 再次验证，以下问题仍需修复：

| ID | 问题 | 位置 | 状态 | 工作量 |
|----|------|------|------|--------|
| ARCH-001 | API 层仍从 adapter 直接导入常量 | `fx.py:10`, `commodity.py:10-12` | ❌ 待修复 | 1h |
| ENG-002 | FredClient `__del__` 方法 | `fred/client.py:82-85` | ❌ 待修复 | 0.5h |
| ENG-003 | industry.py 静默吞异常 | `industry.py:64-66` | ❌ 待修复 | 0.5h |
| ENG-004 | FredClient 环境变量 fallback | `fred/client.py:54` | ⚠️ 可选 | 0.5h |
| ARCH-003 | ValueError 描述配置缺失 | `source.py:90-92` | ⚠️ 可选 | 0.5h |

---

## Phase 2 执行计划

### PR-8：API 层常量解耦

**目标**：API 层从 `ditto_data.models` 导入常量，而非直接从 adapter 导入。

**修改范围**：

```python
# apps/port/src/ditto_port/api/routes/fx.py
# 之前
from ditto_data.sources.tushare.adapters.fx import FX_CODE_TO_INSTRUMENT_ID

# 之后
from ditto_data.models import FX_CODE_TO_INSTRUMENT_ID
```

```python
# apps/port/src/ditto_port/api/routes/commodity.py
# 之前
from ditto_data.sources.fred.adapters.commodity import (
    COMMODITY_CODE_TO_INSTRUMENT_ID,
    VIX_CODE_TO_INSTRUMENT_ID,
)

# 之后
from ditto_data.models import VIX_CODE_TO_INSTRUMENT_ID
from ditto_data.sources.fred.adapters.commodity import COMMODITY_CODE_TO_INSTRUMENT_ID
# 注意：COMMODITY_CODE_TO_INSTRUMENT_ID 需要添加到 models/source_codes.py
```

**验证**：
```bash
pixi run -e dev check
```

**工作量**：1h

---

### PR-9：FredClient 资源管理

**目标**：移除 `__del__` 方法，改用 context manager。

**修改范围**：
- `packages/data/src/ditto_data/sources/fred/client.py`

**具体步骤**：

```python
# 删除第 82-85 行
def __del__(self) -> None:
    """Cleanup HTTP client on destruction."""
    if hasattr(self, "_client"):
        self._client.close()
```

**可选：移除环境变量 fallback**

```python
# 之前
def __init__(self, api_key: str | None = None) -> None:
    self._api_key = api_key or os.environ.get("FRED_API_KEY")

# 之后（更严格）
def __init__(self, api_key: str) -> None:
    if not api_key:
        raise SourceConfigurationError(...)
    self._api_key = api_key
```

**工作量**：0.5h（仅删除 `__del__`）或 1h（包含环境变量移除）

---

### PR-10：观测指标异常日志

**目标**：为静默吞掉的观测指标异常添加低噪日志。

**修改范围**：
- `packages/data/src/ditto_data/sources/tushare/adapters/industry.py`

```python
# 之前
except (AttributeError, TypeError):
    # Observability 未初始化，静默跳过
    pass

# 之后
except (AttributeError, TypeError) as e:
    # Observability 未初始化，低噪日志
    logger.debug(
        "metrics_emit_skipped",
        event="observability_not_initialized",
        reason=str(e),
    )
```

**工作量**：0.5h

---

## Phase 2 执行顺序

```
立即可做（低风险）
├── PR-8（API 层常量解耦）   # 1h
├── PR-9（FredClient __del__） # 0.5h
└── PR-10（观测指标日志）     # 0.5h

可选（需评估影响）
└── PR-9 扩展（环境变量 fallback） # +0.5h
```

**Phase 2 总工作量**：2-2.5h（半天）

---

## 验证清单

### PR-8 完成后
- [ ] `fx.py` 不再从 adapter 直接导入
- [ ] `commodity.py` 不再从 adapter 直接导入 `VIX_CODE_TO_INSTRUMENT_ID`
- [ ] `ruff check` 无跨层导入警告

### PR-9 完成后
- [ ] FredClient 不再有 `__del__` 方法
- [ ] 所有 FredClient 调用点使用 context manager 或显式 close

### PR-10 完成后
- [ ] industry.py 不再有静默 `pass`
- [ ] 观测指标缺失时有 debug 日志
