# DataHub 完整重构计划总览

> 创建日期: 2026-01-27
> 版本: v1.0
> 状态: 计划草案

## 概述

本文档是 DataHub 数据层完整重构的**计划索引和总览**。完整的重构分为 9 个阶段，每个阶段都有独立的详细计划文档。

## 设计文档

完整的架构设计请参考：
- [docs/design/2026-01-26-datahub-complete-redesign.md](../../design/2026-01-26-datahub-complete-redesign.md)

## 执行策略

### 重构模式
- **渐进式迁移**: 每完成一个子域立即删除旧代码
- **不保留兼容层**: 保持代码库简洁
- **TDD 开发**: 测试先行，覆盖率 ≥ 80%

### 域执行顺序
1. **基础层** (BaseStore、配置系统)
2. **Metadata** → Market → Capital → Fundamental → Macro → Features → Factors
3. **Port 层** (应用编排)

### 计划拆分策略
- 按数据域拆分，每个域一个独立的计划文档
- 每个计划可独立执行（依赖前置阶段）

---

## 阶段计划清单

### Phase 0: 基础层重构
**计划文档**: [2026-01-27-datahub-phase0-base-layer.md](./2026-01-27-datahub-phase0-base-layer.md)

**目标**: 建立统一的数据存储接口、简化配置系统

**关键任务**:
- [ ] 实现 BaseStore 抽象基类
- [ ] 实现 ParquetStore 基类
- [ ] 实现 SQLiteStore 基类
- [ ] 重构配置系统 (DataRootConfig)
- [ ] 迁移现有 Store 使用新基类

**预计时间**: 6-7 个工作日

**Git Tag**: `datahub-phase0-base-layer-complete`

---

### Phase 1: Metadata 域重构
**计划文档**: [2026-01-27-datahub-phase1-metadata.md](./2026-01-27-datahub-phase1-metadata.md)

**目标**: 实现 domains/metadata/ 结构，整合所有元数据访问

**关键任务**:
- [ ] 创建 domains/metadata/ 目录
- [ ] 迁移 SecurityStore
- [ ] 拆分 IdentityStore
- [ ] 实现 Industry Stores
- [ ] 迁移 CalendarStore
- [ ] 实现 MetadataQueryService
- [ ] 删除旧的 Accessor

**预计时间**: 9 个工作日

**Git Tag**: `datahub-phase1-metadata-complete`

---

### Phase 2: Market 域重构
**计划文档**: [2026-01-27-datahub-phase2-market.md](./2026-01-27-datahub-phase2-market.md)

**目标**: 实现 domains/market/ 结构，整合市场数据访问

**关键任务**:
- [ ] 创建 domains/market/ 目录
- [ ] 迁移 Stock Bars/Status/AdjFactor
- [ ] 实现 ETF Stores (Bars/Status/Nav/AdjFactor)
- [ ] 实现 Index Stores (Bars/Constituent)
- [ ] 实现 MarketQueryService
- [ ] 删除 BarsAccessor

**预计时间**: 8 个工作日

**Git Tag**: `datahub-phase2-market-complete`

---

### Phase 3: Capital 域重构
**计划文档**: [2026-01-27-datahub-phase3-capital.md](./2026-01-27-datahub-phase3-capital.md)

**目标**: 实现 domains/capital/ 结构，支持资金流向数据

**关键任务**:
- [ ] 实现 Flow Stores (Market/Industry/Stock)
- [ ] 实现 Margin Stores (Detail/Summary)
- [ ] 实现 TopBoardStore
- [ ] 实现 LimitBoardStore
- [ ] 实现 ChipDistributionStore
- [ ] 实现 CapitalQueryService

**预计时间**: 10-12 个工作日

**Git Tag**: `datahub-phase3-capital-complete`

---

### Phase 4: Fundamental 域重构
**计划文档**: [2026-01-27-datahub-phase4-fundamental.md](./2026-01-27-datahub-phase4-fundamental.md)

**目标**: 实现 domains/fundamental/ 结构，支持财务数据

**关键任务**:
- [ ] 实现 Financial Stores (BalanceSheet/IncomeStatement/CashFlow)
- [ ] 实现 FinancialIndicatorStore
- [ ] 实现 Forecast Stores
- [ ] 实现 Holding Stores (Fund/Inst/Shareholder)
- [ ] 实现 DividendStore
- [ ] 实现 FundamentalQueryService

