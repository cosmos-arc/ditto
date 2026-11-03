# P5 运行恢复与持续验收报告（#630 / 父规格 #621 P5·收官票）

交付时间：2026-11-03。覆盖 #630 三项范围：备份恢复演练（不可重拉事实）、
性能基线实测、连续五交易日逐数据集 LIVE 建议门。数据根＝仓库 `data/`
（DITTO_STATE_ROOT 注入；实测于 2026-11-03 晨，EOD 夜链 11-02 波已落账、
11-03 波未开始）。

## 1. 备份恢复演练（不可重拉事实）

### 1.1 配方扩展（CODE，沿用 #446 工作站备份恢复测试）

`ditto_apps.scripts.workstation_backup_recipe` manifest 升 **v2**，不新建框架：

- **provider payload 证据树入册**：`provider_payloads/**`（内容寻址原始载荷
  留存，4.8 GB／20,676 文件）作为证据树备份——存在则必须带 root sha256
  身份恢复；缺失不阻断当前状态恢复，但显式声明「历史对账/审计锚不可
  重放」。`research/artifacts` 维持 #446 原语义（旧实验不可重放）。
- **数据层业务事实入 verify 清单**（metadata/metadata.sqlite）：数据目录
  条目（data_catalog_entries）、摄取证据账本（ingestion_log）、分区完成
  证据（ingestion_partition_checkpoints）、供应商快照证据
  （provider_snapshots）、证券身份（instrument）、交易日历
  （trading_calendar）——与既有账本/策略治理/holdout/agent 事实同级
  FAIL 级核对。
- **域未初始化语义**：库文件连同父目录一起缺失＝域从未初始化
  （manifest 记 `present:false`，verify 记 WARN「该域未初始化」）；
  父目录存在而库缺失＝必需对象缺失，fail closed。本部署 research/agent
  域从未初始化，v1 的全量必需清单会令任何备份永久失败，此语义是其
  最小修正。
- 集成测试扩展至 19 例（`test_workstation_backup_recipe_integration.py`）：
  全量往返、未初始化域演练、payload 缺失不可重放声明、payload 备份
  篡改拒绝（preflight 身份不符、目标零写入）、v1 manifest 拒绝。

### 1.2 真实根演练（LIVE）

对真实数据根完整执行 backup → restore（隔离根）→ verify（票面验收路径），
全程源库只读（SQLite Backup API 只读连接），演练后清理临时根与备份
（~20 GB），证据 JSON 留存本节：

| 步骤 | 结果 |
| --- | --- |
| backup（清单 v2） | 9.6 GiB：catalog 5,079,531,520 B＋trading 70,959,104 B＋payload 树 20,676 文件；research/agent 四库与 artifacts 记 `present:false`（域未初始化） |
| restore（隔离空根） | 前置 preflight 重验备份身份（sha256/逻辑摘要/大小逐项）后恢复；`present:false` 条目零写入并记「域未初始化」 |
| verify | **passed=true，退出码 0**：2 库 integrity+restored_content PASS；13 条业务事实全 PASS；4 条 WARN＝未初始化域 |

恢复根业务身份实测（只读核对）：`data_catalog_entries` 46、`ingestion_log`
21,956、`ingestion_partition_checkpoints` 10,760、`provider_snapshots`
10,642、`instrument` 28,694、`trading_calendar` 5,478、`paper_sessions` 1、
`account_journal_events` 10；payload 树 20,676 文件原样恢复。观察耗时
（本机 M 系列笔记本、冷缓存近似值）：backup ≈3 分钟，restore（含
preflight 全量重哈希）≈6 分钟——单用户天级恢复目标内。

验收条款对照（#621 P5）：完整性＝逐对象 sha256＋逻辑摘要；业务身份＝
逐域可读业务事实核对；依赖工件＝payload 证据树＋catalog 证据账本；
缺必需对象失败＝目录存在而库缺失/备份对象缺失/身份不符均 fail closed；
旧可选工件缺失明确不可重放＝per-tree 显式声明且不清零既有事实。

