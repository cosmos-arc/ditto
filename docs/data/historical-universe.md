# 历史证券池与可投资集合

对应 #251 / #258。历史研究与 Selection 使用 `HistoricalUniverseQuery`，不再用区间末日或今日名单构造过去样本。普通 Universe CRUD / members 是管理视图，其有效日期查询不证明历史可知性。

## 输入证据

`HistoricalUniverseSources` 固定 universe_id、asset_kind、master_snapshot_id、status_snapshot_id，以及可选的 index_id / membership_snapshot_id。股票使用 stock_basic + stock_status；ETF 使用 etf_basic + etf_daily。股票按指数筛选时额外固定 index_weight；ETF 的 index_id 指跟踪标的，来自 etf_basic 的历史 tracking_index。

每个来源必须是已完成摄取、保留载荷、具有可信物理 schema 指纹且在知识截止前已观察的 ProviderSnapshot；实际消费字段还必须通过现有许可、覆盖和认证准入。字段证据不会因为文件存在或可读而自动成立。

供历史投影消费的规范化帧需要以下已审核字段：

| 输入 | 字段 |
| --- | --- |
| 所有历史帧 | instrument_id（Int64）、effective_from / effective_to（Date，半开区间）、publication_at / available_at（带时区 Datetime） |
| 主数据 | list_date / delist_date（Date）；ETF 另有 tracking_index |
| 交易状态 | is_suspended（Boolean，可空；空值不具投资资格） |
| 股票指数成分 | index_id |

这些字段是历史研究的证据要求，**不表示当前供应商响应已经具备这些证据**。普通主数据只有今日状态、月度权重只有采样日、ETF 日线只有 OHLCV 时均不够；不能推导或伪造历史有效区间、停牌状态与公开时间。缺字段明确拒绝，需通过既有摄取、保留载荷和认证流程补齐。日期精度原始公告先按 #257 的认证规则冻结保守可见时点；不能在投影时自行填午夜。

主数据快照定义本次实际观察范围，覆盖认证须包含该范围的失败、退市样本和关系缺口。返回范围只代表该快照的已审核范围，不宣称全市场覆盖。关系/状态字段资格按实际主数据范围验证，不以缺行推定来源具备完整覆盖。

## 时间与缺口

先应用 publication / knowledge cutoffs，再按 business key + effective_from 选择可见修订，最后应用 `effective_from <= as_of < effective_to`。重复修订身份和重叠有效区间拒绝。已知证券的主数据区间断裂拒绝整个查询，不能让样本静默消失。

观察池保留当时已知的退市、尚未上市、停牌和退出指数的证券；投资资格另给 DELISTED、NOT_YET_LISTED、SUSPENDED、TRADING_STATUS_MISSING、NOT_INDEX_MEMBER、OTHER_TRACKING_INDEX 等原因。上市天数与停牌状态由服务端投影，策略的流动性、ST、涨跌停与跟踪误差等限制继续独立执行。

## 使用与重放

- `POST /api/v1/universes/{universe_id}/history` 是只读查询，提交 sources、as_of、knowledge_cutoff、publication_cutoff；返回完整观察池、投资原因及内容寻址的 universe snapshot ID。
- Selection 输入包添加 universe_sources；universe_snapshot_id 必须匹配上述结果，selection_source_snapshot_ids 包含全部历史来源，instruments 保留完整观察池。字段准入预览与创建都核验历史证据。前端输入区域可查看该时点的历史证券池。
- `research_dataset_build_flow` / `ResearchDatasetBuildProcess.build` 必须显式传入 universe_sources，与 spine 的 universe_id 一致。逐交易日恢复证券池，不以末日名单做笛卡尔积。sample_time 使用上海时间当日零点；explicit_cutoff 使用明确截止（无时区的既有日期输入按上海时间解释），该口径冻结在工件中。
- spine manifest 保存逐日 cutoffs、来源、认证与许可引用；数据集保留 investable 和 universe_exclusion_reasons。它们是观察样本属性，构建不删除不可投资行。
- resolved_inputs 中 `input_kind=universe` 独立于派生因子输入，source_snapshot_ids 包含两者并集。导出重新核验所有来源许可，不得遗漏证券池来源。
- 新修订创建新的来源/结果身份；相同证据重试复用工件。资格被撤销后不能启动新研究，既有工件仍可按保存身份审计。

未上线输入按用户确认直接收紧：不再保留未绑定字段/历史来源的 Selection 创建旁路。不迁移旧记录为已认证，也不改写旧研究工件。

自动化使用隔离合成证据，不能证明供应商真实历史覆盖、权益或可投资效果。
