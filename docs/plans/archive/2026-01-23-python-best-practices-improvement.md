# Python 最佳实践改进计划

## 概述

基于 `docs/plans/2026-01-23-python-best-practices-analysis.md` 分析报告，修复 Ditto 项目中不符合 Python 业界最佳实践的代码问题。

**基线数据**（基于实际 Grep 验证）：
- **异常处理**: 17 个源码文件存在 `except Exception`（其中部分已合理处理）
- **类型注解**: 6 个源码文件存在 `: Any`（约 30 处）
- **type:ignore**: 10 个文件存在 `type:ignore`（共 21 处，5 处在源码）

**关键发现**：
1. `datahub.py:283` 的 PLR0913 是 Dishka Provider 固有模式，**不应修改**
2. `security_store.py:590` 已在 `except Exception` 后 `raise`，已合理处理
3. `observability/__init__.py:172` 和 `testing.py:19` 的异常捕获是合理的优雅关闭模式

---

## 阶段划分

| 阶段 | 优先级 | 时间估算 | 目标 |
|------|--------|----------|------|
| **阶段 1** | P0-关键 | 1周 | 修复通知渠道异常处理、类型注解问题 |
| **阶段 2** | P1-质量 | 1周 | 配置管理、复杂度评估 |
| **阶段 3** | P2-优化 | 可选 | 架构优化（工厂模式） |

---

## 阶段 1：P0 关键问题修复（1周）

### Task 1.1: 通知渠道异常处理修复 `[S]`

**文件**:
- `packages/foundation/src/ditto_foundation/notification/channels/webhook.py:76`
- `packages/foundation/src/ditto_foundation/notification/channels/telegram.py:72`
- `packages/foundation/src/ditto_foundation/notification/channels/email.py:85`

**验收标准**:
- 捕获具体异常（`httpx.TimeoutException`, `HTTPStatusError`, `NetworkError`）
- 保留未预期异常的 `raise`（不吞掉异常）
- 日志包含 `error_type` 和 `retryable` 标记
- 补充测试文件中的异常场景测试

**修复示例**:
```python
# ❌ 当前
except Exception as e:
    logger.error(f"Webhook 发送失败: {e}")
    return False

# ✅ 改进
except TimeoutException as e:
    logger.warning(f"Webhook 超时: {e}")
    return NotificationResult(success=False, error="timeout", retryable=True)
except HTTPStatusError as e:
    logger.error(f"HTTP 错误: {e.response.status_code}")
    return NotificationResult(success=False, error=f"http_{e.response.status_code}")
except (ValidationError, ValueError) as e:
    logger.error(f"消息格式错误: {e}", exc_info=True)
    raise  # 配置错误应该抛出
except Exception as e:
    logger.error(f"Webhook 发送失败: {e}", exc_info=True)
    raise  # 未预期错误应该抛出
```

---

### Task 1.2: tracing.py 类型注解修复 `[S]`

**文件**: `packages/foundation/src/ditto_foundation/observability/tracing.py`

**问题**:
- 第 76 行: `__exit__` 参数使用 `Any`
- 第 191 行: 装饰器 `*args: Any, **kwargs: Any`（如存在）

**验收标准**:
- `__exit__` 签名使用标准类型: `(exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> None`
- `traced` 装饰器使用 `ParamSpec` 保留签名
- 通过 `pixi run -e dev type` 检查

**修复示例**:
```python
# ❌ 当前
from typing import Any

def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
    pass

# ✅ 改进
from types import TracebackType
from typing import Type

def __exit__(
    self,
    exc_type: Type[BaseException] | None,
    exc_val: BaseException | None,
    exc_tb: TracebackType | None,
) -> None:
    if exc_type is not None:
        current = trace.get_current_span()
        if current.is_recording():
            current.record_exception(exc_val)
    # ... 退出逻辑
```

---

### Task 1.3: observability/config.py type:ignore 修复 `[S]`

**文件**: `packages/foundation/src/ditto_foundation/observability/config.py:122-139`

**问题**: 5 处 `# type: ignore[arg-type]`

**验收标准**:
- `_resolve` 函数无需 type:ignore
- 使用 TypeGuard 或 `final` 函数类型收窄
- 补充三级优先级测试

