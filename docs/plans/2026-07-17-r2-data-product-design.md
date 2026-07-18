# R2：A 股日频数据产品设计

> **首次创建**：2026-07-17<br>
> **状态**：DEVELOPMENT COMPLETE / RELEASE ACCEPTANCE BLOCKED<br>
> **实施计划**：[2026-07-18 R2 implementation plan](2026-07-18-r2-data-product-implementation-plan.md)<br>
> **最近对账**：2026-07-18；确定性实现与工程门禁通过，真实 provider、历史、性能和连续运行证据尚未完成<br>
> **上游 Gate**：R1 / G1 已通过<br>
> **目标结果**：把 A 股日频数据从“能接入”提升为具有明确历史区间、PIT、质量、来源、恢复和 promotion 证据的数据产品。

## 1. 决策摘要

R2 采用**薄认证底座 + 数据集纵向切片**，复用现有 ingestion、Parquet、
catalog、lineage、DQ、promotion、query/API 主干，不重建第二套数据平台。

| 决策项 | R2 口径 |
|---|---|
| 主要市场 | A 股 ETF、个股和核心指数 |
| 行情 raw 起点 | `2015-01-01` |
| 个股 universe/status 认证起点 | `2016-01-01` |
| 策略可用起点 | 按所需数据集认证区间、证券上市日和真实最大 lookback 动态计算 |
| 数据源 | Tushare、FRED/ALFRED、本地 TDX |
| 运行边界 | 本地、单操作者、日频、人工决策 |
| 因子范围 | 固定因子的输入、计算、物化和数据正确性 smoke 验收 |
| 研究范围 | IC、衰减、换手、参数比较、批量回测和策略治理留到 R3 |
| 估算投入 | 13-19 人周；不含采购、供应商等待和多人并行收益 |

R2 不把 2015 年以前的数据称为噪音；它只是把更早历史移出当前 release
门槛。2015 至今适合作为现代 A 股日频人工决策窗口，但不足以单独证明长期
因子或高维模型稳健。

## 2. 产品目标与非目标

### 2.1 目标

R2 完成后，系统应能对任一范围内数据集回答：

1. 哪些日期、标的和字段实际已落盘？
2. 哪些区间只是 raw，哪些机械完整，哪些已经认证？
3. 数据来自哪个 provider、请求和 source snapshot？
4. 当时可知的数据、universe、公司行动和宏观 revision 是什么？
5. 通过了哪些 DQ、PIT、replay、许可和恢复检查？
6. 失败后如何恢复，何时必须降级、阻塞或撤销 promotion？
7. R1 在某个 signal date 是否可以安全消费这些数据？

### 2.2 严格非目标

- 身份认证（auth）、RBAC、多租户、公网部署和外部 Beta。
- 新付费 provider 作为 R2 完成前提。
- 分钟、tick、盘中增量信号和券商自动交易。
- 完整因子研究、自动参数搜索、批量回测和策略生命周期产品。
- 组合优化、组合风险和两融/质押风险产品。
- 合约级期货 universe、交易规则、保证金和执行。
- AI、LLM 或 Agent runtime。

## 3. 现有基线与阻塞缺口

### 3.1 复用的主干

现有数据集声明和 runtime source/SLA/promotion 语义位于
`packages/data/src/ditto_data/catalog/metadata.py`；ingestion route 位于
`packages/application/src/ditto_application/processes/ingestion/dataset_registry.py`；
post-ingest 已具备 PIT、DQ、physical write、cursor/freeze、log、lineage 和
catalog 流程；query 层也已有 maturity fail-closed gate。

R2 应增强这些契约，而不是再建一组 R2 专用 registry、writer 或 API。

### 3.2 必须优先修复的缺口

1. **Backfill 逐日化且 schedule 不完整。**
   `BackfillManager.backfill_range()` 固定从交易日历生成日期，不能正确表达
   natural-day/source-defined 数据集，也无法高效完成 2015 至今的历史回补。
