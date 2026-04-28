---
paths:
  - ./**/*.py
---

# Python 核心规范

## 代码规模规范

| 指标 | 限制 | 检查方式 |
|------|------|----------|
| **单文件行数** | ≤ 1000 行 | 自动检查脚本 |
| **类 public 方法数** | ≤ 20 个 | 自动检查脚本 |
| **函数长度** | ≤50 行 | Ruff (max-statements) |
| **嵌套深度** | ≤3 层 | Ruff |
| **参数个数** | ≤7 个 | Ruff (max-args) |
| **复杂度** | ≤10 (C90) | Ruff (max-complexity) |
| **行长度** | ≤88 | Ruff |

**检查命令**：
```bash
# 代码规模检查
pixi run -e dev python scripts/check_code_size.py

# 完整检查
pixi run -e dev ci
```

**依据**：业界最佳实践 + 项目实际需求

---

### 重构指导

#### 文件 > 1000 行

| 情况 | 重构策略 |
|------|----------|
| 多个相关类 | 按职责拆分到多个文件 |
| 单个类过大 | 按业务领域拆分职责 |
| 大量辅助函数 | 提取 `utils.py` 或 `helpers.py` |

#### public 方法数 > 20

| 方法类型 | 处理方式 |
|----------|----------|
| 公共 API 多 | 考虑拆分为多个服务类 |
| 私有方法多 | 提取为独立的辅助类 |
| 多个相似方法 | 用模式/注册表简化 |

#### 核心原则

> **单一职责原则（SRP）> 固定行数**

当判断是否需要拆分时，优先考虑：

1. 这个类/文件是否只有一个改变的理由？
2. 如果要修改这个类，是否总是因为同一个原因？
3. 这个类的方法是否都在服务于同一个概念？

---

## 其他代码规范

| 要求 | 值/规则 |
|------|---------|
| 类型注解 | 公开函数 100%，返回类型明确 |

**必须通过**: `pre-commit-run` 和 `ci-check` 所有检查

## 命名规范

```python
class FactorEngine: ...      # PascalCase
def calculate_momentum(): ... # snake_case
MAX_DRAWDOWN = 0.20          # UPPER_SNAKE
```

### Service 层查询方法命名规范

> **适用范围**：本规范仅适用于 `packages/data/src/ditto_data/services/` 下的存储服务类。

| 前缀/方法 | 语义 | 返回 | 参数 | 数据不存在时 | 示例 |
|-----------|------|------|------|-------------|------|
| **`get_`** | 按唯一条件查单条 | 单条或 `None` | 明确参数 | 返回 `None` | `get_by_id(id)` |
| **`find_`** | 多维条件查询 | 多条 | Query 对象或可选参数 | 返回空 DataFrame | `find_bars(query)` |
| **`list_`** | 按条件列多条 | 多条 | 明确参数 | 返回空 DataFrame/列表 | `list_by_exchange(exchange)` |
| **`first()`** | 获取第一条 | 单条或 `None` | 无参 | 返回 `None` | `first()` |
| **`all()`** | 获取所有 | 多条 | 无参 | 返回空 DataFrame/列表 | `all()` |
| **`save_`** | 保存/写入 | 结果对象 | 数据 + 参数 | - | `save_bars(df)` |
| **`count_`** | 计数 | `int` | - | 返回 `0` | `count()` |
| **`is_`** | 布尔判断 | `bool` | - | 返回 `False` | `is_trading_day(date)` |
| **`resolve_`** | 解析转换 | 值或 `None` | - | 返回 `None` | `resolve_instrument_id()` |
| **`exists_`** | 存在性 | `bool` | - | 返回 `False` | `exists()` |

#### 核心区别

