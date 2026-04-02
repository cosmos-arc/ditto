# Tushare 端到端集成测试

## 概述

此目录包含 Tushare 数据源的端到端集成测试，用于验证完整的 Tushare API 调用流程。

## 测试内容

| 测试文件 | 测试内容 | API 调用 |
|---------|---------|---------|
| `test_end_to_end.py` | 完整数据流验证 | trade_cal, stock_basic, daily, fund_basic, fund_daily, adj_factor, fund_adj, stk_limit, stock_st, suspend_d |

### 测试场景

1. **test_end_to_end_tushare_ingestion**: 完整的数据获取流程
   - Calendar 获取
   - Stock Basic 获取
   - Stock Daily 获取
   - Schema 验证
   - OHLC 逻辑验证

2. **test_etf_end_to_end_tushare_ingestion**: ETF 数据获取
   - ETF Basic 获取
   - ETF Daily 获取

3. **test_adj_factor_end_to_end**: 复权因子数据获取
   - Stock Adj Factor 获取
   - Fund Adj 获取
   - Knowledge Date 验证

4. **test_stock_limit_and_status**: 涨跌停价和股票状态
   - Stock Limit 获取
   - Stock Status 获取

5. **test_rate_limiting_respected**: 限流机制验证
   - 连续多次调用
   - 验证限流生效

6. **test_error_handling_invalid_token**: 错误处理验证
   - 无效 token 异常

7. **test_data_consistency_multiple_calls**: 数据一致性验证
   - 多次调用一致性

## 前置条件

### 1. TUSHARE_TOKEN 环境变量

这些测试需要有效的 Tushare Token。设置方式：

```bash
# Linux/macOS
export TUSHARE_TOKEN="your_token_here"

# Windows (PowerShell)
$env:TUSHARE_TOKEN="your_token_here"

# Windows (CMD)
set TUSHARE_TOKEN=your_token_here
```

或者在 `.env` 文件中设置（推荐本地开发）：

```bash
# .env
TUSHARE_TOKEN=your_token_here
```

### 2. 网络连接

测试需要访问 `http://api.tushare.pro`

## 运行测试

### 手动运行（需要 Token）

```bash
# 只运行 external 标记的测试
pytest packages/datahub/tests/integration/sources/tushare/test_end_to_end.py -m external -v

# 运行所有集成测试（包括 external）
pytest packages/datahub/tests/integration/sources/tushare/test_end_to_end.py -v

# 运行特定测试
pytest packages/datahub/tests/integration/sources/tushare/test_end_to_end.py::TestTushareEndToEnd::test_end_to_end_tushare_ingestion -m external -v
```

### CI 运行（跳过 external）

```bash
# 默认跳过 external 测试
pytest packages/datahub/tests/integration/sources/tushare/test_end_to_end.py -m "not external" -v
```

## 预期结果

所有测试应该：

1. **成功获取数据**: API 调用返回非空数据
2. **Schema 正确**: 数据结构符合预期
3. **数据逻辑正确**:
   - High >= Low
   - 日期格式正确
   - knowledge_date = trade_date（复权因子）
4. **错误处理正确**: 无效 token 抛出认证错误

## 故障排查

### 测试失败：认证错误

```
ditto_data.sources.base.SourceAuthenticationError: Failed to authenticate with Tushare
```

**解决方案**：
1. 检查 `TUSHARE_TOKEN` 是否正确设置
2. 验证 token 是否有效
3. 检查 token 是否过期

### 测试失败：网络错误

```
httpx.ConnectError: Error connecting to http://api.tushare.pro
```

**解决方案**：
1. 检查网络连接
2. 确认可以访问 `http://api.tushare.pro`
3. 检查防火墙/代理设置

### 测试失败：数据为空

```
AssertionError: Stock daily 数据不应为空
```

**解决方案**：
1. 确认测试使用的日期是交易日
2. 检查 Tushare 账户是否有相应权限
3. 查看日志获取更多信息

## 注意事项

1. **API 限流**: Tushare 免费账户限流 200次/分钟
2. **账户权限**: 某些 API 需要积分权限
3. **交易日**: 测试使用的日期应该是交易日
4. **Token 安全**: 不要将 token 提交到代码库

## 相关文档

- [Tushare HTTP 重构计划](../../../../../docs/plans/2026-01-03-tushare-http-refactor.md)
- [Tushare API 文档](https://tushare.pro/document/2)
