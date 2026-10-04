# 数据层过度设计成本侧审计（2026-10-04）

**性质**：分析报告（工作区未提交，待用户确认后落票）。
**与既有线的关系**：#420 wayfinder 线（#421 业界对标、#426 裁决"过度设计新增＝空"、报告 PR #441）用的是**功能必要性透镜**（业界有无同构）；本报告用的是**成本透镜**（维护与理解成本、live 用量），是 #421/#426 未测过的维度。两透镜结论并行不悖：功能侧维持清单不变，本报告对其中带量化成本的条目按"新证据"通道提出重开建议（用户 2026-10-04 确认此通道）。

## 1. 判据与基线（本次会话确认）

- **定位**：单用户、单机、本地优先；数据源预算 <2000 元/年。
- **重拉恢复基线**：上游可重拉＝最终恢复手段，天级恢复窗口可接受；只有不可重拉数据（paper/manual 账本、agent 存储）需要本地备份保证。
- **过度设计判据**：主判据＝新 agent 会话接手成本（认知/文档量）＋改动扩散面；辅证＝测试面、依赖耦合。功能上超前但**不增加**维护/理解成本的，归"可接受"，不列整改。
- **对标基础**：复用 #421–#425 + PR #441（Lean/Qlib/Zipline reloaded/ArcticDB/DuckDB+Parquet 个人实践/vn.py/backtrader + 机构级参照）。未发现需补的缺口。

## 2. 结论一览

| 档 | 条目 | 判定依据（成本侧证据） |
|---|---|---|
| 删除 | C1 shadow/certification 发布安全机器 | ~2,000+ LOC＋3 表＋~15 测试文件，live 全 0 行，语义无本地对应物 |
| 删除 | C2 derived 级联失效＋死信队列 | 为假想增量负载预留的队列机制，live 0 行，与 #418 方向冲突 |
| 删除 | C3 DatasetSpec 治理遗留字段 | 3 字段生产消费者为 0 |
| 删除 | C6 双观察账本（旧表） | 同一事实两处写，#393 归一化残留 |
| 删除 | C7 三层备份＋发布候选验收链 | `data/backups/` 为空；重拉恢复基线下只需配方脚本 |
| 简化 | C4 analysis 实验调度器 | 11,080 LOC 中 lease/fence/队列/terminal-retry ≈ 分布式账本，单机单用户 |
| 简化 | C5 摄取分区 8 态状态机 | 三件套之三（三阶段 log）保留，异常态机只服务崩溃恢复边角 |
| 维持 | 三件套、snapshot 身份、身份段位、readiness、对账、DI 分层 | 见 §5 成本画像 |

一句话：**#391–#398 治理方向正确但停在半途——工作流删了，影子留在合同字段（C3）、双账本（C6）和为零流量预建的机器（C1/C2）里。最大单点收益＝砍 publication safety/shadow/cascade 三件套（合计 ~5,000+ LOC、~5 张表、几十个测试文件）。**

## 3. 建议删除（5 项）

### C1. Shadow diff / certification 发布安全机器（最强）

**证据**：
- `packages/features/src/ditto_features/services/publication_safety.py:163-188`：`ShadowDiffReport` 含 `latency_p50_delta/latency_p95_delta/fallback_ratio_delta/request_count`——这是在线特征服务双跑比对的语义，单用户本地工作站没有并发流量可 shadow。#421 对标的全部个人级项目无此形态；业界质检统一是"离线命令＋非零退出"。
- `derived_shadow_slot` 表＋`publication_shadow_sqlite/` 与 9 个 JSON 文件读写器（`storage/runtime/publication_safety/`）**双存储**。
- certification pack 按 `shadow_ready/publish_ready` 两阶段推进（`application/processes/materialization/certification_rules.py` 302 行）。
- 合计约 2,000+ LOC＋3 表＋~15 测试文件；`derived_spec/derived_version/derived_shadow_slot/compiled_expression_cache/research_dataset_snapshot` live 全 0 行；`data/factors` 0B。

**最小等价**：发布前对 candidate 与当前版本做一次确定性重算比对（行数＋分区 checksum＋coverage/null 率——`DerivedMinimalDQSummary` 已有的一半），一个布尔结果落 `derived_version.status`。删 shadow slot、latency/fallback 字段、两阶段 pack、JSON/SQLite 双写。

### C2. Derived 级联失效＋死信队列

**证据**：`cascade_orchestrator.py`（323 行）＋`derived_invalidation` 表（`schema.sql:652-675`，`depth/retry_count/dead_letter_at` 列）——事件驱动增量因子刷新管线。但上游 Tushare/fuyao 可整段重拉，且 live 0 行；与 #418"因子物化阶段二"的声明式方向（产物身份复用 manifest、不重建控制面）重叠且冲突。

**最小等价**：物化产物声明输入的 `source_snapshot_id`（已有），发布前发现输入 snapshot 变了就整日期段重算。删失效队列表和重试/dead-letter 状态机。

### C3. DatasetSpec 治理遗留字段

**证据**：`catalog/dataset_spec.py`（570 行）中 `.certified_target_from`、`.license_policy`、`.raw_target_from` 生产消费者为 0，仅测试断言其存在。#392 删了治理工作流，但把"认证覆盖目标/许可策略"留在了数据集合同里。