边界留档：跨库恢复不原子（#446 原边界，停写窗口内演练）；Parquet 数据
树（market/fundamental/capital 等，可重拉缓存）不在备份清单，灾后按
覆盖合同重拉；`data/metadata.sqlite`（顶层 0 字节陈旧占位）与
`~/.local/state/ditto`（2026-10-06 陈旧库，合同头条 6）不属恢复对象。

## 2. 性能基线（先实测，不虚构预算）

工具：`ditto_apps.scripts.data_perf_baseline`（只读，真实读栈：经组合根
容器取 MarketReaders，与 ops/API 消费者同一路径）。参考日 2026-11-02、
参考标的 instrument_id=1000001、repeat=3 取中位；RSS 为进程高水位增长
（macOS ru_maxrss 字节口径）。观测值，非预算：

| 查询（消费者面） | 行数 | 中位耗时 | RSS 峰值增长 |
| --- | ---: | ---: | ---: |
| stock_daily 单标的 1 年窗口（图表车道） | 242 | 4.9 ms | ≈0 |
| stock_daily 单标的全历史 2014 起 | 3,354 | 22.6 ms | 8.4 MB |
| stock_daily 单日全市场横截面 | 5,574 | 16.2 ms | 7.0 MB |
| stock_daily 全年横截面（因子/回测式） | 1,096,784 | 149.1 ms | 548.6 MB |
| adj_factor 单日全市场 | 5,581 | 2.6 ms | ≈0 |
| index_daily 单日 | 0 | 0.6 ms | ≈0 |
| etf_nav 单日横截面 | 895 | 1.2 ms | ≈0 |
| 覆盖限制蒸馏装载（/datasets/coverage 运行时真源） | 47 项 | <0.5 ms | ≈0 |
| ingestion_log 账本计数（ops status） | 21,956 | 20.7 ms | — |

进程峰值 RSS 899.5 MB（含容器装配；全年横截面主导）。RSS 列为进程
高水位增长：≈0 表示该查询未抬高进程峰值（非零内存占用），其整体
内存足迹由进程峰值一列兜底。结论：当前全部消费者路径毫秒级，无优化
必要；唯一重查询（全年横截面 149 ms／549 MB）留档为未来因子/回测
扩量时的对照锚点，不预设阈值。index_daily 参考日 0 行＝11-02 未覆盖
（见 §3.3 开放项），非性能属性。

## 3. LIVE 建议门（连续五交易日逐数据集 SLA）

工具：`ditto_apps.scripts.data_live_gate`（只读 SQL，完成判定精确镜像
`snapshot_completion.snapshot_completed` 与 `completed_snapshot_index`
市场级范围规则；单元测试 5 例锁定规则，其中
`test_sql_completion_rule_matches_python_rule` 以 Python 真源逐格对拍
SQL 覆盖计数，防规则漂移）。

### 3.1 窗口选择

窗口＝**2026-10-26 … 2026-10-30**（评估时点最近五个连续交易日且全部
补偿闭环已收敛）。11-02 及以后的夜链补偿尚未收敛（§3.3），纳入会以
未决项冒充终态；窗口参数为建议值，脚本可随时重跑滚动窗口。

### 3.2 矩阵结论（46 数据集 × 5 日＝230 格）

- **230/230 格均有已完成市场级覆盖**：214 格 attested（覆盖窗口行数>0），
  16 格 covered_empty（完成请求＋零行＝正常无事件，不冒充失败），0 格
  uncovered。**核心链五数据集（stock_daily/adj_factor/stock_status/
  stock_limit/index_daily）25/25 格逐日 attested 且当日 SUCCESS——
  当夜完成，36h SLA 内，SLA 达标**。
- **正常空结果明细（covered_empty 16 格）**：dividend（10-27/10-29 无
  除权事件）、hk_hold（10-27…10-30 北向季度披露制内无披露）、
  index_weight（5 日）、pledge_ratio（5 日，周披露节奏）——完成请求＋
  零行，与 #623 分类语义一致。
