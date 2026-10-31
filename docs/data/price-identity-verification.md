# 价格与身份核验报告（#624 / 父规格 #621 P2）

实测时间：2026-10-31（数据至 2026-10-30 夜链之后）。覆盖 P2 五项范围：
原始日线/复权/状态/日历/历史证券池逐项核验、逐证券缺口归因、复权真实比较、
周月聚合一致性、原始价/复权/NAV 区分与时间身份传播。

复测入口：

```bash
DITTO_STATE_ROOT=<data root> DITTO_CONFIG_ROOT=<repo> DITTO_CACHE_ROOT=<cache> \
  python -m ditto_apps.cli.main ops audit-price-coverage \
    --start 2014-01-01 --end <最新交易日> --asset-class stock|etf [--json]
DITTO_* 同上 + FUYAO_API_KEY \
  python -m ditto_apps.cli.main ops reconcile <交易日> --dataset adj_factor
```

注意：`DITTO_CONFIG_ROOT` 必须指向**仓库根**（dq 规则解析为
`<config_root>/config/default/dq_rules`）。本次实测曾误指 `<repo>/config`，
复权对账因 cross_source 规则未加载而 `fields=()` → 不可比较失败——该事故
同时实证了「零数值对不可通过」的 fail-closed 语义。

## 能力交付（CODE）

- `ditto_data.quality.coverage_audit`：纯函数逐证券覆盖审计。期望会话 =
  名册生命周期 × 交易日历（#581 union+lifecycle 语义：退市证券保留
  is_active=False 行，上市前/退市后不构成缺口）；缺失会话归因到闭合词汇表
  `COVERAGE_GAP_KINDS`（失败/受限二分由守卫测试锁定穷尽）。ops 物理覆盖
  核验口径，非 PIT 消费查询——知识可见性由 snapshot readiness 与图表层负责。
- `PriceCoverageAuditService`（application）+ `ops audit-price-coverage`（CLI，
  失败退出码 1）；`MarketService.get_fund_adj` 补 fund_adj 读取口。
- 单测 43 项（data 33 + application 6 + CLI 4）覆盖停牌/退市/新上市反例、
  全部归因分支、词汇闭合与日历健全性。
- market_chart 集成测试补口 4 项（文件共 123 项全绿）：月线聚合数值、
  日/周/月跨周期一致性重建、未闭合月 partial 标记、ETF 禁复权拒绝。

## 真实运行结果（LIVE）

### 股票（2014-01-01 ~ 2026-10-30，窗口 3,117 个交易日）

| 维度 | 结果 |
| --- | --- |
| 日历 | ✓ 3,117 会话；重复 0、周末 0、缺年 0、年度会话数全部在界（2026 部分年 198） |
| 名册 | 5,929 只（含退市），5,843 只有期望会话 |
| 期望会话/在场 | 12,735,467 / 12,382,283 |
| 复权因子 | ✓ 12,458,550 个日线会话零缺因子（任一版本在场口径） |
| 停牌（可归因） | suspended 133,654——2014~2016 停牌潮与个股长期停牌 |
| 状态期前（证据边界） | pre_status_era 190,059（stock_status 官方起点 2016-08-09 之前） |
| 真缺口（失败） | status_trading_no_bar 10,201 + status_row_missing 19,270 |
| 异常（失败） | bar_before_list_date 76,267 + suspended_with_bar 1,838 |
| 名册缺陷 | master_list_date_missing 3；另 4 只 list_date=1970-01-01 占位 |

抽样归因：

- 退市保留反例 ✓：600145.SH（list 1999-09-23 / delist 2022-04-28 /
  is_active=0）保留在名册，退市日之后不再产生期望会话。
- 停牌反例 ✓：000002.SZ 2015-12-21 起连续缺失归因 pre_status_era（期前
  无状态证据）；2016-08-09 后同类缺失由状态行归因 suspended。
- list_date=1970-01-01 占位（301569.SZ/301660.SZ/001246.SZ/301716.SZ 等
  2023 年前后新股）把期望区间放大到全窗口，是 top 缺口的前四名
  （3,098~3,105 gap/只）。
- bar_before_list_date 76,267 行全部为 BSE 920 新码标的：主数据生命周期
  自北交所转换日起算，而日线含更早的新三板历史（#575/#592 线）。
- status_trading_no_bar 头部（002260/000670/000995 等）为长期停牌股：
  状态源行存在且 is_suspended=False，但日线缺席——状态源对长期停牌的
  表达失真。status_row_missing 头部（601313/000022/000043）为状态行
  本身缺失的长期停牌段。

### ETF（同窗口）

| 维度 | 结果 |
| --- | --- |
| 名册/期望会话 | 1,868 只；1,810,323 期望 / 1,599,604 在场（88.3%） |
| 缺口归因 | no_status_dataset 210,719——ETF 无状态数据集（market/etf/status
  目录为空、未注册摄取），全部非生命周期缺口诚实落证据边界，不冒充停牌可判 |
| 复权因子 | fund_adj 缺 92 个日线会话（消费者按 #514 fail-closed） |
| 异常 | bar_before_list_date 3,481（新旧代码转换形态） |
| 全窗缺口样本 | 161211.SZ、159908J.SZ、510680J.SH 等 3,116~3,117 全窗缺——
  LOF/场外与「J」旧代码残留（#517-#523 清存量待办） |

