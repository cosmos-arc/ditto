# 可观测性测试重构计划

## 背景

当前 foundation 包可观测性测试存在严重的分类错误：
- **约 70% 的"单元测试"实际是集成测试**
- 使用真实组件而非 Mock
- 测试"接缝"处而非单个类逻辑

## 目标

将测试文件按照单元测试和集成测试正确分类，符合 `python-test.md` 规范。

## 重构方案

### 文件组织结构

**重构后结构**：
```
tests/
├── unit/observability/
│   ├── test_config_unit.py              # 配置逻辑（纯单元）
│   ├── test_json_formatter_unit.py     # JSON 格式化器（保留）
│   ├── test_simple_gauge_unit.py        # SimpleGauge 逻辑（保留）
│   ├── test_metrics_registry_unit.py    # 注册表逻辑（新建，使用 Mock）
│   └── test_tracing_unit.py             # 追踪边界测试（从混合文件提取）
│
└── integration/observability/
    ├── conftest.py                       # Fixtures（已有）
    ├── test_metrics_integration.py       # Metrics SDK 集成（已有）
    ├── test_observability_integration.py # 综合集成测试（从 unit 迁移）
    ├── test_init_integration.py          # 初始化集成测试（从 unit 迁移）
    ├── test_logging_integration.py       # 日志集成测试（从 unit 迁移）
    └── test_tracing_integration.py       # 追踪集成测试（从 unit 迁移）
```

### 文件映射

#### 直接迁移（100% 集成测试）

| 原文件 | 新文件 | 说明 |
|--------|--------|------|
| `test_observability_unit.py` | `test_observability_integration.py` | 综合集成测试 |
| `test_observability_testing_unit.py` | `test_testing_helpers_integration.py` | 测试辅助功能集成测试 |
| `test_observability_logging_unit.py` | `test_logging_integration.py` | 日志集成测试 |

#### 拆分文件（混合测试）

| 原文件 | 保留单元测试 | 迁移集成测试 |
|--------|-------------|-------------|
| `test_observability_init_unit.py` | `TestObservabilityRegistry` | `TestInit`/` → `test_init_integration.py` |
| `test_observability_metrics_unit.py` | `TestSimpleGauge` | `TestMSetup`/` → `test_metrics_integration.py` (合并) |
| `test_observability_tracing_unit.py` | 边界测试 | 装饰器/嵌套/ → `test_tracing_integration.py` |
| `test_metric_definitions_unit.py` | 方法验证 | 指标创建 → `test_metrics_integration.py` (合并) |

#### 保留的单元测试（无需修改）

| 文件 | 状态 |
|------|------|
| `test_json_formatter_unit.py` | ✅ 保留 |
| `test_simple_gauge_unit.py` | ✅ 保留 |

### 执行步骤

1. ✅ 创建 `test_metrics_integration.py`（已完成）
2. 创建 `test_metrics_registry_unit.py`（新建单元测试）
3. 迁移 `test_observability_unit.py` → `test_observability_integration.py`
4. 迁移 `test_observability_testing_unit.py` → `test_testing_helpers_integration.py`
5. 迁移 `test_observability_logging_unit.py` → `test_logging_integration.py`
6. 拆分 `test_observability_init_unit.py`
7. 拆分 `test_observability_metrics_unit.py`
8. 拆分 `test_observability_tracing_unit.py`
9. 拆分 `test_metric_definitions_unit.py`
10. 运行验证

## 验证标准

- [ ] 所有测试通过
- [ ] 测试覆盖率 ≥ 80%
- [ ] 类型检查通过
- [ ] 单元测试完全 Mock 依赖
- [ ] 集成测试使用真实组件
