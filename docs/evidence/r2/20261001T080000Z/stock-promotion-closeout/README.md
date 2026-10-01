# #196 Batch 2 收尾:重认证与重晋级材料(2026-10-01)

> 规则见 [R2 Evidence Index](../../README.md):本目录只归档命令直接生成的机器输出与 reviewer 事实;runtime 中的 append-only 认证/晋级/license 记录是唯一权威,此处不复制其内容。
>
> 上一轮(20260930T083000Z)四项缺口在本批全部处置:中断恢复演练(替代 skip 幂等)、certified fields + 字段级 replay、catalog 读模型消费检查(stock_basic/stock_status 补齐)、index_daily 修复后的正式运行双例。处置过程与遗留边界如实记录如下。

## 重晋级清单处置结果

| # | 缺口(2026-09-30 评审) | 处置 | 证据 |
|---|---|---|---|
| 1 | 正式策略运行双例未执行(index_daily 缺数据) | index_daily 修复后执行:负例=种子财务策略被运行门拦;正例=无财务动量策略无 bypass 通过 recommend 运行 | `formal-gate-verification.json`、`formal-run-negative.json`、`formal-run-positive.json` |
| 2 | certified fields 未建立,replay fail closed | 三数据集建立 certified fields(绑定快照+消费者输入摘要+SSE 日历可见性);instrument/date 键数据集(stock_daily/stock_status)字段级 replay 通过;stock_basic 为注册表快照,结构上不适用 replay 投影器(其主键非 instrument_id/trade_date,应用层契约拒绝),certified fields 随认证冻结 | `replay-stock_{daily,status}.json` |
| 3 | 恢复演练仅证明 skip 幂等 | 真实中断恢复演练:3 次 SIGKILL(含块内杀 python worker),中断块重试闭环,durable identity 无重复 | `recovery-interruption-stock_status.json` |
| 4 | stock_basic/stock_status 消费未走读模型 | 三数据集读模型消费检查(DataProvider bars / MetadataService registry / MarketService status) | `consumer-read-stock_{daily,basic,status}.json` |
| 5 | 全历史覆盖或区间外 fail-closed | stock_basic 2015 起有效日期快照;stock_status 回填 2016→2024 后按 provider 实际边界认证(见下);stock_daily 维持有界声明 | 本 README 边界声明 + `row-level-coverage-stock_status.json` |

## 认证与晋级(新序列机制下首次真实执行)

三数据集以 `selection-fields-v1` profile 重走 build-certification → certify → replay → promotion(三准则)。profile 变更原因:字段级 replay(`FieldAdmissionQuery`)按 `selection-fields-v1` 查找活动认证报告,上一轮 `default` profile 下的认证对 replay 不可见。

certified fields 声明约定(claims 见 runtime 认证报告,此处仅记录约定):

- **日频事实**(stock_daily/stock_status):`time_precision=date`,`publication_at=available_at=covered_to 当日 18:00 Asia/Shanghai`(provider 同晚间发布惯例),`observed_at` 由快照账本强制绑定;可见性边界由认证构建器经 SSE 日历推导(下一开盘)。
- **注册表快照事实**(stock_basic):`time_precision=timestamp`,`available_at=publication_at=observed_at=账本 fetch 时刻`。
- **instrument 范围**=留存消费者读取实际返回的标的集合(bars 5571 / registry 5922 / status 5574);`consumer_bindings`=留存 `field_inputs` 记录的 SHA-256。

## 边界声明(有限范围晋级)

| 数据集 | 认证区间 | 边界性质 |
|---|---|---|
| `stock_daily` | 2025-01-02→2026-09-29(423 交易日) | 有界声明:423 日 ≥ 最长 lookback 252 日的 1.6 倍;更早历史未认证 |
| `stock_basic` | 2015-01-01→2026-09-30(有效日期) | 当前全市场快照(L 5581 + D 341)以 list_date/delist_date 重建有效区间;不含 2015 前退市标的 |
| `stock_status` | 2017-01-03→2026-09-29 | provider 实际边界:bak_basic 在本代理 2016-08 前全空、2016-09~12 散点、2017-01 起连续;2016 的 no-data 观测保留为 catalog 事实 |