```python
# get_ - 返回单条，参数明确（唯一条件）
service.get_instrument(instrument_id)      # → 单条或 None
service.get_symbol(instrument_id)          # → str 或 None

# list_ - 返回多条，参数明确
service.list_by_exchange("SH")             # → 多条 DataFrame
service.list_trading_days(start, end)      # → list[str]

# find_ - 返回多条，Query/可选参数（多维查询）
service.find_securities(SecuritiesQuery(asset_class="stock", exchange="SH"))
service.find_bars(BarsQuery(start="...", end="...", adj=QFQ))

# first() / all() - 无参
service.first()    # → 第一条或 None
service.all()      # → 所有
```

#### 示例

```python
class MetadataService:
    # get_ - 单条
    def get_instrument(self, instrument_id: int) -> dict | None: ...
    def get_symbol(self, instrument_id: int) -> str | None: ...

    # list_ - 多条，参数明确
    def list_by_exchange(self, exchange: str) -> pl.DataFrame: ...
    def list_trading_days(self, start: str, end: str) -> list[str]: ...

    # find_ - 多条，Query/可选参数
    def find_securities(self, query: SecuritiesQuery) -> pl.DataFrame: ...

    # is_ / resolve_ / exists_
    def is_trading_day(self, date: str) -> bool: ...
    def resolve_instrument_id(self, ticker: str, source: str) -> int | None: ...
    def exists_instrument(self, instrument_id: int) -> bool: ...
```

## 模型类与 DTO 规范

### 核心原则

```
Pydantic = 外部边界的数据守门员
dataclass = 内部世界的数据载体
```

### 1. dataclass vs Pydantic 使用边界

| 场景 | 使用类型 | 示例 | 理由 |
|------|----------|------|------|
| 内部运行时数据传输 | `frozen dataclass` | `WriteResult`, `IngestionResult` | 可信数据，追求性能 |
| 不可变数据结构 | `frozen dataclass` | `FreezeManifest`, `IngestionCursor` | 确保安全 |
| 简单数据容器 | `frozen dataclass` | `CacheStats`, `ResultCounts` | 无需验证逻辑 |
| 接收外部输入 | `Pydantic` | API 请求体、用户输入 | 需要验证和类型转换 |
| 环境变量配置 | `Pydantic BaseSettings` | `Settings`, `DatabaseSettings` | 自动加载 |
| 配置文件解析 | `Pydantic` | `DQSpec`, `DatasetSpec` (YAML/JSON) | 复杂验证、默认值 |
| API 响应 | `Pydantic` | FastAPI 响应模型 | FastAPI 集成、JSON Schema |
### 2. 命名规范

#### 核心原则
- 直接用业务语义命名，避免 `Input/Params/Args` 等技术术语
- 能不加后缀就不加，只有需要区分时才使用
- 用单数形式（`Options` 除外）

#### 后缀使用场景

| 后缀 | 含义 | 使用场景 | 示例 |
|------|------|----------|------|
| `Config` | 完整配置 | 系统/组件的完整配置 | `DatabaseConfig`, `APISettings` |
| `Options` | 可选行为配置 | 可选的行为选项集合（复数） | `WriteOptions`, `ParserOptions` |
| `Spec` | 规范/规格 | 定义"是什么"的规范 | `DQSpec`, `DatasetSpec` |
| `Request` | 请求 | API/任务请求 | `BackfillRequest`, `SearchQuery` |
| `Response` | 响应 | API 响应 | `ErrorResponse` |
| `Result` | 结果 | 操作结果 | `WriteResult`, `IngestionResult` |
| `Stats` | 统计 | 统计数据 | `CacheStats` |
| `Info` | 元信息 | 元数据 | `VersionInfo` |

#### 避免使用

| ❌ 避免 | ✅ 替代 | 理由 |
|---------|---------|------|
| `XXXInput` | 直接业务名，如 `Query`、`Request` | 泛泛的技术术语 |
| `XXXParams` | `Spec`/`Config`/`Options`/`Request` | 最泛泛、无语义 |
| `XXXArgs` | `Spec`/`Config`/`Options`/`Request` | 技术实现细节 |

### 3. 包结构规范

