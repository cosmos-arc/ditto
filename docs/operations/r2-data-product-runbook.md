# R2 数据产品运维手册

> 适用范围：R2 A 股日频数据产品的预检、bootstrap、repair、认证、撤销、恢复与验收。
>
> 安全边界：本地单操作者、日频、人工确认。命令和证据不得包含 provider token、API key、账户标识或原始受限数据。

## 1. 发布边界

R2 hard scope 固定为 19 个独立数据产品：

```text
calendar stock_basic etf_basic index_basic stock_daily etf_daily index_daily
adj_factor fund_adj stock_status index_weight corporate_actions balance_sheet
income_statement cash_flow dividend valuation_metrics macro_indicators
commodity_daily
```

每个产品独立维护 raw、complete、certified 三类覆盖区间和不可变认证报告。聚合
bundle readiness 只用于消费门禁，不代替单产品证据。`fx_daily`、`margin_trading`
和 `pledge_ratio` 保持 deferred，不得为了凑齐 R2 范围而晋级。

## 2. 运行前检查

1. 当前分支代码和数据库 migration 已同步，工作树可追溯到 commit SHA。
2. Tushare、FRED/ALFRED 或本地 TDX 凭证只存在于本机 secret/config store。
3. 19 项 contract 至少各有一个可用 provider；entitlement 证据记录接口、权限和检查时间，不记录凭证值。
4. license ledger 对实际使用的 dataset/source 有 effective、reviewed 记录，且 `local_cache` 与 `derivative_compute` 为 allowed。
5. `stock_daily`、`index_daily`、`adj_factor`、`fund_adj` 有同一参考机器和 quota 下的代表 chunk benchmark。
6. 正式 repair/restore 前停止相关写入，并准备全新的 backup/restore 目标路径。

缺失凭证、entitlement、license 或 benchmark 时，live acceptance 必须返回
`configuration_blocked`；性能外推超限必须返回 `performance_blocked`。两者都不是
PASS，也不能靠 fixture 报告覆盖。

## 3. 确定性 fixture 验收

Fixture 验证 19 项静态 contract、预检计算、联合 SQLite/payload 恢复和连续两次
幂等性，不访问真实 provider：

```bash
uv run --no-sync python -m ditto_apps.scripts.r2_data_acceptance --mode fixture
```

通过条件：进程退出码为 0，顶层 `status` 为 `ready`，`preflight.contract_count`
为 19，`recoverability.passed=true`，且第二次运行的 durable write 为 0。

## 4. Live evidence 输入

Live runner 只接受非敏感 JSON。`provider_access` 应覆盖每个 hard-scope product
实际选用的 provider dataset；四个 benchmark dataset 必须使用真实测量值。

```json
{
  "provider_access": [
    {
      "provider_dataset": "tushare:daily",
      "entitled": true,
      "evidence_uri": "artifact://r2/provider-access/tushare-daily.json",
      "checked_at": "2026-07-18T06:00:00Z"
    }
  ],
  "benchmarks": [
    {
      "dataset_id": "stock_daily",
      "sample_partitions": 20,
      "sample_rows": 100000,
      "elapsed_seconds": 60.0,
      "target_partitions": 3000,
      "observed_at": "2026-07-18T06:00:00Z",
      "evidence_uri": "artifact://r2/benchmark/stock-daily.json"
    }
  ],
  "incremental_elapsed_seconds": 600.0,
  "workbench_query_seconds": 1.2,
  "first_run": {
    "durable_identity_count": 2500,
    "write_attempt_count": 2500,
    "snapshot_ids": ["snapshot:stock_daily:2026-07-18"]
  },
  "second_run": {
    "durable_identity_count": 2500,
    "write_attempt_count": 2500,
    "snapshot_ids": ["snapshot:stock_daily:2026-07-18"]
  }
}
```

示例只描述 schema，不是通过证据。实际文件必须包含 19 项 provider access 和四类
benchmark。Live runner 还会从本机配置判断凭证是否存在，并从 runtime license
ledger 读取 reviewed records；输入 JSON 不能替代这两类事实。

## 5. Bootstrap 与 repair

所有危险命令默认只输出 preview。执行时必须原样输入 preview 返回的
`confirmation_phrase`：

