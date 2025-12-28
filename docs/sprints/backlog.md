# Backlog（想法池）

> 待办任务、想法、技术债

---

## 高优先级

<!-- 确定要做，但还没排入 Sprint 的任务 -->

### [datahub] PIT 语义完整性增强（Sprint-03）
- **描述**: 确保 asof 参数在所有场景下正确应用
- **变更**:
  - 复权基准已使用 asof（Sprint 1 已修复）
  - 验证 SQL 引擎与 Repo 层行为一致性
  - 添加端到端 PIT 安全测试
- **影响范围**: `repositories/bars.py`, `runtime/sql_engine.py`, 测试
- **预计工作量**: M
- **关联**: Code Review #5（部分已完成）

## 中优先级

### [datahub] 数据源参数支持
- **描述**: 允许 bars.get() 指定数据源
- **变更**: `bars.get()` 添加 `source` 参数，支持 tushare/akshare
- **影响范围**: `repositories/bars.py`
- **预计工作量**: S
- **关联**: Code Review #8

### [datahub] 成交量复权
- **描述**: 前复权时同时调整成交量
- **变更**: QFQ 调整时同步调整 volume/amount
- **影响范围**: `repositories/bars.py`
- **预计工作量**: S
- **关联**: Code Review #9

### [server] 实时监控仪表板
- **描述**: 数据摄取和质量监控的实时仪表板
- **变更**:
  - Grafana 集成
  - Prometheus 指标导出
  - 实时告警展示
- **影响范围**: `apps/server/`
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

---

## 已完成（移至 Sprint 2）

以下任务已纳入 Sprint 2 数据层完善：

### [datahub] DQ 三层架构实现
- **状态**: ✅ 已纳入 Sprint 2 Phase 1
- **参考**: [sprint-02-data-layer.md Phase 1](./sprint-02-data-layer.md#phase-1-dq-三层架构-10-任务-5-6-天-⭐-p0)

### [datahub] DataHub Facade 完整实现
- **状态**: ✅ 已纳入 Sprint 2 Phase 2
- **参考**: [sprint-02-data-layer.md Phase 2](./sprint-02-data-layer.md#phase-2-datahub-完整实现-8-任务-4-5-天)

### [server] 数据摄取增强
- **状态**: ✅ 已纳入 Sprint 2 Phase 3
- **参考**: [sprint-02-data-layer.md Phase 3](./sprint-02-data-layer.md#phase-3-数据摄取增强-8-任务-4-5-天)

### [validation] 黄金数据集验证
- **状态**: ✅ 已纳入 Sprint 2 Phase 5
- **参考**: [sprint-02-data-layer.md Phase 5](./sprint-02-data-layer.md#phase-5-黄金数据集验证-6-任务-5-7-天-⭐-最终验收)
