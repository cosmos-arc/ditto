# Stores 集成测试

## 测试覆盖

Stores 集成测试验证存储层的并发操作和数据一致性。

| 测试文件 | 测试内容 | 标记 |
|----------|----------|------|
| `test_calendar_store_concurrent.py` | 交易日历并发写入 | `integration`, `slow` |
| `test_pipeline_store.py` | 数据管道状态管理 | `integration` |
| `test_quarantine_store.py` | 隔离数据存储 | `integration` |

## 测试场景

### 交易日历并发测试（test_calendar_store_concurrent.py）

**测试内容**：
- 多线程并发写入交易日历
- 数据一致性验证
- 文件锁机制验证
- 并发冲突处理

**测试场景**：
1. 并发写入不同日期
2. 并发写入相同日期（冲突处理）
3. 大批量并发写入
4. 并发读取和写入

### 数据管道状态测试（test_pipeline_store.py）

**测试内容**：
- 数据管道状态记录
- 状态更新和查询
- 状态历史记录
- 状态过滤和排序

**测试场景**：
1. 创建管道状态记录
2. 更新管道状态
3. 查询管道状态
4. 查询状态历史
5. 按状态过滤

### 隔离数据存储测试（test_quarantine_store.py）

**测试内容**：
- 隔离数据写入
- 隔离数据查询
- 隔离原因记录
- 隔离数据统计

**测试场景**：
1. 写入隔离数据
2. 查询隔离数据
3. 按原因过滤
4. 统计隔离数据

## 运行测试

### 运行所有 Stores 集成测试

```bash
pixi run -e dev pytest packages/datahub/tests/integration/stores -v
```

### 运行特定测试文件

```bash
# 交易日历并发测试
pixi run -e dev pytest packages/datahub/tests/integration/stores/test_calendar_store_concurrent.py -v

# 数据管道状态测试
pixi run -e dev pytest packages/datahub/tests/integration/stores/test_pipeline_store.py -v

# 隔离数据存储测试
pixi run -e dev pytest packages/datahub/tests/integration/stores/test_quarantine_store.py -v
```

### 运行特定测试函数

```bash
# 特定测试
pixi run -e dev pytest packages/datahub/tests/integration/stores/test_calendar_store_concurrent.py::test_concurrent_write_consistency -v
```

### 跳过慢速测试

```bash
# 跳过 slow 标记的测试
pixi run -e dev pytest packages/datahub/tests/integration/stores -m "not slow" -v
```

## 测试特点

### 并发测试

使用多线程模拟并发操作：

```python
import threading

def test_concurrent_write():
    store = CalendarStore(base_path=tmp_path)

    def write_dates(date_range):
        for date in date_range:
            store.save(...)

    threads = [
        threading.Thread(target=write_dates, args=(range1,))
        for _ in range(10)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 验证数据一致性
    ...
```

### 临时目录

使用 `tmp_path` fixture 创建临时目录：

```python
def test_with_temp_store(tmp_path):
    store = CalendarStore(base_path=tmp_path / "calendar")
    # 测试完成后自动清理
```

### 数据验证

使用 Polars 进行数据验证：

```python
from polars.testing import assert_frame_equal

assert_frame_equal(result, expected)
```

## 预期结果

所有测试应该：

### 1. 并发安全性

- 多线程环境下数据一致
- 无数据丢失或损坏
- 文件锁正确工作

### 2. 数据完整性

- 所有数据正确写入
- 数据结构符合预期
- Schema 验证通过

### 3. 性能表现

- 并发操作不阻塞
- 写入速度合理
- 内存使用可控

## 故障排查

### 并发测试失败

```
AssertionError: Concurrent writes resulted in data loss
```

**解决方案**：
1. 检查文件锁实现
2. 验证并发控制逻辑
3. 增加测试超时时间
4. 检查线程安全性

### 文件系统错误

```
OSError: [Errno 36] File name too long
```

**解决方案**：
1. 检查分区路径长度
2. 使用更短的测试数据
3. 临时目录位置优化

### 数据验证失败

```
SchemaError: Expected column 'date' not found
```

**解决方案**：
1. 检查数据 Schema
2. 验证数据转换逻辑
3. 确认数据类型正确

## 相关文档

- [DataHub 集成测试总览](../README.md)
- [Stores 单元测试](../../unit/stores/README.md)