2. **Backfill 完成判断不可信。**
   `backfill_missing()` 按 ingestion log 日期集合排除已摄取日期，没有先证明
   对应记录成功、DQ 通过且 catalog 已 attested。
3. **Payload 与证据不是可恢复提交。**
   普通数据集 physical write 后先写 cursor/freeze/success log，再 soft-fail
   写 lineage/catalog；catalog 失败可能留下 orphan payload 或 unattested success。
4. **多 source 证据会互相覆盖。**
   SQLite DataCatalog 主键没有 source/snapshot/version，相同 canonical partition
   的另一个 provider 会替换原 provider 证据。
5. **DQ 可 soft-pass。**
   未注册规则或未注入 checker 的路径不足以支撑历史 certification。
6. **Promotion 只证明“有资产”。**
   当前 coverage collector 主要统计 catalog asset 数和描述，尚不能证明目标
   区间、缺口、PIT/replay、provider 差异或许可。
7. **`fund_adj` 写入路由错误风险。**
   `FUND_ADJ` 与 `ADJ_FACTOR` 共用 `WriteKind.ADJ_FACTOR`，当前 handler 固定调用
   `save_adj_factor()`，后者固定写 `stock_adj`。ETF 历史回补前必须修复，并
   核查现有 `fund_adj` catalog URI、payload 和 checksum 是否一致。
8. **`index_weight` 尚未闭环。**
   Tushare adapter 已存在，但 application registry 仍是 `WriteKind.UNSUPPORTED`；
   需要补齐 effective-dated schema、writer/reader、ingestion、query maturity gate
   和历史认证。
9. **`stock_status` 尚不 PIT-safe。**
   当前 adapter 没有将目标交易日传给历史 ST 查询，上市状态也不能仅依赖当前
   `stock_basic` 筛选。2016+ certification 是 R2 修复后的目标，不是当前事实。

R1 Wave 1 的 promoted/initial-focus 只证明近期工作流能运行。市场数据主要覆盖
近期两个月，不能直接充当 R2 长历史认证证据。

## 4. 目标架构

```text
Tushare / FRED / local TDX
              │
              ▼
      Provider Adapter
  request + response metadata + source schema
              │
              ▼
 Provider-specific Snapshot
 payload/hash/request/license evidence
              │
              ▼
 Bootstrap / Incremental Planner
 schedule + chunk + checkpoint + resume
              │
              ▼
 Normalize → PIT Gate → DQ Gate
              │
              ▼
      Canonical Data Store
 partitioned + versioned + atomic commit
              │
              ▼
 Catalog + Coverage + Lineage
              │
              ▼
 Immutable Certification Report
 reviewer evidence → maturity promotion
          ┌───┴────┐
          ▼        ▼
      R1 决策    数据工作台
```

### 4.1 包职责

| 包/仓库 | R2 职责 |
|---|---|
| `ditto_data` | 数据产品契约、adapter、storage、catalog、coverage、DQ、PIT、promotion persistence |
| `ditto_application` | planner、摄取/补偿编排、认证报告、修复 use case、R1 readiness query |
| `ditto_apps` | API、CLI、job 和 DI wiring；不复制业务判断 |
| `ditto_features` | 固定因子与最小 materialization 验收；不直接访问 source/storage |
| `ditto-app` | 独立仓库实现数据工作台 UI |

## 5. 数据产品契约

R2 在现有 `DatasetMetadata` 和 `DataCatalogEntry` 上扩展，而不建立平行状态机。

### 5.1 静态契约

- `dataset_id`、domain、asset class、frequency、schedule。
- semantic schema version、主键、分区键、canonical identity、storage policy。
- default/supported/auxiliary source 和 provider dataset/API。
- owner、freshness SLO、DQ profile、bootstrap chunk policy、runbook。
- 本地缓存、内部计算、展示和再分发许可边界。
- fallback 模式：`automatic | manual | none`。
- `knowledge_date`、revision、release lag 和 effective-date 规则。