- **取消顶层 `types.py`**：避免与 Python 内置 `types` 模块混淆
- **统一使用 `models/` 包**：所有模型类集中管理
- **按域分组**：在 `models/` 下按业务域分文件

### 4. 强制约束

#### dataclass 约束
- 所有 dataclass 必须使用 `frozen=True`（除非有明确理由）
- 禁止混用：不要同时继承 `BaseModel` 和使用 `@dataclass`

#### Pydantic 约束（分层规范）

**按使用场景分层配置**：

| 场景 | strict 模式 | extra 策略 | 示例 |
|------|-------------|------------|------|
| **API 响应** | `strict=True` | `extra='ignore'` | `ErrorResponse` |
| **配置文件解析** | `lax` (默认) | `extra='allow'` 或 `extra='ignore'` | `DQSpec`, `DatasetSpec`, `BaseRule` |
| **环境变量加载** | `lax` (默认) | `extra='ignore'` | Settings 模型 |

**配置示例**：

```python
# API 响应：必须 strict 模式
from pydantic import BaseModel, ConfigDict

class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        strict=True,  # 防止类型强制转换
        extra='ignore',
    )
    code: int
    message: str

# 配置文件解析：使用 lax 模式
class DQSpec(BaseModel):
    model_config = {"extra": "allow"}
    dataset: str
    description: str = ""
```

**约束**：
- 只在数据边界使用 Pydantic，内部数据传输优先 dataclass
- API 响应模型必须使用 `strict=True` 确保类型安全
- 配置文件解析使用 lax 模式，允许必要的类型转换

## TDD 流程

```
┌─────────────────────────────────────────┐
│  RED     写失败测试 → 运行确认失败       │
│  GREEN   最小实现 → 运行确认通过         │
│  REFACTOR 优化代码 → 确保测试仍通过      │
└─────────────────────────────────────────┘
```

## 错误处理

### 核心原则

| ✅ 正确 | ❌ 错误 |
|---------|---------|
| `raise DataError("msg")` | `raise Exception("msg")` |
| `except DataError as e` | `except Exception` |
| `except SpecificError` | 捕获所有 Exception |

### 异常处理策略

#### 1. 分层处理原则

| 层级 | 处理策略 | 示例 |
|------|----------|------|
| **Data** | 直接抛出原生异常或领域异常 | `raise SourceFetchError(...)` |
| **Application** | 统一捕获 + 日志 + 业务响应 | `except Exception: logger.exception(...); return IngestionResult.failed(...)` |
| **Interface** | 统一异常处理器 + 用户友好响应 | FastAPI middleware |

**核心原则**：Raise low, catch high（底层抛出，高层捕获）

#### 2. 何时捕获 vs 抛出异常

| 场景 | 操作 | 原因 |
|------|------|------|
| **调用外部库（polars, httpx）** | 根据处理需求决定 | 需要转换为业务问题则捕获，否则抛出 |
| **数据质量检查** | 捕获并转换为 DQIssue | 技术异常 → 业务问题，有语义价值 |
| **容错组件（隔离存储）** | 捕获并返回默认值 | 失败不应阻塞主流程 |
| **应用层协调器** | 统一捕获所有异常 | 日志 + 业务响应，无需细分异常类型 |

#### 3. 避免过度分类

**❌ 避免以下过度设计**：

```python
# 过度：为每种处理方式相同的异常单独捕获
except (pl.ComputeError, pl.SchemaError, ValueError) as e:
    return handle_error("WRITE_ERROR", e)
except Exception as e:
    return handle_error("UNKNOWN_ERROR", e)

# 正确：处理方式相同时统一捕获
except Exception as e:
    logger.exception("write_failed", error_type=type(e).__name__, ...)
    return handle_unknown_error(e)
```

**判断标准**：
- 如果不同异常的**最终处理逻辑相同**，无需单独捕获
- 日志中的 `error_type` 字段已足够诊断
- 遵循 DRY 原则

