# ADR-013: ts_rank 精度策略

**状态**: 已决策（2026-03-05）

---

## 背景

`ts_rank(x, n)` 计算当前值在过去 n 个值中的排名（归一化到 0-1）。对于长周期（如 n=250），有两种实现策略：
1. 精确计算：维护完整窗口，100% 精确
2. 近似计算：使用 T-Digest 或 GK Summary，空间效率高但有误差

---

## 决策

**始终精确计算**

---

## 理由

| 维度 | 精确计算 | 近似计算 | 结论 |
|------|---------|---------|------|
| **因子精度敏感** | 100% 精确 | ε-近似（误差 1-5%） | 精确胜出 |
| **状态大小** | n 个 float（2KB @ n=250） | 100-200 bytes | 都可接受 |
| **与业界一致** | DolphinDB 精确 | Spark SQL 近似 | 精确胜出 |
| **实现复杂度** | 简单 | 需要额外依赖 | 精确胜出 |
| **内存估算** | 5000×5×2KB = 50MB | 5000×5×0.2KB = 5MB | 50MB 可接受 |

---

## 内存估算

```
场景：5000 只 A 股，5 个不同窗口的 ts_rank

精确计算：
  单状态：250 float × 8 bytes = 2 KB
  总计：5000 标的 × 5 窗口 × 2 KB = 50 MB

Kvrocks 容量（来自 11.4.2.1 估算）：~11 MB
实际使用：50 MB 在 Kvrocks 可承受范围内（磁盘存储）
```

---

## 近似算法调研结论

| 算法 | 空间复杂度 | 适用场景 | Ditto 适用性 |
|------|-----------|---------|-------------|
| **Greenwald-Khanna** | O((1/ε) log(εn)) | 无界数据流 | ❌ ts_rank 是有界窗口 |
| **T-Digest** | O(1/δ) | 分布式、尾部精度 | ❌ 因子计算不需要分布式合并 |
| **精确 + sortedcontainers** | O(n) | 固定窗口、精度敏感 | ✅ 采用 |

**关键洞察**: `ts_rank(x, n)` 是**有界窗口**问题，而非无界数据流问题。近似算法（GK、T-Digest）是为无界流设计的，在有界窗口场景下收益有限。

---

## 实现

```python
from sortedcontainers import SortedList
from collections import deque

@dataclass
class TSRankState:
    """ts_rank 精确计算状态"""
    window: deque[float] = field(default_factory=deque)
    sorted_values: SortedList = field(default_factory=SortedList)

    def update(self, new_value: float, window_size: int) -> float:
        """
        增量更新排名

        Args:
            new_value: 新值
            window_size: 窗口大小

        Returns:
            当前排名（0-1 归一化）
        """
        # 淘汰旧值
        if len(self.window) >= window_size:
            old_value = self.window.popleft()
            self.sorted_values.discard(old_value)

        # 插入新值
        self.window.append(new_value)
        self.sorted_values.add(new_value)

        # 计算排名（0-1 归一化）
        rank = self.sorted_values.bisect_left(new_value)
        return rank / len(self.sorted_values) if self.sorted_values else 0.0

    def to_bytes(self) -> bytes:
        """序列化用于 Kvrocks 存储"""
        return orjson.dumps({
            "window": list(self.window),
            # sorted_values 从 window 重建，无需存储
        })

    @classmethod
    def from_bytes(cls, data: bytes) -> "TSRankState":
        """从 Kvrocks 反序列化"""
        obj = orjson.loads(data)
        window = deque(obj["window"])
        sorted_values = SortedList(window)
        return cls(window=window, sorted_values=sorted_values)
```

---

## 边界情况处理

| 场景 | 处理方式 |
|------|---------|
| 窗口内数据不足 n 个 | 使用当前已有数据计算排名 |
| 窗口内所有值相同 | 返回 0.5（中位数排名） |
| 空值处理 | 跳过空值，不参与排名计算 |
| 重复值 | 使用 bisect_left，相同值取最小排名 |

---

## 业界对标

| 平台 | ts_rank 实现 | 精度 | Ditto 选择 |
|------|-------------|------|-----------|
| DolphinDB | mrank（精确 + 增量优化） | 100% | ✓ 采用 |
| WorldQuant Brain | 精确计算 | 100% | ✓ 一致 |
| Qlib | 精确计算 + 缓存 | 100% | ✓ 一致 |