**修复方案 1**（推荐 - TypeGuard）:
```python
from typing import final, TypeGuard

@final
def _is_set(value: bool | None) -> TypeGuard[bool]:
    """类型守卫，确保返回 True 时 value 为 bool"""
    return value is not None

def _resolve(
    local: bool | None,
    preset: bool | None,
    default: bool = False,
) -> bool:
    if _is_set(local):
        return local  # 无需 type: ignore
    if _is_set(preset):
        return preset
    return default
```

---

### Task 1.4: 识别合理的 `except Exception`（添加注释）`[S]`

**文件**:
- `packages/foundation/src/ditto_foundation/observability/__init__.py:172`
- `packages/foundation/src/ditto_foundation/observability/testing.py:19`

**操作**: 添加 `# noqa: S110` 注释说明设计意图
```python
except Exception as e:  # noqa: S110 - 优雅关闭失败不应中断主流程
    logger.debug(f"Graceful shutdown completed with warnings: {e}")
```

---

## 阶段 2：P1 质量改进（1周）

### Task 2.1: VictoriaMetrics endpoint 环境变量化 `[S]`

**文件**: `packages/foundation/src/ditto_foundation/observability/config.py:26`

**验收标准**:
- 支持环境变量 `OBSERVABILITY_VM_ENDPOINT` 覆盖
- 默认值保持不变（`http://localhost:8428/opentelemetry/v1/metrics`）
- 测试验证环境变量覆盖逻辑

**修复方案**:
```python
vm_endpoint: str = Field(
    default_factory=lambda: os.getenv(
        "OBSERVABILITY_VM_ENDPOINT",
        "http://localhost:8428/opentelemetry/v1/metrics"
    ),
    description="VictoriaMetrics 指标推送端点"
)
```

---

### Task 2.2: dq_batch.py 复杂度评估 `[S]`

**文件**: `apps/port/src/ditto_port/jobs/tasks/dq_batch.py:22`

**评估**:
- 函数是否确实超过复杂度阈值？
- 是否可以拆分为子函数？
- 拆分是否影响可读性？

**决策**: 如果拆分降低可读性，保留并添加注释说明

---

## 阶段 3：P2 优化（可选）

### Task 3.1: 数据写入工厂模式 `[M]`

**文件**: `apps/port/src/ditto_port/services/ingestion/data_writer.py:65-138`

**验收标准**:
- 引入 `DataWriterFactory` 注册表模式
- 新增数据集类型只需注册，无需修改主逻辑
- 测试覆盖率不下降

---

## 验证命令
```bash
# 异常处理检查
pixi run -e dev python -c "
import re
from pathlib import Path
count = 0
for f in Path('packages').rglob('*.py'):
    if 'test' in f.parts: continue
    content = f.read_text(encoding='utf-8')
    if 'except Exception' in content:
        count += content.count('except Exception')
print(f'except Exception count: {count}')
"
# 目标: 通知渠道文件无宽泛捕获

# 类型检查
pixi run -e dev type          # 0 errors

# Lint 检查
pixi run -e dev lint          # 通过

# 测试
pixi run -e dev test --fast   # 通过
```

### 最终验证
```bash
pixi run -e dev ci
# 目标: 所有检查通过
```

---

## 关键文件清单

### Critical Files

| 文件 | 原因 |
|------|------|
| `packages/foundation/src/ditto_foundation/observability/tracing.py` | 核心装饰器类型注解修复 |
| `packages/foundation/src/ditto_foundation/observability/config.py` | type:ignore 修复 + VM endpoint |
| `packages/foundation/src/ditto_foundation/notification/channels/webhook.py` | 异常处理模式模板 |
| `packages/datahub/src/ditto_datahub/stores/security_store.py` | Store 层异常处理 |
| `packages/foundation/tests/unit/observability/test_tracing_decorator_unit.py` | 测试补充模板 |

### 不应修改的文件

| 文件 | 原因 |
|------|------|
| `apps/port/src/ditto_port/registry/datahub.py:283` | Dishka Provider 固有模式，PLR0913 可接受 |

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 异常处理重构引入新 bug | 先运行现有测试确保基线正常 |
| 类型修改破坏现有功能 | 通过 pyright 类型检查验证 |
