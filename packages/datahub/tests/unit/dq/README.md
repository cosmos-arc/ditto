# DQ 单元测试

## 测试覆盖

DQ（数据质量）单元测试覆盖数据质量引擎的核心功能。

| 测试文件 | 测试内容 |
|----------|----------|
| `test_engine.py` | DQ 引擎 |
| `test_models.py` | DQ 模型 |
| `test_report.py` | DQ 报告 |
| `test_result.py` | DQ 结果 |

## 测试内容

### DQ 引擎（test_engine.py）

**测试内容**：
- DQ 规则加载
- DQ 检查执行
- DQ 报告生成
- DQ 错误处理

**测试场景**：
1. 加载 YAML 规则配置
2. 执行单条规则检查
3. 批量规则检查
4. 生成 DQ 报告
5. 处理规则异常
6. 性能测试

### DQ 模型（test_models.py）

**测试内容**：
- DQ 级别枚举
- DQ 严重程度
- DQ 规则模型
- DQ 上下文模型

**测试场景**：
1. 级别枚举验证
2. 严重程度验证
3. 规则模型序列化
4. 上下文模型验证

### DQ 报告（test_report.py）

**测试内容**：
- 报告生成
- 报告格式化
- 报告导出
- 报告统计

**测试场景**：
1. 生成文本报告
2. 生成 JSON 报告
3. 生成 HTML 报告
4. 报告统计信息
5. 报告过滤和排序

### DQ 结果（test_result.py）

**测试内容**：
- DQ 检查结果
- 结果聚合
- 结果比较
- 结果序列化

**测试场景**：
1. 创建检查结果
2. 聚合多个结果
3. 比较结果差异
4. 结果序列化和反序列化

## 运行测试

### 运行所有 DQ 单元测试

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq -v
```

### 运行特定测试文件

```bash
# DQ 引擎
pixi run -e dev pytest packages/datahub/tests/unit/dq/test_engine.py -v

# DQ 模型
pixi run -e dev pytest packages/datahub/tests/unit/dq/test_models.py -v

# DQ 报告
pixi run -e dev pytest packages/datahub/tests/unit/dq/test_report.py -v

# DQ 结果
pixi run -e dev pytest packages/datahub/tests/unit/dq/test_result.py -v
```

### 运行 DQ Checkers 测试

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers -v
```

## 测试数据

使用 `fixtures/dq/` 目录下的测试数据：

```python
def test_engine_with_fixtures():
    """使用 fixtures 目录下的规则配置"""
    engine = DQEngine(config_path="tests/fixtures/dq/rules/")
    result = engine.check(data)
    ...
```

## 预期结果

所有测试应该：

1. **规则正确加载**：YAML 配置正确解析
2. **检查正确执行**：规则检查逻辑正确
3. **报告正确生成**：报告格式和内容正确
4. **结果正确聚合**：结果聚合逻辑正确

## 相关文档

- [DataHub 单元测试总览](../README.md)
- [DQ Checkers 测试](dq/checkers/README.md)
