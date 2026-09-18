# ADR: 数据源双源架构（Tushare 主源 + fuyao 冗余源）

> 日期：2026-09-17
> 状态：Accepted（决策票据 cosmos-arc/ditto#191；2026-09 数据源两轮调研后定稿）
> 范围：`ditto_data` 数据源子域、DQ 交叉对账、source fallback、预算纪律

## 背景

2026-09 数据源全景评审（覆盖 Tushare/AkShare/Baostock/同花顺 fuyao/iFinD/TDX 生态/指数公司官方/交易所披露/理杏仁等，两轮）后的核心事实：

- 原状态为单主源依赖（Tushare），source fallback policy 治理的是「未来多源」的框架而非现实冗余；Tushare 2025-08 曾停服近一周。
- 新出现的官方免费冗余通道：同花顺官方开源金融数据服务 fuyao（REST + api-key，全市场 10 年日 K Parquet 打包、复权因子事件流、三大报表、估值快照、特色数据、ETF 日 K，官方明示当前不限累计调用，无 SLA 承诺）。
- 平台约束：macOS/Linux（Windows 终端寄生型方案如 TdxQuant 排除）；预算 < 2000 元/年，纪律目标 1000 元/年。

## 决策

**双源：Tushare 10000 积分（1000 元/年）为主源 + fuyao（当前免费）为冗余/回填源。**

- 10000 积分档的直接原因：ETF 行情（fund_daily/fund_adj）需 8000 积分；ETF 为核心资产类别，行情主源必须是付费契约 + 原始价/因子形态，不用前复权快照型免费源兜底。
- Tushare 职责：日线 + 复权因子、财务三表（`f_ann_date`/`disclosure_date` 为唯一 PIT 披露锚）、估值日频、指数历史成分、申万行业、两融/龙虎榜/解禁/股东户数、ETF 日线/复权/份额、日历；加购席位（研报/公告/互动易）均在 Tushare 内，不引入新源。
- fuyao 职责：10 年日 K Parquet 一次性回填与对账、复权因子事件流交叉、财务数值交叉（披露日仍以 Tushare 为准）、ETF K 线对账（前复权、单次 1 只、最长 5 自然年——仅对账不作主源）、特色数据按缺启用、展示层 L1 快照。

## 明确排除

Baostock（不支持 ETF/基金）；TdxQuant（Windows 终端常驻）；TDX gpcw 审计通道（不留常设依赖）；理杏仁（估值分位由 daily_basic PIT 序列本地自算）；指数公司官方接口进管道（仅具体指数深度不足时定点补）；JQData（2026-08 起非大陆 IP 封锁）、RQData、TickFlow、必盈、共享 key 等灰色渠道；miniQMT/xtquant（2026-07 起停开清退，不入长期路线）。

## 挂起项与触发点

| 项 | 触发点 |
| --- | --- |
| Tushare 研报包（500 元/年）/ 公告 | 文本因子线（#202）启动时 |
| 历史分钟线（TDX 协议免费回溯 1–2 年 + 每日积累；深度不足时 Tushare 官方 2000 元/年） | R6 立项 |
| 盘中执行监控层（L1 快照轮询 + ETF IOPV + 成交时刻五档留档） | deviation 分析显示执行损耗显著 |
| ETF 实时 IOPV 付费 | 确认免费快照无 IOPV 且确有展示需求 |

## 不变量（红线）

1. 一切外部源先落地为本地不可变快照（source snapshot + knowledge date）再进查询。
2. 快照式/展示级数据永不进回测因子管道。
3. 只存原始价 + 复权因子事件流，复权价一律本地自算（qfq/hfq 快照非 PIT-safe）。
4. 财务披露日期唯一锚 = Tushare `f_ann_date`；fuyao 财务仅数值交叉。
5. 数据源年成本纪律上限 1000 元。

## 后果

- 数据源子域新增 fuyao（复制 TushareSource 适配器模式；`.importlinter` 数据源子域两两互斥契约同步扩展）。
- DQ cross_source 对账新增三项：日线值、复权因子事件流、财务报表值。
- 单主源风险消除；Tushare 故障日可降级拉 fuyao（source=auto 逐日选源）。
- **披露锚迁移项**：当前 Tushare fundamental 摄取只请求 `ann_date` 并映射为 `knowledge_date`（adapters/fundamental.py），与红线 4 的 `f_ann_date` 唯一锚尚不一致。落地时须迁移 adapter 字段为 `f_ann_date`，含 schema/存量回填与 future-sentinel 边界测试；迁移完成前现有 `ann_date` 锚继续生效，不得对外宣称已完成 `f_ann_date` 锚定。
