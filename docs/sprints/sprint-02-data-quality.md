# Sprint 2: 数据层完善与验证（Phase 0.5 续）

**时间**: Week 4-8 (4-5 周)
**Phase**: 0.5 数据摄取完善期
**目标**: 完善 DQ 三层架构、DataHub 完整实现、数据摄取增强、黄金数据集验证

## 参考文档

- 《01_system_design.md》 - 系统架构设计
- 《02_data_design.md》 - 数据层设计文档
- 《09_data_quality_design.md》 - 数据质量设计（DQ 三层架构）
- 《06_roadmap.md》 - Phase 0.5 数据质量验证期

## Sprint 目标

1. ⏳ DQ 三层架构完整实现（L1/L2/L3）
2. ⏳ DataHub 完整实现（Universe/Index/Freeze/元数据）
3. ⏳ 数据摄取增强（增量更新/监控/告警/AkShare）
4. ⏳ 数据引擎增强（缓存/PIT SQL）
5. ⏳ 黄金数据集验证（最终验收）

## Sprint 1 状态回顾

### ✅ 已完成（100% P0）

| 组件 | 测试数 | 状态 |
|------|--------|------|
| Runtime Layer | 18 tests | ✅ |
| Store Layer | 132 tests | ✅ |
| Domain Repositories | 8 tests | ✅ |
| DataHub Facade | 49 tests | ✅ |
| Sources Layer (Tushare) | - | ✅ |
| Server 层骨架 | - | ✅ |

### 📋 P1 延后任务（现已纳入 Sprint 2）

- DQ 三层架构完整实现
- Server 调度完善（定时、告警、API 触发）
- AkShare 适配器

---

## 任务分解（51 个任务）

### Phase 0: 技术债务清理（14 任务，3-4 天）✅ 已完成

**完成日期**: 2025-12-28

**涉及文件**：
- `packages/datahub/src/ditto_datahub/repositories/bars.py`
- `packages/datahub/src/ditto_data_hub/stores/adj_factor_store.py`
- `packages/datahub/src/ditto_data_hub/runtime/sqlite_pool.py`
- `packages/datahub/tests/unit/repositories/test_bars_repository.py`
- `packages/datahub/tests/test_adj_factor_store.py`

**关键任务**：
| Task | 描述 | 状态 |
|------|------|------|
| 0.1 | 混合资产查询检测测试 | ✅ |
| 0.2 | QFQ 排序验证（存储层） | ✅ |
| 0.3 | QFQ 排序验证（查询层） | ✅ |
| 0.4 | 复权因子缺失处理（QFQ） | ✅ |
| 0.5 | 复权因子缺失处理（HFQ） | ✅ |
| 0.6 | SQLite 外键启用验证 | ✅ |
| 0.7-0.14 | 其他代码质量改进 | ✅ |

**完成总结**：
- 核心功能已验证完整实现
- 新增边缘测试用例 11 个（6 + 2 + 3）
- 代码重构完成（`_apply_adj` 拆分为 3 个方法）
- 所有测试通过（测试覆盖率保持 100%）
- 函数长度符合规范（每个方法 ≤50 行）

**验收标准**：
- [x] 所有新增测试通过
- [x] 混合资产查询正确抛出 ValueError
- [x] 复权因子缺失正确处理
- [x] SQLite 外键约束生效
- [x] 代码重构完成

---

### Phase 1: DQ 三层架构（10 任务，5-6 天）⭐ P0

**新增文件结构**：
```
packages/datahub/
├── config/
│   └── dq_rules.yaml                 # 统一规则配置
├── src/ditto_data_hub/
│   ├── dq/
│   │   ├── __init__.py
│   │   ├── engine.py                 # DQ 执行引擎
│   │   ├── result.py                 # 结果模型（DQResult, DQIssue）
│   │   ├── rules.py                  # 规则加载
│   │   └── checkers/
│   │       ├── __init__.py
│   │       ├── technical.py          # L1 技术校验
│   │       ├── business.py           # L2 业务规则
│   │       └── statistical.py        # L3 统计异常
│   └── stores/
│       └── quarantine_store.py       # 隔离区存储
```

