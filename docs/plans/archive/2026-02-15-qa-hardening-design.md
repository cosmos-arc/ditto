# QA 加固设计文档

> 目标：将代码质量评分从 88 分提升至满分

## 概述

本轮修复聚焦于4个具体问题（CLI 副作用隔离单独处理）：

| 优先级 | 问题 | 工作量 | 状态 |
|--------|------|--------|------|
| P0 | project_root 最近命中策略 | S | ✅ 完成 |
| P1 | conftest no-op fixture | S | ✅ 完成 |
| P1 | conftest 废弃兼容代码 | S | ✅ 完成 |
| P2 | runtime_flags 强类型 | S | ✅ 完成 |

---

## P0: project_root 最近命中策略

### 问题

当前实现遍历所有父目录，记录每个 marker 的**最后一个**命中目录。在嵌套工作区场景下，这会导致返回外层路径。

**复现场景**：外层和内层都存在 `pixi.toml` 时，返回外层路径。

### 实际修复方案

**优先级 + 最近命中**：按 marker 优先级顺序查找，同 marker 多层时返回最近的。

```python
def find_project_root(start: Path | None = None) -> Path:
    path = (start or Path(__file__)).resolve()

    # 按 marker 优先级顺序查找，找到即返回（同 marker 多层时返回最近的）
    for marker in _ROOT_MARKERS:
        for parent in path.parents:
            if (parent / marker).exists():
                return parent

    raise RuntimeError(f"Cannot find project root from {path}")
```

### 测试补充

新增测试用例：同 marker 多层嵌套。

### 文件修改

| 文件 | 操作 |
|------|------|
| `packages/infra/src/ditto_infra/foundation/config/project_root.py` | 修改实现 |
| `packages/infra/tests/unit/config/test_project_root_unit.py` | 新增测试 |

---

## P1: conftest no-op fixture

### 问题

两个 CLI 测试目录的 `conftest.py` 中，fixture 签名是 `Generator` 但实现是 `return`。

### 实际修复方案

改为 `-> None` 返回类型，保持空操作实现：

```python
@pytest.fixture(autouse=True)
def reset_observability() -> None:
    """CLI 测试不重置 observability，避免 I/O 冲突."""
    # 空操作：覆盖父级 fixture，不做任何事
```

### 文件修改

| 文件 | 操作 |
|------|------|
| `apps/port/tests/unit/cli/conftest.py` | 修改 |
| `apps/port/tests/integration/cli/conftest.py` | 修改 |

---

## P1: conftest 废弃兼容代码

### 分析

| Fixture | 引用数 | 决策 |
|---------|--------|------|
| `app_ctx` | 7 (test_factory_unit.py) | 保留 |
| `mock_hub` | 0（局部变量同名不相关） | 删除 |

### 文件修改

| 文件 | 操作 |
|------|------|
| `apps/port/tests/unit/conftest.py` | 删除 mock_hub + 删除 app_ctx 中的废弃 DataSource mock |

---

## P2: runtime_flags 强类型

### 问题

当前使用 `dict[str, bool]`，字符串 key 耦合，缺少编译期约束。

### 实际修复方案

引入 `RuntimeFlags` dataclass（私有定义在 config.py）：

```python
@dataclass(frozen=True)
class RuntimeFlags:
    """运行时标志。"""
    pytest_running: bool
    assertions_enabled: bool
    verbose_logging: bool
```

### 文件修改

| 文件 | 操作 |
|------|------|
| `apps/port/src/ditto_port/registry/infra/config.py` | 定义 RuntimeFlags，修改返回类型 |
| `apps/port/src/ditto_port/registry/infra/observability.py` | 使用 RuntimeFlags 类型，属性访问 |

---

## 验证清单

- [x] `pixi run -e dev check` 通过（1695 passed）
- [x] arch-check 全绿（6 kept, 0 broken）
- [x] 新增测试覆盖同 marker 嵌套场景
- [x] 无废弃代码残留

---

## 排除项

以下内容不在本轮修复范围（单独处理）：

- **CLI 测试副作用隔离**：需要更深入的 Prefect/日志线程隔离设计
