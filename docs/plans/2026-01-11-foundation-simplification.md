# Foundation 包代码简化计划

## 执行摘要

### 目标
简化 `packages/foundation` 的代码实现，提升可维护性和可读性。

### 重要约束
**⚠️ 无需向后兼容**：所有使用方都在本项目内，破坏性修改直接调整依赖方即可。**严禁添加兼容代码或遗留代码**。

### 当前状态
- **总代码行数**: ~1,791 行（生产代码）
- **测试覆盖率**: 87.69%
- **核心问题**: 复杂的 ObservableGauge 包装器、全局状态管理混乱、重复的指标创建代码、路径解析逻辑复杂

### 预期成果
- **代码行数减少**: 30-40% (约 400-500 行) - *因无需兼容，可以更彻底*
- **圈复杂度降低**: 50%
- **测试覆盖率**: 提升至 >=85%
- **可维护性**: 显著提升
- **无技术债务**: 无兼容代码、无遗留代码

---

## 阶段划分

### 阶段 1: 低风险模块 (logging.py + paths.py)

#### 1.1 logging.py - JSON Formatter 简化

**问题**: `_json_formatter` 函数有 49 行，手动构建 dict

**简化方案**:
- 提取 `_build_log_record` 函数
- 简化 JSON formatter 逻辑
- 预计减少 ~60% 代码 (49行 → ~20行)

**关键文件**: [observability/logging.py](packages/foundation/src/ditto_foundation/observability/logging.py)

**验证**: 运行 `pixi run -e dev pytest -m unit --cov=ditto_foundation.observability.logging`

---

#### 1.2 paths.py - 路径解析逻辑简化

**问题**: `_get_path` 方法有 62 行，5 层优先级逻辑

**简化方案**:
- 引入 `PathResolver` 类（优先级链模式）
- 拆分 `_get_path` 为多个小方法:
  - `_resolve_env_var()`
  - `_resolve_xdg_var()`
  - `_resolve_base_dir()`
  - `_get_platform_default()`
- 新增测试文件 `tests/unit/config/test_paths_unit.py`

**关键文件**: [config/paths.py](packages/foundation/src/ditto_foundation/config/paths.py)

**验证**: 运行 `pixi run -e dev pytest tests/unit/config/`

---

### 阶段 2: 中风险模块 (tracing.py)

#### 2.1 全局状态管理简化

**问题**: 3 个全局变量 (`_tracer`, `_in_memory_exporter`, `_current_span`) 分散管理

**简化方案**:
- 引入 `TracingState` dataclass 封装所有状态
- 替换全局变量为单一 `_state` 对象
- 简化 `reset_tracing()` 逻辑

#### 2.2 SpanContext 简化

**问题**: 手动管理 `_current_span` 全局变量，双重上下文管理

**简化方案**:
- 移除 `_current_span` 全局变量
- 利用 OpenTelemetry 的内置 `trace.get_current_span()`
- 简化 `__enter__` 和 `__exit__` 逻辑

**关键文件**: [observability/tracing.py](packages/foundation/src/ditto_foundation/observability/tracing.py)

**验证**: 运行 `pixi run -e dev pytest -m unit --cov=ditto_foundation.observability.tracing`

---

### 阶段 3: 高风险模块 (metrics.py)

#### 3.1 ObservableGauge 包装器简化

**问题**: `GaugeWrapper` 类有 72 行，使用闭包 + 嵌套类双重模式

**简化方案**:
- 创建独立的 `SimpleGauge` 类
- 移除闭包状态，使用实例变量
- 移除误导性的 `attributes` 参数
- 预计减少 ~60% 代码

#### 3.2 指标创建代码简化

**问题**: `M.setup()` 方法有 155 行重复代码

**简化方案**:
- 创建 `METRIC_DEFINITIONS` 配置字典
- 实现基于配置的指标注册（数据驱动）
- 预计减少 ~70% 代码 (155行 → ~30行)

**关键文件**: [observability/metrics.py](packages/foundation/src/ditto_foundation/observability/metrics.py)

**验证**: 运行 `pixi run -e dev pytest -m unit --cov=ditto_foundation.observability.metrics`

---

## 实施步骤

### 步骤 0: 准备工作

```bash
# 创建功能分支
git checkout -b feat/foundation-simplification

# 记录基线指标
pixi run -e dev pytest --cov=ditto_foundation --cov-report=term
```

---

