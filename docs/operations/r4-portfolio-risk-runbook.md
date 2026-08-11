# R4 Portfolio / Risk 运营手册

## 值班目标

R4 只在证据完整、优化可行、连续风控 ready、三层对账一致且报告新鲜时发布建议。
任何不确定状态按 blocked 处理；报告只读，不自动修复账本。

## 核心信号

关注 optimizer 状态/耗时、daily risk scan 耗时、VaR/ES 越限、risk-state restore
失败、reconciliation mismatch、Daily Decision V3 查询耗时与报告 freshness。SLO 为：
500 标的优化 p95≤5s、盘前风控 p95≤50ms、单账户 EOD p95≤60s、V3 p95≤2s。

## 处置流程

1. 确认 `account_id`、`sleeve_id`、trade date、policy digest 和 source snapshot IDs。
2. 若 optimizer 非 `optimal`，保留 solver/version/status、矩阵修正与约束复验结果；
   不重试其他 solver，不切换 legacy。
3. 若状态恢复失败，核对 schema version、event sequence、integrity hash 与实际持仓
   fingerprint；保持 blocked，禁止跳过恢复或改 hash。
4. 若对账失败，分别核对计划订单↔成交、成交重建持仓↔实际持仓、实际持仓↔
   RiskGate fingerprint。使用告警幂等键避免重复通知。
5. 人工修复必须在权威账本侧完成并重新跑完整 EOD；不得编辑只读报告或风险快照
   来掩盖差异。
6. 恢复后确认 `/daily-decision/v3` provenance 完整且 readiness=`ready`，再按单个
   strategy/sleeve 恢复 enforced。

## 回滚与降级

已启用 R4 的运行不得静默回退。需要停用时，应显式撤销该 strategy/sleeve 的 policy
绑定并保留审计记录；旧 checkpoint 仅在 R4 能力关闭时恢复。ETF 缺少穿透因子数据可
标记 `unavailable/partial`，但协方差风险仍需有效；股票因子证据缺失必须 blocked。

## 数据库边界

当前为开发阶段：data-root 启动初始化会直接、幂等创建 `risk_events`、
`risk_state_snapshots`、`daily_risk_reports`，不维护历史迁移路径或迁移脚本。清空新的
开发数据库后可由 initializer 重建；真实生产数据写入和历史数据迁移不在 R4 范围。
