# R1 日常运营手册

本手册用于单账户、单活动 execution sleeve 的人工/paper 日频闭环。所有宿主机入口只监听 `127.0.0.1`；容器内监听 bridge interface 的服务也只能通过 loopback host port 发布，未实现认证前不得改成外网地址。命令输出和 evidence 中不得出现 provider token、真实账户号或个人路径。

## 1. Preflight

1. 明确信号日 D、由交易日历解析的 intended trade date D+1、活动 published seed、账户别名和 sleeve。不得用自然日 `D + 1` 代替交易日历。
2. 确认账户基线日期不晚于 D，且现金、NAV、持仓、可用数量完整。空仓账户是合法基线，不得用“持仓非空”推断基线存在。
3. 确认磁盘空间和 artifact 目录可写，并按第 6 节完成 SQLite 在线备份。
4. 检查活动策略声明的每个 `required_datasets` 已到达 D，freshness 与 DQ 均通过。任何必需数据集失败只阻塞依赖它的策略；不得让无关策略被全局跳过。
5. 本地启动服务时检查日志中的监听地址为 `http://127.0.0.1:8000`。

## 2. 正常 EOD

创建或更新 Prefect deployment 前，部署进程必须显式提供以下环境变量；缺失或空白时部署脚本会以 `EOD_DEPLOYMENT_CONFIG_MISSING` 拒绝生成定时任务：

- `DITTO_EOD_STRATEGY_ID`：19:45 定时任务唯一允许运行的 published strategy；
- `DITTO_EOD_ACCOUNT_ID`：对应的单账户 execution sleeve 别名；
- `DITTO_EOD_ALLOW_EXPERIMENTAL_DATA`：可选，未配置时为 `false`。仅在已核对 experimental 数据用途和证据后设为 `true`；无法识别的值会以 `EOD_DEPLOYMENT_CONFIG_INVALID` 拒绝部署。

部署完成后在 Prefect UI 核对 `eod-pipeline-prod` 的参数快照确实包含上述 strategy、account 和默认关闭的数据开关。修改活动 strategy/account 时必须重新部署并保存变更证据，不能依赖 flow 在运行时猜测默认值。账户别名由 secret store 或受控进程环境注入，不写入仓库。

收盘数据稳定后，使用显式策略与账户运行 CLI（最终参数以 `ditto ops run-eod --help` 为准）：

```bash
ditto ops run-eod \
  --signal-date YYYY-MM-DD \
  --strategy-id STRATEGY_ID \
  --account-id ACCOUNT_ALIAS
```

若且仅若本次策略声明了尚处于 `experimental` 的数据集，并且操作者已核对其用途与证据，才追加 `--allow-experimental-data`。默认不加该参数，避免实验级数据被静默带入执行建议。

Prefect 调度与该 CLI 必须调用同一个 EOD coordinator。结果会返回 `completed`、`no_rebalance`、`blocked`、`failed` 或 `rerun_conflict`；逐项保存：

- strategy/version、account/sleeve 和 D/D+1；
- required dataset snapshot IDs、freshness、DQ；
- run/batch key、package artifact ID 与 checksum；
- no-rebalance 标记或每个 intent 的目标/当前/差额、数量、参考价、手数和风险原因。

`no_rebalance` 也必须存在可校验 package，不能用“没有 intents”替代运行结果。

## 3. Daily Decision 与人工成交

> **Task 6 能力状态：等待数据库 schema 批准。** 多笔部分成交、append-only
> adjustment、replacement fill 和 effective-fill 计算尚不能作为 R1 已交付能力使用。
> 在 schema 获批、实现并通过验收前，错误成交不得覆盖、删除或用另一笔记录抵消；应停止
> 后续执行，保留原始证据并登记为待处理异常。

在 `runtime=live` 的工作台或 loopback API 中核对：

- `blocked`：只显示 reason code 与恢复入口，不允许成交动作；
- `review`：明确零调仓、风险、日期或重跑冲突，并展示 package/evidence；
- `ready`：显示数量、参考价、理由和风险，人工确认后才录入；
- 现阶段只核对既有 fill 事实；不要把多笔部分成交或成交更正作为可操作流程。

收盘后复盘必须核对现有 fill、成交偏差、费用、PnL 与 package checksum；Task 6
获批并验收后，才增加 effective fills、adjustment 链和剩余数量核对。