#### 4. 异常转换场景

**需要转换**（有业务价值）：
- 技术异常 → 业务问题（`polars.ComputeError` → `DQIssue`）
- 外部异常 → 领域异常（`httpx.HTTPStatusError` → `SourceFetchError`）
- 通用异常 → 特定异常（`ValueError` → `ValidationError` with context）

**无需转换**（处理逻辑相同）：
- 多种异常类型执行相同的处理逻辑
- 日志已记录足够信息供诊断
- 上层不需要根据异常类型做不同决策

#### 5. 日志记录规范

| 异常类型 | 日志级别 | 日志方法 | 必需字段 |
|----------|----------|----------|----------|
| 未知/未预期异常 | ERROR | `logger.exception()` | `error_type`, 业务上下文 |
| 已知业务异常 | ERROR | `logger.error()` | `event`, 业务上下文 |
| 可恢复异常 | WARNING | `logger.warning()` | `error`, 业务上下文 |
| 资源清理失败 | WARNING | `logger.warning()` | `error` |

**关键点**：
- 使用 `logger.exception()` 记录完整堆栈（未知异常）
- 包含业务上下文（`dataset`, `trade_date` 等）
- 避免在日志中暴露敏感信息

#### 6. 自定义异常设计

**异常层次结构**：
```python
# 基础异常
class DataError(Exception):
    def __init__(self, message: str, details: dict[str, object] | None = None):
        self.details = details or {}

# 领域异常
class DataSourceError(DataError): ...
class SourceFetchError(DataSourceError): ...
class SourceAuthenticationError(DataSourceError): ...
```

**设计原则**：
- 按捕获方式定义异常（而非按来源）
- 携带详细上下文（`details` 字典）
- 保留异常链（`raise ... from e`）

## 导入规范（汇总）

**禁止行内导入！！破例需要注释说明具体原因**

### Infra 层导入

```python
# ✅ 正确
from ditto_infra.foundation import logger, span, traced, init, SQLitePool
from ditto_infra.foundation.config import get_environment, Settings

# ❌ 错误
from ditto_infra.config import get_settings  # 应为 ditto_infra.foundation.config
直接访问 os.environ
使用 open() 写文件
```

### Data 层导入

```python
# ✅ 正确
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService

# ❌ 错误
from ditto_data.storage.market import MarketReader  # 直接访问存储层
```

### Interfaces 层导入

```python
# ✅ 正确
from ditto_interfaces.api.errors import error_handler
from ditto_interfaces.exceptions import DittoError

# ❌ 错误
from ditto_interfaces.api.dependencies import get_hub  # 直接导入内部实现
```

## Re-export 规范

> 详细设计见 `docs/plans/2026-04-09-re-export-governance-design.md`

### 分层治理规则

**第 1 层 — 包根入口**（如 `ditto_kernel/__init__.py`）：允许聚合 re-export
- 只 re-export 外部消费者需要的符号，内部实现细节不导出
- 每个 barrel 控制在 **≤ 30 符号**，超过则分拆为子域入口

**第 2 层 — 子包聚合**（如 `ditto_data.storage.capital/__init__.py`）：有条件允许
- 符号数 **≤ 15**
- 仅允许内聚子域聚合（如 Reader/Writer 对），禁止跨子域聚合

**第 3 层+ — 禁止聚合**：链深度最大 **2 层**，更深的 `__init__.py` 不做聚合

### 绝对禁止

```python
# ❌ 跨包 re-export：任何包不得从另一个 ditto 包 re-export 符号
# ditto_data/models/__init__.py
from ditto_kernel.instrument import AssetClass, Exchange  # 禁止

# ❌ Barrel + 内联定义混合：__init__.py 不应混合 re-export 和新符号定义
from .margin import MarginReader
ALL_FACTOR_SPECS = {...}  # 应移到独立模块

# ❌ 内部模块从自身 barrel 导入（制造隐式耦合）
# 在 ditto_data/storage/capital/margin.py 中：
from ditto_data.storage.capital import MarginReader  # 禁止

# ✅ 正确：内部模块直接引用
from ditto_data.storage.capital.margin import MarginReader
```

