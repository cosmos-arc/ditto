# DataHub 集成测试

## 测试覆盖范围

集成测试验证多组件协作和端到端数据流。

| 测试目录 | 测试内容 | API/依赖 |
|----------|----------|----------|
| **runtime** | 运行时集成测试 | SQLite 并发、文件锁、冻结管理器 |
| **sources** | 数据源 E2E 测试 | Tushare API（需要 Token） |
| **stores** | 存储并发测试 | Parquet Store 并发写入 |

## 集成测试场景

### Runtime 集成测试

| 测试文件 | 测试内容 |
|----------|----------|
| `test_freeze_manager.py` | 冻结管理器创建、恢复、校验和 |
| `test_freeze_manager_checksum.py` | 冻结数据校验和验证 |
| `test_instrument_id_allocator.py` | Instrument ID 分配器并发分配和回收 |
| `test_sqlite_pool.py` | SQLite 连接池并发访问 |
| `test_sql_engine.py` | SQL 引擎查询执行 |
| `test_sql_engine_injection.py` | SQL 注入防护 |

### Sources 集成测试

| 测试文件 | 测试内容 | 标记 |
|----------|----------|------|
| `test_end_to_end.py` | Tushare E2E 数据获取 | `external` |

测试场景：
- Calendar 获取
- Stock Basic 获取
- Stock Daily 获取
- Schema 验证
- OHLC 逻辑验证
- ETF 数据获取
- 复权因子数据获取
- 限流机制验证
- 错误处理验证

### Stores 集成测试

| 测试文件 | 测试内容 |
|----------|----------|
| `test_calendar_store_concurrent.py` | 交易日历并发写入 |
| `test_pipeline_store.py` | 数据管道状态管理 |
| `test_quarantine_store.py` | 隔离数据存储 |

## 数据要求

### Runtime 测试

- 使用临时目录（自动清理）
- 并发测试需要多线程/多进程

### Sources 测试（Tushare）

**前置条件**：
1. 设置 `TUSHARE_TOKEN` 环境变量
2. 网络可访问 `http://api.tushare.pro`
3. Token 有相应 API 权限

```bash
# Linux/macOS
export TUSHARE_TOKEN="your_token_here"

# Windows (PowerShell)
$env:TUSHARE_TOKEN="your_token_here"
```

### Stores 测试

- 使用临时 Parquet 文件
- 并发写入测试（多线程）

## 运行测试

### 运行所有集成测试（跳过 external）

```bash
pixi run -e dev pytest packages/datahub/tests/integration -m "not external" -v
```

### 运行特定目录

```bash
# Runtime 集成测试
pixi run -e dev pytest packages/datahub/tests/integration/runtime -v

# Stores 集成测试
pixi run -e dev pytest packages/datahub/tests/integration/stores -v
```

### 运行 External 测试（手动）

```bash
# 需要 TUSHARE_TOKEN
pixi run -e dev pytest packages/datahub/tests/integration/sources/tushare/test_end_to_end.py -m external -v
```

### 运行特定测试

```bash
# 特定测试文件
pixi run -e dev pytest packages/datahub/tests/integration/runtime/test_freeze_manager.py -v

# 特定测试函数
pixi run -e dev pytest packages/datahub/tests/integration/runtime/test_freeze_manager.py::TestFreezeManager::test_create_freeze_generates_manifest_with_checksums -v
```

### 并发测试

```bash
# 运行并发测试（可能较慢）
pixi run -e dev pytest packages/datahub/tests/integration -m "not external" -v --numprocesses=auto
```

## 预期结果

所有集成测试应该：

1. **成功完成端到端流程**
2. **多组件正确协作**
3. **并发安全性验证通过**
4. **数据一致性验证通过**
5. **错误处理正确**

## 故障排查

### Tushare 测试失败

```
ditto_datahub.sources.base.SourceAuthenticationError: Failed to authenticate with Tushare
```

**解决方案**：
1. 检查 `TUSHARE_TOKEN` 是否正确设置
2. 验证 token 是否有效
3. 检查 token 是否过期

### 并发测试失败

```
AssertionError: Concurrent writes resulted in data loss
```

**解决方案**：
1. 检查文件锁实现
2. 验证并发控制逻辑
3. 确认测试环境支持并发

## 相关文档

- [DataHub 测试框架总览](../README.md)
- [Runtime 集成测试](runtime/README.md)
- [Sources 集成测试](sources/README.md)
- [Stores 集成测试](stores/README.md)