### 步骤 1: 阶段 1 - logging.py 简化

1. 提取 `_build_log_record` 函数
2. 简化 `_json_formatter`
3. 更新单元测试
4. **查找并更新所有依赖方**
5. 验证覆盖率 >=85%

---

### 步骤 2: 阶段 1 - paths.py 简化

1. 引入 `PathResolver` 类
2. 拆分 `_get_path` 为多个小方法
3. 提取平台特定逻辑
4. 新增测试文件 `test_paths_unit.py`
5. **查找并更新所有依赖方**
6. 验证覆盖率 >=85%

---

### 步骤 3: 阶段 2 - tracing.py 简化

1. 创建 `TracingState` dataclass
2. 替换全局变量为 `_state`
3. 简化 `SpanContext` 类
4. 更新单元测试
5. **查找并更新所有依赖方**
6. 验证覆盖率 >=85%

---

### 步骤 4: 阶段 3 - metrics.py 简化

1. 创建 `SimpleGauge` 类
2. 简化 `_create_gauge` 函数
3. 创建 `METRIC_DEFINITIONS` 配置
4. 重构 `M.setup` 方法
5. 更新单元测试
6. **查找并更新所有依赖方**
7. 验证覆盖率 >=85%

---

### 步骤 5: 验证与文档

1. 运行完整测试套件
2. 检查覆盖率目标
3. 运行集成测试
4. 更新相关 README

---

## 关键文件清单

| 文件 | 修改类型 | 优先级 |
|------|---------|-------|
| [observability/metrics.py](packages/foundation/src/ditto_foundation/observability/metrics.py) | 高风险重构 | 高 |
| [observability/tracing.py](packages/foundation/src/ditto_foundation/observability/tracing.py) | 中风险重构 | 中 |
| [config/paths.py](packages/foundation/src/ditto_foundation/config/paths.py) | 中等重构 | 中 |
| [observability/logging.py](packages/foundation/src/ditto_foundation/observability/logging.py) | 低风险重构 | 低 |
| [tests/unit/test_observability_unit.py](packages/foundation/tests/unit/test_observability_unit.py) | 测试更新 | 高 |
| [tests/unit/config/test_paths_unit.py](packages/foundation/tests/unit/config/test_paths_unit.py) | 新建测试文件 | 高 |

---

## 验证方法

### 覆盖率检查
```bash
# 检查整体覆盖率
pixi run -e dev pytest --cov=ditto_foundation --cov-report=term --cov-fail-under=85

# 检查特定模块
pixi run -e dev pytest --cov=ditto_foundation.observability.logging --cov-report=term
pixi run -e dev pytest --cov=ditto_foundation.observability.tracing --cov-report=term
pixi run -e dev pytest --cov=ditto_foundation.observability.metrics --cov-report=term
pixi run -e dev pytest --cov=ditto_foundation.config.paths --cov-report=term
```

### 集成测试
```bash
pixi run -e dev pytest -m integration
```

### 代码质量检查
```bash
pixi run -e dev pre-commit-run
```

---

## 风险缓解

| 风险 | 缓解措施 |
|------|---------|
| 破坏现有 API | ✅ 无需兼容，直接调整依赖方 |
| 测试覆盖率下降 | 每阶段结束后立即检查，新增测试必须覆盖新代码 |
| 全局状态重构 | 使用线程安全数据结构，添加并发测试 |

---

## 依赖方处理

由于无需向后兼容，每个阶段简化后需要查找并更新所有依赖方：

### 查找依赖方的方法
```bash
# 使用 Grep 查找对特定 API 的引用
# 例如：查找 M.kill_switch_level 的使用
pixi run grep -r "M\\.kill_switch_level" --include="*.py" ./
```

### 预期需要更新的依赖方
- `packages/foundation/src/ditto_foundation/__init__.py`
- `packages/foundation/src/ditto_foundation/observability/__init__.py`
- `packages/foundation/tests/unit/test_observability_unit.py`
- `apps/server/` 中可能使用 foundation 的代码

---

## 项目约束遵循

- ✅ 语言: 简体中文
- ✅ TDD: RED → GREEN → REFACTOR
- ✅ 测试覆盖率: >= 80% (目标: 85%)
- ✅ 分支策略: 从 main 拉取开发分支，PR 合并
- ✅ Marker 规范: `@pytest.mark.unit` / `@pytest.mark.integration`
- ✅ 验证流程: `pixi run -e dev pre-commit-run`