### 消费者导入路径

```python
# ✅ 需要哪个包的类型就从哪个包导入
from ditto_kernel.instrument import AssetClass, Exchange
from ditto_kernel.identity import InstrumentId

# ❌ 不要通过中间包间接导入
from ditto_data.models import AssetClass  # 跨包 re-export，依赖被隐藏
```

## 文档字符串

- 中文，符合 Google/Numpy 风格
- 公开函数必须包含

## 复杂度控制

```python
# ✅ 提取函数，降低嵌套
def process_data(data):
    validated = validate(data)
    transformed = transform(validated)
    return save(transformed)

# ❌ 嵌套过深
def process_data(data):
    if data:
        for item in data:
            if item.valid:
                for sub in item.items:
                    if sub.active:  # 嵌套 4 层
                        ...
```

## Type System (BasedPyright) 规范（必须遵循）

### 目标（Definition of Done）
- **生产代码（src 下）必须做到：BasedPyright Errors = 0 且 Warnings = 0**。
- **测试代码（tests）不要求清零**，但不应影响生产代码的类型洁净度。
- 类型问题必须通过"补全类型 / 收敛 Any / 建 stub / 调整 API 形状"解决，而不是长期压制。

---

### 工具与运行方式（本仓库唯一认可）
- 生产代码（强约束，CI 必须失败）：
  - `pixi run -e dev type` (基于 basedpyright)
  - `--warnings` 会让 BasedPyright 在出现 warning 时也返回非 0 退出码，从而阻断 CI。 :contentReference[oaicite:0]{index=0}
- 测试代码（弱约束，可不清零）：
  - `pixi run -e dev type --tests` (基于 basedpyright)

---

### 自建 Stub 规范（third-party 缺类型时的标准流程）
> Pyright 支持配置 `stubPath`，默认是 `./typings`，每个包的 stub 必须放到独立子目录中。 :contentReference[oaicite:1]{index=1}

#### 目录约定
- 统一使用：`typings/`
- 结构示例：
  - `typings/<import_root>/__init__.pyi`
  - `typings/<import_root>/<submodule>.pyi`

#### 决策顺序（必须按顺序做）
1. **优先装官方/社区 stub 包**（如 `types-xxx`）。
2. 若没有可用 stub：用 BasedPyright 生成"草稿 stub"，再人工收敛：
   - `basedpyright --createstub <import-name>`
   - 生成的 stub 是"起点"，通常需要把 `Any/Unknown` 收敛成更精确的类型。 :contentReference[oaicite:2]{index=2}
3. 自建 stub 的范围必须 **"最小可用"**：
   - 只补齐本项目实际用到的 API 面；
   - 不要把整个库的完整类型都搬进来（维护成本极高）。

#### Stub 质量要求
- 禁止在 stub 中长期放任 `Any` 扩散：
  - stub 的目的就是"消除歧义"，能精确就精确；
  - 实在无法精确：用更窄的上界（如 `Protocol`、`TypedDict`、`Literal`、`Mapping[str, object]` 等），或在调用侧做"边界校验后再 cast"。

---

### 项目内 Typed 规范（PEP 561 / py.typed）
> 若你希望"包对外提供类型信息"，按 PEP 561 必须在包内加入 `py.typed` 标记文件。 :contentReference[oaicite:3]{index=3}

#### 适用范围
- 本仓库内 **任何可能被别的包引用/复用/发布的 package**，都应该：
  - 在其顶层包目录下放置空文件 `py.typed`
  - 并确保打包时将其包含进发行物（wheel/sdist）

#### 目录示例
- `packages/foo/src/foo/py.typed`
- `interfaces/src/ditto_interfaces/py.typed`（interfaces 也会作为库被引用）

#### 实施检查清单

