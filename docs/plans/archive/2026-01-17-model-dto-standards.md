# 模型类与数据传输对象（DTO）规范重构

## 背景

当前项目存在以下问题：
1. **工具混用不一致**：`IngestionResult` 用 dataclass，`BackfillResult` 用 Pydantic
2. **包结构分散**：结果模型散落在各自模块中
3. **缺乏明确规范**：没有文档说明何时用 dataclass vs Pydantic
4. **命名混淆**：`types.py` 与 `config` 命名不够清晰

## 设计原则

### 核心决策标准：数据的来源

```
┌─────────────────────────────────────────────────────────────────┐
│  决策标准：数据的来源和流向                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  外部 ────────────────────────────────────────────► 内部        │
│         (Pydantic: 验证 + 转换 + 清洗)              │
│                                                                 │
│  内部 ────────────────────────────────────────────► 内部        │
│         (dataclass: 轻量传输)                     │
│                                                                 │
│  内部 ────────────────────────────────────────────► 外部        │
│         (可选 Pydantic: 序列化成 JSON)            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 简化规则

```
Pydantic = 外部边界的数据守门员
dataclass = 内部世界的数据载体
```

## 使用规范

### dataclass 使用场景

| 场景 | 示例 | 理由 |
|------|------|------|
| **内部运行时数据传输** | `WriteResult`, `IngestionResult` | 可信数据，追求性能 |
| **不可变数据结构** | `FreezeManifest`, `IngestionCursor` | 使用 `frozen=True` 确保安全 |
| **简单数据容器** | `CacheStats`, `ResultCounts` | 无需验证逻辑 |
| **领域实体** | 未来 DDD 的 Entity/ValueObject | 保持 Domain Layer 纯净 |

### Pydantic 使用场景

| 场景 | 示例 | 理由 |
|------|------|------|
| **接收外部输入** | API 请求体、用户输入 | 需要验证和类型转换 |
| **环境变量配置** | `Settings`, `DatabaseSettings` | BaseSettings 自动加载 |
| **配置文件解析** | `DQSpec`, `DatasetSpec` (YAML/JSON) | 复杂验证、默认值、别名 |
| **API 响应** | FastAPI 响应模型 | FastAPI 集成、JSON Schema |

### 命名规范

#### 核心原则

1. **直接用业务语义命名**，避免 Input/Params/Args 这样的技术术语
2. **能不加后缀就不加**，只有在需要区分同类概念时才使用后缀
3. **用单数形式**，除非真的是集合类型（Options 除外）

#### 后缀使用场景

| 后缀 | 含义 | 使用场景 | 示例 |
|------|------|----------|------|
| **`Config`** | 完整配置 | 系统/组件的完整配置 | `DatabaseConfig`, `APISettings` |
| **`Options`** | 可选行为配置 | 可选的行为选项集合（复数） | `WriteOptions`, `ParserOptions` |
| **`Spec`** | 规范/规格 | 定义"是什么"的规范 | `DQSpec`, `DatasetSpec` |
| **`Request`** | 请求 | API/任务请求 | `BackfillRequest`, `SearchQuery` |
| **`Response`** | 响应 | API 响应 | `ErrorResponse` |
| **`Result`** | 结果 | 操作结果 | `WriteResult`, `IngestionResult` |
| **`Stats`** | 统计 | 统计数据 | `CacheStats` |
| **`Info`** | 元信息 | 元数据 | `VersionInfo` |

#### Config vs Options 的区别

| 维度 | `Config` | `Options` |
|------|----------|-----------|
| **语义** | 完整配置 | 可选行为配置 |
| **必需性** | 通常必需 | 全部可选 |
| **示例** | `DatabaseConfig` | `WriteOptions` |

```python
# Config: 完整配置（可能有必需字段）
class DatabaseConfig(BaseModel):
    host: str           # 必需
    port: int = 5432    # 有默认值
    username: str       # 必需

# Options: 可选行为配置（全部可选）
class WriteOptions(BaseModel):
    compression: CompressionType = CompressionType.SNAPPY  # 可选
    overwrite: bool = False                                # 可选
    write_metadata: bool = True                            # 可选
