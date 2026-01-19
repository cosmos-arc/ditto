# Sources 单元测试

## 测试覆盖

Sources 单元测试覆盖数据源客户端的核心功能。

| 测试文件 | 测试内容 |
|----------|----------|
| `test_provider.py` | 数据提供器 |
| `test_base.py` | 数据源基类 |
| `tushare/test_client.py` | Tushare 客户端 |
| `tushare/test_http_utils.py` | HTTP 工具函数 |
| `tushare/test_rate_limiter.py` | 限流器 |
| `tushare/test_source.py` | Tushare 数据源 |

## 测试内容

### 数据提供器（test_provider.py）

**测试内容**：
- 列访问
- 表达式访问
- 类型转换
- 嵌套访问

**测试场景**：
1. 访问 DataFrame 列
2. 访问嵌套字段
3. 类型自动转换
4. 错误处理

### 数据源基类（test_base.py）

**测试内容**：
- 数据源初始化
- 认证处理
- 错误处理
- 重试逻辑

**测试场景**：
1. 初始化数据源
2. 处理认证错误
3. 处理网络错误
4. 重试机制验证

### Tushare 客户端（tushare/test_client.py）

**测试内容**：
- HTTP 请求
- 响应解析
- 错误处理
- Token 管理

**测试场景**：
1. 发送 HTTP 请求
2. 解析 JSON 响应
3. 处理 API 错误
4. Token 验证

### HTTP 工具函数（tushare/test_http_utils.py）

**测试内容**：
- URL 构建
- 请求参数处理
- 响应验证
- 错误解析

**测试场景**：
1. 构建 API URL
2. 处理请求参数
3. 验证响应格式
4. 解析错误消息

### 限流器（tushare/test_rate_limiter.py）

**测试内容**：
- 限流逻辑
- 速率计算
- 等待时间
- 并发限流

**测试场景**：
1. 单线程限流
2. 多线程限流
3. 速率计算验证
4. 等待时间验证

### Tushare 数据源（tushare/test_source.py）

**测试内容**：
- 数据获取
- 数据转换
- Schema 验证
- PIT 处理

**测试场景**：
1. 获取交易日历
2. 获取股票列表
3. 获取日行情
4. 数据转换验证
5. Knowledge Date 设置

## 运行测试

### 运行所有 Sources 单元测试

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources -v
```

### 运行 Tushare 测试

```bash
# 所有 Tushare 测试
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare -v

# 特定测试文件
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/test_client.py -v
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/test_rate_limiter.py -v
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/test_source.py -v
```

### 运行特定测试函数

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/test_rate_limiter.py::test_rate_limiting -v
```

## Mock 使用

### Mock HTTP 请求（respx）

```python
import respx

def test_tushare_client(respx_mock):
    """Mock Tushare API 响应"""
    respx_mock.post("https://api.tushare.pro").mock(
        return_value=httpx.Response(200, json={
            "code": 0,
            "msg": None,
            "data": {"items": [...]}
        })
    )

    client = TushareClient(token="test_token")
    result = client.call_api("daily", params={...})
    assert result is not None
```

### Mock 限流器

```python
def test_with_mock_rate_limiter(mocker):
    """Mock 限流器"""
    mock_limiter = mocker.Mock()
    mock_limiter.acquire.return_value = True

    source = TushareSource(rate_limiter=mock_limiter)
    source.fetch_daily(...)
    mock_limiter.acquire.assert_called()
```

### Mock 时间（fake_time）

```python
def test_rate_limiting_with_fake_time(fake_time):
    """使用 fake_time 测试限流"""
    limiter = RateLimiter(max_calls=10, period=60)

    for i in range(10):
        limiter.acquire()  # 前 10 次成功

    # 第 11 次需要等待
    time.sleep(60)  # fake_time 立即完成
    limiter.acquire()  # 成功
```

## 预期结果

所有测试应该：

1. **HTTP 请求正确**：请求参数、URL 正确
2. **响应解析正确**：JSON 解析、数据提取正确
3. **限流正确工作**：速率限制逻辑正确
4. **数据转换正确**：Schema 转换、PIT 处理正确
5. **错误处理正确**：各种错误情况正确处理

## 相关文档

- [DataHub 单元测试总览](../README.md)
- [Sources 集成测试](../../integration/sources/README.md)
