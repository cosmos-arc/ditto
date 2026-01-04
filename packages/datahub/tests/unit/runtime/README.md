# Runtime 单元测试

## 测试覆盖

Runtime 单元测试覆盖运行时基础设施的核心功能。

| 测试文件 | 测试内容 |
|----------|----------|
| `test_cache.py` | 数据缓存 |
| `test_cache_ttl.py` | 缓存 TTL |
| `test_fake_time.py` | 假时间 |
| `test_file_lock.py` | 文件锁 |
| `test_pit_helper.py` | PIT 辅助函数 |
| `test_pit_helper_property.py` | PIT 辅助 Property 测试 |

## 测试内容

### 数据缓存（test_cache.py）

**测试内容**：
- 缓存读写
- 缓存过期
- 缓存统计
- 缓存容量限制

**测试场景**：
1. 基本读写操作
2. 缓存未命中返回默认值
3. 缓存统计（命中率）
4. 缓存失效
5. 缓存容量限制
6. 缓存清理

### 缓存 TTL（test_cache_ttl.py）

**测试内容**：
- TTL 过期
- TTL 刷新
- TTL 滑动窗口

**测试场景**：
1. 缓存项过期
2. 访问时刷新 TTL
3. 滑动窗口 TTL
4. 批量过期检查

### 假时间（test_fake_time.py）

**测试内容**：
- 时间控制
- 时间加速
- 时间回拨

**测试场景**：
1. 替换 time.sleep
2. 替换 time.time
3. 时间加速
4. 时间一致性

### 文件锁（test_file_lock.py）

**测试内容**：
- 文件锁获取
- 文件锁释放
- 文件锁超时
- 文件锁并发

**测试场景**：
1. 获取文件锁
2. 释放文件锁
3. 锁超时处理
4. 并发锁竞争
5. 上下文管理器

### PIT 辅助函数（test_pit_helper.py）

**测试内容**：
- Knowledge Date 计算
- 游标管理
- PIT 数据查询

**测试场景**：
1. 计算 Knowledge Date
2. 更新游标
3. 查询 PIT 数据
4. 验证 PIT 原则

### PIT 辅助 Property 测试（test_pit_helper_property.py）

**测试内容**：
- 基于 Hypothesis 的 Property-based 测试
- 随机日期生成
- Knowledge Date 验证

**测试场景**：
1. 随机日期 Knowledge Date 计算
2. 边界日期验证
3. Property 验证

## 运行测试

### 运行所有 Runtime 单元测试

```bash
pixi run -e dev pytest packages/datahub/tests/unit/runtime -v
```

### 运行特定测试文件

```bash
# 缓存
pixi run -e dev pytest packages/datahub/tests/unit/runtime/test_cache.py -v

# 缓存 TTL
pixi run -e dev pytest packages/datahub/tests/unit/runtime/test_cache_ttl.py -v

# 假时间
pixi run -e dev pytest packages/datahub/tests/unit/runtime/test_fake_time.py -v

# 文件锁
pixi run -e dev pytest packages/datahub/tests/unit/runtime/test_file_lock.py -v

# PIT 辅助
pixi run -e dev pytest packages/datahub/tests/unit/runtime/test_pit_helper.py -v

# PIT Property 测试
pixi run -e dev pytest packages/datahub/tests/unit/runtime/test_pit_helper_property.py -v
```

### 运行特定测试函数

```bash
pixi run -e dev pytest packages/datahub/tests/unit/runtime/test_cache.py::test_set_and_get -v
```

## Fake Time Fixture

使用 `fake_time` fixture 进行时间控制测试：

```python
def test_with_fake_time(fake_time):
    """使用 fake_time fixture"""
    # time.sleep 立即完成
    # time.time 按预期前进
    cache = DataCache(ttl_seconds=1)
    cache.set("key", "value")
    time.sleep(2)  # 立即完成
    assert cache.get("key") is None  # 已过期
```

## Property-based 测试

使用 Hypothesis 进行 PIT Property 测试：

```python
from hypothesis import given, strategies as st

@given(st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31)))
def test_knowledge_date_property(trade_date):
    """Knowledge Date 应该是 Trade Date + 1"""
    knowledge_date = calculate_knowledge_date(trade_date)
    expected = trade_date + timedelta(days=1)
    assert knowledge_date == expected
```

## 预期结果

所有测试应该：

1. **缓存正确工作**：读写、过期、统计正确
2. **时间控制正确**：时间加速、回拨正确
3. **文件锁正确工作**：获取、释放、超时正确
4. **PIT 原则正确**：Knowledge Date 计算正确

## 相关文档

- [DataHub 单元测试总览](../README.md)
- [PIT 数据安全](../../../../../.claude/rules/pit.md)