### 复权真实比较（2026-10-30，真实除权事件日）

```
主源行数: 5581
主侧=11 辅侧=11 匹配=11 主侧未匹配=0 辅侧未匹配=0 重复键=0
差异数=0 事件不可推导=0 字段比较数={'adjustment_ratio': 11}
对账结果: passed=True 比较=可比
```

比较数（分母）= 字段比较数 11/双侧 11，口径 = 当日因子变化 ∩ fuyao
除权事件（比例比较、黄金集对 adj_factor 旁路沿用 #620 裁决）。零交集
不可通过由两路实证：单测（`test_adj_factor_rule_wiring_unit.py` 零交集
not_comparable）与本次配置根错误事故（fields=() → 不可比较 → 失败）。

### 周月聚合一致性（TEST + LIVE）

- TEST：`test_market_chart_api_integration.py` 123 项全绿；新增月线数值、
  日/周/月重建一致性（周月 K 线可由同窗口日线逐项重建、月 close == 月内
  末周 close、会话计数守恒）、未闭合月 partial=True/完整月 False、ETF
  禁复权显式拒绝。
- LIVE：真实日线直接重建守恒——000001.SZ 198 日线 → 42 周/10 月，
  会话守恒 ✓；ETF 样本 144 → 31/8 ✓；2026-10 为天然未闭合月。

### 图表与导出的价格身份（TEST + 真实阻断发现）

契约与导出身份既有覆盖：`MarketChartResponse.adjustment` 回显 + 每 bar
`source_snapshot_ids/available_at/published_at/partial`；CSV 导出身份列
（as_of/snapshot_id/双 cutoff/adjustment/period/partial，#208-4）有
`chart-data.test.ts` 逐列断言。NAV 与价格通道分离：独立端点
`/market/etf-nav`（unit_nav/acc_nav 双口径），真实库 1,526,180 行、近一周
6,713 行（例 520790.SH 2026-10-27~29 unit_nav 0.7233/0.727/0.7098），
叠加线在图表层不与 K 线价格混淆。

**真实阻断（F1，已修复 #635，2026-10-31）**：曾出现于当前库——`/market/chart` 对任何窗口 fail-closed
（`retained chart calendar is unavailable at cutoff`）。根因：2026-10-08
bootstrap 的 14 个年度日历快照 payload 全部带次年首月
（如 2026 快照 payload 至 2027-01-31，request 界只声明至 2026-12-31），
`retained_calendar` 的越界校验（payload 行不得超出自身快照 request 界，
#308 引入）按设计拒绝。图表消费链因此整体不可用。修复（#635）：fetch 窗口改回自然年与
chunk 声明一致；16 个年度快照重拉（新快照 payload=request=自然年）；
10-08 批 14 个越界快照登记删除。复验：近窗/全年/跨年/数据起点边界
窗口全部恢复，真实数据三周期重建 52/52 OK（上方「周月聚合一致性」
的 LIVE 段自本修复起成立）。

**验收状态**：P2「图表/导出一致」条款中，导出身份列与价格身份字段由
既有测试验收；**图表在真实数据上的端到端一致性受 F1 阻断，待日历快照
重拉后复跑本节 LIVE 核验**（三周期重建的真实数据路径已由纯日线重建
与集成测试双线覆盖）。

## 发现清单与后续行动

| # | 发现 | 影响 | 建议 |
| --- | --- | --- | --- |
| F1 | 日历快照 payload 越自身 request 界（14/16 个） | Chart Cockpit 全窗口不可用 | **已修复 #635**（2026-10-31：窗口对齐+重拉+清旧登记，图表恢复） |
| F2 | list_date=1970-01-01 占位 4 只 + null 3 只 | 期望区间放大、伪缺口 | 立票：主数据修正（新股上市日回填） |
| F3 | BSE 920 新码日线早于生命周期 76,267 行 | 审计异常桶；语义未裁决 | 立票：#575 裁决边界内明确「新三板历史行情」处置（裁剪或扩展生命周期语义） |
| F4 | 长期停牌股状态表达失真（trading_no_bar 10,201 / row_missing 19,270） | 真缺口口径污染 | 立票：suspend_d 历史回补评估（源可得性先行） |
| F5 | ETF LOF/旧代码全窗缺 + fund_adj 缺 92 会话 | ETF 覆盖与复权消费者 | 并入 #517-#523 清存量待办；92 会话逐票核对 |
| F6 | suspended_with_bar 1,838（停牌声明却有日线） | 矛盾证据（报告不裁决，#507 C1 语义） | 随 F4 一并抽样核验 |

## 边界

- 本审计为 ops 物理覆盖核验：按业务键去重后判「任一版本在场」，
  不回答决策时点可见性（PIT）与修订选择——那由 snapshot readiness、
  图表层与快照重放负责。
- pre_status_era 与 no_status_dataset 是**证据边界**而非通过：停牌/退市/
  新上市三反例的判定能力在证据在场的范围内成立；期前窗口的状态归因
  不可得是 stock_status 官方起点（2016-08-09）的固有边界。
- 日历健全性检查是序列启发式（重复/周末/缺年/年度区间），不与交易所
  真值对拍；对拍由来源摄取与复权对账承担。
