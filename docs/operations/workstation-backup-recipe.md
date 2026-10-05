# 工作站备份配方（#446）

单用户本地工作站的唯一备份入口。替代已删除的三层备份包装与发布候选
验收链（成本审计 C7）；不提供自动调度、引用垃圾回收或云备份。

## 恢复边界（先读）

- 备份保证**当前可用状态**：paper/manual 账本与用户输入、agent 状态、
  当前策略/配置与 review/activation 事实、holdout 消费记录，以及恢复
  当前所选运行配置必需的文件。
- 旧实验的历史 raw payload 与 artifact 是**可选树**：缺失不阻断当前
  恢复，但旧实验**显式不可重放**——重拉得到的是新观察与新快照，不冒
  充旧版本；缺依赖的旧 COMPLETE 只说明曾经完成，不是新数据可读证据。
- 大批量可重建市场缓存恢复后重拉。
- 恢复点＝最近一次成功手动备份；两次备份间新增状态可能丢失。天级恢复
  时间是目标，**不承诺 24 小时 RPO 或"不丢数据"**。
- 停写窗口内逐库复制，单库一致性由 SQLite Backup API 保证，**跨库不原
  子**——恢复后以 `verify` 的业务事实检查为准，不以"库能打开/行数相
  同"为准。

## 精确恢复清单

6 个物理 SQLite 库（相对 `DITTO_DATA_ROOT`，不是三个逻辑域）：

| 相对路径 | 恢复对象 |
|---|---|
| `metadata/metadata.sqlite` | 数据 catalog、策略治理/激活事实（`strategy_active_pointer`/`strategy_activation_event`） |
| `research/research.sqlite` | 实验规格/run、**holdout 消费事实**（`holdout_claim`） |
| `trading/trading.sqlite` | paper/manual 账本（`paper_sessions`、`account_journal_events`） |
| `agent/agent.sqlite` | agent 运行状态（`agent_sessions` 等） |
| `agent/agent-presentation.sqlite3` | agent 展示层状态 |
| `agent/agent-shadow/decision-opinion.sqlite` | agent 影子意见 |

可选树：`research/artifacts/**`（旧实验 artifact；缺失→旧实验不可重放）。

路径覆盖部署注意：`SQLITE_PATH`/`DITTO_TRADING_SQLITE_PATH` 等环境变量
会搬走单个库；使用覆盖时不要直接套本配方默认路径，先停写并把各库实际
路径显式列入备份目录。配置（`.env`/`config/`）在数据根之外，另行纳入
主机级备份。

## 命令

```bash
# 1) 停写：停掉 CLI/调度/agent 等全部写入进程，确认无 -wal 增长
# 2) 备份（备份目录必须不存在；逐库 SQLite Backup API + sha256 校验）
python -m ditto_apps.scripts.workstation_backup_recipe backup \
    --data-root <DITTO_DATA_ROOT> --backup-dir <新备份目录>

# 3) 恢复演练（目标根必须为空；恢复到临时根，验证后再切换）
python -m ditto_apps.scripts.workstation_backup_recipe restore \
    --backup-dir <备份目录> --data-root <空目标根>

# 4) 校验：完整性 + 每域业务事实（账本/策略激活/holdout/agent）
python -m ditto_apps.scripts.workstation_backup_recipe verify \
    --data-root <目标根>
```

`verify` 退出码非零＝恢复失败；每条检查输出 PASS/WARN/FAIL：
- FAIL：必需库缺失、完整性校验失败、恢复内容与备份业务身份不符、业务事实查询出错（非缺表）。
- WARN：业务表存在但 0 行（该域当前无记录）或表不存在（该域未初始化）。

恢复在创建目标文件前校验 manifest schema、必需条目、路径及备份 SHA-256。
SQLite 恢复后按 schema 和完整有序字段值核对逻辑摘要；字节布局变化不影响业务等价。
目标根的 `restore-manifest.json` 保留备份基线，`verify` 据此检查恢复后的内容漂移。
此校验用于停写的恢复演练；恢复正常写入后，内容与旧恢复点不同是预期行为。

## 恢复演练核对单

演练必须在实际备份目录的临时恢复根上完成并通过 `verify`：

1. 账本：会话、事件和金额与备份逻辑身份一致（FAIL 级）。
2. 当前策略/配置与 review/activation 全部字段与备份一致（FAIL 级）。
3. agent 各库状态与备份一致（FAIL 级）。
4. holdout 消费身份和状态与备份一致（FAIL 级）。
5. 当前运行必需文件缺失 → `verify` 明确失败。
6. 可选旧 artifact 缺失 → 恢复继续，输出"旧实验不可重放"，不得清零
   holdout 消费事实。

## 与其他恢复线的关系

- R3 研究域验收的 `r3_research_backup`（`docs/runbooks/backup-restore.md`）
  是 R3 live acceptance 的组成，不属本配方。
- R2 运维门的可恢复性演练内嵌在 `r2_data_acceptance`，不属本配方。
- 本配方只做工作站级灾后恢复；上述验收线的证据边界见各自 runbook。