创建新包时，必须包含 `py.typed` 文件：

- [ ] 在包根目录（与 `__init__.py` 同级）创建空文件 `py.typed`
- [ ] 确认打包配置自动包含该文件（setuptools-scm/hatchling 默认包含）
- [ ] 运行类型检查验证生效

#### 打包配置规范

使用 `setuptools-scm` 时（Ditto 默认），`py.typed` 会自动被包含在 wheel 中。

如需手动验证，检查生成的 wheel 包含 `*.py.typed`：

```bash
pixi run build
tar -tzf dist/*.whl | grep py.typed
```

#### 当前项目状态

| 包 | py.typed 状态 | 路径 |
|---|--------------|------|
| ditto_engine | ✅ | `packages/engine/src/ditto_engine/py.typed` |
| ditto_data | ✅ | `packages/data/src/ditto_data/py.typed` |
| ditto_infra | ✅ | `packages/infra/src/ditto_infra/py.typed` |
| ditto_kernel | ✅ | `packages/kernel/src/ditto_kernel/py.typed` |
| ditto_analytics | ✅ | `packages/analytics/src/ditto_analytics/py.typed` |
| ditto_app | ✅ | `packages/app/src/ditto_app/py.typed` |
| ditto_interfaces | ✅ | `interfaces/src/ditto_interfaces/py.typed` |

---

### 代码类型标注规则（AI 写码必须默认遵守）
#### 1) 公共 API 必须完整注解
- 任何 **对外可调用的函数/方法/类构造**：参数与返回值必须注解。
- 允许局部变量依赖推导，但一旦出现 Unknown/Any 扩散，必须补注解或重构。

#### 2) Any 的使用边界（强约束）
- 生产代码中禁止"无边界 Any"：
  - 只能在 **IO/外部边界** 出现（JSON、DB 行、HTTP 响应、第三方动态对象）；
  - 进入领域逻辑前必须完成 **解析/校验/收敛**（TypedDict / dataclass / pydantic / 自定义解析器）。
- 优先选择（按适用场景排序）：
  - `A | B` / `T | None`（值是几种已知类型之一）
  - `Protocol`（约束行为面）
  - `TypedDict`（约束 JSON/dict 结构）
  - `dataclass` / Pydantic（定义领域模型）
  - `TypeAlias` / `NewType`（约束领域值）
  - `Literal`（约束枚举值）
  - `overload`（约束多态签名）
- **Any 白名单**（仅限以下场景，无需收敛）：
  - SQL 参数/结果（`list[Any]`、`tuple[Any, ...]`）
  - 通用缓存值（`VTTLCache[str, Any]`）
  - 日志/指标 attributes（`dict[str, Any]`）
  - 领域事件 payload（`DomainEvent.payload`）
  - 第三方库适配（Prefect `Flow[Any, Any]` 等）
  - 底层库类型不兼容（必须注释原因）
- **Any 红线**（禁止场景）：
  - 延迟初始化：用 `X | None` 而非 `Any = None`
  - `.get()` 返回值：用 `str | None` 而非 `Any`
  - Service 层对外 API 返回值：用 TypedDict/dataclass 而非 `dict[str, Any]`
  - 有明确行为约束的参数：用 Protocol 而非 `Any`
- 详见 `docs/plans/2026-04-09-any-usage-audit-and-rules.md`

#### 3) import 与 typing 书写习惯
- 新文件默认加：`from __future__ import annotations`
- 参数类型优先用 `collections.abc`（`Sequence/Mapping/Iterable`）而不是具体容器类型（`list/dict`），除非你明确需要可变性语义。

---

### 忽略/压制规则（必须极少使用）
- **默认不允许** `# type: ignore`。
- 如必须压制，优先使用 BasedPyright 的"可定位规则名"的 ignore：
  - `x = foo()  # type: ignore[reportGeneralTypeIssues]`
  - BasedPyright 支持在 `# type: ignore[...]` 中列出规则名，只压制指定类别。 :contentReference[oaicite:4]{index=4}
