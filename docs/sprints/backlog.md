# Backlog（想法池）

> 待办任务、想法、技术债

---

## 高优先级

<!-- 确定要做，但还没排入 Sprint 的任务 -->

### [datahub] DQ 三层架构实现（Sprint-02 P1 任务7）
- **描述**: 实现 DQ 三层架构（L1 技术校验、L2 业务规则、L3 统计异常）
- **变更**:
  - YAML 配置文件定义规则（替代当前硬编码）
  - L1 失败时硬失败（阻断写入，而非仅记录警告）
  - L3 统计校验（Z-score、完整性检查）
  - 隔离区机制（失败数据隔离存储）
- **影响范围**: `runtime/dq_checker.py`, `runtime/dq_rules.py`, `repositories/`
- **预计工作量**: L
- **关联**: Code Review #1, #2, #6

### [datahub] DataHub Facade 完整实现（Sprint-02）
- **描述**: 添加缺失的核心入口方法
- **变更**:
  - `hub.universe` - UniverseRepository（股票池/成分股）
  - `hub.index` - IndexRepository（指数数据查询）
  - `hub.freeze` - FreezeManager（数据冻结点）
- **影响范围**: `hub.py`, 新增 repository 文件
- **预计工作量**: M
- **关联**: Code Review #7

## 中优先级

### [datahub] PIT 语义完整性增强
- **描述**: 确保 asof 参数在所有场景下正确应用
- **变更**:
  - 复权基准已使用 asof（本次 Sprint 1 已修复）
  - 验证 SQL 引擎与 Repo 层行为一致性
  - 添加端到端 PIT 安全测试
- **影响范围**: `repositories/bars.py`, `runtime/sql_engine.py`, 测试
- **预计工作量**: M
- **关联**: Code Review #5（部分已完成）

## 低优先级

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

### [idea] 示例想法
- **拒绝原因**: ...
- **日期**: 2024-12-26