## 4. 重跑、冲突与中断恢复

相同 D、策略版本、账户基线和输入重复运行应 no-op，返回相同 artifact/checksum，且不新增 intent。单策略重跑示例：

```bash
ditto ops run-eod \
  --signal-date YYYY-MM-DD \
  --strategy-id STRATEGY_ID \
  --account-id ACCOUNT_ALIAS
```

若业务输入 checksum 改变：

- 尚无有效成交的 pending package 可按显式规则 supersede；
- 已有成交时返回机器可读 `RERUN_CONFLICT`，不得静默覆盖；
- 在 intent 写入后、状态更新前中断时必须通过已持久化 fill 事实检测冲突，不能只信 intent 状态。

Task 6 schema 获批并完成实现后，冲突判断才扩展到 adjustment/replacement 链与
effective fills；在此之前不得以手工覆盖模拟该能力。

中断演练：记录中断点，停止进程，保存数据库与 artifact hash，再以完全相同参数重跑。验收标准是无重复 intent/fill、package/checksum 一致，或明确的可恢复冲突。

已批准范围的确定性回归（包含同输入重跑、已有单笔 fill 的变更冲突和 finalize 中断恢复）可用下列命令复跑；它不覆盖尚未批准的 Task 6 adjustment ledger：

```bash
uv run --no-sync pytest --no-cov \
  apps/backend/tests/e2e/test_r1_daily_manual_trading.py -q
```

## 5. Blocked/failed 处置

按稳定 reason code 处理，不解析中文 message：

| Reason | 处置 |
|---|---|
| `NO_ACTIVE_STRATEGY` | bootstrap/发布并显式选择活动 seed |
| `EOD_RUN_MISSING` / `SIGNAL_PACKAGE_MISSING` | 用同一 coordinator 运行或重跑 EOD |
| `REQUIRED_DATA_NOT_READY` | 修复对应 required dataset 的 freshness/DQ 后只重跑受影响策略 |
| `ACCOUNT_BASELINE_MISSING` | 导入 D 前最近有效账户基线 |
| `QUANTITY_UNAVAILABLE` | 补齐现金、NAV、收盘价、手数或可用数量证据 |
| `CHECKSUM_MISMATCH` / `RERUN_CONFLICT` | 停止执行，保存两份输入/checksum，人工复核；不得强制覆盖 |
| `EOD_RUN_FAILED` | 根据结构化错误修复后用相同参数重跑 |

### 稀疏 PIT 历史证据恢复

当 `balance_sheet` 等稀疏 PIT 数据集因历史 catalog 分量缺少 L1/L2 证明、物理数据与
SUCCESS ingestion log 不匹配，或出现 `INGESTION_COMPONENT_QUALITY_EVIDENCE_INVALID` /
`PIT_COMPONENT_QUALITY_EVIDENCE_INVALID` 时，先停止 EOD 与其他写操作，并按第 6 节备份、
验证活动 SQLite。随后使用具体 provider（不能使用 `auto`）执行全历史重摄取：

```bash
uv run --no-sync python -m ditto_apps.cli.main ops reattest-sparse-pit \
  --dataset balance_sheet \
  --signal-date YYYY-MM-DD \
  --source tushare
```

该命令会枚举 catalog 中截止 D 的每个同源分量，包括已有 attestation 的分量，并逐个以
`force=true` 走正常摄取写路径、L1/L2 DQ、catalog upsert 和 SUCCESS ingestion log；不会直接
修改 `source_snapshot_id`。只有以下证据同时成立才视为恢复成功：

- 进程退出码为 0，顶层 `passed=true`，每个 `components[].passed=true`；
- 输出包含非空 `source_snapshot_id`、完整 `source_snapshot_ids` 与累计 `row_count`；
- 每个分量的 catalog checksum/row count、物理写结果与同源同日 SUCCESS log 匹配；
- 用完全相同参数再次执行仍返回相同聚合 snapshot ID 和 row count。重复执行仍会全量重摄取，
  因此应保留 provider 请求与耗时 evidence。

