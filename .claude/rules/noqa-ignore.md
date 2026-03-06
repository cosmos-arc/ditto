---
paths:
  - ./**/*.py
---

# noqa 和 type: ignore 使用规范

## 核心原则

**核心源码零容忍**：`packages/**/src` 和 `apps/port/**/src` 中不应有任何 `# noqa` 或 `# type: ignore`。

**测试代码适度豁免**：测试文件可使用合理豁免（已在 `pyproject.toml` 配置）。

**优先使用类型系统工具**：用 TypeGuard/Protocol/TypedDict 替代忽略。

---

## 禁止规则

### 生产代码（src）禁止项

| 规则             | 例外                     | 说明               |
| ---------------- | ------------------------ | ------------------ |
| `# noqa`         | S608/S108/S110（需注释） | 通过重构解决       |
| `# type: ignore` | 无                       | 通过类型修正解决   |
| `global` 语句    | 无                       | 使用类属性单例模式 |
| 行内导入         | 无                       | 重构解决循环依赖   |

### global 语句示例

```python
# ❌ 错误
_settings: Settings | None = None
def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

# ✅ 正确：类属性单例
class SettingsManager:
    _instance: SettingsManager | None = None
    _settings: Settings | None = None

    @classmethod
    def get_instance(cls) -> SettingsManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_settings(self) -> Settings:
        if self._settings is None:
            self._settings = Settings()
        return self._settings
```

---

## 允许的豁免

### 1. SQL 安全（S608）

```python
# ✅ 允许（需注释）
ALLOWED_TABLES = {"security", "bars"}
table = get_table_name()
if table not in ALLOWED_TABLES:
    raise ValueError(f"Invalid table: {table}")
query = f"SELECT * FROM {table}"  # noqa: S608 - table 已通过白名单验证

# ❌ 禁止（无注释）
query = f"SELECT * FROM {table}"  # noqa: S608
```

### 2. 临时目录（S108）

```python
# ✅ 允许（需注释）
temp = os.environ.get("TEMP", "/tmp")  # noqa: S108 - Windows TEMP fallback
```

### 3. 优雅关闭（S110）

```python
# ✅ 允许（需注释）
try:
    cleanup_resources()
except Exception:  # noqa: S110 - 优雅关闭不应抛异常
    pass
```

---

## TypeGuard 使用指南

### 何时使用

需要区分子类进行类型收窄时：

```python
from typing import TypeGuard, Any
from datetime import date, datetime

# 问题：isinstance 无法区分 date 和 datetime
if isinstance(value, date):  # datetime 也是 date！
    return value.strftime("%Y-%m-%d")

# 解决：TypeGuard 精确收窄
def is_pure_date(value: Any) -> TypeGuard[date]:
    """确保 value 是 date 但不是 datetime。"""
    return isinstance(value, date) and not isinstance(value, datetime)

if is_pure_date(value):  # 类型被收窄为 date
    return value.strftime("%Y-%m-%d")
```

### 常见模式

```python
# 区分具体类型
def is_str(value: Any) -> TypeGuard[str]:
    return isinstance(value, str)

# 区分联合类型
def is_positive_int(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and value > 0

# 区分 TypedDict
class ValidConfig(TypedDict):
    key: str

def is_valid_config(obj: Any) -> TypeGuard[ValidConfig]:
    return isinstance(obj, dict) and "key" in obj
```

---

## TYPE_CHECKING 使用指南

### 原则

**非必要禁止延迟导入，必须重构解决循环依赖。**

### 正确使用

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ditto_datahub.stores.bars_store import BarsStore

class BarsRepository:
    def __init__(self, store: Any):
        self._store = store

    @property
    def store(self) -> "BarsStore":
        return self._store  # type: ignore[no-any-return]
```

### 禁止使用

```python
# ❌ 错误：掩盖循环依赖
if TYPE_CHECKING:
    from module_a import ClassA  # 实际有循环依赖

class ClassB:
    def method(self) -> ClassA:
        ...
```

**正确做法**：重构架构，消除循环依赖。

---

## 修复流程

### 处理步骤

1. **理解原因**：运行 `pixi run -e dev lint` 和 `pixi run -e dev type`
2. **评估方案**（按优先级）：
   - 重构消除（优先）
   - TypeGuard/Protocol 解决
   - 配置对象简化
3. **TDD 实施**：RED → GREEN → REFACTOR
4. **验证**：
   ```bash
   pixi run -e dev lint          # 无错误（除 S608/S108/S110）
   pixi run -e dev type --all    # 0 errors
   pixi run -e dev test --fast   # 通过
   ```

### 常见问题方案

| 问题                    | 解决方案        |
| ----------------------- | --------------- |
| 参数过多（PLR0913）     | 配置对象/数据类 |
| 返回语句过多（PLR0911） | 提取辅助方法    |
| 复杂度过高（C901）      | 拆分函数        |
| 循环依赖（PLC0415）     | 重构架构        |
| global 语句（PLW0603）  | 类属性单例      |
| 类型收窄问题            | TypeGuard       |

---

## 违规检测

### CI 检查命令

```bash
# 检查 noqa（除 S608/S108/S110）
git grep "# noqa" packages/*/src apps/*/src | grep -v "S608\|S108\|S110"

# 检查 type: ignore
git grep "# type: ignore" packages/*/src apps/*/src

# 检查 global 语句
git grep "^global " packages/*/src apps/*/src
```

### 验证标准

- ✅ 核心源码 `# noqa` = 0（除 S608/S108/S110 且带注释）
- ✅ 核心源码 `# type: ignore` = 0
- ✅ 核心源码 `global` 语句 = 0
- ✅ Pyright strict 检查通过
- ✅ Ruff lint 检查通过

---

## 参考资源

- [core.md](../../.claude/rules/core.md) - Python 核心规范
- [BasedPyright Type Guards](https://docs.basedpyright.com/)
- [Ruff Rules](https://docs.astral.sh/ruff/rules/)
