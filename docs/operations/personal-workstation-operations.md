# 个人量化工作站运行与恢复手册

本手册覆盖五域产品首次上线前的日常调度、停机决策、四域数据库恢复和审计取证。它不授权真实券商操作，也不允许用实验数据、模型猜测或人工改库绕过 fail-closed 状态。

## 每日调度与职责

所有时间使用 `Asia/Shanghai`。工作日 19:45 由 data 阶段启动，成功后依次解锁 Selection、Paper，最后运行 EOD 证据聚合。任何上游阶段失败，下游不得启动。

| 阶段 | 触发 | 前置 | 责任模块 | 失败动作 |
|---|---|---|---|---|
| data | 工作日 19:45 cron | 无 | `ditto_apps.jobs.flows.eod` | 冻结 Selection/Paper/EOD |
| Selection | data success | data | `ditto_apps.jobs.flows.eod` | 冻结 Paper/EOD |
| Paper | Selection success | Selection | `ditto_apps.jobs.paper_eod` | 冻结 EOD，保留原账本 |
| EOD | after success | data、Selection、Paper | `ditto_apps.jobs.eod_evidence` | 本日不得标记完成 |

机器合同在 `ditto_apps.jobs.workstation_schedule.WORKSTATION_SCHEDULE`。操作员同时检查 freshness、DQ、run、Paper、Agent 和 E2E 六组 dashboard 信号；缺少任一信号按不完整运行处理。

## Data outage

1. 立即把当日运行标记为 blocked，停止 Selection、Paper 和 EOD；不要启用 experimental provider 或 latest fallback。
2. 记录 correlation ID、失败 dataset、provider、knowledge/publication cutoff、source snapshot 和最后成功游标。日志或工单中不得粘贴 token、原始账户备注或完整 provider payload。
3. 在 System / Data Products 核对 freshness、DQ、license、coverage 和 provider unavailable policy。许可、时间可见性或 snapshot 身份缺失时不得重试下游。
4. 修复后从确定的游标幂等重摄取，重跑 DQ、PIT future sentinel 和 snapshot replay；只有新认证报告被明确批准后才恢复链路。
5. 以相同 correlation ID 建立恢复记录，但新的 ingestion/run ID 必须独立。确认旧运行仍为 failed/blocked，不能覆写为 success。

## Paper pause

1. 暂停目标 Paper session；暂停后不接受新 intent/fill，已有账本事件保持不可变。
2. 记录 session、account、last event sequence、valuation snapshot 和 correlation ID；先完成四域备份。
3. 运行 reconcile。unbalanced、重复事件、游标漂移或 source snapshot 漂移都保持暂停；不得直接编辑 SQLite 行。
4. 必要修复只能追加 reversal/correction 或通过幂等重放完成。恢复前验证现金、持仓、费用、未成交与最后序号。
5. 由操作员显式恢复 session；自动任务不得自行解除暂停。

## Agent unavailable

1. 确定性 Today、Markets、Selection、TA、Portfolio 和 ledger 功能继续可用；不得用模板文本伪装模型结果。
2. 新 Agent run 返回结构化 unavailable/failed。已排队但未提交的 run 保留为 queued，可在同一 run ID 上恢复。
3. 检查 provider health、approved license class、egress allowlist 和模型配置。任何许可不明先阻断 evidence 到模型的传输。
4. SSE 客户端使用持久化 `Last-Event-ID` 恢复；只回放该 ID 之后的事件，不重新执行模型。
5. 同一个 idempotency key 只允许相同请求重放；请求体漂移必须 conflict。

## Manual correction

1. Manual 账户只追加事件。错误成交、转入转出或期初余额通过 correction/reversal 事件修正，不删除或更新历史行。
2. 提交前展示 account、原事件、修正原因、币种和金额并要求显式确认；保留 created_by、correlation ID 与 event sequence。
3. 云端 Agent evidence 删除自由文本身份、备注和精确金额；本地详细视图也永不返回私人自由文本。
4. 从期初和完整事件序列重建投影，核对现金、持仓和 valuation snapshot。重建差异存在时保持 blocked。

## PAP-09 账户 bootstrap、live anchor 与可选自然日记录

唯一提案是 `docs/evidence/personal-workstation/pap09/account-acceptance-proposal-20260902.json`。先验证 proposal 中的 `exact_acceptance_request.approval_hash` 与 canonical `arguments` 一致，并确认批准短语来自操作员本人；此前的策略保存或提交审核批准不能复用。bootstrap 是生产式本地账户写入，只能在收到 proposal 内完整精确批准短语后执行一次。

