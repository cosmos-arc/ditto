# 股票数据集运行职责与新鲜度策略（2026-09 晋级材料）

> 适用数据集:`stock_basic`、`stock_daily`、`stock_status`(Tushare 主源,经 `https://t.xiaodefa.top/` 代理;fuyao 为冗余源)。
> 本文档是 [#196](https://github.com/cosmos-arc/ditto/issues/196) 晋级准则二「document runtime owner, freshness SLA, and source failover policy」的评审材料,与 runtime 中 append-only 的 license/promotion 记录配套,不复制其事实。

## 运行负责人（runtime owner）

- 单操作者工作站(chevy),本地运行时,无部署环境。
- 数据面责任:按交易日终态更新、失败重试与 repair(`ditto data-products repair`)、覆盖缺口处置;不修改已冻结认证报告,coverage 回归先 revoke 再修复。
- 升级责任:provider 接口/权限/quota 变化时更新本文件与 license 记录(append 新版本,不改旧记录)。

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
2. `stock_daily` 主源失败(配额/网络/接口变更)时:保持 blocked/stale 展示与最后认证快照身份;经人工确认备源口径(schema、复权、时间语义、许可)一致后,以 `--source fuyao --license-record-id <fuyao 的 license 记录>` 显式补数(缺 license-record-id 时 R2 证据提交 fail closed,且 Tushare 的 license 记录不覆盖 fuyao 源)。
3. **failover 顺序(关闭旧晋级/旧认证下的新源暴露窗口)**:主源失败决定切换时,若数据集在册晋级,先 `ops promotion-revoke` 撤销晋级并 `data-products revoke` 撤销当前认证,再执行补数——普通读路径不校验认证身份,且治理存储在存在活动认证时拒绝追加不同报告;若先写分后撤,正式消费者会在旧晋级下读到未认证的新源行。补数完成后重新认证(certify 新快照集),再逐条重记三准则证据(撤销后旧证据自动失效,#380/#383),最后重新晋级。
4. `stock_basic`/`stock_status` 主源失败时:无备源,保持 blocked 并重试主源;不以前日数据顶替当日快照。
5. 主备共用上游时不得视为独立校验;切换与回切都以新快照/新证据落账,旧结果不回写。
6. 连续失败或覆盖回归 → revoke 晋级,按 runbook 修复后重新认证。

## 前向观察窗(2026-10-01 重晋级起)

**窗口**:自 2026-10-01 重晋级起 20 个交易日(约至 2026-10-30);期间按 SLA 正常运维并观察以下停止条件。

**日常动作**(与上文 SLA 一致,不新增流程):

1. 每交易日终 `bootstrap stock_daily`/`stock_status`,每周一次 `stock_basic` 快照;
2. 每次更新后核对 readiness/catalog status overlay 与 DQ(L1/L2)结果;
3. 观察窗结束日重跑 `row-level-coverage-stock_status.json` 量化并与基线比对。

**停止条件(任一触发 → `ops promotion-revoke` 撤晋级 + `data-products revoke` 撤认证,按上文 failover 顺序修复后重走认证/晋级;#380/#383 机制下旧证据自动失效)**:

1. **覆盖回归**:调度交易日在 36h SLA 到期后仍缺分区(非 provider 全站故障);
2. **行级空洞增长**:新增 provider 空洞日超出基线(已取时代 20 日 + `row-level-coverage-stock_status.json` 终版记录的 2022-2024 空洞集);
3. **DQ 失败**:新块 L1/L2 失败且 2 个交易日内未修复;
4. **provider/代理退化**:配额耗尽、代理不可用超 SLA,或接口口径变化未评审;
5. **消费者事故**:bars/status 读路径报错或发现错数据(如错误复权、状态错标);
6. **许可/权限变化**:Tushare 或代理条款变化影响 local_cache/derivative_compute 权利。

窗口无停止条件触发 → 观察窗收口记录于 #196,数据集维持 initial-focus;有触发 → 按停止条件处置并在 #196 记录事件。

## 版本

- 2026-09-30:随 #196 Batch 2 首次评审建立(chevy)。
- 2026-10-01:重晋级收尾——新增前向观察窗(20 交易日)与停止条件;stock_status 认证边界按 provider 实际覆盖定为 2017-01-03 起(chevy)。
