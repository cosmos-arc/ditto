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
