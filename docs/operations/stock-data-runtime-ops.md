# 股票数据集运行职责与新鲜度策略（2026-09 晋级材料）

> 适用数据集:`stock_basic`、`stock_daily`、`stock_status`(Tushare 主源,经 `https://t.xiaodefa.top/` 代理;fuyao 为冗余源)。
> 本文档源于 [#196](https://github.com/cosmos-arc/ditto/issues/196) 准则二「document runtime owner, freshness SLA, and source failover policy」的评审;原 license/promotion 记录已随 #392 治理删除,现行证据以 provider snapshots 与 fetch log 为准。
>
> 财务三表(`balance_sheet`/`income_statement`/`cash_flow`)的运行职责见文末[财务报表数据集段](#财务报表数据集运行职责2026-10-晋级材料)。

## 运行负责人（runtime owner）

- 单操作者工作站(chevy),本地运行时,无部署环境。
- 数据面责任:按交易日终态更新、失败重试与 repair(`ditto data-products repair`)、覆盖缺口处置;覆盖回归先修复并重摄取,再恢复读路径判定。
- 升级责任:provider 接口/权限/quota 变化时更新本文件(append 新版本说明,不改旧记录)。

## 新鲜度 SLA

以 catalog `DatasetMetadata` 声明为准(读侧 readiness 门按此判定;数值不一致时以 metadata 为权威并修订本文件):

| 数据集 | 频率 | SLA(metadata 权威值) | 说明 |
|---|---|---|---|
| `stock_basic` | 按需快照 | 168h(7 天) | 全市场列表快照;周内旧快照仍判 fresh |
| `stock_daily` | 交易日 | 36h | 日线 OHLCV+量额,单日全市场一次调用 |
| `stock_status` | 交易日 | 36h | 停复牌/交易状态,可投资集合判定输入 |

- 触发:工作日终人工执行 bootstrap/repair(个人工作站无常驻调度);`stock_daily`/`stock_status` 以 T+1 晚间补齐为操作目标(36h SLA 内)。
- 超期处置:新鲜度判定作用于 readiness/catalog status overlay 与治理面;**普通行情读路径不做 per-read 新鲜度检查**(`MarketQueryFacade`/`ServiceBackedDataProvider` 直接读存储),超期数据的拦截依赖上层 readiness 展示与操作者执行本 SLA,不声称读路径自动 fail closed。

## 主备与故障切换（source failover policy）

1. 主源 Tushare(代理端点);备源 fuyao(同花顺开源数据)。**fuyao 当前仅对 `stock_daily` 注册了 adapter 能力**;`stock_basic`/`stock_status` 无已注册备源。
2. `stock_daily` 主源失败(配额/网络/接口变更)时:保持 blocked/stale 展示与最后完成快照身份;经人工确认备源口径(schema、复权、时间语义)一致后,以 `--source fuyao` 显式补数,新内容按独立 provider snapshot 落账,不覆盖 Tushare 快照身份。
3. **failover 顺序**:主源失败决定切换时,新源补数以独立来源快照写入;来源覆盖与选源读取按完成快照事实判定(#394),不依赖已删除的认证/晋级状态。补数完成后按数据集来源覆盖展示核对,再恢复正常运维。
4. `stock_basic`/`stock_status` 主源失败时:无备源,保持 blocked 并重试主源;不以前日数据顶替当日快照。
5. 主备共用上游时不得视为独立校验;切换与回切都以新快照/新证据落账,旧结果不回写。
6. 连续失败或覆盖回归 → revoke 晋级,按 runbook 修复后重新认证。

## 前向观察窗(2026-10-01 重晋级起)

**窗口**:自 2026-10-01 重晋级起 20 个交易日(约至 2026-10-30);期间按 SLA 正常运维并观察以下停止条件。

**日常动作**(与上文 SLA 一致,不新增流程):

1. 每交易日终 `bootstrap stock_daily`/`stock_status`,每周一次 `stock_basic` 快照;
2. 每次更新后核对 readiness/catalog status overlay 与 DQ(L1/L2)结果;
3. 观察窗结束日重跑 `row-level-coverage-stock_status.json` 量化并与基线比对。

**停止条件(任一触发 → 停用该数据集日常发布,按上文 failover 顺序修复并重摄取后恢复;处置事件记录于 #196)**:

1. **覆盖回归**:调度交易日在 36h SLA 到期后仍缺分区(非 provider 全站故障);
2. **行级空洞增长**:新增 provider 空洞日超出基线(已取时代 20 日 + `row-level-coverage-stock_status.json` 终版记录的 2022-2024 空洞集);
3. **DQ 失败**:新块 L1/L2 失败且 2 个交易日内未修复;
4. **provider/代理退化**:配额耗尽、代理不可用超 SLA,或接口口径变化未评审;
5. **消费者事故**:bars/status 读路径报错或发现错数据(如错误复权、状态错标);
6. **许可/权限变化**:Tushare 或代理条款变化影响本地缓存与衍生计算权利。

窗口无停止条件触发 → 观察窗收口记录于 #196,数据集维持当前成熟度;有触发 → 按停止条件处置并在 #196 记录事件。

## 代理端点风险（t.xiaodefa.top，#507 I2）

主源 Tushare 全部经代理 `https://t.xiaodefa.top/` 访问。代理是单点风险面，
与官方直连的分叉无法在上游归因，运维上按以下事实与约定处理：

- **零文档/无 SLA**：代理无公开接口文档与可用性承诺；实测存在约 2 周的
  数据滞后窗口（新数据可能晚于官方发布），已知形态差异全部固化在源码
  注释（`cn_pmi` 恒空、`fut_basic` 需交易所全称、`fund_nav` 仅接受单日、
  忽略错误参数名返回全历史——见 `sources/tushare/adapters/` 与
  `processors/mappings/` 内注释）。
- **对账通道对象是 fuyao**（第二独立源）而非官方 Tushare：代理与官方
  分叉时，现有对账（`ditto ops reconcile`，#473-#475/#438）只能发现
  「两源不一致」，无法判定哪侧偏离官方。adj_factor 对账自 #515 起随
  每日 T3 例行执行（结果在 daily flow `reconcile_results` 键），辅源
  dump 缺失/陈旧时显式 skip 留痕。fuyao client 自 #516 起默认 0.1s
  请求节流 + 限流(429/code=4001)退避重试：宽基对账（数千标的逐个
  REST 请求）耗时会比此前多出数分钟，属预期节流而非故障；触发限流后
  节流间隔在单次进程内只升不降（下次运行自然重置）。FRED 侧同理自
  #516 起 0.5s 节流（官方 120 req/min），51 序列日增多出约 25 秒。
- **官方直连采样通道保留**：配置位已具备（`http_base_url` 指向
  `api.tushare.pro` + `rate_limit_profile=official_*`；官方档位自带
  10 万次/天客户端配额计数，#515 G1）。怀疑代理数据形态异常时，可临时
  切官方直连做小范围采样对拍，比全量切源便宜得多。
- **代理寿终/条款变化**：按上文「停止条件 4/6」处置——先以官方直连
  采样确认差异形态，再决定是否整体切换 transport（官方直连需重估积分
  档位与频次预算）。

## 版本

- 2026-09-30:随 #196 Batch 2 首次评审建立(chevy)。
- 2026-10-01:重晋级收尾——新增前向观察窗(20 交易日)与停止条件;stock_status 认证边界按 provider 实际覆盖定为 2017-01-03 起(chevy)。
- 2026-10-03:#392 删除认证/晋级/license 治理后同步收口——failover 与停止条件改按完成快照事实表述(chevy)。
- 2026-10-05:#515 新增「代理端点风险」段(#507 I2):零文档边界、fuyao 对账归因限制、官方直连采样通道与日配额计数。
- 2026-10-06:#516 次源节流说明——fuyao 0.1s 间隔+限流退避(宽基对账耗时上升属预期)、FRED 0.5s 节流(chevy)。

# 财务报表数据集运行职责（2026-10 晋级材料）

> 适用数据集:`balance_sheet`、`income_statement`(2026-10-19 随 #196 策略腿晋级 initial-focus);`cash_flow` 同窗回补但**无正式消费者,维持 experimental**,消费方出现时按同一模板补评审。主源 Tushare vip 端点(`balancesheet_vip`/`income_vip`/`cashflow_vip`,经代理);无备源。

## 运行负责人（runtime owner）

- 同上:单操作者工作站(chevy)。披露季(4/8/10 月)后跑增量回补;上游同披露键重发布由 ingestion 通道 `VERIFY_IDENTICAL` 拒收,处置裁决记录于 #196(先例:fina_indicator Q2/Q3 拒收留档)。

## 新鲜度 SLA 与历史版本证据

| 数据集 | 频率 | SLA(metadata 权威值) | 披露锚 |
|---|---|---|---|
| `balance_sheet` | 披露事件 | 1080h(45 天) | `f_ann_date`(实际公告日) |
| `income_statement` | 披露事件 | 1080h(45 天) | `f_ann_date` |

- 历史版本证据(回应「不能只凭 f_ann_date 字段晋级」):披露锚 + 三层防护构成——(1) `report_type=1` 合并报表口径、同一披露键取 `update_flag` 最新行(#482 语义);(2) ingestion 通道对非 force 重拉一律 `VERIFY_IDENTICAL`(`instrument_ingestion`/`post_ingest` 两路径,fina_indicator Q2/Q3 拒收先例实证),不静默改史;(3) 回放读冻结 provider snapshot,不触活数据。上游无逐版本历史,残余风险=老披露键的静默修订不可检测,由(2)在重拉通道拦截。
- 覆盖:回补窗口 2014-01-01 起(2014Q1 起报告期,披露超集窗口 8Q+区间);实际行数底账、PIT 抽查与缺口(如有)以 #196 票评论留证为准。

## 主备与故障切换（source failover policy）

1. 仅 Tushare vip 端点一源;fuyao 无财务三表 adapter。主源失败:保持缺口展示并重试(增量回补自带重试;已知瞬态=代理翻页 offset 重复触发 fail-closed,重试自愈)。
2. 代理对大结果集的翻页重复是结构性风险(corporate_actions 先例):若某报告期持续失败且重试不愈,记名缺口并按代理端点风险段的官方直连采样通道对拍,不 force 覆盖。
3. 同键修订冲突一律拒收留档,不得以 `KEEP_LAST` 覆盖存量好数据。

## 前向观察窗

自晋级日(2026-10-19)起 2 个披露季(至 2027-04-30):每季增量回补后核对 L1/L2 与拒收日志;上游同键修订事件如出现,按 #196 先例裁决。停止条件同上文股票面(覆盖回归/DQ 失败/provider 退化/消费者事故/许可变化),触发则回退 experimental 并修档。

## 版本

- 2026-10-19:#196 策略腿晋级——`balance_sheet`/`income_statement` 升 initial-focus(cash_flow 维持 experimental)(chevy)。
