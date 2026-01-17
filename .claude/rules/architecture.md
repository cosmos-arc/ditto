---
paths: ./**/*.py
---

# 架构设计规范

## 单一职责原则（SRP）

### 禁止混合职责

| ❌ 违反 SRP | ✅ 正确 |
|------------|--------|
| Protocol + Factory 混在同一文件 | `base.py`（接口）+ `factory.py`（工厂） |
| 使用 `importlib` 绕过"循环依赖" | 顶层导入 + 字典映射 |

**识别信号**：注释解释"为什么用复杂方案" → 可能是架构问题

---

## PLC0415 处理决策树

```
遇到 PLC0415
    │
    ├─ 使用 importlib？ → 检查是否真的循环（验证反向导入）
    │   ├─ 否 → 顶层导入
    │   └─ 是 → 重构架构（拆分职责）
    │
    ├─ Facade @cached_property？ → 顶层导入（延迟实例化已足够）
    │
    ├─ Pydantic computed_field？ → 在 pyproject.toml 添加 noqa
    │
    └─ 可选依赖？ → try/except + 顶层导入
```

---

## 导入规范（架构补充）

### 可选依赖处理

```python
# ✅ 正确
try:
    import keyring
except ImportError:
    keyring = None

# ❌ 错误
keyring = importlib.import_module("keyring")
```

---

## 延迟初始化

### 延迟导入 vs 延迟实例化

```python
# ❌ 不推荐（除非必要）
@cached_property
def pool(self):
    from foo import Pool  # PLC0415
    return Pool()

# ✅ 推荐
from foo import Pool

@cached_property
def pool(self):
    return Pool()  # 延迟 __init__，非延迟 import
```

**原理**：顶层导入（~1-10ms）+ 延迟实例化（~10-100ms）

---

## 工厂模式

### 简单工厂（解决 SRP 违反）

```python
# factory.py
def get_source(name: str) -> DataSource:
    sources: dict[str, type[DataSource]] = {
        "tushare": TushareSource,
    }
    return sources[name]
```

**何时使用**：根据字符串名称创建实例

---

## 案例：base.py 违反 SRP

**问题**：`get_source()` 使用 `importlib`，注释说"避免循环依赖"

**验证**：`grep -r "from.*base import" tushare/` → 无反向导入 → **不是循环依赖**

**解决**：
1. 拆分：`base.py`（接口）+ `factory.py`（工厂）
2. 顶层导入：`from tushare.source import TushareSource`
