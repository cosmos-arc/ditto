# Sprint 2 Phase 1: DQ 三层架构 - 实施计划

**日期**: 2025-12-28
**Sprint**: Sprint 2 - 数据层完善与验证
**Phase**: Phase 1 - DQ 三层架构

---

## 参考文档

- `docs/design/09_data_quality_design.md` - 数据质量设计（DQ 三层架构）
- `docs/design/02_data_design.md` - 数据层设计
- `docs/design/06_roadmap.md` - 路线图 Phase 0.5
- `docs/sprints/sprint-02-data-quality.md` - Sprint 2 详细计划

---

## 架构设计决策

基于 `09_data_quality_design.md` 设计文档，采用以下架构：

### 1. 配置方式：YAML + Pydantic
- 规则定义使用 YAML（可审计、diff 友好）
- 加载时使用 Pydantic 验证（类型安全）
- 内置规则 + 插件规则的混合模式
- **兼容现有**：保留现有的 Python 配置实现作为过渡

### 2. DQ 三层规则

| 层级 | 检测内容 | 执行时机 | 失败处理 |
|------|----------|----------|----------|
| **L1: 技术校验** | 非空、唯一、外键 | 写入时同步 | **阻断写入** |
| **L2: 业务规则** | OHLC、涨跌幅 | 写入时同步 | **警告记录** |
| **L3: 统计异常** | Z-score、完整性 | 定时批量 | **告警通知** |

### 3. L3 实现：异步任务专用
- L1/L2 在写入时同步执行
- L3 统计异常检查仅在 Server 定时任务中执行
- L3 不集成到写入流程

### 4. 隔离区：SQLite 专用表
- 在 SQLite 中创建 `quarantine_failed_data` 表
- 结构简单便于查询

---

## 开发规范遵循

### 1. TDD 流程（RED → GREEN → REFACTOR）
- **先写测试**：每个功能模块先写测试用例
- **测试失败**：运行测试确认失败（RED）
- **最小实现**：编写最少代码使测试通过（GREEN）
- **重构优化**：在测试保护下重构代码（REFACTOR）

### 2. 代码风格规范
- **函数长度**：≤ 50 行
- **嵌套深度**：≤ 3 层
- **类型注解**：公开函数 100% 类型注解
- **命名规范**：
  - 类：`PascalCase`
  - 函数/变量：`snake_case`
  - 常量：`UPPER_SNAKE`

### 3. 必须加载的 Skills
| 开发场景 | Skill | 触发时机 |
|----------|-------|----------|
| Polars 代码 | `polars-guide` | 处理 DataFrame 时 |
| PIT 数据 | `pit-guide` | 涉及时点数据时 |
| 日志追踪 | `observability` | 添加日志/指标时 |

---

## 任务分解（10 任务）

### Task 1.1: 创建 YAML 规则配置文件
**文件**: `packages/datahub/config/dq_rules/*.yml`

创建以下 YAML 文件：
- `etf_daily.yml` - ETF 日频数据规则
- `index_daily.yml` - 指数日频数据规则
- `market_daily.yml` - 股票日频数据规则
- `index_weight.yml` - 指数权重规则
- `adj_factor.yml` - 复权因子规则

**TDD 步骤**：
1. 创建 `test_models.py`，测试 YAML 解析和 Pydantic 验证
2. 创建最小 YAML 文件使测试通过
3. 扩展规则类型覆盖

---

### Task 1.2-1.10: 详细任务描述

（详见 plan 文件，包含完整的代码示例和 TDD 步骤）

---

## 执行步骤（TDD 流程）

### Phase 1: 核心模型和配置（Task 1.1 - 1.2）
### Phase 2: DQEngine 和 L1 检查器（Task 1.3 - 1.4）
### Phase 3: L2/L3 检查器（Task 1.5 - 1.6）
### Phase 4: 隔离区和 Repository 集成（Task 1.7 - 1.8）
### Phase 5: Server 任务和报告（Task 1.9 - 1.10）

---

## 验收标准

### 功能验收
- [ ] YAML 规则文件完整（5 个数据集）
- [ ] DQEngine 通过所有层级测试
- [ ] L1 ERROR 失败正确阻断写入并进入隔离区
- [ ] L2 WARNING 失败记录日志但允许写入
- [ ] L3 ALERT 批量检查任务正常运行并生成报告

### 代码质量验收
- [ ] 测试覆盖率 >= 80%
- [ ] `pixi run -e dev ci-check` 通过
- [ ] 所有函数长度 ≤ 50 行
- [ ] 所有公开函数有类型注解
- [ ] 无 ruff linting 错误

### 集成验收
- [ ] Repository 集成 DQEngine 后现有测试通过
- [ ] Server 任务可以手动触发执行
- [ ] 隔离区数据可以正确查询

---

## 新建文件（15 个）

| 文件路径 | 用途 |
|----------|------|
| `packages/datahub/config/dq_rules/etf_daily.yml` | ETF 规则 |
| `packages/datahub/config/dq_rules/index_daily.yml` | 指数规则 |
| `packages/datahub/config/dq_rules/market_daily.yml` | 股票规则 |
| `packages/datahub/config/dq_rules/index_weight.yml` | 权重规则 |
| `packages/datahub/config/dq_rules/adj_factor.yml` | 复权规则 |
| `packages/datahub/src/ditto_datahub/dq/models.py` | 模型定义 |
| `packages/datahub/src/ditto_datahub/dq/engine.py` | DQ 引擎 |
| `packages/datahub/src/ditto_datahub/dq/result.py` | 结果模型 |
| `packages/datahub/src/ditto_datahub/dq/checkers/technical.py` | L1 检查器 |
| `packages/datahub/src/ditto_datahub/dq/checkers/business.py` | L2 检查器 |
| `packages/datahub/src/ditto_datahub/dq/checkers/statistical.py` | L3 检查器 |
| `packages/datahub/src/ditto_datahub/stores/quarantine_store.py` | 隔离区 |
| `packages/datahub/src/ditto_datahub/dq/report.py` | 报告生成 |
| `apps/server/src/ditto_port/ingestion/tasks/dq_batch.py` | L3 任务 |
| `tests/unit/dq/` | 测试文件 |

---

## 修改文件（2 个）

| 文件路径 | 修改内容 |
|----------|----------|
| `packages/datahub/src/ditto_datahub/repositories/bars.py` | 集成 DQEngine，添加 DQ 检查逻辑 |
| `packages/datahub/src/ditto_datahub/dq/__init__.py` | 导出 DQEngine, DQResult 等 |