```bash
# preview
uv run --no-sync ditto data-products bootstrap stock_daily \
  --start-date 2015-01-01 --end-date 2026-07-17 --source tushare

# explicit confirm
uv run --no-sync ditto data-products bootstrap stock_daily \
  --start-date 2015-01-01 --end-date 2026-07-17 --source tushare \
  --confirm data-product:bootstrap:stock_daily:confirm

# schedule-aware missing repair
uv run --no-sync ditto data-products repair stock_daily
uv run --no-sync ditto data-products repair stock_daily \
  --confirm data-product:repair:stock_daily:confirm
```

Bootstrap/repair 只处理 planner 标记为 missing、failed 或 evidence-incomplete 的
chunk。完成态要求 payload、catalog、lineage 与 success evidence 同时闭环；补偿
失败时不得手工把 partition 改为 complete。

## 6. Certification 与治理

认证报告先由机器冻结，人工 review 只能追加审批事实，不能修改 coverage、hash、
DQ、PIT 或 license 内容：

```bash
uv run --no-sync ditto data-products certify stock_daily
uv run --no-sync ditto data-products certify stock_daily \
  --report-id <REPORT_ID> --actor <ACTOR> \
  --confirm data-product:certify:stock_daily:confirm

uv run --no-sync ditto data-products promotion stock_daily
uv run --no-sync ditto data-products promotion stock_daily \
  --criterion <CRITERION> --evidence-uri <EVIDENCE_URI> --actor <ACTOR> \
  --confirm data-product:promotion:stock_daily:confirm

uv run --no-sync ditto data-products revoke stock_daily
uv run --no-sync ditto data-products revoke stock_daily \
  --report-id <REPORT_ID> --actor <ACTOR> --reason <REASON> \
  --confirm data-product:revoke:stock_daily:confirm
```

Revoke 为 append-only；历史报告和 review 不删除。Coverage regression、许可失效、
source snapshot 不可解析或 consumer replay 失败时，先 revoke，再 repair 和
recertify。

## 7. 联合 backup/restore 与 live acceptance

四个目标路径必须明确且 restore 目标不存在。不要把 `$HOME`、`~`、仓库根目录或
未解析 glob 作为目标：

```bash
uv run --no-sync python -m ditto_apps.scripts.r2_data_acceptance \
  --mode live \
  --evidence /absolute/path/r2-live-evidence.json \
  --sqlite-path /absolute/path/runtime.db \
  --payload-root /absolute/path/data-products \
  --backup-root /absolute/path/r2-backup-20260718 \
  --restore-root /absolute/path/r2-restore-20260718
```

Runner 会验证 manifest、SQLite 逻辑行数和 payload tree hash，并在独立目标恢复。
目标已存在、manifest/hash 不一致或恢复不完整时 fail closed。备份和真实 payload
不提交仓库；只归档脱敏的机器报告、hash、行数和 artifact URI。

## 8. API 与工作台

```bash
# API + production Web build, loopback only
task dev
```

工作台路径为 `/platform/data-products`，只调用 `/api/v1/data-products/*`。Overview、
Coverage、Quality、Runs & Repair、Evidence & License 都必须显示真实 API 状态。
Loading、empty、error 或缺认证报告时不得回退到硬编码数据。

## 9. 故障处理

| 状态 / reason | 操作 |
|---|---|
| `missing_provider_credential` | 在本机 secret/config store 配置凭证，重新运行 preflight；不要把值写入 evidence |
| `provider_entitlement_denied` | 核对账号权限或按已审批 fallback policy 改源；不隐式采购 provider |
| `license_evidence_missing` | 由 reviewer 向 append-only ledger 写入 effective 许可记录，再重新认证 |
| `bootstrap_projection_exceeds_24h` | 调整 range/chunk/parallel 策略后重新 benchmark，不能放宽 Gate 冒充通过 |
| `incremental_exceeds_30m` | 检查 quota、重试和 provider availability，保留实际完成时间 |
| `workbench_query_exceeds_5s` | 检查 read model 聚合与索引，修复后重新测量 |
| `recoverability_*` | 停写，保留失败 backup，使用新目标重跑；不要覆盖原数据 |
| `second_run_wrote_durable_state` | 阻止 promotion，定位 identity/checkpoint 冲突并重新跑两次 |

## 10. 发布门禁

```bash
task check
task pit
task check-contract
task test-system
task ci
```

完整 DoD 和本次证据映射见
[R2 设计 §16](../plans/2026-07-17-r2-data-product-design.md#16-definition-of-done) 与
[R2 evidence index](../evidence/r2/README.md)。
