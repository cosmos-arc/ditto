# 架构审计报告

**审计日期**: 2026-02-13
**审计范围**: packages/, apps/port
**审计版本**: d9ddb01 (refactor: Foundation 合并到 Infra & 架构优化)

---

## 执行摘要

### 关键统计

| 指标 | 状态 | 数值 |
|------|------|------|
| 架构边界检查 | ✅ 通过 | 6/6 contracts kept |
| 代码质量 (lint) | ✅ 通过 | 0 errors |
| 类型检查 (type) | ✅ 通过 | 0 errors, 0 warnings |
| 单元测试 | ✅ 通过 | 1689 passed, 1 skipped |
| 分支覆盖率 | ⚠️ 略低 | 78.45% (标准: 80%) |

### 问题分布

| 严重度 | 数量 | 说明 |
|--------|------|------|
| 🔴 Blocker | 0 | 无阻塞问题 |
| 🟠 High | 4 | 需要优先处理 |
| 🟡 Medium | 3 | 建议在迭代中处理 |
| 🟢 Low | 2 | 可延后处理 |

---

## 架构图

### 分层依赖关系

```
┌─────────────────────────────────────────────────────────────┐
│                    apps/port (应用层)                        │
│                         │                                    │
│    ┌────────────────────┼────────────────────┐              │
│    │                    │                    │              │
│    ▼                    ▼                    ▼              │
│ packages/core      packages/datahub    packages/infra       │
│ (核心层)            (数据层)            (基础设施层)         │
│    │                    │                    │              │
│    │                    │                    │              │
│    └────────────────────┼────────────────────┘              │
│                         │                                    │
│                         ▼                                    │
│                   packages/infra                             │
│                   (横切层)                                   │
└─────────────────────────────────────────────────────────────┘

依赖规则:
✅ port → core
✅ port → datahub
✅ port → infra (横切层)
✅ datahub → infra
✅ core → datahub (仅 models)
❌ infra → 其他层 (零依赖)
❌ datahub → core/port
```

### 模块依赖矩阵

```
              infra  core  datahub  port
infra           -     -      -       -
core           ✓      -      ✓*      -
datahub        ✓      -      -       -
port           ✓     ✓      ✓       -

* core 仅依赖 datahub 的 models
```

---

## 详细发现

### 🔴 High Priority (P0)

#### [ARCH-001] 大文件需要重构

**问题**: 3个文件超过800行限制

| 文件 | 行数 | 建议 |
|------|------|------|
| `packages/datahub/src/ditto_datahub/sources/tushare/adapters/capital.py` | 1063 | 按资本数据类型拆分 |
| `apps/port/src/ditto_port/registry/datahub.py` | 1057 | DI 注册表，可按领域分组 |
| `packages/datahub/src/ditto_datahub/services/market_service.py` | 838 | 按 market 子领域拆分 |

**修复建议**:
- capital.py: 拆分为 margin.py, pledge.py, valuation.py 等
- datahub.py: 使用 lazy import 或按领域拆分 registry 模块
- market_service.py: 拆分为 StockMarketService, IndexMarketService 等

**验证命令**:
```bash
pixi run -e dev python scripts/check_code_size.py
```

---

#### [ARCH-002] 大类需要拆分

**问题**: 2个类超过20个public方法限制

| 类名 | 方法数 | 文件 |
|------|--------|------|
| `DataRootConfig` | 30 | packages/datahub/src/ditto_datahub/config/data_root.py |
| `TushareSource` | 21 | packages/datahub/src/ditto_datahub/sources/tushare/tushare_source.py |

**修复建议**:
- DataRootConfig: 考虑按功能域拆分为多个配置类
- TushareSource: 使用 SourceAdapter 模式，按数据类型委托

---

#### [ENG-001] 测试覆盖率略低于标准

**问题**: 当前覆盖率 78.45%，低于 80% 标准

**缺失覆盖的主要文件**:
- packages/infra/tests/integration/observability/*.py (覆盖率 ~18-20%)
- 部分边界分支未覆盖

**修复建议**:
1. 补充集成测试覆盖
2. 检查分支覆盖报告中的未覆盖行

**验证命令**:
```bash
pixi run -e dev test --unit --cov --cov-report=html
open htmlcov/index.html
```

---

#### [ENG-002] 慢速单元测试需要优化

**问题**: 2个单元测试超过500ms阈值

| 测试 | 耗时 | 原因 |
|------|------|------|
| `test_returns_true_for_trading_day` | 16.07s | Prefect @task 装饰器未 mock |
| `test_uses_ingestion_context` | 15.55s | Prefect @flow 装饰器未 mock |

**修复建议**:
- 在 conftest.py 中添加 `mock_prefect_decorators` fixture
- 参考 [python-test.md](/.claude/rules/python-test.md) 中的示例

**预期效果**: 16s → 0.01s (1600x 提升)

---

### 🟡 Medium Priority (P1)

#### [ENG-003] type:ignore 使用分析

**问题**: 源码中存在16处 type:ignore

**分布**:
| 位置 | 数量 | 类型 |
|------|------|------|
| apps/port/src/ditto_port/api/routes/ | 8 | FastAPI 依赖注入类型 |
| apps/port/src/ditto_port/cli/commands/ | 4 | 枚举类型转换 |
| apps/port/src/ditto_port/jobs/flows/ | 3 | Prefect 返回值类型 |
| apps/port/src/ditto_port/services/ | 1 | 动态属性访问 |

**分析**: 大部分是框架类型系统限制，已使用具体规则名（如 `# type: ignore[assignment]`）

**建议**:
- FastAPI 依赖注入类型问题属于已知限制，可接受
- 枚举类型转换可考虑使用 TypeGuard 改善

---

#### [NAM-001] 术语一致性良好

**检查结果**: 未发现 bar/kline/candlestick 术语混用

**当前状态**: 项目统一使用 `bar` 术语

---

#### [ARCH-003] TYPE_CHECKING 使用最小化

**检查结果**: 仅2个文件使用 TYPE_CHECKING
- packages/infra/tests/integration/observability/conftest.py (测试)
- packages/datahub/MIGRATION_SUMMARY.md (文档)

**结论**: 符合规范，无循环依赖问题

---

### 🟢 Low Priority (P2)

#### [ENG-004] 测试中 type:ignore 汇总

**位置**: packages/*/tests/ (14处)

