> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# Backlog（想法池）

> 待办任务、想法、技术债

---

## 高优先级

<!-- 确定要做，但还没排入 Sprint 的任务 -->

### [data] 数据源参数支持
- **描述**: 允许 bars.get() 指定数据源
- **变更**: `bars.get()` 添加 `source` 参数，支持 tushare/tdx
- **影响范围**: `data/sources/`
- **预计工作量**: S
- **关联**: Code Review #8

### [data] 成交量复权
- **描述**: 前复权时同时调整成交量
- **变更**: QFQ 调整时同步调整 volume/amount
- **影响范围**: `data/`
- **预计工作量**: S
- **关联**: Code Review #9

## 中优先级

### [interfaces] 实时监控仪表板
- **描述**: 数据摄取和质量监控的实时仪表板
- **变更**:
  - Grafana 集成
  - OTel 指标导出
  - 实时告警展示
- **影响范围**: `interfaces/`
- **预计工作量**: L

## 低优先级

---

## 技术债

<!-- 需要重构或优化的部分 -->

### [refactor] 示例：重构 XXX
- **原因**: ...
- **影响范围**: ...
- **预计工作量**: S/M/L

---

## 想法池

<!-- 随时记录的想法，定期整理 -->

-
-

---

## 已拒绝 / 暂缓

<!-- 决定不做或暂缓的想法，记录原因 -->

### [idea] 双源校验（Tushare vs AkShare）
- **拒绝原因**: 复杂度高、收益低，已采用黄金数据集验证 + 时序异常检测替代方案
- **日期**: 2025-12-28
- **参考**: `docs/design/09_data_quality_design.md`

### [data] PIT 语义完整性增强
- **状态**: ✅ 已在 V1 Sprint Phase 7 完成
- **内容**: rolling window `closed="left"` 强制、execution_delay PIT 文档、断言增强
