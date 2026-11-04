# 期货双库与指数估值消费接线验证（#658 批次4c）

交付时间：2026-11-04。范围：futures_daily（六所实际合约日线）历史回补+查询、
futures_basic（同范围含到期合约）身份读取、index_valuation（冻结代码列表）
历史回补+读取。三数据集此前仅有摄取通道（EOD 近端数据），无任何消费方。

## 1. 消费接线（CODE）

三数据集均为 experimental 成熟度（catalog metadata），全部读路径带
`allow_experimental_data` 显式 opt-in 门（`_maturity_gate`）：

| 数据集 | Store/Service | Application | HTTP | read_semantics |
| --- | --- | --- | --- | --- |
| futures_daily | `MarketService.get_futures_daily`（source_ticker 列过滤——reader instrument_ids 只作用于 instrument_id 列，期货无此列） | `FuturesQueryFacade.get_futures_daily` | `POST /futures/bars` | latest_available |
| futures_basic | `MarketService.get_futures_contracts`（filters-only 读，无日期界） | `FuturesQueryFacade.get_futures_contracts` | `GET /futures/contracts` | latest_available |
| index_valuation | `CapitalStore.get_index_valuation`（instrument_id 窗口读） | `CapitalQueryFacade.get_index_valuation` | `GET /capital/index-valuation`（DateRangeQueryParams+倒置窗口/未来 as_of 400） | latest_available |

关键语义随 DTO/描述传播：

- 合约键＝source_ticker（ts_code 形态，如 `RB2410.SHF`）；期货合约不是
  证券主数据标的，不映射 instrument_id。
- 期货 amount 万元；settle/pre_settle 结算价口径；上市首日 pre_settle
  与无成交日 OHLC null 透出不填 0（`_optional_float` null 保真）。
- **修订收敛（三轴 correctness F1/F2 根修）**：两库存储键均含
  knowledge_date（＝摄取日非源发布日），重拉/回补产生同日多版本；读取层
  `unique(subset=事实键, keep="last")` 按 knowledge_date 收敛到最新版本
  （fina_indicator 先例，#628 词表 latest_available）。姊妹项
  `get_moneyflow`（批次3）同型暴露已立后续票。
- 空合约列表拒绝（422）：非缺省选择不得静默全量；limit 取窗口内最新
  N 行（交易日倒序截断后回正）。
- futures_basic 的 list_date/delist_date 为源端声明窗口（非本地观察），
  delist_date null=源未提供而非在市推断；source/knowledge_date 随行
  （来源与快照摄取日传播）；「与日线同范围含到期合约」由 79,495 行
  全量身份快照承载。
- **index_valuation 市值单位＝元**（与个股 daily_basic 万元不同，
  doc_id=128）；pe/pe_ttm/pb 倍数；同日多版本收敛同上。

## 2. index_valuation 冻结代码列表（15 码）

源端（tushare index_dailybasic）当前支持的正式指数估值集合，回补与
读取范围以此为准：

```text
000001.SH 000005.SH 000006.SH 000016.SH 000300.SH
000688.SH 000852.SH 000905.SH 399001.SZ 399005.SZ
399006.SZ 399016.SZ 399300.SZ 399673.SZ 399905.SZ
```

## 3. 历史回补（LIVE）

- futures_daily：2014-01-01 → 2026-10-31 日期路径回补（六所逐交易日，
  chunk 月粒度+checkpoint+账本审计）；2026-11 起由 EOD 车道常态承接。
  回补前存量仅 7,527 行（2026-10-26..11-03）；回补结果与源端起点取证
  见回补完成后的账本证据（GFEX 2022-12 上市等各所实际起点自然呈现）。
- index_valuation：同窗回补（15 码），回补前存量 105 行近端数据。
- 请求预算：两轮回补合计 ~6.3k 请求（日期路径），与批次计划口径一致；
  顺序执行不与 EOD 车道争用（~25 req/min 匀速）。

## 4. 验证证据

- 集成测试 3 例（真实 ParquetStore→facade→HTTP）：修订收敛（同日双版本
  →单行最新值）/行透传/ISO 日期/null 保真（首日 pre_settle）/experimental
  门 400/倒置窗口与空合约列表 422/limit 最新 N/合约代码过滤（未知码空列表
  非全量）/交易所品种过滤/source+knowledge_date 传播。
- facade 单测 4 例：两数据集门+委托；type-all 0 错误；contract-static
  纯绿（新增端点纯加性，无 breaking finding）；R5 证据刷新。
- 三轴：Spec/Standards 6 项（单位元/403→400/source 传播/coverage/
  空列表/__all__）+ correctness 6 项（双库收敛 HIGH×2/空列表反演/
  测试配置镜像/limit 语义/null 日期留档）全部修复或留档。
