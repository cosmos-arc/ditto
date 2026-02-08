---
paths: ./**/*.py
---

# Python 核心规范

## 代码规模规范

| 指标 | 限制 | 检查方式 |
|------|------|----------|
| **单文件行数** | ≤ 800 行 | 自动检查脚本 |
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

#### 文件 > 800 行

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
| `raise DataHubError("msg")` | `raise Exception("msg")` |
| `except DataHubError as e` | `except Exception` |
| `except SpecificError` | 捕获所有 Exception |

### 异常处理策略

#### 1. 分层处理原则

| 层级 | 处理策略 | 示例 |
|------|----------|------|
| **Foundation/DataHub** | 直接抛出原生异常或领域异常 | `raise SourceFetchError(...)` |
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
class DataHubError(Exception):
    def __init__(self, message: str, details: dict[str, object] | None = None):
        self.details = details or {}

# 领域异常
class DataSourceError(DataHubError): ...
class SourceFetchError(DataSourceError): ...
class SourceAuthenticationError(DataSourceError): ...
```

**设计原则**：
- 按捕获方式定义异常（而非按来源）
- 携带详细上下文（`details` 字典）
- 保留异常链（`raise ... from e`）

## 导入规范（汇总）

**禁止行内导入！！破例需要注释说明具体原因**

### Foundation 层导入

```python
# ✅ 正确
from ditto_foundation import logger, M, span, traced, init
from ditto_foundation.config import get_settings
from ditto_foundation.util.io import atomic_write

# ❌ 错误
from ditto_foundation.observability.logging import get_logger
直接访问 os.environ
使用 open() 写文件
```

### DataHub 层导入

```python
# ✅ 正确
from ditto_datahub import DataHub

# ❌ 错误
from ditto_datahub.stores.bars_store import BarsStore
```

### Server 层导入

```python
# ✅ 正确
from ditto_server.api import get_hub
from ditto_server.ingestion import flows

# ❌ 错误
from ditto_server.api.dependencies import hub
直接导入内部实现
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
- `apps/xxx/src/xxx/py.typed`（若该 app 也会作为库被引用）

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
| ditto_core | ✅ | `packages/core/src/ditto_core/py.typed` |
| ditto_datahub | ✅ | `packages/datahub/src/ditto_datahub/py.typed` |
| ditto_foundation | ✅ | `packages/foundation/src/ditto_foundation/py.typed` |
| ditto_port | ✅ | `apps/port/src/ditto_port/py.typed` |

---

### 代码类型标注规则（AI 写码必须默认遵守）
#### 1) 公共 API 必须完整注解
- 任何 **对外可调用的函数/方法/类构造**：参数与返回值必须注解。
- 允许局部变量依赖推导，但一旦出现 Unknown/Any 扩散，必须补注解或重构。

#### 2) Any 的使用边界（强约束）
- 生产代码中禁止"无边界 Any"：
  - 只能在 **IO/外部边界** 出现（JSON、DB 行、HTTP 响应、第三方动态对象）；
  - 进入领域逻辑前必须完成 **解析/校验/收敛**（TypedDict / dataclass / pydantic / 自定义解析器）。
- 优先选择：
  - `Protocol`（约束行为面）
  - `TypedDict`（约束 JSON 结构）
  - `TypeAlias` / `NewType`（约束领域值）
  - `Literal`（约束枚举值）
  - `overload`（约束多态签名）

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
| **DataHub Store** | 数据持久化、基础查询 | SecurityStore, BarsStore | 包含业务逻辑 |
| **DataHub Accessor** | 业务封装、领域接口 | SecurityAccessor, BarsAccessor | 直接访问文件系统 |
| **DataHub Runtime** | 基础设施（连接池、锁、分配器） | SQLitePool, FileLockManager, InstrumentIdAllocator | 包含业务逻辑 |
| **DataHub Source** | 外部数据源适配 | TushareSource, AkshareSource | 包含业务逻辑 |
| **Server Service** | 流程编排、任务协调 | IngestionCoordinator, RetryManager | 直接数据访问 |
| **Server Flow** | 应用层用例组合 | DailyFlow, BackfillFlow | - |

### 依赖方向规则

**允许的单向依赖：**
```
Server Flow → Server Service → DataHub Accessor → DataHub Store/Runtime → Foundation
```

**禁止的依赖模式：**
- ❌ Server → DataHub Store (跨层访问)
- ❌ Server → DataHub Runtime (跨层访问)
- ❌ DataHub → Server (反向依赖)
- ❌ 同层组件间的循环依赖

### 跨层检测规则

**导入语句检查：**

```python
# ❌ Server 层禁止直接导入 Store
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.bars_store import BarsStore

# ❌ Server 层禁止直接导入 Runtime
from ditto_datahub.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_datahub.runtime.sqlite_pool import SQLitePool

# ✅ Server 层应该使用 Accessor
from ditto_datahub import DataHub
from ditto_datahub.accessors.security import SecurityAccessor

# ✅ DataHub 内部可以导入下层
# packages/datahub 内的 Store 可以导入 Runtime
```

**职责识别检查：**

当添加新组件时，通过以下问题判断其归属：

| 问题 | 回答 Yes → 归属 | 回答 No → 归属 |
|------|-----------------|----------------|
| 是否直接访问存储文件/数据库？ | DataHub Store | 使用 Accessor |
| 是否需要分配/管理唯一标识符（如 instrument_id）？ | DataHub Accessor | 不应在此层 |
| 是否包含数据映射/转换逻辑（如 source_ticker → instrument_id）？ | DataHub Accessor | 不应在此层 |
| 是否依赖外部数据源（API/爬虫）？ | DataHub Source | 不应在此层 |
| 是否是流程编排/任务协调？ | Server Service | 不应在此层 |
| 是否是应用层用例组合？ | Server Flow | 不应在此层 |

### 代码重复检测

在实现新功能前，必须检查 DataHub Accessor 是否已有类似实现：

```bash
# 检查 SecurityAccessor 是否已有相关方法
grep -r "def.*register" packages/datahub/accessors/
grep -r "def.*resolve" packages/datahub/accessors/
```

**禁止重复实现：**
- ❌ Server 层重复实现 Accessor 已有的数据访问逻辑
- ❌ 多个地方重复实现相同的映射/转换规则
