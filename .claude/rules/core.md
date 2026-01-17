---
paths: ./**/*.py
---

# Python 核心规范

## 代码规范

| 要求 | 值/规则 |
|------|---------|
| 类型注解 | 公开函数 100%，返回类型明确 |
| 函数长度 | ≤50 行 (ruff check) |
| 嵌套深度 | ≤3 层 |
| 参数个数 | ≤5 个 |
| 复杂度 | ≤10 (C90) |
| 行长度 | ≤88 |

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

#### Pydantic 约束
- Pydantic 模型配置 `strict=True`（Python 3.12+）
- 只在数据边界使用，内部数据传输优先 dataclass

## TDD 流程

```
┌─────────────────────────────────────────┐
│  RED     写失败测试 → 运行确认失败       │
│  GREEN   最小实现 → 运行确认通过         │
│  REFACTOR 优化代码 → 确保测试仍通过      │
└─────────────────────────────────────────┘
```

## 错误处理

| ✅ 正确 | ❌ 错误 |
|---------|---------|
| `raise DataHubError("msg")` | `raise Exception("msg")` |
| `except DataHubError as e` | `except Exception` |
| `except SpecificError` | 捕获所有 Exception |

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

## Type System (Pyright) 规范（必须遵循）

### 目标（Definition of Done）
- **生产代码（src 下）必须做到：Pyright Errors = 0 且 Warnings = 0**。
- **测试代码（tests）不要求清零**，但不应影响生产代码的类型洁净度。
- 类型问题必须通过“补全类型 / 收敛 Any / 建 stub / 调整 API 形状”解决，而不是长期压制。

---

### 工具与运行方式（本仓库唯一认可）
- 生产代码（强约束，CI 必须失败）：
  - `pyright -p pyproject.toml --warnings`
  - `--warnings` 会让 Pyright 在出现 warning 时也返回非 0 退出码，从而阻断 CI。 :contentReference[oaicite:0]{index=0}
- 测试代码（弱约束，可不清零）：
  - `pyright -p pyright.tests.json`

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
2. 若没有可用 stub：用 Pyright 生成“草稿 stub”，再人工收敛：
   - `pyright --createstub <import-name>`
   - 生成的 stub 是“起点”，通常需要把 `Any/Unknown` 收敛成更精确的类型。 :contentReference[oaicite:2]{index=2}
3. 自建 stub 的范围必须 **“最小可用”**：
   - 只补齐本项目实际用到的 API 面；
   - 不要把整个库的完整类型都搬进来（维护成本极高）。

#### Stub 质量要求
- 禁止在 stub 中长期放任 `Any` 扩散：
  - stub 的目的就是“消除歧义”，能精确就精确；
  - 实在无法精确：用更窄的上界（如 `Protocol`、`TypedDict`、`Literal`、`Mapping[str, object]` 等），或在调用侧做“边界校验后再 cast”。

---

### 项目内 Typed 规范（PEP 561 / py.typed）
> 若你希望“包对外提供类型信息”，按 PEP 561 必须在包内加入 `py.typed` 标记文件。 :contentReference[oaicite:3]{index=3}

#### 适用范围
- 本仓库内 **任何可能被别的包引用/复用/发布的 package**，都应该：
  - 在其顶层包目录下放置空文件 `py.typed`
  - 并确保打包时将其包含进发行物（wheel/sdist）

#### 目录示例
- `packages/foo/src/foo/py.typed`
- `apps/xxx/src/xxx/py.typed`（若该 app 也会作为库被引用）

---

### 代码类型标注规则（AI 写码必须默认遵守）
#### 1) 公共 API 必须完整注解
- 任何 **对外可调用的函数/方法/类构造**：参数与返回值必须注解。
- 允许局部变量依赖推导，但一旦出现 Unknown/Any 扩散，必须补注解或重构。

#### 2) Any 的使用边界（强约束）
- 生产代码中禁止“无边界 Any”：
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
- 如必须压制，优先使用 Pyright 的“可定位规则名”的 ignore：
  - `x = foo()  # pyright: ignore[reportGeneralTypeIssues]`
  - Pyright 支持在 `# pyright: ignore[...]` 中列出规则名，只压制指定类别。 :contentReference[oaicite:4]{index=4}
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
| **DataHub Repository** | 业务封装、领域接口 | SecurityRepository, BarsRepository | 直接访问文件系统 |
| **DataHub Runtime** | 基础设施（连接池、锁、分配器） | SQLitePool, FileLockManager, SidAllocator | 包含业务逻辑 |
| **DataHub Source** | 外部数据源适配 | TushareSource, AkshareSource | 包含业务逻辑 |
| **Server Service** | 流程编排、任务协调 | IngestionCoordinator, RetryManager | 直接数据访问 |
| **Server Flow** | 应用层用例组合 | DailyFlow, BackfillFlow | - |

### 依赖方向规则

**允许的单向依赖：**
```
Server Flow → Server Service → DataHub Repository → DataHub Store/Runtime → Foundation
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
from ditto_datahub.runtime.sid_allocator import SidAllocator
from ditto_datahub.runtime.sqlite_pool import SQLitePool

# ✅ Server 层应该使用 Repository
from ditto_datahub import DataHub
from ditto_datahub.repositories.security import SecurityRepository

# ✅ DataHub 内部可以导入下层
# packages/datahub 内的 Store 可以导入 Runtime
```

**职责识别检查：**

当添加新组件时，通过以下问题判断其归属：

| 问题 | 回答 Yes → 归属 | 回答 No → 归属 |
|------|-----------------|----------------|
| 是否直接访问存储文件/数据库？ | DataHub Store | 使用 Repository |
| 是否需要分配/管理唯一标识符（如 SID）？ | DataHub Repository | 不应在此层 |
| 是否包含数据映射/转换逻辑（如 src_code → sid）？ | DataHub Repository | 不应在此层 |
| 是否依赖外部数据源（API/爬虫）？ | DataHub Source | 不应在此层 |
| 是否是流程编排/任务协调？ | Server Service | 不应在此层 |
| 是否是应用层用例组合？ | Server Flow | 不应在此层 |

### 代码重复检测

在实现新功能前，必须检查 DataHub Repository 是否已有类似实现：

```bash
# 检查 SecurityRepository 是否已有相关方法
grep -r "def.*register" packages/datahub/repositories/
grep -r "def.*resolve" packages/datahub/repositories/
```

**禁止重复实现：**
- ❌ Server 层重复实现 Repository 已有的数据访问逻辑
- ❌ 多个地方重复实现相同的映射/转换规则