```bash
uv run --no-sync python -m ditto_apps.scripts.q4_live_account_acceptance bootstrap \
  --proposal docs/evidence/personal-workstation/pap09/account-acceptance-proposal-20260902.json \
  --approved-request-hash 8f9e27eff65976bf42413335ae80e63cb9982b3cbb8a4727d69b2450792922e2 \
  --operator-id workspace-user
```

bootstrap 必须产生专用 Manual/Paper 账户、Manual 追加事件与重建回执，同时保持 Paper session/fill、broker connection 和 real order 为 0。随后每次调度最多记录一个严格晚于批准本地日期、已经结束且 Tushare bar 已发布的交易日：

```bash
uv run --no-sync python -m ditto_apps.scripts.q4_live_account_acceptance record-day \
  --proposal docs/evidence/personal-workstation/pap09/account-acceptance-proposal-20260902.json \
  --approved-request-hash 8f9e27eff65976bf42413335ae80e63cb9982b3cbb8a4727d69b2450792922e2 \
  --operator-id workspace-user

uv run --no-sync python -m ditto_apps.scripts.q4_live_account_acceptance status \
  --proposal docs/evidence/personal-workstation/pap09/account-acceptance-proposal-20260902.json \
  --approved-request-hash 8f9e27eff65976bf42413335ae80e63cb9982b3cbb8a4727d69b2450792922e2
```

`waiting_for_next_published_day` 是这个可选自然日记录器的正常状态，不得回填当日或未来日。缺 bar、非连续日期、证据签名/公开镜像漂移、重复成交、账本不平或 snapshot 漂移均 fail closed，并要求人工复核。该记录器已经产生 2026-09-02 live anchor；后续自然日累计不是 Q4/PAP-09 发布阻塞项，发布 Gate 使用下一节的 20 日加速验收。核心账本、Paper 语义或 snapshot 合同改变后必须废弃相关计数并重新提案和批准。全过程不得启用 broker、发布/激活策略或发真实订单。

### PAP-09 历史真实交易日加速验收

发布验收不要求等待 20 个自然交易日。`docs/evidence/personal-workstation/pap09-accelerated-proposal-20260902.json` 冻结了 Tushare 交易日历、20 个已收盘真实交易日的逐日 bar、每日独立 Paper session、结算日以及 2026-09-02 live anchor。该模式逐日执行生产 Paper、账本、reconcile、签名和重启恢复合同，可解除 Q4/PAP-09 的跨日输入验收，但明确不宣称 wall-clock soak。它使用隔离的账户、数据库和证据目录，不修改 Day 1 live 账户。

加速提案需要独立的精确批准，不能复用账户 bootstrap、策略保存或提交审核批准。收到 proposal 内完整批准短语后运行：

```bash
uv run --no-sync python -m ditto_apps.scripts.q4_accelerated_paper_acceptance run \
  --proposal docs/evidence/personal-workstation/pap09-accelerated-proposal-20260902.json \
  --approved-request-hash 4a3a257bf97afe893cd402be34ab890869a96ac2e6db8b599f60c799b8a5032b \
  --operator-id workspace-user

uv run --no-sync python -m ditto_apps.scripts.q4_accelerated_paper_acceptance status \
  --proposal docs/evidence/personal-workstation/pap09-accelerated-proposal-20260902.json \
  --approved-request-hash 4a3a257bf97afe893cd402be34ab890869a96ac2e6db8b599f60c799b8a5032b
```

通过条件是 20/20 个日期与冻结日历一致、每日只有一个成交、逐日 EOD reconcile 平衡、HMAC 链连续、最终状态可从数据库和签名证据完全重建，且 broker connection、real order、策略发布/激活均为 0。任一 provider bar 漂移、未来日期、重复成交、账本差异或不可重建状态使整组失败；核心语义变化后必须重新生成提案并重跑完整 20 日。

## Q5 只读组合闭环与 GLM 诊断

`docs/evidence/personal-workstation/q5/live-portfolio-proposal-20260902.json` 冻结同一时点的 Model、Paper、Manual 身份、真实 Tushare snapshot、Selection lineage、策略输出和禁止写入项。它只写派生的 signal package、Manual execution baseline 与验收证据，不修改 Paper/Manual journal，不发布或激活策略。收到提案内完整精确批准短语后运行：

```bash
uv run --no-sync python -m ditto_apps.scripts.q5_live_portfolio_acceptance run \
  --proposal docs/evidence/personal-workstation/q5/live-portfolio-proposal-20260902.json \
  --approved-request-hash f6661fefac9294bf1dee388b1fa19b050633d1f233768526c9e374f596c88811 \
  --operator-id workspace-user
```

