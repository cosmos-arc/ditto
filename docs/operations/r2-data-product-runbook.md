# R2 数据产品运维手册

> 适用范围：R2 A 股日频数据产品的预检、bootstrap、repair、恢复与验收。
>
> 安全边界：本地单操作者、日频、人工确认。命令和证据不得包含 provider token、API key、账户标识或原始受限数据。
>
> 2026-10-03 注：认证/晋级/许可治理已随 #392/#396 删除,本手册只保留仍存在的通路。

## 1. 发布边界

R2 hard scope 固定为 19 个独立数据产品：

```text
calendar stock_basic etf_basic index_basic stock_daily etf_daily index_daily
adj_factor fund_adj stock_status index_weight corporate_actions balance_sheet
income_statement cash_flow dividend valuation_metrics macro_indicators
commodity_daily
```

每个产品独立维护 raw/complete 覆盖事实与不可变 provider snapshot 证据。聚合
bundle readiness 只用于消费门禁，不代替单产品证据。`fx_daily`、`margin_trading`
和 `pledge_ratio` 保持 deferred，不得为了凑齐 R2 范围而强行纳入。

## 2. 运行前检查

1. 当前分支代码和数据库 migration 已同步，工作树可追溯到 commit SHA。
2. Tushare、FRED/ALFRED 或 fuyao 凭证只存在于本机 secret/config store。
3. 19 项 contract 至少各有一个可用 provider；entitlement 证据记录接口、权限和检查时间，不记录凭证值。
4. `stock_daily`、`index_daily`、`adj_factor`、`fund_adj` 有同一参考机器和 quota 下的代表 chunk benchmark。
5. 正式 repair/restore 前停止相关写入，并准备全新的 backup/restore 目标路径。

缺失凭证、entitlement 或 benchmark 时，live acceptance 必须返回
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
benchmark。Live runner 还会从本机配置判断凭证是否存在；输入 JSON 不能替代该事实。

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
chunk。完成态要求 payload、catalog 与 success evidence 同时闭环；补偿
失败时不得手工把 partition 改为 complete。

### index_weight 观察事实表重建（#452）

2026-10 起 `index_weight` 表改为月度观察事实形状
`(index_id, instrument_id, trade_date, weight)`，不再维护
`effective_from/effective_to` 区间。schema 以 `CREATE TABLE IF NOT EXISTS`
应用，存量库中的旧表不会被自动改写；升级后继续写旧表会因缺 `trade_date`
列失败。处置（#451 裁决允许可重建缓存重拉）：

```bash
sqlite3 <market.db> "DROP TABLE IF EXISTS index_weight; DROP INDEX IF EXISTS idx_index_weight_current;"
# 重启应用/重跑 schema 初始化后，按第 5 节 bootstrap/repair 重拉 index_weight
```

旧表中的 `effective_from` 值即原观察日，如需留存可在 DROP 前自行归档。

## 6. 联合 backup/restore 与 live acceptance

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

## 7. 故障处理

| 状态 / reason | 操作 |
|---|---|
| `missing_provider_credential` | 在本机 secret/config store 配置凭证，重新运行 preflight；不要把值写入 evidence |
| `provider_entitlement_denied` | 核对账号权限或按已审批 fallback policy 改源；不隐式采购 provider |
| `bootstrap_projection_exceeds_24h` | 调整 range/chunk/parallel 策略后重新 benchmark，不能放宽 Gate 冒充通过 |
| `incremental_exceeds_30m` | 检查 quota、重试和 provider availability，保留实际完成时间 |
| `workbench_query_exceeds_5s` | 检查 read model 聚合与索引，修复后重新测量 |
| `recoverability_*` | 停写，保留失败 backup，使用新目标重跑；不要覆盖原数据 |
| `second_run_wrote_durable_state` | 阻止验收，定位 identity/checkpoint 冲突并重新跑两次 |

## 8. 发布门禁

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

## 9. #434 四组增补数据集（futures_daily / futures_basic / earnings_forecast / earnings_express / index_valuation）

单位与身份合同（2026-10-05 真实账号核验，代理 t.xiaodefa.top）：

- `futures_daily`：国内期货合约日线，身份=具体合约 ts_code（如 CU2506.SHF）。
  `amount` 万元；2020-01-01 前后成交量单/双边口径变化，原始口径保留不换算；
  `close` 可 null（结算价 settle 有效时不互填）。PK
  `(source_ticker, trade_date, knowledge_date)`，append-only。