**关键任务**：
| Task | 描述 | 关键文件 | 状态 |
|------|------|----------|------|
| 1.1 | 创建 `dq_rules.yaml` | `config/dq_rules.yaml` | ❌ |
| 1.2 | 实现 DQResult 模型 | `dq/result.py` | ❌ |
| 1.3 | 实现 DQEngine 核心 | `dq/engine.py` | ❌ |
| 1.4 | 实现 TechnicalChecker（L1） | `dq/checkers/technical.py` | ❌ |
| 1.5 | 实现 BusinessChecker（L2） | `dq/checkers/business.py` | ❌ |
| 1.6 | 实现 StatisticalChecker（L3） | `dq/checkers/statistical.py` | ❌ |
| 1.7 | 隔离区机制 | `stores/quarantine_store.py` | ❌ |
| 1.8 | Repository 集成 DQEngine | `repositories/bars.py` | ❌ |
| 1.9 | Server 批量 DQ 检查任务 | `apps/server/.../tasks/dq_batch.py` | ❌ |
| 1.10 | DQ 报告生成 | `dq/report.py` | ❌ |

**DQ 三层规则**：
| 层级 | 检测内容 | 执行时机 | 失败处理 |
|------|----------|----------|----------|
| L1 | 非空、唯一、外键 | 写入时 | **阻断写入** |
| L2 | OHLC、涨跌幅 | 写入时 | **警告记录** |
| L3 | Z-score、完整性 | 定时批量 | **告警通知** |

**验收标准**：
- [ ] `dq_rules.yaml` 配置完整（etf_daily, index_daily, adj_factor）
- [ ] DQEngine 通过所有层级测试
- [ ] L1 失败数据被隔离
- [ ] L2 失败记录警告
- [ ] L3 批量检查任务运行
- [ ] 质量报告正确生成

---

### Phase 2: DataHub 完整实现（8 任务，4-5 天）

**新增文件结构**：
```
packages/datahub/src/ditto_data_hub/
├── repositories/
│   ├── universe.py                  # UniverseRepository
│   ├── index.py                     # IndexRepository
│   └── metadata.py                  # MetadataRepository
├── runtime/
│   └── freeze_manager.py            # FreezeManager
└── hub.py                            # DataHub 增强
```

**关键任务**：
| Task | 描述 | 接口 | 状态 |
|------|------|------|------|
| 2.1 | UniverseRepository | `get_constituents()`, `list_universes()` | ❌ |
| 2.2 | IndexRepository | `get_index_bars()`, `get_constituents()` | ❌ |
| 2.3 | FreezeManager | `create_freeze()`, `verify()`, `restore()` | ❌ |
| 2.4 | DataHub.freeze() | freeze/verify/restore 接口 | ❌ |
| 2.5 | DataHub.universe() | universe repository | ❌ |
| 2.6 | DataHub.index() | index repository | ❌ |
| 2.7 | 增强 get_bars() | 更多过滤选项 | ❌ |
| 2.8 | 元数据查询接口 | `get_trading_days()`, `is_trading_day()` | ❌ |

**验收标准**：
- [ ] universe/index repository 可用
- [ ] freeze/verify/restore 工作
- [ ] 元数据查询接口完整
- [ ] 所有新接口测试覆盖率 >= 80%

---

### Phase 3: 数据摄取增强（8 任务，4-5 天）