组合证据通过后，以下入口只在显式 `--approval-a4` 之后加载已保存的本机 GLM 凭据，并仅发送 `approved-research` 最小化 evidence；原始 provider rows、账户流水和自由文本不会出站：

```bash
uv run --no-sync python -m ditto_apps.scripts.q5_live_portfolio_diagnostic \
  --model glm-5.3 \
  --approval-a4 \
  --agent-data-root /private/tmp/ditto-q5-portfolio-diagnostic-20260902 \
  --portfolio-acceptance docs/evidence/personal-workstation/q5/live-portfolio-acceptance-20260902.json \
  --output docs/evidence/personal-workstation/q5/live-portfolio-diagnostic-20260902.json
```

两步都必须保持 broker connection、real order、账户/target 写入和 Agent write tool 为 0。诊断中的每个数值必须绑定 sealed evidence 的精确 dotted path 与字符串值。

## 工作站备份与恢复（#446 配方）

恢复单位是 6 个物理 SQLite 库 + 可选 research artifacts 树，恢复边界、精确清单、命令与演练核对单见[工作站备份配方](workstation-backup-recipe.md)。三层备份包装与 `ops workstation` 命令已随 #446 删除；R3 研究域恢复（含 pinned artifacts）仍走 [R3 恢复流程](../runbooks/backup-restore.md)，两种恢复分别进入全新目标，不能覆盖同一个根。

备份前停止全部 API、jobs、Agent 和其他 writer，保持停写直到备份与验证结束。各库逐次复制（SQLite Backup API），不构成自动跨库原子快照。恢复永不覆盖活动运行时：先在隔离根 `verify`（完整性 + 每域业务事实），切换活动根属于单独变更，必须再次明确批准。

配方回归测试：`apps/backend/tests/integration/operations/test_workstation_backup_recipe_integration.py`（非空根 备份→恢复→校验 演练、必需文件缺失失败、可选 artifact 缺失不阻断且旧实验不可重放）。R3 领域恢复继续由既有 `test_r3_backup_restore.py` 验证 governance、holdout、pinned packet 与 artifact bytes。

组合/Agent 的 `tests/system/portfolio-agent.spec.ts` 验证精确身份 URL 下三类组合、实际工具 evidence 和刷新回读，仅模型边界使用确定性替身。它不证明 LIVE 模型质量。研究页面到组合的日常导航、普通 UI 审批后的写入恢复仍未接通，不属于这项工程验收。

## 恢复演练

每个候选版本至少执行以下四项，并把精确测试 selector、退出码和时间写入 recovery evidence：

- 进程在提交前中断：run 保持 queued 且可重试；
- DB 损坏：hash/integrity 验证拒绝恢复且不留部分目录；
- SSE 断线：按 Last-Event-ID 单调恢复且不重新执行；
- duplicate request：相同请求精确 replay，body drift conflict。

## 监控与升级

一个 ingest→Agent→ledger 旅程共享 correlation ID 和 OTel trace；span 只记录 evidence hash，不记录原始证据。以下任一条件立即升级并阻断相应链路：freshness 超 SLA、DQ issue、daily run 非 completed、Paper reconcile unbalanced、Agent run failed/unavailable、E2E trace 缺 stage 或超预算。

事故记录至少包含开始/发现/恢复时间、影响 dataset/account/session、correlation/run/snapshot IDs、许可判断、已执行命令和验证结果。不得包含密钥、精确账户金额或私人自由文本。

## Tabletop checklist

- [ ] 操作员能从 schedule 指出每个下游为何被阻断。
- [ ] Data outage 不允许 experimental/latest fallback。
- [ ] Paper pause 不产生新 fill，修复只追加事件。
- [ ] Agent unavailable 不影响确定性产品，SSE 恢复不重新执行。
- [ ] Manual correction 不改历史行，云 evidence 已脱敏。
- [ ] 备份配方覆盖 6 库+可选 artifact 树，恢复目标全新且隔离。
- [ ] 恢复演练与 privacy/performance 报告均由 Gate manifest 哈希。

## OPS-10 发布候选签发（已随 #446 删除）

发布候选聚合器 `ditto_apps.scripts.personal_workstation_release_candidate` 已按成本审计 C7 删除：本地 review 流程取代机器签发。历史签发证据保留在 `docs/evidence/personal-workstation/ops/release-candidate-20260902.json` 及其 manifest，仅作历史记录，不再续签。
