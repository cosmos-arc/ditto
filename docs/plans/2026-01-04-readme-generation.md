# 生成所有缺失的 README.md 文档

> **状态**: ✅ 已完成 (2026-01-04)

## 概述

为项目中 33 个缺失 README.md 的文件夹生成文档，确保每个主要模块都有清晰的说明文档。

**初始覆盖率**: 31.25% (15/48)
**最终覆盖率**: ~93.75% (45/48)
**实际生成**: 40 个 README.md 文档

## 实施计划

### 阶段 1: 核心包文档（高优先级）

#### 1.1 packages/core/
- `packages/core/README.md` - 核心引擎包总览
  - 模块职责
  - 子模块介绍（engine、portfolio、strategy）
  - 依赖关系
  - 快速开始

- `packages/core/src/ditto_core/README.md` - 核心模块根目录
- `packages/core/src/ditto_core/engine/README.md` - 引擎模块
  - Regime（市场状态识别）
  - Factor（因子计算）
  - Rotation（轮动策略）
  - Backtest（回测）
  - Risk（风险管理）

- `packages/core/src/ditto_core/portfolio/README.md` - 投资组合管理
- `packages/core/src/ditto_core/strategy/README.md` - 策略模块

- `packages/core/tests/README.md` - 测试说明
- `packages/core/tests/integration/README.md`
- `packages/core/tests/unit/README.md`

### 阶段 2: DataHub 关键模块（高优先级）

#### 2.1 repositories/
- `packages/datahub/src/ditto_datahub/repositories/README.md`
  - 所有 Repository 说明（Security、Bars、Calendar、AdjFactor、Index、Universe）
  - 数据访问模式
  - PIT 查询支持
  - 并发安全机制

#### 2.2 dq/（数据质量）
- `packages/datahub/src/ditto_datahub/dq/README.md`
  - 三层检查机制（L1/L2/L3）
  - 检查器类型
  - 配置驱动设计
  - DQ 处理流程

- `packages/datahub/src/ditto_datahub/dq/checkers/README.md`
  - TechnicalChecker
  - BusinessChecker
  - StatisticalChecker

#### 2.3 其他重要模块
- `packages/datahub/src/ditto_datahub/alerts/README.md` - 告警模块
- `packages/datahub/src/ditto_datahub/utils/README.md` - 工具模块

### 阶段 3: Web 应用（高优先级）

#### 3.1 apps/web/
- `apps/web/README.md` - Web 应用总览
  - 项目状态（待开发）
  - 目录结构说明
  - 预期技术栈

- `apps/web/src/README.md`
- `apps/web/src/app/README.md`
- `apps/web/src/components/README.md`
- `apps/web/src/stores/README.md`
- `apps/web/src/types/README.md`

### 阶段 4: 测试文档（中优先级）

#### 4.1 datahub 测试
- `packages/datahub/tests/README.md` - 测试框架总览
  - pytest 配置
  - 测试标记（integration、pit、external、slow）
  - 测试工具（polars.testing、hypothesis、respx、inline-snapshot）

- `packages/datahub/tests/unit/README.md` - 单元测试说明
- `packages/datahub/tests/integration/README.md` - 集成测试说明
- `packages/datahub/tests/integration/runtime/README.md`
- `packages/datahub/tests/integration/sources/README.md`
- `packages/datahub/tests/integration/stores/README.md`

- `packages/datahub/tests/unit/alerts/README.md`
- `packages/datahub/tests/unit/dq/README.md`
- `packages/datahub/tests/unit/dq/checkers/README.md`
- `packages/datahub/tests/unit/meta/README.md`
- `packages/datahub/tests/unit/repositories/README.md`
- `packages/datahub/tests/unit/runtime/README.md`
- `packages/datahub/tests/unit/sources/README.md`
- `packages/datahub/tests/unit/stores/README.md`
- `packages/datahub/tests/unit/utils/README.md`

#### 4.2 foundation 测试
- `packages/foundation/tests/README.md`
- `packages/foundation/tests/integration/README.md`
- `packages/foundation/tests/unit/README.md`

### 阶段 5: 文档索引（低优先级）

#### 5.1 docs/
- `docs/adr/README.md` - 架构决策索引
- `docs/design/README.md` - 设计文档索引
- `docs/plans/archive/README.md` - 归档规划索引

## README.md 内容模板

### 包/模块级 README.md 模板

```markdown
# <模块名称>

## 概述

<一句话描述模块职责>

## 目录结构

```
<目录树>
```

## 核心功能

- <功能1>: <描述>
- <功能2>: <描述>

## 依赖关系

- 上游: <依赖的模块>
- 下游: <被依赖的模块>

## 使用示例

<代码示例>

## 相关文档

- <链接到相关文档>
```

### 测试目录 README.md 模板

```markdown
# <测试范围> 测试

## 测试框架

- pytest
- <其他工具>

## 测试覆盖

- <模块1>: `test_*.py`
- <模块2>: `test_*.py`

## 运行测试

```bash
# 运行所有测试
pixi run -e dev pytest <路径>

# 运行特定测试
pixi run -e dev pytest <路径>::<测试函数>
```

## 测试标记

- `@pytest.mark.integration` - 集成测试
- `@pytest.mark.pit` - PIT 数据验证
- `@pytest.mark.external` - 外部 API 测试
- `@pytest.mark.slow` - 耗时测试
```

## 关键文件

- 模板参考: `packages/datahub/README.md`
- 测试文档参考: `packages/datahub/tests/integration/sources/tushare/README.md`

## 执行记录

按阶段顺序执行，确保核心模块优先完成：

- [x] 阶段 1 → packages/core/ (8 个 README)
- [x] 阶段 2 → datahub repositories + dq (5 个 README)
- [x] 阶段 3 → apps/web/ (6 个 README)
- [x] 阶段 4 → 测试文档 (18 个 README)
- [x] 阶段 5 → 文档索引 (3 个 README)

## 额外完成

- 修复项目 lint 问题（test_monitoring.py、alerts 模块、test_pit_helper.py、test_task_factory.py）
- 修复 mypy 类型问题（alerts/base.py、email.py、deploy.py）
- 所有 pre-commit 检查通过
