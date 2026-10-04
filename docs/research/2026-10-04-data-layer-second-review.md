# 数据层二次复审：先修数据语义，再做可证明等价的精简

日期：2026-10-04。代码基线：`1acf7427090402e5724a52d3066235671c55f264`（main）。性质：研究与实施规格复审。维护者已于本轮确认 Q1:B、Q2:B、Q3:按推荐顺序；最终范围见第12节及裁决票，早期研究建议不覆盖该决定。

复审对象包括「数据层业界对标与多资产数据源升级」地图及前置调研/裁决评论、用户指定的全部 18 个编号、成本审计报告。编号中 441、443 实际是文档 PR；440、442 是已关闭的任务/裁决，其余 14 个是开放实施票。两份文档均尚未合入 main：对标报告 PR head 为 `21c912bddaef9d42d36d9078cbb769f4d881f6a5`，成本报告 PR head 为 `057c66e194b5e61b9182bf57d6072e9270fcfb48`。这是本轮读取时的状态。

[二次复审地图](https://github.com/cosmos-arc/ditto/issues/449)记录决策索引，[研究票](https://github.com/cosmos-arc/ditto/issues/450)保存事实依据，[最终裁决](https://github.com/cosmos-arc/ditto/issues/451#issuecomment-5975629762)明确：灾后只恢复当前可用状态、接受旧实验不可重放；全球指数/FRED/海外大宗本轮只展示；先修语义再精简与扩覆盖。既有实施规格已按该边界同步，均仍待实施。

## 1. 结论

**保留 SQLite + Parquet + Polars、instrument 身份、原始/标准化载荷、快照绑定和 PIT 约束；支持删除在线 shadow/certification、级联队列、重复账本等不匹配当前规模的机制。原实施票的字面方案存在语义错误和不等价替代，本轮已修订规格。正常运行保障继续保留；灾后全历史重放按维护者选择明确不再承诺。**

系统主要矛盾不是吞吐不足、数据库落后或数据源太少，而是：

1. **供应商语义与内部类型有偏差**：同比名称装了指数水平；单值序列被包装成 OHLC；不同黄金基准共用身份；指数点位被描述为原币价格。
2. **可知时间和增量坐标不一致**：宏观观察期与发布日期混用；日期级 vintage 不能自动等于中国市场开盘前可知；统一 T+1 不能代替跨市场时间模型。
3. **完整性验收不够具体**：分页终止、空结果、缺失覆盖、部分源失败，都不能仅以请求成功/行数非零认定通过。
4. **成本审计有些替代方案不等价**：checksum 不等于完成；重拉不等于原版本；四个状态字段不等于可复现实验记录。

这不是要求重建治理平台。合理终态是少量明确的数据产品、来源合同和恢复行为，全部落在现有结构内。

证据分册：

- [Tushare 端点、接入与模型复审](2026-10-04-tushare-second-review.md)
- [fuyao 与 FRED/ALFRED 复审](2026-10-04-fuyao-fred-second-review.md)
- [业界对标与全球补源复审](2026-10-04-industry-source-second-review.md)

## 2. 业界对标：学保障与边界，不照搬整套产品

前轮把「没有逐行 knowledge_date 列」推成「行情侧无 PIT」，再使用「零同构三件套」解释 Ditto 特殊性，证据不足。LEAN 用数据结束时间/time frontier 防前视；Qlib 对财务做 PIT；Zipline 有证券身份、日历、复权与 bundle 身份。它们的实现形式不同，不能据此断言不存在同类保障。LEAN 源码还包含 DataMonitor，故「业界均无常驻监控」也应收窄。来源及源码位置见业界分册。

| 对照对象 | 值得学习 | 对 Ditto 的最小应用 | 不应照搬 |
|---|---|---|---|
| LEAN | 证券身份、市场时区、数据结束时间、复权/公司行动、连续合约与具体合约分离 | 全球参考先准确展示并限制消费，策略阶段再补 available time；公司行动与价格分开；连续参考不可当成交价格 | 完整实时交易引擎、券商与多资产保证金系统 |
| Qlib | 研究数据与模型训练分层；财务 PIT 与表达式 | 原始指标和派生同比分开；固定输入快照构建研究数据 | 为少数日频策略搭全套机器学习数据平台 |
| Zipline-reloaded | bundle、sid、日历与 adjustments 明确 | 沿用现有 instrument_id；历史证券池和复权有各自契约 | 为对标换掉现有 Polars/Parquet 数据布局 |
| DuckDB/Parquet | 本地列式分析、列裁剪/过滤下推 | 保留 Parquet；先测现有 Polars 真实瓶颈 | 重新引入刚删除且无消费者的第三查询引擎 |
| ArcticDB | 大规模版本化时间序列及快照能力 | 借鉴不可变输入身份的思想 | 为当前日频单机系统引入另一套存储与运维 |
| vn.py / Backtrader | 有限数据 feed、清楚的 bar/时区边界 | 接口职责薄、可替换范围明确 | 把实盘交易框架当成数据质量或历史版本保证 |

官方入口：[LEAN time modeling](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/timeslices)、[Qlib PIT](https://qlib.readthedocs.io/en/latest/advanced/PIT.html)、[Zipline bundles](https://zipline.ml4trading.io/bundles.html)、[DuckDB Parquet](https://duckdb.org/docs/stable/data/parquet/overview.html)、[ArcticDB](https://docs.arcticdb.io/latest/)。各产品只证明其自身能力，不证明「所有优秀个人系统」统一使用某种架构。

**过度设计判断应同时问：现在谁消费它、删除会损失什么、是否存在更短且等价的实现。** 空表、零流量、LOC 和测试文件数是筛选线索，不能单独充当删除依据。本轮没有重新统计用户真实数据库行数；成本报告的 live 行数仍是前轮特定根的历史观察。

### 存储和摄取不需要整体重建

元数据/小型关系事实保留 SQLite，批量时序保留 Parquet，Polars 继续作为唯一生产查询轨。`parquet_store.py:154–177` 已按日期选择文件并进入 scan；不能因“年分区”三个字就认定全表扫描，也没有本轮性能基准支持分区迁移。

需要优先测量的是日更是否反复 merge/rewrite 同一年分区、全市场回填是否逐证券重复读写、dump 是否过滤/投影前整份读入内存。若出现实际瓶颈，先把同一分区写入合批、复用 lazy scan、减少重复读取；再评估月分区或其它引擎。单活写者、临时文件后发布、失败时不提前推进游标比换数据库更重要。原始响应和 canonical 数据有不同用途，二者并存不是重复账本；额外的治理状态缓存才是优先清理对象。

DQ 按数据产品选择规则：股票正价格规则不能直接套在全部期货/利率序列，真实 WTI 曾出现负结算价；单值参考无日内高低价，允许缺成交量的指数不应补零。复用已有 DQ checker，按有限数据集配置约束，不建设新的验证 DSL。[CME 负价格测试说明](https://www.cmegroup.com/notices/clearing/2020/04/Chadv20-160.html)、[CFTC WTI 调查](https://www.cftc.gov/PressRoom/PressReleases/8315-20)。本轮没有证明当前 DQ 已误删这些历史行；这是新增品种验收必须防住的反例。

## 3. 成本审计逐项复审

### C1/C2：支持删除机器；重写发布条件和失效语义

[删除 shadow/certification 发布安全机器与 derived 级联失效队列](https://github.com/cosmos-arc/ditto/issues/444)的方向成立。当前 `packages/features/src/ditto_features/publication_safety.py:163` 确有请求数、延迟分位、fallback 比率等在线服务语言；个人本地离线物化不需要为它们保留双跑发布控制面。

但「candidate 与当前版本确定性重算比对，checksum 一致才推进」有两个漏洞：

- 新公式、新输入版本本来就可能产生新值，不能要求与旧版本相同；首版也没有 baseline。
- 同一份有 bug 的代码运行两次并得到相同 checksum，只能证明确定性，不能证明计算正确。

最小替代：输入身份冻结（spec/代码语义版本/源快照/日期范围/时间策略）→计算→必要 DQ/固定小样本正确性验证→原子发布产物和 manifest。**同一身份重试**要求内容一致；**不同身份**允许值变化且保留旧产物。旧版差异可以作为报告，不一律当发布阻断。

级联队列可以删，但「失效」必须拆清：新请求使用新快照时重算；旧实验明确绑定旧快照时继续重放。不能“发现 latest 已变”就自动重写历史产物。滚动因子的区间重算须包含 lookback，不能只重算目标展示区间而丢前序输入。

验收：首版无 baseline 可发布；公式升级产生新身份；同身份异内容拒绝；发布中断不暴露半产物；旧实验不随 latest 改变；带 lookback 的整段重算与基准一致。

### C3/C6：最适合优先处理，但不要照抄「只留六字段」

[清理 DatasetSpec 治理遗留字段与旧观察账本](https://github.com/cosmos-arc/ditto/issues/445)里三个字段的清理有直接代码支持：`raw_target_from/certified_target_from/license_policy` 的外部引用搜索主要落在测试，治理目标校验可以随字段删除。

然而 `DatasetSpec` 并非只需六字段：`bootstrap_planner.py:127` 真正消费 `bootstrap_chunk`，`r2_preflight.py:250` 消费 `r2_scope`。票据又要求保留 runbook 消费，两者与「保留六字段」的字面清单冲突。应把范围写成**删已证实无用的三个字段及配套构造/校验，其他字段逐消费者判断**。时区、单位、修订语义要有一个权威位置，不因今天只有静态消费者就随意丢弃。

旧表 `provider_snapshot_observations` 确为兼容写缓存。`source_snapshot_store.py:220,287` 还在写；`get_predecessor/get_observed_at` 已从事件表读取（296–315）。可删除旧写侧与旧表，但必须保留：同一次尝试重试幂等；后来相同内容的再观察；A→B→A 的顺序与首次可知时间；请求范围区分。

票据的一次性迁移与上一轮明确允许旧开发数据直接重建存在规格张力。建议沿用已授权的开发数据重建边界，不自动做兼容迁移；若确有需要保留的新数据，先核对目标再迁移。此次复审没有删库。

### C7：支持脚本化；反对把恢复单元硬编码为三库

[备份收敛为配方脚本](https://github.com/cosmos-arc/ditto/issues/446)的「可重拉」假设过宽：

- 本地观察事件、首次采集时刻和旧响应版本不是上游当前 API 能重拉的事实。
- research.sqlite 保存的索引不能代替对应 artifact/sidecar 字节。
- metadata 库不仅是行情缓存；现有 `docs/runbooks/backup-restore.md:5` 明确包含策略版本、review decision、activation pointer 等恢复对象。
- 当前 `WORKSTATION_DATABASES` 在 `workstation_backup.py:59` 列出 **6 个物理 SQLite 文件**，agent 逻辑域占多个文件。「trading/agent/research 三个逻辑域」不等于三个文件。

维护者最终选择 **B：灾后只恢复当前可用状态，接受部分旧实验无法重放**。据此继续删三层包装和 release-candidate 驱动；按真实运行时路径保留当前账本、用户输入、agent状态、策略/配置/review/activation、有效holdout消费记录及恢复当前配置必需的文件。metadata不应因同时含行情缓存就整库排除；整库复制若更简单即可，不做精细引用垃圾回收。

旧实验的历史raw payload/artifact闭包不要求备份，市场缓存恢复后可重拉。重拉得到新观察与新快照，不能冒充旧版本。旧索引依赖缺失时明确“不可重放/缺失”，不偷偷用latest重算为旧结果。该取舍不授权正常运行中丢弃仍使用的PIT和提交完成证据。

SQLite使用原生`.backup`/Backup API；多个库和文件树复制前停写，不把单库一致性误当跨库原子性。[SQLite Backup API](https://www.sqlite.org/backup.html)。恢复时间以天级为目标，恢复点是最近一次成功手动备份；不引入自动调度，也不声称24小时RPO或两次备份间不丢新增状态。验收当前账本/配置/agent/holdout可用、必要文件缺失失败，以及可选旧artifact缺失时当前恢复成功而旧实验明确不可重放。

### C5：支持三阶段；checksum 不能定义 COMPLETE

[摄取分区状态机收敛为三阶段 log＋checksum 完成](https://github.com/cosmos-arc/ditto/issues/447)最需要修订标题和完成判据。

`evidence_commit.py:116` 在标准化文件修改前登记意图；147–176 分别提交源快照、catalog/成功记录、完成状态；`snapshot_completion.py:20–46` 核对 dataset/source/请求区间/payload/snapshot/complete_evidence_id。`canonical_write_identity` 另有 canonical checksum 与行数。**这些字段不是同一种 checksum 的重复表达。**

反例：载荷写完，canonical 写到一半崩溃；同一原始载荷被新 schema 解释；已有旧 COMPLETE，而新修订写了一半。三种情况下原始 checksum 都不能单独证明新结果可读。

最小实现可以是三阶段 + `error_code`，不必保留八个枚举和完整事件迁移机器；但 COMPLETE 必须绑定本次精确 snapshot、标准化输出身份、成功范围及必要质量结果，最后推进。未完成意图仍应挡住把新数据标成旧完成来源。有限 HTTP 重试与分区 retry-budget 是两件事，删除后者不意味着网络层无限重试或完全不重试。

还应修正测试口径：「同载荷重跑不产生新观察事实」仅适用于**同一次摄取尝试的恢复**。另一天同内容再观察是新事实，尤其 A→B→A；不能按内容 hash 全局去重观察。

本轮复跑现有三份相关测试，30 passed，说明这些防护已被测试约束；精简时迁移行为测试，不保留旧状态名断言即可。

### C4：顺序 runner 合适；单用户不等于不会重复启动

[analysis 实验调度器瘦身为顺序 runner](https://github.com/cosmos-arc/ditto/issues/448)可删多 worker 租约、心跳和调度协议。但需要保留最小本机运行权：例如一个 OS 文件锁，或者 SQLite 原子 claim；不用分布式 lease，也不能允许两个 CLI/API 启动覆盖同一 run。[SQLite 写事务隔离](https://www.sqlite.org/isolation.html)。

run 不应只有 status/started/finished/error。还需要引用已有不可变实验规格：strategy/code、参数/seed、输入 snapshot、fold/holdout 范围、产物身份及错误原因；字段可留在原 spec/manifest，run 只存引用，无需复制。

「保留 holdout 五文件」也不够：`_holdout_preflight.py:29` 直接导入拟删除 `_enqueue_fence` 的 payload-hash 构造。必须沿公开提交→执行→产物→holdout 消费路径重接这些语义。验收包含重复启动拒绝、运行中退出后 interrupted/failed、恢复不二次消费 holdout、旧产物与新 attempt 不串线。无须建设通用任务队列。

### 对审计报告自身的修订

- 把「工作区未提交、待确认落票」「待用户确认」更新为已确认裁决/待实施，当前状态以票据为准。
- 修复 `services/publication_safety.py` 过期定位，当前定义在 `features/publication_safety.py`。
- 删除「零同构」作为领域术语；推荐「可知时间、快照身份、提交完成证据」，领域词汇表不承载外部调查结论或具体实现决策。
- 不把空表/空备份目录当无用证明；备份目录为空也可能说明运行缺口。
- 「与数据源票正交、不需重排」不准确：摄取状态精简影响新接口的完成验收；备份与因子物化共享 manifest/证据保留边界；精简目录与新数据集注册会碰同一合同文件。

## 4. 数据模型：保留现有骨架，补当前已经需要的语义

推荐最小逻辑布局如下。它是现有结构的约束，不要求一次性新建六个框架。

| 层/对象 | 应保存什么 | 关键边界 |
|---|---|---|
| instrument + source mapping | 证券身份、来源代码、上市/退市/有效区间、市场/币种/资产类别 | 同名商品或指数不代表同一价格基准；内部整数段位不是对外业务语义 |
| price bars | 真正 OHLCV、价格口径、单位、交易 session、可用时间、来源 | 原始价/复权价/结算价分开；外汇 bid 不伪装 exchange last |
| reference observations | 观察期、单值、单位、频率、季调、变换、修订/可知时间 | CPI、利率、VIX、能源现货不是都应变成可交易 bar |
| events/financial facts | 报告期、公告/生效日、报表口径、修订身份、来源 | 当期重述与原始披露是不同事实 |
| provider snapshot + observations + fetch log | 内容、请求坐标、真实 source/transport、观察历史、完成证据 | 内容身份与观察事件不能合一；重试与新观察不能混同 |
| derived/research artifact | 输入身份、计算规格、输出内容、完成标记 | 新版本产生新身份；正常运行保留绑定，灾后缺旧依赖明确不可重放 |

新增静态字段可以先放现有数据集/序列注册项或 instrument 扩展字段。只在真实消费者需要时建表，不引入通用 EAV、数据治理 DSL、插件注册平台、Iceberg/Kafka/服务网格。

### 三个当前就需要修的模型问题

**参考单值与 K 线分离。** `fred/adapters/commodity.py:83–109` 把单值复制到 O/H/L/C，并根据日期构造纽约午夜 UTC 时间；schema 还写「商品价格不需要 PIT」。这是形状适配，不是市场实际开高低收或发布时间证明。本轮展示明确为单值观察，复用已有类型/注册元数据，不让ATR、日内振幅、成交模拟消费。观察日期与真实采集时间保留，未知发布时间不编造；完整available_at/knowledge_date规则随未来策略接入补齐。

**同金属不同基准不能无缝拼接。** 当前 `tushare/adapters/metal.py:23` 把 FXCM XAUUSD/XAGUSD 绑定到与 FRED 旧金银相同的整数 ID。实际通道为 `fx_daily` 的 bid OHLC，不是票据写的 `sge_daily`。LBMA fixing、FXCM bid、上金所人民币品种、COMEX 合约是不同观察对象。可以统一归 gold 暴露，不能共用一条 price series 冒充连续同口径历史。

**复合源的完成与来源应逐组件验证。** `commodity_fetcher.py:80–126` 分别调用 FRED 和 Tushare，异常记录 warning 后继续合并；摄取上下文主要传一个 `source_name`。应增加端到端反例证明：只返回黄金时不把油/VIX 也报告完成；混合数据能追到各自源快照。这是待闭合的调用链风险，本轮未对真实数据库触发它，不能写成已发生的数据污染。

### 多资产：本轮展示接入，策略时间契约延后

维护者选择 **B：全球数据只展示，不进入策略、回测和决策输入**。本轮保留自然observation date、准确身份/数值/单位/来源、真实采集时间、最新值日期与缺口说明；未知发布时间可明确未知。不为了展示建设完整市场日历、历史vintage仓库或交易执行规则。

在已有注册和消费者入口落实最小限制，检查现有消费者而不只约束未来调用：全球指数、FRED宏观/汇率、海外大宗拒绝策略特征、回测、Paper自动决策及Agent决策输入。展示数据不能通过通用查询入口绕过限制。A股个股/ETF已有价格、NAV和Paper所需参考事实仍遵守原PIT合同，不因这一决定降级。

将来策略真正需要这些全球输入时，另行完成发布时间/时区、cutoff/asof、修订与历史vintage支持。届时标注美国某日的收盘或发布数据不能按同一北京自然日直接join，也不能编造00:00或统一date+1；这些是未来策略准入的工作，本轮不作为展示完成门槛。

## 5. Tushare：维持主源，先修共享接入再扩端点

详细官方链接、字段与代码证据见 Tushare 分册。

- **分页根因已离线复现**：实际 `TushareClient.query` 对 2501 行、服务端 cap=2000 的模拟源，仅取到 2000，因请求 limit=9000 而误判结束。修复应按端点能力定义 cap/参数/分页方式；不把 2000 当所有端点安全值。`vix_index` 官方上限只有 300，`fut_basic` 则为 10000。
- **不要用市场规模乘交易日当所有数据集的硬断言**：股票上市/退市/停牌会产生合法空洞，财务/预告/宏观更是稀疏事件；正确验收是端点期望范围、主键去重、分窗交集/并集、缺口分类及重复页不前进检测。
- **频控分 source transport 与 endpoint**：15000 积分官方档与代理权益不能混称；限制取实证合同中的更严值，碰到权限不足/限流要区分，不能降成空 DataFrame。官方专页和总目录也可能冲突，最终以账号具体接口实测为准。
- **四组接口可保留既定范围，分数据产品验收**：期货日线保留具体合约/到期/结算与换月信息；forecast/express 保留预告区间/实际报告类型/修订；国内宏观修 `start_m/end_m` 等参数映射；指数估值不要复用股票 daily_basic 单位转换。
- **现有财务优先于新接口数量**：已用真实 transformer 离线复现：官方 `n_cashflow_inv_act=-20` 因本地请求/mapping写成 `n_cash_flows_inv_act`，被补缺逻辑变成 null，并影响 net cashflow。应核验所有实际消费字段及 `report_type/update_flag` 保留；目标代理是否另有别名和真实存量损失仍未知。[官方现金流字段](https://tushare.pro/document/2?doc_id=44)。
- **金额单位不能按接口家族一刀切**：`forecast` 净利润万元，`express` 金额元；`index_dailybasic` 市值元/股本股；社融增量亿元、存量万亿元。应把单位纳入每列/序列合同。[预告](https://tushare.pro/document/2?doc_id=45)、[快报](https://tushare.pro/document/2?doc_id=46)、[指数估值](https://tushare.pro/document/2?doc_id=128)、[社融](https://tushare.pro/document/2?doc_id=310)。
- **ETF 核心缺口仍在**：结构化 `etf_basic`、基金 NAV 的观察/披露日期、份额、分红、跟踪指数/收益版本、上市退市与跨境状态。先补身份、日线/复权与可用 NAV；PCF/实时 IOPV 只有真实策略消费者才接。
- **ETF 交易约束需复核接口迁移**：官方2026-09-07变更记录将ETF涨跌停迁至 `etf_limit`，本地检索只有 `stk_limit`。这不代表当前股票链坏了，但ETF Paper不得假定股票接口仍覆盖ETF。[官方变更记录](https://tushare.pro/document/1?doc_id=9)。
- **全球指数 21 个是供应方清单，不是目标覆盖结论**：官方包括 IXIC，不包括票据示例 NDX。两者不可互换；对跨境纳指100 ETF 尤其要显式声明基准缺口。指数点位不能直接乘汇率称为人民币价格；若要计算人民币投资者视角回报，应固定价格/总回报版本与基期，按相应 FX 比率计算。

基础关系示例：若 FX 是每单位外币折合本币，未对冲回报可按 `(1+r_local) × (FX_t/FX_0) − 1`；它不把不同指数的点位变成可比价格，更不替代分红/总回报和时点对齐。

## 6. FRED/ALFRED：修展示正确性，延后完整历史PIT

[FRED适配修正](https://github.com/cosmos-arc/ditto/issues/432)优先修日更坐标、数值与来源；按最终B裁决，本轮不再要求完整ALFRED历史PIT才能扩量。

1. **日更坐标错误**：`dataset_registry.py:357` 调用 `FREDSource.fetch_macro_indicators(trade_date)`，后者用 observation_start=end=当天。月度数据的 date 通常是观察期坐标；发布/修订日不同。要按发布/修订发现机制拉变化，或对小注册集做有界回看并定期覆盖历史修订；realtime 指定 vintage，可知日和观察期仍分开。固定短回看不能声称覆盖所有基准修订。
2. **指标命名/变换不匹配**：`US_CPI_YOY/US_CPI_CORE_YOY/US_PCE_YOY/US_PCE_CORE_YOY/US_M2_YOY` 实际对应价格指数或货币存量，原样读取没有同比。建议存原始level的准确名称；展示YoY的计算口径明确，未来策略消费还须固定同一vintage；若用 API `units=pch/pc1` 等变换，名称、单位、频率、请求身份一起固定，不能重复变换。
3. **PIT 标志不等于时间语义**：UNRATE 会修订；M2 也不能因 false 就忽略版本。即使不修订，数据仍有发布滞后。realtime interval 与查询窗口有关，不能无条件将行级 realtime_start 解释为首次发布精确时间。当前 adapter 在入库前把同 observation 的 revision collapse 成一行，client 又未核对 count/offset；未来完整历史vintage接入必须同时修这两处；本轮仅展示，延后该能力，不声称已支持历史回放。用户指定的 vintage_dates 可是任意历史日期；只有 vintagedates 端点返回的变更日期具有相应发布/修订语义。[FRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)。
4. **小而明确的序列注册表**：记录精确 ID、频率、单位、季调、变换、原始发布者、更新检查、修订策略。GASREGW 是周频，现有 FrequencyType 只有 daily/monthly/quarterly，扩充前先支持 weekly 或明确转换。
5. **不要因错误 ID 判断需要新源**：全商品指数有 `PALLFNFINDEXM/Q`；日度 Baa 与 Baa-10Y 有 `DBAA/BAA10Y`。旧调查失败的候选 ID 不能推出 FRED 没有该类数据。最新值日期/频率比缺 Next Release 更能说明当前覆盖，不能凭缺发布日判“死序列”。
6. **扩量不以「单日成功」验收**：每个新增项要查观察期与更新日期；本轮至少验证新发布旧观察期能够更新、缺失标记/周频/单位准确、展示允许而策略入口拒绝；完整历史修订回放与跨A股截止join延后。FRED 汇率与 Tushare FX 报价固定各自角色，差异不等于坏数据。

无需为 20–40 条参考序列搭建宏观数据仓库；但一条字段语义错误的序列接十年，会比少接一个指标更伤研究结果。

## 7. fuyao：辅源与手动回填合理，等价范围必须可证明

保留已确认的 A 股对账和手动回填角色，不做自动切源；ETF 前复权历史不进入原始价主链。官方软件仓库许可不能自动当成所有上游数据的使用承诺。[官方 Financial-API](https://github.com/HiThink-Tech/Financial-API)。

- REST 大窗口分片要防截断，但「末条日期等于请求 end」「空数组必错误」会误伤周末、停牌、退市或窗口无数据。需区分正常空、权限/源故障、不完整返回；端点未给可证完整性时报告 unknown/incomplete，不能伪造成功。
- long-history dump 与 REST 分窗是两条恢复路径；dump 下载也要完整文件、格式、范围、唯一键与尾部缺口检查。手动 dump 回填不应因为 REST 分窗尚未修好而被无关逻辑阻塞；密钥入口统一及来源准入仍可共享。
- `adjustment-factors` dump 是公司行动事件字段，不是与 Tushare 累计 adj_factor 一列直接 join 即可。比较归一化后的相邻因子比例/事件推导价格调整，单列现金分红、送转、配股和基准差异；不能复用价格 vol/amount 单位转换作为因子规则。现有 fuyao 股/元到内部手/千元实际是除以100/1000，旧票的“×”方向也应纠正。
- 除权日 pre_close 的定义、首根缺前价、北交所身份、源符号有效区间、停牌/退市覆盖都进入回填金集。
- 手动回填默认展示冲突，避免无提示覆盖同区间主源。独立 source snapshot、真实观察时间、选源规则和原始 payload 同批落地；今天抓到的历史 dump 不能自动宣称是十年前的 vintage。

两个 API 能互相发现差异，但如果原始上游未证明独立，一致也不是准确率证明；争议样本按交易所/基金公司原件核对即可，不需要全量第三源。

## 8. 新数据源：有选择地补缺，不为覆盖表凑满而接

| 候选 | 当前建议 | 触发条件/限制 |
|---|---|---|
| Tushare + fuyao + FRED | 继续作为基线 | 先闭合上述接入和语义错误 |
| 新浪外盘连续参考 | 保留已批准候选，收窄语义和验收后实施 | 只能标为非可交易参考，补源 ticker/历史起点/更新时间/未知换月规则；不能承诺所有品种30年 |
| 交易所、指数公司、基金管理人 | 定点事实核对/ETF身份与基准补缺 | 不建另一个全市场抓取平台；必要时仅保存用户所需原件及出处 |
| EIA、BLS、BEA、IMF、World Bank 等直接源 | 暂不全接 | FRED 确实缺序列、时效、发布明细或上游停止提供时，挑一个端点验证 |
| EODHD | 条件备选，撤销“一份199美元套餐覆盖所有连续商品期货”的确定性描述 | 当前官方 Commodities API 主要为FRED转发序列；需要端点/样本/套餐权利证明再采购 |
| RQData 等正式中国数据服务 | 针对历史 PIT 财务/证券池试样本候选 | 现有源不能提供所需历史版本时比较样本、授权与总预算；不默认新增订阅 |
| 未来美股数据服务 | 本轮不选定 | 真正启动美股研究时核验退市、symbol mapping、corporate actions、交易所覆盖/成交口径、授权与价格 |

新浪本轮公开端点只读抽样：CL 为 7689 行、起于 1996-10-04；GC 仅 2589 行、起于 2016-10-04；ZSD 也为 2016 年起。CL/GC 新近行 volume/position/settlement 为字符串零，ZSD 缺 settlement 字段。该观察只证明这些 ticker 当时的返回，不是服务保证；不能把占位零当真实零成交或结算。精确请求、字段与来源见业界分册。

成本范围坚持数据源总预算 <2000 元/年：新增套餐按已有支出后的剩余额度评估，不把美元标价直接当预算内；税费、汇率及实际权益另验。当前不需要为了这轮复审购买任何服务。

## 9. 用户指定的全部票据处置矩阵

下表是已同步到实施规格的处置结果；14张实施票保持开放，另在既有ETF/Paper票补充核心字段和接口迁移核验，没有另建实现票。两份旧文档PR仍需作者修正文档正文。标题为可读简称，链接保留原票身份。

| 票据 | 复审判定 | 实施前必须补的规格 |
|---|---|---|
| [Tushare 分页与频控修复](https://github.com/cosmos-arc/ditto/issues/431) | 优先修 | 端点 cap/分页/窗口，不统一2000；重复页/不前进检测；权益分 transport；类型化覆盖验收 |
| [FRED 适配修正](https://github.com/cosmos-arc/ditto/issues/432) | 优先修，扩大根因范围 | 日更观察坐标、同比/level、展示限制；METAL通道/身份纠正；完整vintage延后 |
| [fuyao 截断与密钥入口](https://github.com/cosmos-arc/ditto/issues/433) | 保留修复，修正验收 | 合法空/停牌/退市与截断区分；历史文档里的空配置不当成本次实测 |
| [Tushare 四组接口增补](https://github.com/cosmos-arc/ditto/issues/434) | 保留裁决，分组交付 | 期货合约与settlement、财务/预告口径、宏观月份参数、指数估值单位，各有独立验收 |
| [全球指数全量注册与摄取](https://github.com/cosmos-arc/ditto/issues/435) | 保留，先改错误示例 | NDX不在21清单；点位/收益版本；逐symbol覆盖与展示限制；策略时间契约延后 |
| [新浪外盘期货接入](https://github.com/cosmos-arc/ditto/issues/436) | 保留候选，收窄为reference | 历史长度逐品种；占位零/缺字段；未知换月；无key源不能套“缺key跳过”而永不注册 |
| [FRED 序列扩充](https://github.com/cosmos-arc/ditto/issues/437) | 修好现有语义后扩充 | 精确ID、周频、更新/回看、汇率口径与展示限制；完整PIT延后 |
| [跨源 adj_factor 对账](https://github.com/cosmos-arc/ditto/issues/438) | 保留，重写比较量 | 公司行动事件 vs 累计因子；比较比例/可推导调整，零交集not_comparable |
| [fuyao 手动回填二源](https://github.com/cosmos-arc/ditto/issues/439) | 保留 | dump与REST区别、冲突裁决、源身份及观察时刻、partial complete反例 |
| [对标报告终点交付](https://github.com/cosmos-arc/ditto/issues/440) | 历史完成记录保留 | 不以closed推断所关联报告已合并或实施已完成 |
| [业界对标与数据源报告 PR](https://github.com/cosmos-arc/ditto/pull/441) | 合并前更正文档 | 零同构/无监控等绝对措辞、EODHD商品承诺、NDX/汇率、三源新发现 |
| [成本侧审计三档裁决](https://github.com/cosmos-arc/ditto/issues/442) | 保留既有授权，补新证据 | 瘦身方向不变；恢复单元、完成判据、调度唯一性需承接 |
| [成本审计与词汇表 PR](https://github.com/cosmos-arc/ditto/pull/443) | 合并前更正事实与状态 | 报告过期路径/待确认状态；删零同构术语；补替代方案等价边界 |
| [删除 shadow/certification/cascade](https://github.com/cosmos-arc/ditto/issues/444) | 支持删除，先补发布语义 | 同身份确定性≠新旧版本相同；首版/冻结旧snapshot/lookback/半发布 |
| [DatasetSpec 与旧观察账本清理](https://github.com/cosmos-arc/ditto/issues/445) | 支持，最小低风险批 | 只删证实无用字段；保留真实消费者；A→B→A；开发重建与迁移选择一致 |
| [备份配方化](https://github.com/cosmos-arc/ditto/issues/446) | 按B配方化 | 真实文件清单/当前业务状态；不保证历史闭包；最近备份恢复点；缺旧依赖显式不可重放 |
| [摄取状态机三阶段化](https://github.com/cosmos-arc/ditto/issues/447) | 支持简化，原完成定义不宜执行 | 完成身份闭包、canonical证据、半写遮蔽、重试与新观察分离 |
| [analysis 顺序 runner](https://github.com/cosmos-arc/ditto/issues/448) | 支持，消费者范围需补 | 最小单实例拒重、run-spec-artifact绑定、holdout依赖重接、崩溃后可判断 |

## 10. 执行安排

**第一批：纠正规格与源接口正确性。** 先更新两份待合并报告中的错误事实；实施 Tushare 分页、FRED 生产日更/变换、fuyao 合法空与截断防护。选择少量已有真实消费者的数据做端到端验收，不用全量历史回填掩盖接口错误。

**第二批：并行价值明确的清理与模型补缺。** 清理三个治理残留字段/旧观察表；明确 ETF 产品身份与 NAV、宏观序列元数据、全球展示身份/单位与消费限制。期货具体合约与连续参考分开。这里的数据合同由 integrator 单写，不能让目录清理与新数据集接入并行改同一字段表。

**第三批：shadow/cascade 删除后推进因子物化最小链。** 继续遵守已确认的先砍后建。三阶段摄取精简如果同时启动，应先交付公共完成合同或串行落地，避免因子物化一边实现、一边又换恢复接口。

**第四批：扩覆盖与手动辅源。** 按已确认范围接四组 Tushare、全球指数、FRED清单、adj对账和fuyao回填。先少量 ticker 全旅程，再按端点契约扩到目标清单；新浪仅在reference语义明确后接。

备份配方化与顺序runner按本轮B恢复边界及holdout依赖修订后可各自实施；不阻塞源客户端修复。它们不是整个数据源升级的前置总闸。

### 最小充分验收包

| 场景 | 必须证明的行为 |
|---|---|
| 超分页上限/重复页/合法空 | 不截断、不死循环，缺口与无数据分开 |
| 一只重述财报股票 | 初始披露与修订在不同cutoff可见，报表口径不混 |
| 一只分红ETF与一只跨境ETF | 原始价/复权/NAV分开；净值所属日不当披露时刻；基准身份精确 |
| 一只退市股、一次除权、一次指数换仓 | 历史身份/状态有证据；不能用当前池回填成过去事实 |
| 一条月度FRED与周频序列 | 新发布日能抓到旧观察期；level/YoY/频率准确；历史vintage回放本轮不承诺 |
| 一条海外收盘/发布数据 | 展示身份/单位/日期/来源准确；策略、回测、Paper自动决策及Agent决策入口拒绝 |
| 摄取与发布故障注入 | 载荷存在但半提交仍不可读；重跑收敛且不篡改旧观察 |
| 非空备份恢复 | 当前账本/配置/agent/holdout可用，必需文件缺失失败；可选旧artifact缺失时旧实验明确不可重放 |

每项区分：CODE（接线存在）、TEST（确定性反例）、CONTRACT（官方语义）、LIVE（该账号该端点样本）、连续运行（实际按计划更新）。这些不是新增评分体系，而是避免用测试绿代替数据真的齐全。

## 11. 本轮实际验证与限制

实际执行：

```bash
uv run --no-sync pytest \
  packages/data/tests/unit/catalog/test_snapshot_completion_unit.py \
  packages/data/tests/unit/catalog/test_source_snapshot_store_unit.py \
  packages/application/tests/unit/process/ingestion/test_evidence_commit_unit.py \
  -q -n0 --no-cov
```

结果：**30 passed in 0.52s**；有 OpenTelemetry provider 重复初始化/关闭 warning，无失败。本轮只是复核现有保障，未改生产代码，不宣称新方案已经实现。另有 Tushare 分页离线复现与新浪公开端点只读抽样，见分册。

没有读取密钥、调用本机 Tushare/fuyao/FRED 账户做真实回填、修改真实数据或运行全库门禁。既有 API 权益、前轮 live 截断样本、live 行数与每日连续成功记录未在本轮刷新。远端 CI 依仓库已确认整改策略暂停，不作 CI 通过声明。

## 12. 维护者最终裁决与交接

[恢复证据保留与全球参考数据的最小正确性边界](https://github.com/cosmos-arc/ditto/issues/451#issuecomment-5975629762)保存唯一正式裁决，维护者原话为“Q1:B Q2:B Q3:按你推荐”。本报告据此更新，不再保留待确认状态。

- 恢复范围取B：只保障灾后当前可用状态，接受旧实验不能重放；正常运行的PIT/快照/完成保障不降级。
- 全球参考取B：本轮只展示；完整vintage、跨市场策略时间语义和美股交易延后。
- 次序采用推荐：先三源正确性，再价值明确的清理/ETF核心事实/全球展示限制，再删shadow/cascade并衔接因子物化，随后扩覆盖；备份与runner独立推进。FRED完整历史PIT从本轮前置移出。

下一步首批可交接Tushare客户端、FRED展示修复、fuyao截断/合法空三条已有票；共享schema/注册/完成合同仍由integrator单写。此轮没有实施上述代码，也未合并文档PR；本报告及分册目前为本地未提交文件。