### 5.2 历史覆盖契约

| 字段 | 含义 |
|---|---|
| `native_from` | provider 原生可用最早日期 |
| `raw_from/raw_to` | 实际已保存的区间 |
| `complete_from` | 按 dataset schedule 机械完整的起点 |
| `certified_from/certified_to` | 通过 DQ、PIT、replay 和人工审批的区间 |
| `strategy_eligible_from` | 消费侧根据所有输入和最大 lookback 推导，不静态硬编码 |

### 5.3 三维状态

```text
maturity:
  reserved | experimental | initial-focus

runtime_health:
  ready | degraded | blocked

coverage:
  raw_from | complete_from | certified_from
```

已有 `initial-focus` 数据集不自动降级，但必须有新的
`r2-modern-a-share-v1` certification report 才计入 R2 完成度。

### 5.4 Provider snapshot 与 canonical asset

Provider-specific snapshot identity 至少包含：

```text
dataset + source + request interval + schema version + checksum
```

不同 source 的证据不得互相覆盖。Canonical partition 继续按统一
dataset/date/instrument 对消费者暴露。若许可不允许保存完整 raw response，则保存
标准化不可变 snapshot、请求参数、响应元数据、checksum 和许可说明。

## 6. R2 数据集矩阵

当前 registry 共 22 个数据集。R2 硬范围纳入 19 个，延期 3 个。

### 6.1 P0：A 股市场核心，12 个

| 数据产品 | Dataset | R2 目标 |
|---|---|---|
| 交易日历 | `calendar` | 2015 至今交易日、休市状态完整 |
| 证券主数据 | `stock_basic` | 上市、退市、板块、代码和身份历史 |
| ETF 主数据 | `etf_basic` | 上市、退市和跟踪标的信息 |
| 指数主数据 | `index_basic` | R1 benchmark/universe 所需核心指数 |
| 个股行情 | `stock_daily` | 2015 至今未复权日线 |
| ETF 行情 | `etf_daily` | 2015 至今或产品上市日至今 |
| 指数行情 | `index_daily` | 2015 至今核心指数日线 |
| 股票复权 | `adj_factor` | 与公司行动一致的 PIT 复权因子 |
| ETF 复权 | `fund_adj` | 独立 ETF writer、storage 和证据 |
| 个股状态 | `stock_status` | 2016 至今 ST、停牌和上市状态 |
| 指数成分权重 | `index_weight` | effective-dated 成分和权重 |
| 公司行动 | `corporate_actions` | 拆并股、送转等事件和生效日期 |

### 6.2 P1：财务、宏观和商品，7 个

| 数据产品 | Dataset | R2 目标 |
|---|---|---|
| 资产负债表 | `balance_sheet` | 披露日和修订版本可还原 |
| 利润表 | `income_statement` | 披露日和修订版本可还原 |
| 现金流量表 | `cash_flow` | 披露日和修订版本可还原 |
| 分红 | `dividend` | 公告、登记、除权和派息日期 |
| 估值 | `valuation_metrics` | 每日 PIT 估值快照 |
| 宏观指标 | `macro_indicators` | 中国和美国代表指标及 revision |
| 商品参考 | `commodity_daily` | 现货、指数和条件性连续品种切片 |

宏观最低集合：

- 中国：GDP、CPI、PPI、PMI、M2、Shibor、LPR。
- 美国：GDP、CPI、失业率、联邦基金利率、2Y/10Y 收益率和期限利差。

商品硬门槛是现有权限已覆盖的原油、黄金等现货/参考序列和至少一个国内商品
指数。若当前 Tushare 权限已可使用 `fut_mapping`，再增加一个 provider-mapped
主力连续纵切；权限不足不阻塞 R2，也不扩展为合约级期货产品。