**新增文件结构**：
```
packages/datahub/src/ditto_data_hub/sources/
├── base.py                            # 增量更新接口
├── akshare/                           # AkShare 适配器
│   ├── __init__.py
│   ├── client.py
│   └── source.py
└── failover.py                        # 自动切换

apps/server/src/ditto_server/
├── ingestion/
│   ├── scheduler.py                   # 定时调度
│   ├── alerts.py                      # 告警发送
│   └── tasks/
│       ├── quality_monitor.py         # 质量监控
│       └── incremental.py             # 增量摄取
└── api/
    └── ingestion.py                   # API 触发接口
```

**关键任务**：
| Task | 描述 | 关键功能 | 状态 |
|------|------|----------|------|
| 3.1 | 增量更新机制设计 | `get_incremental()`, `detect_changes()` | ❌ |
| 3.2 | Tushare 增量适配 | 基于 trade_date 的增量查询 | ❌ |
| 3.3 | 摄取质量监控 | `monitor_ingestion_quality()` | ❌ |
| 3.4 | 摄取异常告警 | AlertSender 抽象 | ❌ |
| 3.5 | 定时调度配置 | IngestionScheduler | ❌ |
| 3.6 | API 触发接口 | `/ingestion/trigger/{trade_date}` | ❌ |
| 3.7 | AkShare 适配器 | 接口对齐 Tushare | ❌ |
| 3.8 | 数据源自动切换 | FailoverSource | ❌ |

**验收标准**：
- [ ] 增量更新正常工作
- [ ] 质量监控产生指标
- [ ] 告警正确发送
- [ ] API 触发接口可用
- [ ] AkShare 降级切换

---

### Phase 4: 数据引擎增强（5 任务，3-4 天）

**新增文件结构**：
```
packages/datahub/src/ditto_data_hub/runtime/
├── sql_engine.py                      # 查询优化
└── cache.py                           # 缓存层
```

**关键任务**：
| Task | 描述 | 关键功能 | 状态 |
|------|------|----------|------|
| 4.1 | SqlEngine 复杂查询优化 | 查询计划缓存、慢查询日志 | ❌ |
| 4.2 | PIT 查询 SQL 生成 | 自动生成 PIT 过滤 SQL | ❌ |
| 4.3 | 缓存层设计 | DataCache 类 | ❌ |
| 4.4 | 热点数据缓存策略 | 交易日历、元数据缓存 | ❌ |
| 4.5 | 缓存命中率监控 | Prometheus 指标 | ❌ |

**验收标准**：
- [ ] 复杂查询性能提升
- [ ] PIT SQL 正确生成
- [ ] 缓存层正常工作
- [ ] 缓存命中率 >= 70%

---

### Phase 5: 黄金数据集验证（6 任务，5-7 天）⭐ 最终验收

**设计文档参考**：`docs/design/06_roadmap.md` Phase 0.5 数据质量验证期

**核心目标**：
- 验证数据摄取的准确性
- 建立数据质量基线
- 输出《数据质量基线报告 v1》
- 确保 Tushare 数据源可靠可用

**新增文件结构**：
```
apps/server/src/ditto_server/validation/
├── __init__.py
├── golden_dataset.py                  # 黄金数据集管理
├── comparison.py                      # 数据比对引擎
└── report.py                          # 验证报告生成

tests/
└── golden_dataset/
    ├── test_prices.py                 # 收盘价验证
    ├── test_adj_factor.py             # 复权因子验证
    └── test_limits.py                 # 涨跌停验证

doc/
└── validation/
    └── golden_dataset_baseline_v1.md  # 数据质量基线报告
```

**黄金数据集选取**：
| 标的 | 代码 | 选取原因 | 验证重点 |
|------|------|----------|----------|
| 沪深300 ETF | 510300.SH | 流动性最好，基准 | 收盘价、涨跌停 |
| 游戏 ETF | 516010.SH | 流动性较差，极端情况 | 数据完整性 |
| 纳指 ETF | 513100.SH | 跨境 ETF，有熔断 | 溢价、熔断处理 |
| 沪深300 指数 | 000300.SH | Regime 基准 | 指数成分股 |