`stock_status` 行级覆盖(分区级完整性之内的 provider 空洞,详见 `row-level-coverage-stock_status.json`):2,366 个调度交易日中 2,346 日有行(约 10.5M 行,2017-2026);20 个交易日 provider 当日 0 行(2017×2、2019×4、2020×12、2021×2:2017-01-17、2017-06-23、2019-04-01、2019-10-24、2019-11-04、2019-11-28、2020-01-02、2020-02-20、2020-02-25、2020-03-16、2020-04-23、2020-06-18、2020-07-08、2020-07-20、2020-08-03、2020-08-04、2020-08-24、2020-11-20、2021-01-29、2021-03-16;逐日 API 探测证实 provider 空,非取数失败,无可 repair 项)。2018-03-23 为账本内唯一 FETCH_ERROR 日。空洞集合是前向观察窗的停止条件基线。

## 中断恢复演练要点

对 stock_status 2016-01-01→2024-12-31 真实回填执行:SIGKILL uv 监督进程(worker 孤儿续跑)、SIGKILL 重跑(首写前)、SIGKILL python worker 本体(块内拉取 ~18s)。任一中断点 durable 状态零残留(无半态 checkpoint/快照),重跑跳过已完成块、识别 evidence-incomplete 块(2018-03)并重完成、中断块(2021-01)重试闭环(attempts=1,无重复身份);一次重跑与孤儿 worker 短暂并发也未产生重复 durable identity。

## 正式运行双例

- 负例:`seed_stock_selection_rotation`(required: stock_daily/adj_factor/balance_sheet/income_statement)在晋级后仍被运行门拦(仅财务数据集 experimental)。
- 正例:`stock_momentum_selection_196b2`(template `stock_selection`,纯动量,required: stock_daily+adj_factor,universe `a-share-custom-202609`,benchmark 000300.SH)无 bypass 通过 recommend 运行。
- 模板偏差如实记录:检查单原文的「无财务 sector_rotation 策略」在 recommend 路径不可达——`stock_sector_rotation` 模板依赖的 `is_sector`/`sector_id` 结构列在 research/recommend 路径无生产者(仅回测路径的 classification snapshot 注入,且 industry_mapping 为空)。正例改用与种子同族的 `stock_selection` 模板;该缺口转入 #196 Batch 3(UI 旅程)范围。

## 证据文件(机器生成,含机器时间戳;时间戳早于所在提交)

- `recovery-interruption-stock_status.json` — 中断恢复演练(durable 计数+时间线+不变量)。
- `consumer-read-stock_{daily,basic,status}.json` — 读模型消费检查(含 `field_inputs` 留存,certified fields 绑定其摘要)。
- `replay-stock_{daily,status}.json` — 字段级 replay-snapshots 通过记录(stock_basic 不适用,见上)。
- `formal-gate-verification.json` — 晋级后真实 promotion store 上的门核验。
- `formal-run-negative.json` / `formal-run-positive.json` — 双例运行机器输出。
- `row-level-coverage-stock_status.json` — 行级覆盖量化(含 provider 空洞清单)。

## 运维责任与前向观察窗

runtime owner / freshness SLA / failover policy 见 `docs/operations/stock-data-runtime-ops.md`(含本次新增的前向观察窗与停止条件)。

## 已知缺口(如实记录)

- `stock_sector_rotation` 模板在 research/recommend 路径无 `is_sector`/`sector_id` 生产者(Batch 3 范围)。
- bak_basic 经本代理的 2016 覆盖散点(9/11/12 月有数据),已取为 raw 事实但不在认证区间内;`industry_mapping`/`industry_basic` 为空,行业分类数据未接入。
- 普通行情读路径(`MarketQueryFacade`/`ServiceBackedDataProvider`)不执行 per-read 新鲜度/覆盖/行级检查(与上一轮记录一致);行级空洞的拦截依赖本声明与 readiness overlay。
- 正例宇宙 `a-share-custom-202609` 的成员资格按 2026-09-30 stock_basic 快照声明、effective_date=2026-09-01 起:成员以 list_date 判定可交易性,快照晚于生效日的少数新上市成员在更早交易日无行情行,由数据存在性自然排除。