19 个数据集是已确认的 hard scope，不能因 provider entitlement 缺失而静默删减。
W0 若发现除上述条件性 `fut_mapping` 外的硬范围无法用现有来源交付，应停止对应
切片并显式重定设计基线；不把购买新付费 provider 当作默认解决方案，也不得在
缺失数据集时宣告 R2 完成。

### 6.3 延期

| Dataset | 去向 | 原因 |
|---|---|---|
| `margin_trading` | R4；可做 R2 stretch | 更接近组合/市场风险产品 |
| `pledge_ratio` | R4；可做 R2 stretch | 更接近个股/组合风险产品 |
| `fx_daily` | R7 或明确用例后 | R2 没有必须消费它的业务闭环 |

## 7. 历史区间和 PIT 规则

| 数据类型 | Raw 起点 | Certified 起点 | 规则 |
|---|---:|---:|---|
| 股票/ETF/指数行情 | 2015-01-01 | dataset-specific | ETF 不早于自身上市日；认证起点由实际证据决定 |
| 股票历史 universe | 2015-01-01 | 2016-01-01 | 上市/退市 + 每日 ST/停牌联合重建 |
| 股票每日 ST | 2016-01-01 | 2016-01-01 | 更早历史不声明完整 |
| 财务/分红 | 按 `knowledge_date >= 2015-01-01` | dataset-specific | report period 可以早于 2015 |
| 指数成分权重 | provider native interval | core-index-specific | 保存 effective period，不前视回填 |
| 宏观 | series native interval | series-specific | 保存 observation、release、revision |
| 商品 | product native interval | product-specific | 标明 `spot/index/continuous` 类型 |

`2015-01-01` 是 R2 的现代运营窗口选择，不是 provider 原生下限。Tushare 当前
`daily` 文档说明单次请求可提取单只股票约 23 年历史；更早数据保留为后续研究
扩展，不进入本 release Gate。

点时主键至少为：

- 财务：`instrument_id + report_date + report_type + knowledge_date + revision_id`。
- 宏观：`indicator_code + observation_date + knowledge_date`。
- 指数权重：`index_id + constituent_id + effective_from`。
- 公司行动：`instrument_id + action_type + announcement/effective date`。
- 股票状态：`instrument_id + trade_date`。
- 行情 canonical key：`instrument_id + trade_date`；provider snapshot 使用独立
  identity，并通过 lineage 关联 canonical observation。

Promoted query 必须显式传递 `as_of/knowledge_date`。缺失点时语义时 fail closed，
不得用 `trade_date` 静默替代。

## 8. Bootstrap 与增量数据流

历史回补和每日更新共用同一条认证管线，只使用不同 planner。

### 8.1 Bootstrap planner

1. 根据 dataset schedule 生成 expected partitions。
2. 根据 provider capability 选择按日期、按标的或按区间获取。
3. 按年、季度或月生成 chunk，不逐日重复 merge 年度文件。
4. 为每个 chunk 建立 durable checkpoint 和 retry budget。
5. 只有 payload、catalog、lineage 和 success evidence 全部闭环的 `COMPLETE`
   chunk 才视为已完成。
6. 重跑只处理 missing、failed 或 evidence-incomplete chunk。

分区生命周期：

```text
PLANNED
  → FETCHED
  → NORMALIZED
  → PIT_PASSED
  → DQ_PASSED
  → PAYLOAD_COMMITTED
  → CATALOG_ATTESTED
  → LINEAGE_RECORDED
  → SUCCESS_RECORDED
  → COMPLETE
```

异常状态：

```text
FAILED | QUARANTINED | ORPHAN_PAYLOAD | LOG_ONLY | CATALOG_ONLY
```

每个状态都支持幂等补偿，不能靠覆盖 payload 隐藏证据缺失。

### 8.2 增量更新

- 行情：补最新交易日，并回看短窗口修复延迟数据。
- 财务/分红：回看最近披露窗口，捕获修订。
- 宏观：按发布日和 revision window 更新。
- 指数权重：围绕调仓生效窗口更新。

修订追加新版本，不原地覆盖旧的 point-in-time 事实。

