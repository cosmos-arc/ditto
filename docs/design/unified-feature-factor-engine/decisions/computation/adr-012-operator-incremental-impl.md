# ADR-012: 算子增量实现架构

**状态**: 已决策（2026-03-05）

---

## 背景

表达式引擎需要为 52 个算子（ADR-007）提供增量计算能力。不同算子的增量实现复杂度差异巨大：
- `ts_mean` 可以用 O(1) 的滑动窗口 + 累计量实现
- `ts_rank` 需要维护有序结构，增量复杂度 O(log n)
- `ts_corr` 需要维护两个序列的协方差统计量

---

## 决策

### 1. 独立状态管理模块

延续 ADR-006 的决策，算子的增量计算逻辑通过**独立状态管理模块**实现：

```
packages/core/src/ditto_kernel/
├── expression/                 # 表达式引擎（纯计算）
│   ├── engine.py
│   └── operators.py
│
└── state/                      # 状态管理（独立模块）
    ├── manager.py              # StateManager 接口
    ├── adapters/
    │   ├── memory.py           # 内存适配器（测试用）
    │   └── kvrocks.py          # Kvrocks 适配器
    └── windows/
        ├── sliding.py          # 滑动窗口状态
        ├── incremental.py      # 增量统计状态
        └── ordered.py          # 有序结构状态
```

---

### 2. 算子 5 层分类

| Tier | 算子类型 | 状态内容 | 增量复杂度 | 状态大小 |
|------|---------|---------|-----------|---------|
| **Tier 1** | O(1) 状态 | 单值或固定大小 | O(1) | O(1) |
| | `ts_delay`, `ts_ema`, `ts_delta`, `ts_pct_change` | | | |
| **Tier 2** | 简单增量 | window + sum/sum_sq | O(1) | O(n) |
| | `ts_mean`, `ts_sum`, `ts_std`, `ts_var`, `ts_count` | | | |
| **Tier 3** | 有序结构 | window + sorted_list | O(log n) | O(n) |
| | `ts_rank`, `ts_median`, `ts_quantile`, `ts_argmax`, `ts_argmin` | | | |
| **Tier 4** | 多变量 | window_x + window_y + stats | O(1) | O(2n) |
| | `ts_corr`, `ts_cov`, `ts_regression` | | | |
| **Tier 5** | 单调队列 | window + deque | O(1)* | O(n) |
| | `ts_min`, `ts_max` | | | |

*均摊复杂度

---

### 3. 引入 sortedcontainers 依赖

对于 Tier 3 算子（需要维护有序结构），引入 `sortedcontainers` 库：

```python
from sortedcontainers import SortedList

class TSRankState:
    """ts_rank 状态 - 使用 SortedList 实现 O(log n) 增量"""
    window: deque[float]
    sorted_values: SortedList

    def update(self, new_value: float, window_size: int) -> float:
        # 淘汰旧值
        if len(self.window) >= window_size:
            old_value = self.window.popleft()
            self.sorted_values.remove(old_value)  # O(log n)

        # 插入新值
        self.window.append(new_value)
        self.sorted_values.add(new_value)  # O(log n)

        # 计算排名
        rank = self.sorted_values.bisect_left(new_value)
        return rank / len(self.sorted_values)
```

**选型对比**:

| 方案 | 复杂度 | 依赖 | 决策 |
|------|-------|------|------|
| 纯 Python + bisect | O(n) | 无 | ❌ 不采用 |
| sortedcontainers | O(log n) | 有 | ✅ 采用 |

**理由**:
- 因子计算对性能敏感，O(n) vs O(log n) 在 n=250 时差异明显
- `sortedcontainers` 是成熟的 Python 库，广泛使用，维护活跃
- 与 DolphinDB `mrank` 的 O(n log k) 复杂度对齐

---

### 4. 状态接口设计

```python
class StateManager(Protocol):
    """状态管理器接口"""

    def get(self, key: str) -> bytes | None:
        """获取状态"""
        ...

    def set(self, key: str, state: bytes, ttl: int | None = None) -> None:
        """设置状态（可选 TTL）"""
        ...

    def delete(self, key: str) -> None:
        """删除状态"""
        ...

    def update(self, key: str, fn: Callable[[bytes | None], bytes]) -> bytes:
        """原子更新状态"""
        ...
```

**Key 命名规范**:

```
ditto:{type}:{factor_signature}:{instrument_id}

示例:
ditto:ts_state:ts_mean_close_20:000001
ditto:ts_state:ts_rank_volume_10:600000
ditto:cs_slice:cs_rank:2024-03-01T14:30
```

---

## 业界对标

| 平台 | 状态管理策略 | Ditto 选择 |
|------|-------------|-----------|
| DolphinDB | 响应式状态引擎 + 内置优化 | ✓ 独立模块 + 分层状态 |
| WorldQuant Brain | DAG 执行 + 自动缓存 | ✓ 类似，状态可复用 |
| Qlib | 延迟计算 + 缓存 | ✓ 借鉴缓存策略 |