- `futures_basic`：合约信息快照（品种/乘数/上市/最后交易日），按交易所
  SHFE/CZCE/DCE/INE/CFFEX/GFEX 分片全量抓取（全表 11287 行 > 单页 10000）。
  注意官方交易所代码是 SHFE/CZCE，不是 SHF/ZCE（后者静默返回空）。
- `earnings_forecast`：业绩预告上下界，净利润上下限**万元**。同日同标的同
  类型存在 update_flag 0/1 两行（修订身份进主键，不去重）；PK
  `(source_ticker, ann_date, report_date, forecast_type, update_flag, knowledge_date)`。
  日更走 `forecast_vip`（按 ann_date 全市场）；非 VIP `forecast` 必填 ts_code。
- `earnings_express`：业绩快报，金额字段**元**（与 forecast 万元不可共用换算）。
  PK `(source_ticker, ann_date, report_date, knowledge_date)`；日更走 `express_vip`。
- `index_valuation`：指数每日估值（社区计算指标），市值**元**、股本**股**，
  不能套用个股 daily_basic 的万元/万股换算。端点日覆盖 15 个大盘指数；
  空结果如实报告，不填零。PK `(instrument_id, trade_date, knowledge_date)`。

已知边界：代理对 `cn_pmi` 任何参数形态均返回空（端点可达、无数据）；
`sf_month` 社融三系列（增量当月/累计亿元、存量万亿元）已入宏观长表，
月度窗口参数 `start_m/end_m`（发 `start_date` 会被代理忽略并返回全历史）。

```bash
uv run --no-sync ditto ingest market futures 2026-09-30
uv run --no-sync ditto ingest market futures-basic 2026-10-05
uv run --no-sync ditto ingest fundamental forecast 2026-01-30
uv run --no-sync ditto ingest fundamental express 2026-01-30
uv run --no-sync ditto ingest market index-valuation 2026-09-30
```

## 10. 全球指数 21 指数全量摄取（#435）

`index_global` 官方 21 指数白名单落在
`ditto_data.models.GLOBAL_INDEX_CODES`（权威清单，摄取篮子与探针共用），
适配器 `_GLOBAL_INDEX_SPECS` 逐码声明时区/计价币种/收市时刻。官方表无
NDX；IXIC 是纳斯达克综合指数，不能替代纳斯达克 100（跨境纳指 100 ETF
基准缺口如实保留）。

- 用途为展示-only（#451 裁决）：`market_context` 以展示 metrics 暴露每码
  最新观察 close（`global_index_<code>_close`，unit=index_point），
  `global_return_1d` 恒为 None 并计入 declared_missing_inputs。
- 发布时刻官方不可知：published_at/available_at 恒为实际采集时刻；
  close_time 仅是 event_time 会话元数据（标 approx 的为最佳已知近似）。
- **调度语义（#507 H3）**：欧美指数的当日行情要等当地收盘（北京时间
  凌晨/早上）后才可得——白天跑日更会缺最新日。这不是错误：knowledge_date
  =采集日使其 fail-safe（不会把隔日数据当当日），缺的行由下一次摄取自然
  补齐；操作上把全球指数补数安排在午后（欧美均已收盘）即可取到前一当地
  交易日全量。
- 2026-10-05 实测可得区间：主流指数 1990 起；XIN9 2004-07、HKAH/AS51
  2007、SPTSX 2001、CSX5P 1998、CKLSE 1995、HKTECH 2020-07、
  RTS 2020-01 起；RUT/RTS/XIN9/HKAH/HKTECH vol 缺失率 100%，
  缺失保留 null 不补零。
- 摄取走既有 `global_index_daily` 日更路由（SOURCE_DEFINED），
  单码长历史由 client 按页宽 4000 自动翻页。

## 11. 新浪外盘连续期货参考（#436）

免费公开无 key 源（`GlobalFuturesService.getGlobalFuturesDailyKLine`，
JSONP），默认启用（`SINA_ENABLED=false` 可关）。作为商品复合源第三条腿
进入 `commodity_daily`（FRED 油/VIX + Tushare 金银 + Sina 外盘连续），
失败按 #432 完整性合同整体报错，不静默降级。