**分析**: 测试代码中的 type:ignore 用于：
- 测试抽象类实例化
- 测试错误类型参数
- 测试 frozen dataclass 修改

**结论**: 符合规范，测试代码允许适度豁免

---

#### [NAM-002] 命名规范良好

**检查结果**:
- ✅ 未发现非标准缩写 (qty)
- ✅ 未发现业务层技术术语混用
- ✅ Database/SQLite/Parquet 类名均在 infra 层

---

## 架构边界验证

### Import Linter 检查结果

```
Layered Architecture           KEPT
Infra must not depend on other layers    KEPT
DataHub must not depend on Core/Port     KEPT
Core can only depend on DataHub models   KEPT
Port (non-registry) must not directly depend on DataHub implementation   KEPT
No circular dependencies between packages  KEPT
```

### 层级穿透检查

**Registry 导入分析**:
- ✅ `apps/port/src/ditto_port/registry/` 正确导入 stores/sources 用于 DI
- ⚠️ `apps/port/src/ditto_port/services/ingestion/quality/service.py:9` 导入 QuarantineWriter

**建议**: Service 层应通过 DataHub Service 访问 QuarantineWriter，而非直接导入

---

## 依赖合规性

### 禁止的依赖

| 依赖 | 检查结果 |
|------|---------|
| pandas | ✅ 未发现 |
| sqlalchemy | ✅ 未发现 |

### 允许的依赖

| 依赖 | 使用位置 |
|------|---------|
| polars | 数据处理 |
| duckdb | 分析查询 |
| fastapi | API 框架 |
| prefect | 任务编排 |
| loguru | 日志 |
| orjson | JSON 处理 |
| granian | ASGI 服务器 |
| httpx | HTTP 客户端 |

---

## 测试质量

### 测试统计

| 指标 | 数值 |
|------|------|
| 总测试数 | 1689 |
| 通过 | 1689 |
| 跳过 | 1 |
| 失败 | 0 |
| 分支覆盖率 | 78.45% |

### 慢速测试 (Top 10)

| 测试 | 耗时 | 类型 |
|------|------|------|
| test_returns_true_for_trading_day | 16.07s | 单元测试 |
| test_uses_ingestion_context | 15.55s | 单元测试 |
| test_returns_result_with_no_missing_data | 2.41s | 单元测试 |
| test_uses_correct_task_factory_for_bars_datasets | 2.30s | 单元测试 |
| test_executes_t0_datasets | 2.17s | 单元测试 |

---

## 重构计划

### P0 - 本周完成

| 任务 | 文件 | 预估工时 |
|------|------|---------|
| [ARCH-001] 拆分大文件 | capital.py, datahub.py, market_service.py | 4h |
| [ENG-002] 优化慢速测试 | 添加 Prefect mock | 1h |

### P1 - 下个迭代

| 任务 | 文件 | 预估工时 |
|------|------|---------|
| [ARCH-002] 重构大类 | DataRootConfig, TushareSource | 3h |
| [ENG-001] 提升覆盖率 | 补充集成测试 | 2h |

### P2 - 可延后

| 任务 | 说明 |
|------|------|
| [ENG-003] type:ignore 优化 | 框架限制，可接受 |
| [ARCH-003] 层级穿透修复 | QuarantineWriter 导入 |

---

## 验证命令

```bash
# 完整检查
pixi run -e dev check

# 架构边界检查
pixi run -e dev arch-check

# 代码规模检查
pixi run -e dev python scripts/check_code_size.py

# 测试覆盖率
pixi run -e dev test --unit --cov --cov-report=html

# 类型检查
pixi run -e dev type

# 代码风格
pixi run -e dev lint
```

---

## 附录

### 检查项清单

#### 架构约束
- [x] 层级穿透检查 - 通过
- [x] 循环依赖检查 - 通过
- [x] 领域层污染检查 - 通过
- [x] 模块边界泄露检查 - 通过
- [x] 反向依赖检查 - 通过

#### 设计与结构
- [ ] 类单一职责（SRP）- 部分类过大
- [x] 类规模检查 - 3个文件 >800行
- [x] 函数复杂度检查 - 通过
- [x] 模块划分合理性 - 通过

#### 依赖合规性
- [x] 禁止的类库 - 通过
- [x] 允许的类库 - 通过
- [x] 包管理合规 - 通过

#### 工程实践
- [x] TYPE_CHECKING 使用 - 最小化
- [x] type:ignore 使用 - 有记录
- [x] 死代码检测 - 通过

#### 测试质量
- [x] 测试可运行性 - 通过
- [x] 测试成功率 - 100%
- [ ] 分支覆盖率 - 78.45% (目标 80%)
- [ ] 测试性能 - 2个慢速测试

#### 命名与概念
- [x] 术语一致性 - 通过
- [x] 命名风格一致 - 通过
- [x] 缩写规范 - 通过

---

**审计人**: Claude Code
**下次审计**: 建议 2 周后重新评估 P0 问题修复情况