```

#### 避免

| 避免使用 | 原因 | 替代 |
|---------|------|------|
| `XXXInput` | 泛泛的技术术语 | 直接用业务名，如 `Query`、`Filter`、`Request` |
| `XXXParams` | 最泛泛、无语义 | `Spec`/`Config`/`Options`/`Request` |
| `XXXArgs` | 技术实现细节 | 同上 |

#### 命名对比

| ❌ 避免 | ✅ 推荐 | 理由 |
|--------|---------|------|
| `QueryInput` | `Query` 或 `SearchQuery` | 直接业务名 |
| `ProcessInput` | 具体业务名，如 `TradeRequest` | 业务语义 |
| `BackfillParams` | `BackfillRequest` | 明确是请求 |
| `FilterCriteria` | `Filter` 或 `SearchFilter` | 更简洁 |
| `T1ConfigParams` | `T1ConfigSpec` | Spec 表达规范 |
| `ErrorResponseParams` | `ErrorResponse` | 直接命名 |

## 包结构规范

### 统一原则

1. **取消顶层 `types.py`**：避免与 Python 内置 `types` 模块混淆
2. **统一使用 `models/` 包**：所有模型类集中管理
3. **按域分组**：在 `models/` 下按业务域分文件

### 推荐结构

```
packages/
├── foundation/src/ditto_foundation/
│   └── models/                      # 统一组织
│       ├── __init__.py
│       ├── config.py                # Settings (Pydantic) + PathConfig (dataclass)
│       └── observability.py         # ObservabilityConfig, TracingConfig
│
├── datahub/src/ditto_datahub/
│   └── models/                      # 重组统一
│       ├── __init__.py
│       ├── common.py                # 枚举、NamedTuple (OnDuplicate, DQSeverity, SidRange)
│       ├── storage.py               # WriteResult, WriteResultStore, FreezeManifest
│       ├── quality.py               # DQSpec, DQResult, DQIssue (统一 dq/models.py)
│       ├── ingestion.py             # IngestionLog, IngestionCursor
│       └── alerts.py                # AlertMessage
│
└── core/src/ditto_core/
    └── models/                      # 预留
        ├── __init__.py
        ├── portfolio.py
        └── strategy.py

apps/port/src/ditto_port/
└── models/                          # 新建统一
    ├── __init__.py
    ├── ingestion.py                 # IngestionResult, BackfillResult, RetryResult
    ├── config.py                    # DatasetSpec
    └── common.py                    # 枚举、简单别名
```

### 导入规范

```python
# 推荐：统一从 models 导入
from ditto_datahub.models import (
    WriteResult,
    FreezeManifest,
    OnDuplicate,
    DQSpec,
    DQResult,
)

# 避免：分散导入
from ditto_datahub.types import WriteResult
from ditto_datahub.dq.models import DQSpec
```

## 强制约束

### dataclass 约束

1. **所有 dataclass 必须使用 `frozen=True`**（除非有明确理由）
2. **禁止混用**：不要同时继承 `BaseModel` 和使用 `@dataclass`

```python
# ✅ 正确
@dataclass(frozen=True)
class WriteResult:
    file_path: str
    checksum: str

# ❌ 错误
@dataclass  # 缺少 frozen=True
class WriteResult: ...
```

### Pydantic 约束

#### 1. 分层使用原则

**Pydantic 模型按使用场景分层配置**：

| 场景 | strict 模式 | extra 策略 | 理由 |
|------|-------------|------------|------|
| **API 响应** | `strict=True` | `extra='ignore'` | 防止类型强制转换，确保数据安全 |
| **配置文件解析** | `lax` (默认) | `extra='allow'` 或 `extra='ignore'` | 需要类型转换的灵活性 |
| **环境变量加载** | `lax` (默认) | `extra='ignore'` | Pydantic Settings 默认行为 |

#### 2. 场景示例

**API 响应模型（必须 `strict=True`）**：

```python
from pydantic import BaseModel, ConfigDict

# ✅ 正确：API 响应使用 strict 模式
class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        strict=True,  # 防止类型强制转换
        extra='ignore',  # 忽略额外字段
    )
    code: int
    message: str
