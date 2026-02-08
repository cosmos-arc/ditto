# Runtime 集成测试

## 测试覆盖

Runtime 集成测试验证运行时基础设施的多组件协作。

| 测试文件 | 测试内容 | 标记 |
|----------|----------|------|
| `test_freeze_manager.py` | 冻结管理器创建、恢复、校验和 | `integration` |
| `test_freeze_manager_checksum.py` | 冻结数据校验和验证（MD5/SHA256） | `integration` |
| `test_instrument_id_allocator.py` | Instrument ID 分配器并发分配和回收 | `integration` |
| `test_sqlite_pool.py` | SQLite 连接池并发访问 | `integration` |
| `test_sql_engine.py` | SQL 引擎查询执行 | `integration` |
| `test_sql_engine_injection.py` | SQL 注入防护 | `integration` |

## 测试场景

### 冻结管理器（FreezeManager）

**测试内容**：
- 创建冻结清单（manifest）
- 文件校验和计算（MD5/SHA256）
- 恢复冻结数据
- 验证冻结数据完整性
- 冻结元数据管理

**测试文件**：
- `test_freeze_manager.py` - 基础功能测试
- `test_freeze_manager_checksum.py` - 校验和验证

### Instrument ID 分配器（InstrumentIdAllocator）

**测试内容**：
- 并发 Instrument ID 分配
- Instrument ID 回收和重用
- 分配器状态管理
- 线程安全性

**测试文件**：
- `test_instrument_id_allocator.py`

### SQLite 连接池（SQLitePool）

**测试内容**：
- 并发连接获取和释放
- 连接池大小限制
- 连接超时处理
- 线程安全性

**测试文件**：
- `test_sqlite_pool.py`

### SQL 引擎（SQLEngine）

**测试内容**：
- SQL 查询执行
- 结果集处理
- SQL 注入防护
- 参数化查询

**测试文件**：
- `test_sql_engine.py`
- `test_sql_engine_injection.py`

## 运行测试

### 运行所有 Runtime 集成测试

```bash
pixi run -e dev pytest packages/datahub/tests/integration/runtime -v
```

### 运行特定测试文件

```bash
# 冻结管理器
pixi run -e dev pytest packages/datahub/tests/integration/runtime/test_freeze_manager.py -v

# Instrument ID 分配器
pixi run -e dev pytest packages/datahub/tests/integration/runtime/test_instrument_id_allocator.py -v

# SQLite 连接池
pixi run -e dev pytest packages/datahub/tests/integration/runtime/test_sqlite_pool.py -v
```

### 运行特定测试函数

```bash
# 特定测试
pixi run -e dev pytest packages/datahub/tests/integration/runtime/test_freeze_manager.py::TestFreezeManager::test_create_freeze_generates_manifest_with_checksums -v
```

## 测试特点

### 并发测试

Runtime 集成测试包含多线程并发测试，验证：

- 线程安全性
- 死锁预防
- 数据一致性
- 性能表现

### 文件系统测试

使用临时目录进行文件系统操作：

```python
def setup_method(self):
    self.temp_dir = TemporaryDirectory()
    self.data_root = Path(self.temp_dir.name)

def teardown_method(self):
    self.temp_dir.cleanup()
```

### 数据库测试

使用内存数据库或临时文件：

```python
# 内存 SQLite
conn = sqlite3.connect(":memory:")

# 临时文件数据库
conn = sqlite3.connect(str(temp_dir / "test.db"))
```

## 预期结果

所有测试应该：

1. **并发安全性**：多线程环境下无竞态条件
2. **数据一致性**：并发操作后数据正确
3. **资源管理**：连接、文件句柄正确释放
4. **错误处理**：异常情况正确处理

## 故障排查

### 并发测试失败

```
AssertionError: Race condition detected
```

**解决方案**：
1. 检查锁实现
2. 验证线程安全性
3. 增加测试超时时间

### 文件系统测试失败

```
FileNotFoundError: Test data directory not found
```

**解决方案**：
1. 检查临时目录创建
2. 验证文件权限
3. 确认清理逻辑正确

## 相关文档

- [DataHub 集成测试总览](../README.md)
- [Runtime 单元测试](../../unit/runtime/README.md)
