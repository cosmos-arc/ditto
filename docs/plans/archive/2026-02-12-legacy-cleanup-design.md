# 遗留代码清理计划

## 概述

清理项目中不再需要的兼容性代码、过时配置和重复 TODO。项目处于开发期，无需维护向后兼容。

## 清理清单

### Phase 1: 删除废弃文件（P1）

#### 1.1 删除 `registry/app.py`

**原因**：空的兼容性类，无外部使用

| 操作 | 文件 |
|------|------|
| 删除 | `apps/port/src/ditto_port/registry/app.py` |
| 修改 | `apps/port/src/ditto_port/registry/__init__.py` - 移除 AppProvider 导入 |

**修改详情**：

`registry/__init__.py` 修改前：
```python
from ditto_port.registry.app import AppProvider
from ditto_port.registry.config import ConfigProvider
# ...

__all__ = [
    "AppProvider",  # 移除此行
    "ConfigProvider",
    # ...
]
```

修改后：
```python
from ditto_port.registry.config import ConfigProvider
# ...

__all__ = [
    "ConfigProvider",
    # ...
]
```

#### 1.2 删除 `.pyrightignore`

**原因**：所有引用的文件已不存在

| 操作 | 文件 |
|------|------|
| 删除 | `packages/data/.pyrightignore` |

**当前内容**（全部过时）：
```
src/ditto_data/domains/market/stock/adj/adj_factor_store.py  # 不存在
packages/data/src/ditto_data/stores/adj_factor_store.py   # 不存在
src/ditto_data/domains/market/market_query_service.py        # 不存在
```

---

### Phase 2: 统一 TODO 注释（P2）

#### 2.1 合并重复告警 TODO

**现状**：3 处重复的告警发送 TODO

| 文件 | 建议 |
|------|------|
| `reconciliation_service.py:244` | 保留（主实现位置） |
| `l3_batch_service.py:231` | 删除（重复） |
| `dq_batch.py:190` | 删除（重复） |

**操作**：
1. 在 `reconciliation_service.py` 保留 TODO 并增强描述
2. 删除 `l3_batch_service.py:231` 和 `dq_batch.py:190` 的重复 TODO
3. （可选）创建 GitHub Issue 跟踪

#### 2.2 保留的功能 TODO

| 文件 | 内容 | 状态 |
|------|------|------|
| `capital.py:602` | 数据源 report_date 增强 | 保留 |
| `source.py:109` | 批量查询性能优化 | 保留 |

---

### Phase 3: 源码 type: ignore 评估（P3 - 可选）

**位置**：`apps/port/src/ditto_port/jobs/flows/deploy.py`

**当前状态**：3 处 `type: ignore`，都有清晰注释说明原因

**结论**：保留现状（合理使用，重构收益小）

---

## 实施步骤

### Step 1: 删除 app.py 和更新 __init__.py
```bash
# 删除废弃文件
rm apps/port/src/ditto_port/registry/app.py

# 编辑 __init__.py 移除 AppProvider
```

### Step 2: 删除 .pyrightignore
```bash
rm packages/data/.pyrightignore
```

### Step 3: 清理重复 TODO
- 删除 `l3_batch_service.py:231` 的 TODO
- 删除 `dq_batch.py:190` 的 TODO

### Step 4: 验证
```bash
pixi run -e dev check
```

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 删除 AppProvider | 无 | 搜索确认无外部引用 |
| 删除 .pyrightignore | 无 | 文件内容已全部过时 |
| 清理 TODO | 低 | 仅删除重复项 |

---

## 预期结果

| 指标 | 清理前 | 清理后 |
|------|--------|--------|
| 废弃文件 | 1 个 | 0 个 |
| 过时配置 | 1 个 | 0 个 |
| 重复 TODO | 3 处 | 1 处 |
| 源码 type:ignore | 3 处 | 3 处（保留） |
