---
paths: ./**/*.py
---

## 代码规范

- 类型注解: 公开函数 100%，返回类型明确标注
- 函数长度: ≤50 行 (利用ruff check检查，不要自己计算！！)
- 嵌套深度: ≤3 层
- 参数个数: ≤5 个
- 复杂度 ≤ 10 (C90)
- 符合Pythonic最佳实践
- **必须**通过`pre-commit-run`所有检查，不能忽略跳过
- **必须**通过`ci-check`所有检查，不能忽略跳过

## 代码风格
- 行长度 ≤ 88
- 有意义的变量命名（非单字母，除循环外）
- 文档字符串（中文，符合 D 规则）

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
