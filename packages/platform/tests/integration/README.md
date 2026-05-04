# Platform 集成测试

## 测试分类

| 目录 | 测试内容 |
|------|----------|
| `observability/` | 日志/追踪/指标端到端集成、初始化流程、测试辅助验证 |

## 运行测试

```bash
pixi run -e dev pytest packages/platform/tests/integration -v                   # 全部
pixi run -e dev pytest packages/platform/tests/integration/observability -v     # 可观测性
```

## 说明

Platform 层作为基础设施，集成测试较少，核心逻辑由单元测试覆盖。