## 9. DQ、覆盖和 Promotion

### 9.1 DQ 层级

| 层级 | 检查 |
|---|---|
| L1 Schema | 列、类型、主键、schema version、非空 |
| L2 内容 | OHLC、价格/成交量范围、重复、交叉字段一致性 |
| L3 历史覆盖 | expected/actual、缺口、生命周期和连续性 |
| L4 PIT/对账 | knowledge date、revision、universe replay、复权/公司行动、跨源抽样 |

准备 certification 的数据集没有 checker 或规则时必须 fail closed。

### 9.2 覆盖标准

- `calendar`：目标区间 100%。
- 行情：活跃证券在交易日无未解释缺口；停牌无成交由状态数据解释。
- 股票状态：认证区间 active universe 全覆盖。
- 财务/分红：按披露事件而不是交易日判断 completeness。
- 宏观：按各序列发布计划判断。
- 指数权重：每次有效调仓区间可还原。
- 批准的缺口必须有 exception code、owner 和 evidence。

### 9.3 不可变 certification report

人工审批的对象必须是一份机器生成并冻结的报告，至少包含：

- target/native/actual interval。
- expected/actual partition 数。
- gaps 和批准例外。
- source/schema/snapshot 集合。
- DQ rule version 和结果。
- PIT replay 结果。
- fallback/override 历史。
- freshness 和恢复演练。
- license ledger。
- consumer integration 结果。

成熟度继续沿用 `experimental → initial-focus`。每个 dataset 独立 promotion 和
revoke；`market_core_bundle`、`fundamental_bundle` 等只提供聚合 readiness，不替代
单数据集 evidence。

## 10. Source、对账和许可

| 来源 | R2 角色 |
|---|---|
| Tushare | A 股主数据、行情、状态、财务、估值、指数权重和中国宏观 |
| FRED/ALFRED | 美国宏观 revision、国际利率和商品参考序列 |
| local TDX | 先作为行情抽样对账；语义等价认证后才可成为显式 fallback |

W0 需要按实施当日官方页面重新核验 entitlement。2026-07-17 的 preflight
baseline 是：`daily` 120 积分起、`stock_st` 3000、`bak_basic` 5000、
`fund_adj` 5000 起、`index_weight` 2000。权限门槛会变化，不能把本设计中的
数字当作长期 provider contract。

Fallback 规则：

1. 只有 schema、时区、复权、PIT 和 revision 语义兼容时才能自动切换。
2. 记录 attempted sources、失败原因和最终来源。
3. 禁止同一 canonical partition 静默混合 provider。
4. Query 层不透明切源；fallback 只发生在 ingestion/certification 阶段。
5. 单来源可以 promotion，但必须声明 `fallback=none` 和 unavailable policy。
6. Provider 数量不提高 maturity。

每个 dataset/source 记录使用权、本地缓存权、衍生计算权、展示权和再分发限制，
但不在 ledger 中保存 token 或 secret。

## 11. 数据工作台

现有 `/ingestion` API 已包含 status、history、DQ、promotion、maturity、source
health 和 remediation 主干。R2 只补缺失 read model/command，不建立第二套 ops API。

工作台包含：

1. **Overview**：19 个数据集的 maturity、health、coverage 和 bundle readiness。
2. **Coverage**：时间轴、缺失区间、标的覆盖率和三类起点。
3. **Quality**：DQ 规则、失败样本、provider 差异和 PIT replay。
4. **Runs & Repair**：bootstrap job、chunk、重试、隔离和证据补偿。
5. **Evidence & License**：certification、promotion/revoke、snapshot 和许可。

本地单用户不增加 RBAC，但替换 canonical partition、接受 coverage exception、
切换 provider、promotion/revoke 和 repair execute 仍需 preview 与显式确认。

工作台不包含因子实验、策略比较、参数优化或回测报告。

## 12. R1 和固定因子集成

R2 不改变 R1 的 intent、fill、人工执行和复盘语义，只增强 data preflight。