**最小等价**：DatasetSpec 砍到 `dataset_id/primary_key/partition_keys/provider_datasets/schema_version/frequency`，删三字段及其校验。

### C6. 双观察账本（旧表）

**证据**：`source_snapshot_store.py:131-289` 同时维护 `provider_snapshot_observations`（INSERT OR REPLACE，旧）与 `provider_snapshot_observation_events`（INSERT OR IGNORE，#393 新，注释自称"单一事实"）。归一化时旧表没删。

**最小等价**：只留事件表，读侧聚合；一次迁移删旧表。

### C7. 三层备份＋发布候选验收链

**证据**：`payload_backup.py`（sha256 全树校验拷贝）→`workstation_backup.py`（manifest/digest）→`sqlite_backup.py`→`workstation_recovery.py`→`personal_workstation_release_candidate.py`（481 行）＋r2/r3 验收脚本。`data/backups/` 实际为空。重拉恢复基线下，真正需要本地备份保证的只有不可重拉数据（trading/agent/research 库）。

**最小等价**：文档化配方脚本（~50 行）：`sqlite3 .backup` 三个库＋rsync 到备份目标；删 release-candidate 验收驱动（本地 review 流程已取代）。payload_backup 的树校验可用 `rsync -c` 覆盖。

## 4. 建议简化（2 项）

### C4. Analysis 实验调度器（analysis 包，随本轮纳入）

`packages/analysis/src/ditto_analysis/storage/sqlite/experiments/` 共 11,080 LOC，其中 `_dispatch.py`(777)、`_lease.py`(515)、`_enqueue_fence.py`(233)、`_terminal_retry.py`(344)、`_scheduler_queue.py`——单机单用户的实验跑批配了分布式任务队列的账本。
**简化**：顺序 runner＋一张 run 表（status/started/finished/error）。**保留** holdout 隔离记账（5 文件）——那是承重的防泄漏部分。

### C5. 摄取分区 8 态生命周期

`partition_state.py` 的 8 态（PLANNED/PAYLOAD_COMMITTED/COMPLETE/FAILED/QUARANTINED/ORPHAN_PAYLOAD/LOG_ONLY/CATALOG_ONLY）＋事件表＋470 行 store（retry budget/resume）。
**简化边界（不碰三件套）**：保留三阶段 fetch log＋`complete_evidence_id`（#426 维持件）；砍掉三阶段之外的 5 个异常态与 retry budget——内容寻址载荷天然幂等，"已完成"由 payload checksum 判定。live 仅 9 个 checkpoint，不足以正当化状态机。

## 5. 维持（成本画像确认承重）

| 机器 | 成本画像 | 为什么可接受 |
|---|---|---|
| PIT 传播 | kernel 45 行＋2 个 helper＋schema 列/索引；重量在传播广度（~20 张表带时间列、192 文件引用 snapshot 身份） | 薄而广正是正确性核心该有的形态；AGENTS.md 第一不变量 |
| 内容寻址 snapshot 身份＋provider_payloads | 承重的是 ~30 行确定性身份函数＋幂等重拉 | CNEquity staging 同派；readiness/ETF 参考绑定的证据基础；#426 维持 |
| 证券身份段位＋可信历史写侧 | `InstrumentService` 1,346 行可议拆分，但机制本身（sid 段位、PIT 映射、生效+可知+来源三元组、source 唯一键幂等） | 本地主数据存储的全部价值，删了无法重建 |
| SnapshotReadinessQuery | 161 行、两依赖 | #391 治理后的"最小充分"样板 |
| fuyao 跨源对账 | 单文件＋近期落地（#413），#438 在排 | 换源接管的比对金集 |
| DI Provider 分层（C8 弱候选） | 12 文件/10 Provider | 层数问题属实，但改动扩散成本＞理解收益，记为已接受成本 |

## 6. 时序与落票建议（待用户确认）

1. **先砍后建**：C1＋C2 删除票先行，#418 因子物化二期在清理后的地基上实施（物化直线＝重算＋checksum＋snapshot 绑定，与 #398 详设"不重建控制面"一致）。不碰 #426 保护的地基（stock_daily/adj_factor/balance_sheet）。
2. **票结构提案**：一张裁决票（确认本文三档＋重开 C1/C2/C6）＋五张实施票（①C1+C2 删除、②C3+C6 合同与账本收尾、③C7 备份配方化、④C5 状态机收敛、⑤C4 调度器瘦身，analysis 侧独立）。
3. **无冲突确认**：#431–#433 修复票、#434–#439 实施票与本清单正交，不需重排。
4. **Housekeeping**：#391–#395、#397 在 GitHub 仍 OPEN，与"PR #409–#419 已合并"的收官叙述不一致，建议核实后关闭。

## 7. 证据来源

三路并行探索（2026-10-04）：票据线 #420–#433 全量拉取（含评论）、数据层代码盘点（含 `metadata.sqlite` 62 表 live 行数实测）、设计文档重建（`docs/data/data-layer-review-2026-10.md` D1–D17、ADR-0003、data-layer-map）。业界对标底稿见 PR #441（`docs/data/data-layer-benchmark-2026-10.md`，分支待评审）。