**关键任务**：
| Task | 描述 | 预估工时 | 状态 |
|------|------|----------|------|
| 5.1 | 实现黄金数据集管理器 | 2h | ❌ |
| 5.2 | 实现数据比对引擎 | 4h | ❌ |
| 5.3 | 手工核验收盘价（100 天） | 8h | ❌ |
| 5.4 | 手工核验复权因子 | 8h | ❌ |
| 5.5 | 手工核验涨跌停状态 | 4h | ❌ |
| 5.6 | 生成数据质量基线报告 | 8h | ❌ |

**验收标准**：
- [ ] 黄金数据集管理器可用
- [ ] 数据比对引擎正常工作
- [ ] 手工核验完成 100% 覆盖
- [ ] 数据质量基线报告生成
- [ ] **数据准确率 >= 99.5%**
- [ ] 所有已知问题记录在案

---

## 执行顺序和依赖关系

```
Phase 0: 技术债务清理
    |
    v
Phase 1: DQ 三层架构 ──────┐
    |                      |
    v                      v
Phase 2: DataHub 完整实现 ──┤
    |                      |
    v                      v
Phase 3: 数据摄取增强 <─────┘
    |
    v
Phase 4: 数据引擎增强
    |
    v
Phase 5: 黄金数据集验证 ⭐ 最终验收
```

**关键路径**：
1. **Phase 0 必须最先完成**（基础正确性）
2. **Phase 1 DQ 架构必须在 Phase 3 数据摄取增强前完成**
3. **Phase 2 和 Phase 1 可并行开发**
4. **Phase 4 可以在 Phase 2 后开始**
5. **Phase 5 必须在所有其他 Phase 完成后执行**（最终验收）

---

## 预估工作量

| Phase | 任务数 | 预估工作量 |
|-------|--------|-----------|
| Phase 0: 技术债务清理 | 14 | 3-4 天 |
| Phase 1: DQ 三层架构 | 10 | 5-6 天 |
| Phase 2: DataHub 完整实现 | 8 | 4-5 天 |
| Phase 3: 数据摄取增强 | 8 | 4-5 天 |
| Phase 4: 数据引擎增强 | 5 | 3-4 天 |
| Phase 5: 黄金数据集验证 | 6 | 5-7 天 |
| **总计** | **51** | **24-31 天** ≈ **4-5 周** |

---

## 涉及的 Skills

| Phase | Skills |
|-------|--------|
| Phase 0 | `polars-guide`, `observability` |
| Phase 1 | `polars-guide`, `pit-guide`, `observability` |
| Phase 2 | `pit-guide`, `polars-guide` |
| Phase 3 | `fastapi-guide`, `observability` |
| Phase 4 | `polars-guide`, `pit-guide` |
| Phase 5 | `polars-guide`, `observability` |

---

## 总体验收标准

### 数据完整性
- [ ] DQ 三层架构正常运行
- [ ] L1/L2 写入时检查生效
- [ ] L3 定时批量检查产生报告
- [ ] 隔离区机制工作

### 数据可用性
- [ ] Universe/Index 查询正常
- [ ] Freeze/Restore 功能可用
- [ ] 元数据查询接口完整

### 数据摄取
- [ ] 增量更新正常工作
- [ ] 质量监控产生指标
- [ ] 告警正确发送
- [ ] AkShare 降级切换

### 性能指标
- [ ] 缓存命中率 >= 70%
- [ ] 复杂查询性能提升
- [ ] PIT 查询正确生成

### 代码质量
- [ ] 所有测试通过
- [ ] 测试覆盖率 >= 80%
- [ ] `pixi run -e dev ci-check` 通过
- [ ] 无新增 linting 错误

### 黄金数据集验证 ⭐ 最终验收
- [ ] 黄金数据集管理器可用
- [ ] 数据比对引擎正常工作
- [ ] 手工核验完成 100% 覆盖
- [ ] 数据质量基线报告生成
- [ ] **数据准确率 >= 99.5%**
- [ ] 所有已知问题记录在案