`SPARSE_REATTEST_COMPONENT_EXCEPTION` 或 `SPARSE_REATTEST_COMPONENT_INGESTION_FAILED` 表示
正常摄取未完成；`SPARSE_REATTEST_COMPONENT_QUALITY_EVIDENCE_INVALID` 表示 L1/L2 结果不完整；
`SPARSE_REATTEST_COMPONENT_DURABLE_EVIDENCE_INVALID` 表示 catalog 与 SUCCESS log 不一致；
`SPARSE_REATTEST_COMPONENT_DISCOVERY_FAILED` 表示无法读取待恢复 catalog 分量；
`SPARSE_REATTEST_SNAPSHOT_EVIDENCE_INVALID` 表示分量通过但累计证据仍不闭合。任何失败都保持
EOD blocked，修复 provider、物理存储或 SQLite 后用同一命令重跑。禁止手工拼接
`:quality=l1-l2`、直接更新 catalog marker，或只补 ingestion log 来伪造恢复。

通知失败不改变主业务结果。所有 token 只保存在 secret store/进程环境，不进入命令历史、日志或仓库。

## 6. SQLite 备份与恢复演练

数据库默认位于 data root 下的 `metadata/metadata.sqlite`，也可能由 `SQLITE_PATH` 覆盖。先从运行配置确认实际路径，以下用占位符表示，禁止直接复制未核对的路径。

### 备份

1. 停止 EOD、API 写操作和前端 mutation，记录开始时间。
2. 使用 Ditto 封装的 SQLite online backup API，而不是直接复制活动 WAL 文件；命令会拒绝覆盖已有 evidence，并在原子落盘前后执行完整性检查：

```bash
ditto ops backup-sqlite \
  --source /ABSOLUTE/PATH/metadata.sqlite \
  --destination /ABSOLUTE/PATH/r1-backup.sqlite
ditto ops verify-sqlite \
  --database /ABSOLUTE/PATH/r1-backup.sqlite
```

3. 两条命令都必须返回 `status=completed`、`integrity_check=ok`；保存 backup 的 SHA-256、逐表行数、artifact 目录清单与 package 文件 hash。备份文件留在受控位置，不提交仓库。

### 恢复

1. 不覆盖原库。准备独立临时 data root，将备份恢复为新 `metadata.sqlite`；命令在目标已存在时 fail closed。artifact 目录也恢复到对应位置：

```bash
ditto ops restore-sqlite \
  --backup /ABSOLUTE/PATH/r1-backup.sqlite \
  --destination /ABSOLUTE/PATH/restore-root/metadata/metadata.sqlite
ditto ops verify-sqlite \
  --database /ABSOLUTE/PATH/restore-root/metadata/metadata.sqlite
```

2. 恢复与验证命令都必须返回 `integrity_check=ok`，并与备份 evidence 比较逐表行数；文件 SHA 只用于标识各自 evidence，不要求经过 online restore 后字节级相等。
3. 用恢复路径和 loopback-only 配置启动服务，禁止使用生产 provider 写操作。
4. 比较关键表行数、活动策略版本、账户 baseline、package artifact/checksum、intents、fills 和 Daily Decision 输出。只有 Task 6 schema 获批并完成实现后，才把 adjustments/effective fills 加入恢复核对项。
5. 记录恢复耗时；完成后停止恢复实例。只有内容一致且服务可查询，恢复演练才 PASS。

## 7. 真实数据 acceptance 与交接

真实数据演练必须显式启用，固定 `2024-03-29` 和内置 published seed `seed_stock_selection_rotation`。测试必须运行 `strategy bootstrap-seeds`，不得发布临时 custom spec 代替。保存 dataset snapshot、DQ/freshness、published version、package/checksum 和 Daily Decision reason codes；凭证与真实账户信息不得落盘。

```bash
DITTO_RUN_REAL_DATA_ACCEPTANCE=1 \
  uv run --no-sync pytest --no-cov \
  apps/backend/tests/e2e/test_real_data_stock_selection_pipeline.py \
  -m e2e -q
```

未设置显式开关时测试必须在网络访问前 skip，以保持默认测试确定性；正式演练中任何 live 用例 skip 都只能记录为 `BLOCKED_EXTERNAL`。provider 不可用时记录时间、脱敏响应摘要和重试责任人，G1 仍为 FAIL。

每天使用 [`docs/acceptance/r1-g1-evidence-template.md`](../acceptance/r1-g1-evidence-template.md) 记录命令、时间、commit SHA、artifact/checksum、截图与结果。只有确定性 E2E、恢复、真实数据、前端 desktop/mobile 和所有质量门禁全部 PASS 后，才允许更新 maturity/能力评分。
