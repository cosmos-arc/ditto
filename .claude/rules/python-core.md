---
paths: **/*.py
---

## 代码规范

- 类型注解: 公开函数 100%
- 函数长度: ≤50 行
- 嵌套深度: ≤3 层
- 参数个数: ≤5 个
- 符合Pythonic最佳实践
- **必须**通过`pre-push-check`所有检查，不能忽略跳过
- **必须**通过`ci-check`所有检查，不能忽略跳过

## 命名

```python
class FactorEngine: ...      # PascalCase
def calculate_momentum(): ... # snake_case
MAX_DRAWDOWN = 0.20          # UPPER_SNAKE
```

## TDD 流程

1. RED: 写失败测试
2. GREEN: 最小实现
3. REFACTOR: 优化

## 测试规范

- AAA 模式: Arrange → Act → Assert
- 测试隔离: 禁止测试间依赖
- 边界覆盖: 正常/边界/异常

## 导入规范

| ✅ 正确 | ❌ 错误 |
|---------|---------|
| from ditto_foundation import logger, M, span, traced, init | from ditto_foundation.observability.logging import get_logger |
| from ditto_datahub import DataHub | from ditto_datahub.stores.bars_store import BarsStore |
| from ditto_server.api import get_hub | from ditto_server.api.dependencies import hub |

## 错误处理

| ✅ 正确 | ❌ 错误 |
|---------|---------|
| raise DataHubError("msg") | raise Exception("msg") |
| except DataHubError as e | except Exception |
| except SpecificError | 捕获所有 Exception |