- 每一个 ignore 必须附带原因（为什么无法用更好的类型表达解决），并尽量链接到 issue/任务编号。

---

### 生产代码类型洁净的硬标准
- 生产代码任何 warning 都视为缺陷（必须修复），CI 使用 `--warnings` 强制执行。 :contentReference[oaicite:5]{index=5}
- 如果某目录暂时无法做到类型洁净，应拆分为"隔离层"（adapter/boundary），而不是放宽核心目录规则。

## 架构分层约束

### 分层职责定义

| 层级 | 职责 | 典型组件 | 禁止 |
|------|------|----------|------|
| **Data Store** | 数据持久化、基础查询 | Reader/Writer CQRS（如 `MarketReader`, `MetadataWriter`） | 包含业务逻辑 |
| **Data Service** | 领域封装、查询/写入契约 | MarketService, MetadataService | 直接暴露存储实现细节 |
| **Data Runtime** | 基础设施（连接池、锁、分配器) | SQLitePool, FileLockManager, InstrumentIdAllocator（均属 Infra 层） | 包含业务逻辑 |
| **Data Source/Adapter** | 外部数据源适配与字段规范化 | TushareSource, CapitalAdapter | 包含业务编排逻辑 |
| **Interfaces Service** | 流程编排、任务协调 | IngestionCoordinator, RetryManager | 直接数据访问 |
 | **Interfaces Flow** | 应用层用例组合 | DailyFlow, BackfillFlow | - |

### 依赖方向规则

**允许的单向依赖：**
```
Interfaces Flow → Interfaces Service → App Service → Data Service → Data Store/Runtime → Infra
```

**禁止的依赖模式：**
- ❌ Interfaces → Data Store (跨层访问)
- ❌ Interfaces → Data Runtime (跨层访问)
- ❌ Interfaces 非 registry 模块 → Data Source(跨层访问)
- ❌ Data → Interfaces (反向依赖)
- ❌ 同层组件间的循环依赖

### 跨层检测规则

**导入语句检查：**

```python
# ❌ Interfaces 层禁止直接导入 Store
from ditto_data.storage.metadata import MetadataReader

# ❌ Interfaces 层禁止直接导入 Runtime
from ditto_data.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_infra.foundation.db import SQLitePool  # SQLitePool 属于 Infra 层

# ✅ Interfaces 层应该使用 Service（通过 DI 获取）
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService

# ✅ 仅 registry 模块允许导入 Store/Source 做 DI 装配
from ditto_data.sources.tushare import TushareSource
from ditto_data.storage.sqlite_client import SQLiteClient

# ✅ Data 内部可以导入下层
# packages/data 内的 Store 可以导入 Runtime```

**职责识别检查：**

当添加新组件时，通过以下问题判断其归属：

| 问题 | 回答 Yes → 归属 | 回答 No → 归属 |
|------|-----------------|----------------|
| 是否直接访问存储文件/数据库？ | Data Store | 使用 Data Service |
| 是否需要分配/管理唯一标识符（如 instrument_id）？ | Data Service | 不应在此层 |
| 是否包含数据映射/转换逻辑（如 source_ticker → instrument_id）？ | Data Service | 不应在此层 |
| 是否依赖外部数据源（API/爬虫）？ | Data Source/Adapter | 不应在此层 |
| 是否是流程编排/任务协调？ | App 层 Service | 不应在此层 |
| 是否是应用层用例组合？ | App 层 Flow | 不应在此层 |

### 代码重复检测

在实现新功能前，必须检查 Data Service 是否已有类似实现：

```bash
# 检查 MetadataService 是否已有相关方法
grep -r "def.*register" packages/data/src/ditto_data/services/metadata/
```

**禁止重复实现：**
- ❌ Interfaces 层重复实现 Service 已有的数据访问逻辑
- ❌ 多个地方重复实现相同的映射/转换规则
```