R1 每日决策前检查：

1. Required dataset maturity 可用。
2. Signal date 和 lookback 区间位于认证区间内。
3. PIT universe 可还原。
4. Source snapshot 和 certification profile 可解析。
5. Required partition health 不是 blocked。

失败时返回 dataset、日期和 reason code，进入 `blocked`；不得回退到 experimental
数据。

迁移先 shadow-run 旧门禁与 coverage preflight；P0 bundle 稳定后再把
`r2-modern-a-share-v1` 变为 R1 强制条件。

R2 只为现有固定 seed 因子验收输入完整、最大 lookback、物化重放和
`knowledge_date`。IC、衰减、换手、因子发现和策略 promotion 归 R3。

## 13. 故障处理

| 故障 | 行为 |
|---|---|
| 网络超时、限流、5xx | 有预算的指数退避和 jitter |
| 鉴权、权限不足 | 不重试，标记 `configuration_blocked` |
| Schema drift | 隔离 payload，阻止 canonical write |
| 空响应 | 依据 dataset schedule 判定 legitimate empty 或异常 |
| DQ/PIT 失败 | quarantine，不写 canonical |
| Payload 已写、catalog 失败 | 重试 attestation，不重复 fetch/overwrite |
| Lineage 失败 | partition 不进入 COMPLETE |
| Provider 差异超阈值 | 禁止自动 fallback，等待人工 review |
| Coverage regression | runtime degraded/blocked，可 revoke certification |
| Promotion evidence 失效 | append-only revoke，不删除历史 |

不同 dataset 的 ingest 故障互相隔离；R1 required bundle 任一必需数据失败时，
R1 fail closed。

## 14. 测试和验收

### 14.1 自动测试

- 数据契约/schema unit tests。
- 每个 adapter 的 fixture/contract tests。
- Schedule-aware planner、chunk 幂等和 checkpoint 恢复测试。
- Provider snapshot 不覆盖测试。
- DQ/PIT property tests。
- Catalog migration、backup/restore 测试。
- Query maturity/coverage fail-closed 测试。
- API integration、OpenAPI diff 和前端 codegen/check。
- R1 daily decision regression。

### 14.2 故障注入

分别在 fetch、normalize、DQ、payload commit、catalog attestation、success log、
lineage 和 promotion review 阶段注入失败并证明可恢复。

### 14.3 Golden PIT cases

- 2015 异常波动阶段。
- 2016 熔断日。
- 一次 ST 进入/退出和一次停复牌。
- 一次上市和一次退市。
- 一次分红/送转。
- 一次指数调仓。
- 一次财报 revision。
- 一次宏观 revision。

每个 case 证明目标 `as_of` 只能看到当时已知事实。

### 14.4 性能目标

在文档化的参考机器和 provider quota 下：

- P0 2015 至今首次 bootstrap 不超过 24 小时。
- 中断恢复不重新处理已完成 chunk。
- 正常日增量在 provider 数据可用后 30 分钟内完成 P0 更新。
- Coverage/workbench 聚合查询目标 5 秒内。
- 同一区间连续运行两次，第二次无重复写且 snapshot 结果一致。

24 小时是 range/chunk 改造后的目标，不是当前实现基线。W0 必须在同一参考机器
和 quota 下对代表性的 stock/index/adj/fund_adj chunk 做 benchmark；若外推不能
满足目标，应在 W1 前显式调整架构或重新审批性能 Gate，不能留到 W5 才处理。

### 14.5 Release acceptance

- 确定性 fixture 全量通过。
- 20 个历史交易日 replay 通过。
- 至少 5 个连续真实交易日增量运行保留 evidence。
- 19 个数据集逐一生成 certification report。
- P0/P1 bundle readiness 为 ready。
- R1 在真实 promoted 数据下完成 ready/review/blocked 回归。
- 固定 seed 因子在 certified snapshot 上通过输入契约、最大 lookback、确定性
  materialization replay 和数据正确性 smoke。
