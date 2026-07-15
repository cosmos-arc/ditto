# R1 日常运营手册

## Preflight

确认交易日、数据库备份、数据源凭据和磁盘空间正常；先运行数据状态与 DQ 检查，核对每个已发布策略声明的 `required_datasets` 均已到达目标信号日。

## 正常运行

收盘数据稳定后执行：

```bash
ditto ops run-eod --signal-date YYYY-MM-DD
```

结果按策略返回 `completed`、`no_rebalance`、`blocked`、`failed` 或 `rerun_conflict`。逐项核对 batch key、artifact ID、checksum 和所需数据集状态。

## 重跑与冲突

相同信号日、策略版本和输入可安全重跑，返回同一产物。输入 checksum 改变时，仅无成交的 pending intent 可被 supersede；已有成交会返回 `rerun_conflict`，不得强制覆盖。单策略重跑：

```bash
ditto ops run-eod --signal-date YYYY-MM-DD --strategy-id STRATEGY_ID
```

## 失败恢复

`blocked` 先修复缺失、过期或 DQ 失败的数据集；`failed` 根据机器可读 reason 修复后重跑。告警或通知失败不替代主结果核对，日志中不得记录 token。

## 备份与收盘后核对

变更前备份 SQLite 与 artifact 目录。运行后确认 Signal Package（包括零调仓）已持久化、intent 数量与 checksum 一致、账户基线日期不晚于信号日，并保存每日 outcome 作为交接证据。