**预计时间**: 12-15 个工作日

**Git Tag**: `datahub-phase4-fundamental-complete`

---

### Phase 5-7: Macro、Features、Factors 域重构
**计划文档**: [2026-01-27-datahub-phase5-7-macro-features-factors.md](./2026-01-27-datahub-phase5-7-macro-features-factors.md)

**目标**: 实现宏观数据、特征数据、因子数据支持

**关键任务**:

**Phase 5 - Macro 域** (3-4 天):
- [ ] 实现 IndicatorStore (支持 PIT)
- [ ] 实现 IndicatorMetadataStore
- [ ] 实现 MacroQueryService

**Phase 6 - Features 域** (6-8 天):
- [ ] 实现 Technical 特征 Stores
- [ ] 实现窄表 + 宽表存储
- [ ] 实现 FeaturesQueryService

**Phase 7 - Factors 域** (8-10 天):
- [ ] 实现 Style 因子 Stores
- [ ] 实现后处理模块
- [ ] 实现窄表 + 宽表存储
- [ ] 实现 FactorsQueryService

**Git Tags**:
- `datahub-phase5-macro-complete`
- `datahub-phase6-features-complete`
- `datahub-phase7-factors-complete`

---

### Phase 8: Port 层重构
**计划文档**: [2026-01-27-datahub-phase8-port.md](./2026-01-27-datahub-phase8-port.md)

**目标**: 重构 Port 层服务，实现应用编排

**关键任务**:
- [ ] 实现 SourceService
- [ ] 实现 Writer
- [ ] 实现 IngestionService
- [ ] 实现 DataService
- [ ] 实现 ReconciliationService
- [ ] 更新 API 路由

**预计时间**: 12 个工作日

**Git Tag**: `datahub-phase8-port-complete`

---

## 总时间估算

| 阶段 | 预计时间 |
|------|----------|
| Phase 0: 基础层 | 6-7 天 |
| Phase 1: Metadata 域 | 9 天 |
| Phase 2: Market 域 | 8 天 |
| Phase 3: Capital 域 | 10-12 天 |
| Phase 4: Fundamental 域 | 12-15 天 |
| Phase 5-7: Macro/Features/Factors | 17-22 天 |
| Phase 8: Port 层 | 12 天 |

**总计**: 约 **74-85 个工作日** (约 3.5-4 个月)

---

## 验收标准

### 代码质量
- [ ] Pyright 类型检查通过 (strict)
- [ ] Ruff 代码检查通过
- [ ] Pre-commit hooks 通过
- [ ] 测试覆盖率 ≥ 80%

### 架构验收
- [ ] domains/ 目录结构完整
- [ ] 所有域级 QueryService 实现完整
- [ ] Accessor 层完全移除
- [ ] Port 层服务编排清晰

### 功能验收
- [ ] 所有现有功能正常工作
- [ ] 新增数据域功能完整
- [ ] 数据摄入流程正常
- [ ] 质量对账功能正常

---

## 风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 现有功能破坏 | 高 | 中 | 充分测试，保持接口兼容 |
| 数据迁移失败 | 高 | 低 | 保留旧数据，编写迁移脚本 |
| 时间超期 | 中 | 中 | 按优先级调整，P0 优先 |
| 测试覆盖不足 | 中 | 低 | TDD 开发，覆盖率 ≥ 80% |

---

## 里程碑

1. **M1 - 基础层完成**: Phase 0 完成后
2. **M2 - 核心域完成**: Phase 1-2 完成后
3. **M3 - 数据域完成**: Phase 3-4 完成后
4. **M4 - 完整架构**: Phase 5-8 完成后

---

## 执行建议

1. **优先级**: 按 Phase 0 → Phase 1 → Phase 2 顺序执行
2. **并行度**: Phase 3-4 可以考虑并行开发
3. **灵活性**: Phase 5-7 可根据实际需求调整优先级
4. **稳定性**: 每个 Phase 完成后创建 Git Tag，确保可回滚

---

## 相关文档

- 设计文档: [docs/design/2026-01-26-datahub-complete-redesign.md](../../design/2026-01-26-datahub-complete-redesign.md)
- 各阶段详细计划: 见上述链接

---

## 变更记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-01-27 | v1.0 | 初始版本 |