- **窗口内失败×2，均有补偿闭环**：
  - `fund_portfolio` 10-27：FETCH_ERROR「chunk skipped failed partition
    day; repair pending」（5 次尝试至 11-02 04:49 CST）；账本侧 10-27
    日分区 chunk 10-27 21:55 CST COMPLETE＋2026-Q4 chunk 11-02 04:49
    CST COMPLETE 双重覆盖——日级数据已补（补偿完成于披露时限之外，
    补偿闭环语义而非新鲜度 SLA 语义），残余 FAIL 日志行留痕取数历史。
  - `global_index_daily` 10-27：ColumnNotFoundError（source_ticker 列，
    #629 修复对象）；后续 7 日窗口 chunk（10-23…10-30 于 10-30 21:56
    CST COMPLETE、10-26…11-02 于 11-02 21:56 CST COMPLETE）覆盖
    10-27——根因修复＋窗口回补双闭环。
- **事件/低频源不以五日无事件宣称通过**：龙虎榜/机构席位/北向分段以
  实际披露事件样本验证（[event-disclosure-verification.md](
  event-disclosure-verification.md) 对拍 9/9），基金持仓/前十大双榜以
  披露矩阵＋场外定界验证（[holdings-disclosure-verification.md](
  holdings-disclosure-verification.md)）。
- **受限/部分数据集按 P0 覆盖合同记录，不宣称通过**：fx_daily（合同
  ready，#629 回补 23,993 行）、commodity_daily/macro_indicators（partial，
  forecast 2024-01-31 代理翻页损坏等缺口在册）——窗口内夜链失败由
  #629 窗口修复＋回补收敛（合同已按 2026-11-03T00:15 复测刷新），其
  补偿完成时点晚于任何新鲜度窗（回补闭环而非 SLA 达标）；修复后连续
  绿窗自 11-02 起算，满五日后再以本脚本滚动复验。etf_nav（partial
  末端）、moneyflow（BSE 源端限制 2026-10-31 起）、rights/csrc 接口
  （#517-#523 降级裁决）均按合同在册。

### 3.3 开放项（窗口后，补偿闭环进行中）

- `index_daily` 2026-11-02：3/188 指数代码失败（801072/801074/801145.SI），
  #511 部分日拒绝语义正确生效（拒绝半完成市场覆盖），4 次重试未果、
  无覆盖 chunk——待 11-03 夜链修复重试；verify-eod 超高优先级告警通路
  在值。
- `industry_mapping` 2026-11-02：3 只未解析证券（含 920085.BJ，BSE
  边界已知）致周刷失败，chunk PLANNED；现值覆盖至 10-30。
- 账本卫生：`stock_basic` 存在一条空 trade_date 历史 FAIL 行（11-03
  02:20 已以正常日期 SUCCESS 重取，5,920 行），建议随下次账本清理处置。

### 3.4 验收判定

#621 LIVE 建议门条款：核心链连续五交易日逐数据集 SLA 达标 ✓；窗口内
失败补偿闭环 ✓（2/2 收敛）；事件/低频源以实际披露事件样本另验 ✓；
受限项按覆盖合同记录、不宣称通过 ✓。**五日窗口判定通过**；fx/commodity/
macro 的修复后绿窗与 §3.3 两开放项按上述节奏滚动复验，不阻塞本票。

## 复测入口

```bash
# 备份配方（集成测试）
cd apps/backend && pytest tests/integration/operations/test_workstation_backup_recipe_integration.py -q
# LIVE 门矩阵（只读）
.venv/bin/python -m ditto_apps.scripts.data_live_gate \
  --database data/metadata/metadata.sqlite --start 2026-11-02 --end <滚动>
# 性能基线（只读）
.venv/bin/python -m ditto_apps.scripts.data_perf_baseline --data-root data
# 真实根演练（停写窗口内；备份目录必须不存在）
.venv/bin/python -m ditto_apps.scripts.workstation_backup_recipe backup \
  --data-root data --backup-dir <新目录>
.venv/bin/python -m ditto_apps.scripts.workstation_backup_recipe restore \
  --backup-dir <目录> --data-root <空隔离根>
.venv/bin/python -m ditto_apps.scripts.workstation_backup_recipe verify \
  --data-root <隔离根>
```