- Backup、restore、promotion revoke 和 recertification 演练通过。

## 15. 实施波次与投入

| 波次 | 主要内容 | 退出条件 | 估算 |
|---|---|---|---:|
| W0 设计冻结与预检 | Contract、provider entitlement、license、migration、`fund_adj` 核查、代表性 chunk benchmark | 权限/契约矩阵、迁移方案和 24h 性能 Gate 冻结 | 1-2 人周 |
| W1 认证底座 | Coverage、partition state、batch planner、reconciliation、immutable report | 一个 fixture dataset 完整通过 bootstrap/repair/certify | 3-4 人周 |
| W2 市场核心 | ETF/index → stock/status → index_weight → corporate actions | P0 bundle 通过历史与 R1 shadow gate | 3-4 人周 |
| W3 稀疏 PIT | 三表、分红、估值、revision/replay | Fundamental bundle 通过 PIT golden cases | 2-3 人周 |
| W4 宏观商品 | 中美宏观、revision、商品代表产品 | Macro/commodity products 独立认证 | 2-3 人周 |
| W5 工作台与收口 | API、ditto-app、R1 强制门禁、性能、真实数据验收 | R2 Definition of Done 全部满足 | 2-3 人周 |

总投入建议 **13-19 人周**。W1 契约冻结后，W2 市场核心与 W3/W4 的
source-specific 工作可部分并行，但共享 schema、coverage 和 certification policy
不得分叉。

## 16. Definition of Done

R2 只有在以下条件全部满足时才完成：

1. 19 个范围内 dataset 都有冻结的数据产品契约。
2. P0 行情 raw 从 2015 开始。
3. 个股 PIT universe 从 2016 开始认证。
4. 所有缺口可解释或有批准例外。
5. 所有 dataset 都有独立 immutable certification report。
6. Provider snapshot、canonical asset 和 lineage 可互相追溯。
7. Bootstrap 可恢复、可重跑且结果确定。
8. Promotion、revoke 和 recertification 闭环通过。
9. 数据工作台使用真实 API。
10. R1 只消费满足 coverage 和 maturity gate 的数据。
11. 固定 seed 因子的输入、最大 lookback、确定性物化重放和数据正确性 smoke 通过。
12. 完整因子研究、回测和策略产品没有泄漏进 R2。
13. 真实数据、性能、backup/restore 和连续运行证据完成。

### 16.1 2026-07-18 开发完成与发布证据对账

“开发完成”表示本设计对应的代码、测试、API、CLI、工作台、runbook 和
fail-closed acceptance runner 已落地；它不等于 R2 已通过真实数据发布验收。

| DoD | 开发证据 | 发布证据状态 |
|---:|---|---|
| 1 | 19 个 hard-scope 与 3 个 deferred contract 已冻结并通过 contract tests | **开发已完成**；部署 contract snapshot 待归档 |
| 2 | raw/certified target、coverage query 与 certification boundary 已实现 | **阻塞**：尚无 2015 至今真实 P0 raw coverage artifact |
| 3 | stock status 按目标交易日查询，PIT universe 规则与 golden tests 已实现 | **阻塞**：尚无 2016 至今真实 universe/status replay |
| 4 | schedule-aware gap、exception 与 readiness fail-closed 已实现 | **阻塞**：尚无真实 gap/approved-exception report |
| 5 | 每个 dataset 的 immutable certification store、command/query 已实现 | **阻塞**：尚无 19 个真实独立 report ID/content hash |
| 6 | provider snapshot、canonical asset、lineage 与 ingestion evidence saga 已实现 | **阻塞**：尚无真实 lineage traversal artifact |
| 7 | checkpoint/resume、补偿、联合 backup/restore 与连续幂等 fixture 通过 | **阻塞**：尚无真实区间中断恢复与连续运行 artifact |
| 8 | promotion review、revoke、recertification 与审计查询闭环已实现 | **阻塞**：尚无真实 append-only 演练记录 |
| 9 | 工作台五视图消费生成的 OpenAPI 类型和真实 API hooks；1942 个前端测试与 build 通过 | **阻塞**：尚无 `VITE_USE_MOCK=false` live UI artifact |
| 10 | `DataReadinessQuery` 与 EOD/R1 preflight 强制 coverage/maturity gate | **阻塞**：尚无真实 promoted snapshot 下的三状态回归 |
| 11 | 固定 seed 输入、最大 lookback、确定性 replay 与 smoke gate 已实现并测试 | **阻塞**：尚无真实 certified snapshot 机器报告 |
| 12 | contract、API、路由与 UI 保持 R2 non-goals，架构契约全部通过 | **开发已完成**；release reviewer 尚未签署 |
| 13 | fixture 报告通过性能外推、恢复与第二轮零写；live runner 正确 fail-closed | **阻塞**：缺 entitlement、真实 benchmark/backup/restore 和 5 日连续运行证据 |