- 品种小白名单 `ditto_data.models.SINA_FOREIGN_FUTURES`：CL
  (5,000,005, 美元/桶)、GC (5,000,006, 美元/盎司)、SI (5,000,007,
  美元/盎司)。**ZSD 身份未核实**（2026-10-05 实测数值 3706 与已知金属
  品种不符且源无名称字段），不入表；核实后逐品种登记再扩。
- 连续参考身份：换月规则未知，不与具体可交易合约混身份（Tushare
  fut_daily 是合约日线，两者身份不同）；展示-only，不进入策略/回测/
  Paper/Agent 决策输入。
- 占位零语义：CL/GC 的 volume/position/settlement 恒为 0、ZSD 缺
  settlement——不证明真实成交/持仓/结算，一律不入库，仅存真实 OHLC。
- 端点无窗口参数：源侧返回全量当前视图后本地过滤；实测历史起点恰为
  探测日 30/10 年前（CL 1996-10-07、GC/SI 2016-10-05），疑似滚动窗口，
  回填深度以逐日摄取为准。trade_date_utc 为纽约午夜占位，真实收盘
  时刻未验证。
- 2026-10-05 LIVE：窄窗口 6 交易日×3 品种=18 行写入读回一致；
  重复写 KEEP_LAST updated=18。

## 12. FRED 序列扩充（#437，全部展示-only）

`sources/fred/indicators.py` 注册 31 个新序列（#424 候选全集），
`FRED_INDICATOR_CODES` 镜像同步扩充（消费边界自动覆盖：不进入策略
特征/回测/Paper/Agent 决策输入）。频率类型新增 `weekly`（GASREGW
周频如实注册，日更回看 90 天）。类别新增 `exchange_rate`。

- **汇率身份分离**：DEXJPUS/DEXUSEU/DEXCHUS/DEXUSUK 与 DTWEXAFEGS
  是 H.10 口径（周一发布上周值），存于宏观长表；Tushare fx_daily
  （FXCM 口径）是另一身份，不静默合并同一序列。
- **ID 修正**（2026-10-05 CSV 端点核实）：PALLFNFINDEXM（旧
  PALLFNF/PALLFIN 错误 404）、DBAA（日度 Baa）、BAA10Y、PNGASEUUSDM
  （候选清单 PNGASUSDM 为错误 ID 404，正确为 PNGASEUUSDM——欧盟
  天然气，与 Henry Hub 分属不同基准）。
- **已知边界**：ICE BofA OAS 两序列自 2026-04 仅滚动 3 年窗口；
  DGS20 存在 1987-1993 停发段缺失；BAA 仅月度、DBAA 为日度（不同
  序列）；EFFR 与 DFF 为不同序列并存。
- 31/31 序列经 fredgraph.csv 公开端点核验身份与最新观察日
  （2026-10-05）；正式摄取仍走 api.stlouisfed.org（key 注入不变）。

## 13. 维护者确认的 ETF 参考事实（etf_reference，#408）

`config/default/etf_reference.json`（跨环境默认层）承载维护者确认的
ETF Paper 参考事实：交易限制、交易币种、lot/tick/结算周期/涨跌幅与
账户费用（佣金/最低佣金/印花税/过户费）。外部数据源无结构化提供方，
声明文件即唯一合法来源；每条事实独立声明 `basis`（来源依据）与
`effective_from`（生效日），`confirmed_at` 记录确认日。

- **摄取**：`source=config`、`dataset=etf_reference`，走真实摄取链
  （快照 + payload 留存 + 幂等 + 完成证据）；观察日=摄取请求日，
  生效日=声明确认的生效日，发布时刻=快照创建时刻。
- **身份**：声明 `source_ticker` 经裸码+后缀交易所唯一匹配已注册
  instrument 后登记 `instrument_mapping(source='config')`；未注册或
  多义 → 摄取 fail closed（先摄取 etf_basic）。
- **读侧**：Paper handoff/execution 以 `etf_reference` 补充输入快照
  消费；未声明标的/字段保持缺失并精确拒绝，不推断、不默认。
- **变更**：修改事实 = 编辑声明文件后按新摄取日期重新摄取（追加
  观察行）；已记录证据不改写。账户费用变化须同步更新 `basis` 与
  生效日。
