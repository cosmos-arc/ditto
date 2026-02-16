# Foundation 集成测试

## 测试覆盖

Foundation 集成测试验证多组件协作和端到端功能。

**注意**：Foundation 层作为基础设施，集成测试较少。大多数测试在单元测试中完成。

## 测试场景

### 可观测性集成测试（如果有）

**测试内容**：
- 日志、追踪、指标的集成
- 端到端可观测性流程
- 多组件追踪链路

**测试场景**：
1. 完整的追踪链路
2. 日志与追踪关联
3. 指标记录验证

## 运行测试

### 运行所有集成测试

```bash
pixi run -e dev pytest packages/foundation/tests/integration -v
```

### 运行特定测试文件

```bash
# 特定测试文件
pixi run -e dev pytest packages/foundation/tests/integration/test_*.py -v
```

### 运行特定测试函数

```bash
# 特定测试函数
pixi run -e dev pytest packages/foundation/tests/integration/test_*.py::test_function_name -v
```

## 预期结果

所有测试应该：

1. **组件正确协作**：多组件协作正确
2. **数据正确流转**：数据流转正确
3. **集成正确工作**：集成功能正确

## 相关文档

- [Foundation 测试框架总览](../README.md)
- [Foundation 单元测试](../unit/README.md)