本次机器报告与 SHA-256 见
[R2 evidence index](../evidence/r2/README.md#5-current-release-review)。由于上述
真实证据 Gate 未关闭，本文件不将状态标为 `IMPLEMENTED`，也不宣称 R2 release
已经完成。

## 17. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Provider quota/权限不足 | W0 做 entitlement preflight；硬范围缺口需显式重定设计，条件性 `fut_mapping` 不阻塞，不隐式采购新 provider |
| 2015 行情被误称全周期 | 文档标为 modern operational window；长期研究边界留 R3 |
| 当前 maturity 造成虚假就绪 | R2 单独要求 `r2-modern-a-share-v1` certification profile |
| 历史写入耗时过长 | Range fetch、chunk write、checkpoint、resume 和明确性能 Gate |
| 多 source 混合污染 canonical | Provider-specific snapshot identity 和 compatibility gate |
| PIT 通过形式检查但仍泄漏 | Golden event replay + query fail-closed + revision-preserving storage |
| R2 膨胀成 R3/R4 | 因子研究、回测、risk datasets 保持严格 non-goals |
| 后端工作台掩盖前端空壳 | `VITE_USE_MOCK=false`、OpenAPI codegen 和真实 API E2E |

## 18. 外部来源说明

- Tushare `daily` 官方说明单次请求可提取单只股票约 23 年历史；2015 是 R2
  产品范围选择，不是 provider native 下限：
  <https://tushare.pro/document/1?doc_id=27>
- Tushare `bak_basic` 官方说明股票历史列表从 2016 年开始：
  <https://tushare.pro/document/1?doc_id=262>
- Tushare `stock_st` 官方说明数据从 2016-01-01 开始，更早历史无法补齐：
  <https://tushare.pro/document/2?doc_id=397>
- Tushare 官方权限表列出 `fund_adj`、月度指数成分/权重等当前积分门槛：
  <https://tushare.pro/document/1?doc_id=108>
- Tushare 提供期货主力/连续合约映射 `fut_mapping`：
  <https://tushare.pro/document/2?doc_id=189>

## 19. 后续步骤

开发任务已按
[R2 implementation plan](2026-07-18-r2-data-product-implementation-plan.md)
完成。剩余工作全部属于真实环境发布证据，不得用 fixture 或手写状态替代：

1. 录入 19 项 provider entitlement 与 reviewer-approved license ledger 记录。
2. 执行 2015/2016 起历史 bootstrap、20 日 replay，并生成 19 个独立 certification report。
3. 在同一参考机器和 quota 下完成四类 benchmark、真实 backup/restore、同区间连续两次运行及 5 个连续交易日增量。
4. 在真实 promoted snapshot 下完成 R1 三状态回归和 `VITE_USE_MOCK=false` 工作台验收。
5. 使用运维手册的隔离路径重跑 live acceptance；只有 §16 十三项发布证据全部关闭后，才将状态改为 `IMPLEMENTED`。