---

## Sprint 2 完成后的系统能力

完成 Sprint 2 后，系统将具备：

1. **完整的数据质量保障**：L1/L2/L3 三层检查机制
2. **可靠的数据摄取**：增量更新、质量监控、异常告警
3. **灵活的数据查询**：Universe、Index、Freeze、元数据
4. **高性能数据访问**：缓存层、查询优化
5. **生产就绪**：定时调度、API 触发、自动切换
6. **数据质量基线**：黄金数据集验证，数据源可靠性评估

这将为 Sprint 3 的引擎开发提供坚实的数据基础。

---

## 关键文件清单

### 新建文件（18 个）
| 文件路径 | 用途 |
|----------|------|
| `packages/datahub/config/dq_rules.yaml` | DQ 规则配置 |
| `packages/datahub/src/ditto_data_hub/dq/engine.py` | DQ 执行引擎 |
| `packages/datahub/src/ditto_data_hub/dq/result.py` | DQ 结果模型 |
| `packages/datahub/src/ditto_data_hub/dq/checkers/technical.py` | L1 检查器 |
| `packages/datahub/src/ditto_data_hub/dq/checkers/business.py` | L2 检查器 |
| `packages/datahub/src/ditto_data_hub/dq/checkers/statistical.py` | L3 检查器 |
| `packages/datahub/src/ditto_data_hub/stores/quarantine_store.py` | 隔离区存储 |
| `packages/datahub/src/ditto_data_hub/repositories/universe.py` | Universe 仓库 |
| `packages/datahub/src/ditto_data_hub/repositories/index.py` | Index 仓库 |
| `packages/datahub/src/ditto_data_hub/repositories/metadata.py` | 元数据仓库 |
| `packages/datahub/src/ditto_data_hub/runtime/freeze_manager.py` | Freeze 管理 |
| `packages/datahub/src/ditto_data_hub/runtime/cache.py` | 缓存层 |
| `packages/datahub/src/ditto_data_hub/sources/failover.py` | 自动切换 |
| `apps/server/src/ditto_server/validation/golden_dataset.py` | 黄金数据集管理器 |
| `apps/server/src/ditto_server/validation/comparison.py` | 数据比对引擎 |
| `apps/server/src/ditto_server/validation/report.py` | 验证报告生成 |
| `doc/validation/golden_dataset_baseline_v1.md` | 数据质量基线报告 |

### 修改文件（8 个）
| 文件路径 | 主要修改 |
|----------|----------|
| `packages/datahub/src/ditto_data_hub/repositories/bars.py` | 集成 DQEngine |
| `packages/datahub/src/ditto_data_hub/sources/base.py` | 增量更新接口 |
| `packages/datahub/src/ditto_data_hub/sources/tushare/source.py` | 增量适配 |
| `packages/datahub/src/ditto_data_hub/runtime/sql_engine.py` | 查询优化 |
| `packages/datahub/src/ditto_data_hub/hub.py` | freeze/universe/index 接口 |
| `apps/server/src/ditto_server/ingestion/tasks/dq_batch.py` | L3 批量检查 |
| `apps/server/src/ditto_server/ingestion/scheduler.py` | 定时调度 |
| `apps/server/src/ditto_server/api/ingestion.py` | API 触发 |

---

## 调整原因

原 Sprint 2 的核心引擎任务延后到 Sprint 3，原因是：

1. **数据层是整个系统的基石**，必须充分完善
2. **DQ 三层架构是数据质量的保证**，P0 优先级
3. **数据摄取增强是生产运行的必要条件**
4. **黄金数据集验证**确保数据源可靠可用，为引擎开发提供信心

---

## 状态图例

- ❌ 未开始
- 🔄 进行中
- ✅ 已完成
- 🚧 阻塞中
- 📝 规划中
