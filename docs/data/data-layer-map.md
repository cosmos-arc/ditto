# Ditto 数据层全景图(现状说明)

> 本文记录**2026-10-03 精简前的开发环境观察**，不是生产运行或最终实现证明。
> 行数和数据根描述沿用初评记录，本轮未重新统计。后续审阅修正见下文；最终处置已在
> [Issue #390](https://github.com/cosmos-arc/ditto/issues/390) 和
> [审阅结论](data-layer-review-2026-10.md)确认，尚未实施。旧开发数据包括 payload 均可清空重建。

## 0. 三十秒心智模型

数据层只做三件事:

1. **搬数(通路)**:外部源 → 不可变快照+原始载荷 → Parquet/SQLite 业务表 → 查询服务。约 28k 行(sources 12k + storage 8.7k + services 4.7k + quality 2.4k),是核心,全部在转。
2. **记账(证据)**:搬运的每一步留下不可变记录——快照身份、分区完成事件、认证报告、晋级证据、血缘事件。约 7k 行(catalog),"感觉复杂"的主体。
3. **查账(门禁)**:消费时(选股/Paper/估值)现场核对账本+时间语义,不合格 fail-closed。

迷糊的根源:账本有 8 种、门有 4 层,其中约一半账本**从未被任何门查过**(空转,见 §8)。

## 1. 词汇表:时间语义("认知"指什么)

| 概念 | 含义 | 用在哪 |
|---|---|---|
| trade_date | 交易日 | 业务主键 |
| knowledge_date | 业务数据的可知时间字段；覆盖范围须逐数据集核实，不能假定每张表都有 | 写入+查询过滤 |
| effective_from/to | 版本生效区间；单有有效时间不证明已具备完整可知时间与修订历史 | PIT 版本链 |
| knowledge_cutoff | 请求自带"我只知道到此刻"上界 | 所有消费请求 |
| publication_cutoff | 供应商已发布时间上界 | admission、paper 执行 |
| observed_at / revised_at | 本地观察 / 供应商修订时间；同内容可被多次独立观察 | 快照修订链(#257) |

铁律:PIT 查询 fail-closed；必要时间或来源证据缺失须拒绝，摄取时间不冒充历史公开时间。
日期精度、cutoff 默认值与交易日历按各入口既有合同解释，不把某个 admission 路径的
“次一交易日 09:30”规则无差别推广到全部数据集。

另注:research.sqlite 里还有 `research_knowledge` 表(研究认知库),与 knowledge_date 是两回事,当前 0 行。

## 2. 一次摄取会发生什么(通路+留下的账)

```
Tushare(经 t.xiaodefa.top 代理)/ fuyao(冗余源,仅 stock_daily)/ FRED / TDX(仅对账)
  │  ditto_data/sources/*:适配器+限流+token
  ▼
摄取编排 application/processes/ingestion/coordinator(jobs/flows/{daily,eod,backfill,repair} 触发)
  │  选源 source_selection:读 fallback_policy(空表)+ catalog 新鲜度
  ▼
① 快照 ProviderSnapshot(内容寻址)→ provider_snapshots(1,319 行)
   同"供应商+数据集+区间+canonical分区"的新内容=新快照+记前版ID;A→B→A 复用 A
② 原始载荷 → data/provider_payloads/(不可变,内容寻址)
③ 分区生命周期 → ingestion_partition_checkpoints(1,319)/ partition_events(13,190)
   intent → checkpoint → COMPLETE(绑定精确 snapshot_id;旧完成事件不能证明新版本)
④ DQ 四类检查 → quarantine_failed_data(0 行:从未真正隔离过数据)
⑤ 血缘事件 → data_lineage_events(1,937)
  ▼
业务数据 → data/{market,fundamental,capital,macro}/**.parquet(年分区,含 knowledge_date 列)
         + metadata.sqlite 业务表(balance_sheet 等,本根 0 行——业务数据在 parquet 侧)
```

## 3. 数据集的一生:三个状态机

### 3.1 成熟度 maturity(晋级 promotion 管的正是它)

```
            promotion-collect(工具只收客观证据 → Markdown 报告)
experimental ─────────────────────────────────────► 人工审阅
    ▲                                                  │
    │                               promotion-review ×3 条(逐条 --passed/--rejected)
    │                                                  │ 全部 passed → 自动晋级
    └────── promotion-revoke(4 种 reason,append-only)◄─ initial-focus(生产默认可用)
```

- 3 条统一 criteria:①PIT/replay 覆盖完整 ②文档(owner/新鲜度 SLA/源切换策略)③catalog-backed 测试通过
- 唯一写路径 `ReviewDatasetPromotionEvidenceHandler`;工具不得自造通过条件
- 账本:evidence_log(18)/ promotion_events(9)/ maturity_promotions(3);2026-09-30 真实 revoke → 10-01 re-promote 走过完整闭环
- 14 个 launch 数据集:8 个走过晋级,6 个 ETF/指数类生来 initial-focus

### 3.2 认证 certification(数据集级证据包)

```
claims.json(= CertifiedField 数组:字段/精确快照/证券集合/覆盖区间/时间上界/consumer_bindings)
  → ditto data-products build-certification(CLI)→ 不可变报告(report_id + sha256 自校验)
  → approve(append-only 事件)→ active
  → revoke(append-only)→ 报告保留、阻断新消费;旧研究按原快照照常可读
```

- 现状:7 报告 / 10 事件
- **chicken-and-egg 在这**:报告冻结时记下 consumer 输入摘要(SHA-256);选股准入要求现场摘要与冻结摘要逐字节匹配 → 输入包任何漂移(连行业集合清空、缺失声明追加都算)→ `CONSUMER_INPUT_MISMATCH` → 整环 revoke→re-cert→re-promote 重跑(#386 两天两轮)

### 3.3 分区生命周期(摄取侧)

intent → checkpoint → COMPLETE(绑定精确 snapshot_id)。修订不改历史:同区间新内容=新快照+新完成事件,旧完成证据不迁移。

## 4. 消费时的门(field admission)与一次选股全流程

以下是组装与保存链的概念摘要。当前 `POST /selections/runs` 还可直接接收完整事实包，
并不保证先经过服务端组装；#391 将修正该信任边界：

```
1. 组装事实 assemble_facts:knowledge_date 列过滤(_without_future_knowledge)
   + 行级 source_snapshot_id 缺失 → declared_missing_inputs,fail-closed 保留
2. certified 窗口检查:stock_daily/status/basic/adj_factor 全窗要有认证覆盖
3. field admission 五连查:
   ① license(用途 × 实际使用日)
   ② CertifiedField 边界 + snapshot 绑定(跨阶段引用 → SNAPSHOT_CONFLICT)
   ③ maturity override  ④ coverage 例外  ⑤ PIT 可见性上界(交易日历解析)
4. consumer_input_hash 与认证冻结摘要匹配(不匹配 → CONSUMER_INPUT_MISMATCH)
5. 全过 → 保存 run;任一不过 → SELECTION_DATA_ADMISSION_BLOCKED
```

- #256 废弃窗口:旧请求一个绑定都不声明 → 保持原行为不进门;声明任何一个 → 全量进门
- ETF paper 执行走同一门的简化路径(purpose=promotion_paper,信号/执行/估值三 cutoff 因果序校验)
- 历史估值 #249 **不进这门**:只查快照唯一性 + cutoff

## 5. "血缘"是两样东西(+一个易混的第三者)

| 名字 | 是什么 | 状态 |
|---|---|---|
| 行级 lineage | 每根 bar 贴 `source_snapshot_id` 列 | **活**:选股链在用,Web 有 LINEAGE 区块 |
| lineage 事件存储 | `data_lineage_events` append-only(写:摄取/回填/派生/回测) | 写 1,937 行;读侧只有摄取去重在用;4 个 REST 端点建好,**Web 零调用** |
| #317-C 影响闭包 | tooling 里选测试范围的包级依赖闭包 | 与数据血缘无关,勿混 |

命名陷阱另两处:certification 的"freeze"(报告冻结)≠ `freeze_point`(回测冻结点,0 行);
根下 0 字节 `data/metadata.sqlite` 是占位,真库是 `data/metadata/metadata.sqlite`。

## 6. 存储地图(4 个物理库 + parquet)

**data/metadata/metadata.sqlite(15.8MB,唯一活跃治理+元数据库,80 张表)**

| 角色 | 表 | 行数 | 状态 |
|---|---|---|---|
| 主数据 | instrument(15,738)、trading_calendar(8,401)、instrument_*×7、industry_*、universe_*、index_weight | 万级 | 活 |
| 治理注册表 | data_catalog_entries 1,930、provider_snapshots 1,319(+observations/events)、certification 报告 7/事件 10、maturity 3/事件 9、evidence_log 18、license 6 | 千级 | 活 |
| 摄取运行时 | partition_checkpoints 1,319、partition_events 13,190、ingestion_log 1,975、cursor 10、lineage_events 1,937 | 千级 | 活 |
| 空转治理 | quarantine 0、freeze_point 0、fallback_polic(y|y_events) 0、derived_*+compiled_* 14 张 0、research_* 4 张 0、daily_risk_reports 0、remediation(表未建)、specimen(表未建) | 0 | **空转** |
| 业务/策略(本根) | balance_sheet/valuation_metrics 等 0、strategy_run 2、selection_run 0、trade_intents/execution_fills/risk_events 0 | 0 | 见注 |

**data/trading/trading.sqlite**:ETF paper 账本(paper_sessions/executions、account_journal_*、execution_*、对账修复)——**全 0 行**。此根为 #196 重建,paper 链未在此根运行过;代码已交付、CI golden-e2e 在测。
**data/research/research.sqlite**:研究/实验面(experiment、research_campaign、research_knowledge、gate_evaluation 等 20 张)——**全 0 行**,从未在此根使用。
**data/{market,fundamental,capital,macro}/**:Parquet 年分区,业务数据主体(knowledge_date 在 parquet 里)。
**data/provider_payloads/**:原始载荷;**data/factors、features/**:因子/特征;**data/freezes/**(空)、**data/quarantine/**(仅测试产物)。

## 7. 三条主线消费矩阵(运行时实测)

| 设施 | 选股 #196 | ETF paper | 历史估值 #249 |
|---|---|---|---|
| knowledge/publication cutoff | ✅ | ✅ | ✅ |
| ProviderSnapshot | ✅ 认证窗口+行级绑定 | ✅ 精确快照 | ✅ 价格源 |
| ProviderPayload + PITQueryService | — | ✅ | ✅ |
| certification(经 admission 链) | ✅ | ✅ | — |
| field admission 门 | ✅ 全量 | ✅ 简化 | — |
| 行级 source_snapshot_id | ✅ | — | —(上游携带) |
| lineage 事件存储 | — | — | — |
| promotion | —(间接:certified 窗口存在性) | — | — |

此矩阵只覆盖列出的三条路径，不是完整消费者清单。snapshot completion、范围与 payload
检查即使由 admission 调用，也属于独有正确性保障；删除工作流不能直接删掉这些语义。
观察事件、分区来源及摄取 lineage 的其他消费者见下文补充。

## 8. 在转 vs 空转(总表)

**在转**:通路全家(摄取/快照/载荷/分区/查询)、admission 门、certification、promotion(运维面,Web data-products workbench 有 UI:readiness/history/revoke)、license、行级 lineage、catalog 注册表、ingestion 运行时、OTel 测试卫生、oasdiff/osv-trivy 契约与安全门。

**本数据根未见业务产物或直接消费者的候选项**（不是生产全局零使用证明，删除需核对独有保障）：
specimen 五类试样(表未建)、remediation 审批(表未建)、fallback_policy 双源回退(0 行)、freeze 回测冻结(0 行)、derived 派生物化(14 张表 0 行)、research 控制面(4 张表 0 行)+ 整个 research.sqlite(20 张 0 行)、quarantine 隔离(0 行)、lineage 读侧 4 端点(Web 零调用)、pit_query/DuckDB 引擎(库文件从未生成)、r5 发布 preflight(798 行,近 4 个月零提交,仅自测消费)、slow_test_gate(716 行,自述 not a merge gate)。

初评提交分类：所选 124 个提交中 tooling 43 + catalog 12 ≈ 44%。该口径不等于
维护工时或无效成本，不能据此直接决定删除。


## 9. 同日审阅补充：删除前必须承接的消费者

| 设施 | 已确认消费者/语义 | 最终处置 |
| --- | --- | --- |
| 观察事件与请求坐标 | 历史日历、图表、技术分析；A→B→A 重观察顺序及交易所/证券/日期作用域 | #393 收敛到新摄取事实，不能只留 created_at |
| 分区 catalog | data provider 行级来源绑定、按日期选源与覆盖 | #394 同批切换到真实数据和精确完成范围 |
| admission 内容与完成检查 | 原始选股事实提交、Paper、历史证券池/研究构建 | #391 服务端事实和最小自动检查接替 |
| 许可检查中的来源闭包 | 研究导出的输入版本、证券池、来源集合和精确快照身份 | #391 分离并保留完整性，许可工作流不再承载这些检查 |
| 摄取 lineage 写侧 | run 幂等、同身份不同内容冲突拒绝、完成状态推进 | #392 暂留该活跃写侧，#393 新事实接替后同批删除 |
| 名称/ST 历史表 | 当前实现主要按生效时间查询，尚不证明完整可知历史 | #395 明确可信起点与缺失，不以当前值或默认日期造历史 |
| cross_source inner join | 零交集可能无差异报告 | #395 增加有效比较/未匹配/重复键与口径验收 |

本图的旧工作流与旧路径仅描述变更前实现。最终规格取消旧数据迁移、兼容和备份要求，
但新采集数据的来源、观察、提交与回放证据仍需保留；实施后由 #397 更新为最终形态。