```

**配置文件解析模型（使用 lax 模式）**：

```python
from pydantic import BaseModel, Field
from typing import Any

# ✅ 正确：配置文件解析使用 lax 模式，允许类型转换
class DQSpec(BaseModel):
    model_config = {"extra": "allow"}
    dataset: str
    description: str = ""
    l1_technical: list[dict[str, Any]] = Field(default_factory=list)

# ✅ 正确：动态规则使用 extra='allow' 容纳不同规则类型
class BaseRule(BaseModel):
    model_config = {"extra": "allow"}
    rule: str
    columns: list[str]
    message: str
```

#### 3. 只在数据边界使用

内部数据传输优先 dataclass，Pydantic 只用于外部边界。

```python
# ❌ 错误：内部结果不需要 Pydantic
class BackfillResult(BaseModel):  # 应该用 dataclass
    results: list[IngestionResult]

# ✅ 正确：内部结果使用 frozen dataclass
@dataclass(frozen=True)
class BackfillResult:
    dataset: str
    results: tuple[IngestionResult, ...]
```

## 迁移计划

### 第一阶段：更新规约文档

1. **更新 `.claude/rules/core.md`**：添加"模型类与 DTO 规范"章节
   - dataclass vs Pydantic 使用边界
   - 命名规范
   - 包结构规范
   - 强制约束

### 第二阶段：重组包结构

按以下优先级迁移：

1. **packages/datahub**: 重组 `dq/models.py` → `models/quality.py`
2. **apps/port**: 创建 `models/`，迁移分散的结果类
3. **packages/foundation**: 可选（当前结构相对合理）

### 第三阶段：代码重构

1. **改 Pydantic 为 dataclass**：
   - `BackfillResult` → dataclass
   - `RetryResult` → dataclass
   - 保持 `IngestionResult` 为 dataclass

2. **重命名**：
   - `DQConfig` → `DQSpec`
   - `DatasetConfig` → `DatasetSpec`
   - `T1ConfigParams` → `T1ConfigSpec`
   - `ErrorResponseParams` → `ErrorResponse`

3. **更新导入**：统一使用 `from xxx.models import`

### 第四阶段：清理废弃代码

1. 移除旧的 `types.py`（添加过渡期 DeprecationWarning）
2. 更新所有引用

## 验证标准

1. ✅ 所有模型类从 `models/` 包统一导入
2. ✅ Pydantic 只用于外部数据边界
3. ✅ 内部数据传输统一使用 frozen dataclass
4. ✅ 命名使用直接业务语义（Config/Options/Spec/Request/Result 等）
5. ✅ 避免 Input/Params/Args 等技术术语
6. ✅ **API 响应模型使用 `strict=True`**（如 `ErrorResponse`）
7. ✅ **配置文件解析模型使用 lax 模式**（如 `DQSpec`, `DatasetSpec`）
8. ✅ 通过 pyright、ruff 检查
9. ✅ 所有测试通过

## 参考资料

### 架构与设计
- [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices)
- [Structuring a FastAPI Project: Best Practices](https://dev.to/mohammad222pr/structuring-a-fastapi-project-best-practices-53l6)
- [Pydantic vs Data Classes: Which Should You Use?](https://zakforster.com/posts/pydantic-vs-dataclasses/)
- [Keep Pydantic out of your Domain Layer](https://news.ycombinator.com/item?id=44656419)

### Pydantic Strict Mode 规范
- [Pydantic Strict Mode 官方文档](https://docs.pydantic.dev/latest/concepts/strict_mode/)
  - **关键原则**：Strict mode 主要用于 API 场景，防止类型强制转换
  - **配置解析**：环境变量和配置文件使用 lax 模式，允许必要的类型转换
- [Pydantic Settings 官方文档](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
  - **默认行为**：Settings 使用 lax 模式加载环境变量和配置文件
  - **extra 配置**：推荐使用 `extra='ignore'` 处理未知字段

### 行业实践
- **API 响应模型**：使用 `strict=True` 确保类型安全
- **配置文件解析**：使用 lax 模式提供灵活性
- **数据边界分离**：Domain Layer 使用 dataclass，边界层使用 Pydantic
