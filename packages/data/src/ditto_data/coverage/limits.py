"""
数据集覆盖限制运行时真源（#622 测量证据的蒸馏，#628 接入消费）。

docs/data/coverage-contract.yaml 是测量真源；本模块是其运行时投影，
供 application/backend/Web 在 API、图表与导出中传播覆盖限制。
应用运行时**不读取** docs/（docs 不随应用分发）；同步由守卫测试
``tests/unit/coverage/test_limits_sync_unit.py`` 强制——YAML 刷新后
未同步蒸馏会在测试中响亮失败。刷新方法见 coverage-contract.md。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

__all__ = [
    "COVERAGE_MEASURED_AT",
    "KNOWLEDGE_AXIS_VOCABULARY",
    "DatasetCoverageLimit",
    "get_dataset_coverage",
    "get_knowledge_axis",
    "list_dataset_coverage",
]

# 覆盖合同测量时刻（coverage-contract.yaml meta.measured_at）
COVERAGE_MEASURED_AT = date(2026, 11, 3)

# 知识轴分类词汇表（pit-time-semantics.md §1.2 四类口径）：
# - provider_anchor: 供应商公告锚（kd=披露日；date 精度，日终语义）
# - derived_t1: 事实日 T+1 推导（日线族；bar 类另有日内发布时刻规则）
# - same_day: 即日可知（=trade_date）
# - observation: 观察日本身（无公告可知性，#452 类取舍——不宣称公告锚）
KNOWLEDGE_AXIS_VOCABULARY = frozenset(
    {"provider_anchor", "derived_t1", "same_day", "observation"}
)

_KNOWLEDGE_AXES: dict[str, str] = {
    # 披露锚（sparse_pit 披露锚族 + 事件披露/持仓披露 lane 的公告日锚）
    "balance_sheet": "provider_anchor",
    "income_statement": "provider_anchor",
    "cash_flow": "provider_anchor",
    "dividend": "provider_anchor",
    "corporate_actions": "provider_anchor",
    "fina_indicator": "provider_anchor",
    "fund_portfolio": "provider_anchor",
    "top10_holders": "provider_anchor",
    "top10_floatholders": "provider_anchor",
    "etf_nav": "provider_anchor",
    "hk_hold": "provider_anchor",
    "hsgt_top10": "provider_anchor",
    "top_list": "provider_anchor",
    "top_inst": "provider_anchor",
    "pledge_ratio": "provider_anchor",
    # T+1 推导（日线族；#625 margin 官方口径 T+1 上午 8:30 更新亦归此类）
    "stock_daily": "derived_t1",
    "etf_daily": "derived_t1",
    "index_daily": "derived_t1",
    "moneyflow": "derived_t1",
    "stock_limit": "derived_t1",
    "limit_list": "derived_t1",
    "fund_share": "derived_t1",
    "valuation_metrics": "derived_t1",
    "margin_trading": "derived_t1",
    "cyq_perf": "derived_t1",
    "commodity_daily": "derived_t1",
    "fx_daily": "derived_t1",
    "stock_status": "derived_t1",
    # 即日
    "adj_factor": "same_day",
    "fund_adj": "same_day",
    # 观察日（#452：官方无公告时刻，不伪造）
    "global_index_daily": "observation",
    "index_valuation": "observation",
    "futures_daily": "observation",
    "futures_basic": "observation",
    "earnings_forecast": "observation",
    "earnings_express": "observation",
    "index_weight": "observation",
    "macro_indicators": "observation",
    "fred_observation": "observation",
}


def get_knowledge_axis(dataset: str) -> str | None:
    """返回数据集知识轴分类；未分类（如纯元数据集）返回 None。"""
    return _KNOWLEDGE_AXES.get(dataset)


@dataclass(frozen=True)
class DatasetCoverageLimit:
    """单数据集覆盖限制（测量时点 2026-10-30，非实时）。"""

    dataset: str
    domain: str
    # ready=预期范围完整且当前 / partial=起点/末端/味道/品种有缺 / empty=本地零行
    status: str
    measured_start: str | None
    measured_end: str | None
    gaps: tuple[str, ...]
    notes: str | None


_DATASET_COVERAGE: dict[str, DatasetCoverageLimit] = {
    "adj_factor": DatasetCoverageLimit(
        dataset="adj_factor",
        domain="market",
        status="ready",
        measured_start="2013-01-04",
        measured_end="2026-10-29",
        gaps=(),
        notes="2013-01-04 起；fuyao dump 每日刷新(#617)；黄金集作用域=#620",
    ),
    "balance_sheet": DatasetCoverageLimit(
        dataset="balance_sheet",
        domain="fundamental",
        status="ready",
        measured_start="2011-12-31",
        measured_end="2026-09-30",
        gaps=(),
        notes="2011-12-31 起超目标，Q 报告期至 2026-09-30",
    ),
    "calendar": DatasetCoverageLimit(
        dataset="calendar",
        domain="metadata",
        status="ready",
        measured_start="2013-01-01",
        measured_end="2027-12-31",
        gaps=(),
        notes="实测 2013-01-01~2027-12-31 全量交易日历（覆盖回测与研究目标窗）",
    ),
    "cash_flow": DatasetCoverageLimit(
        dataset="cash_flow",
        domain="fundamental",
        status="ready",
        measured_start="2011-12-31",
        measured_end="2026-09-30",
        gaps=(),
        notes="2011-12-31 起；12 分区代理 EOF 留档（#196）；10-29 摄取 failed 待 P1",
    ),
    "commodity_daily": DatasetCoverageLimit(
        dataset="commodity_daily",
        domain="macro",
        status="partial",
        measured_start="2014-01-01",
        measured_end="2026-10-31",
        gaps=(
            "FRED 油/VIX 三品种腿「复合取数器内、运行时腿未配置」——R2 证据守卫下 tushare 车道不带 FRED 直连且无 fred 车道（#629 实测定界，接线需逐腿证据归属设计）",
            "新浪 GC/SI 2016-11-02 起（端点历史深度），CL 2014-01-01 起",
        ),
        notes="#629 回补：金属腿（FXCM XAU/XAG bid）2014 全覆盖、新浪连续参考三品种、FRED 腿未接线（同 FRED 48 系列口径）；三腿 trade_date_utc 统一 ms 无时区合同精度；窗口修复后 11-02 夜链 31 行/日落地（金属+新浪）；矩阵见 supporting-sources-verification.md",
    ),
    "corporate_actions": DatasetCoverageLimit(
        dataset="corporate_actions",
        domain="capital",
        status="partial",
        measured_start="2007-05-23",
        measured_end="2034-01-20",
        gaps=(
            "rights（分配预案）经代理 50101 不可达（#517-#523 降级裁决）；repurchase/share_float 可达",
        ),
        notes="2007-05-23 起 9.3 万行；含未来日期=预案计划日，PIT 由 knowledge_date 守",
    ),
    "cyq_perf": DatasetCoverageLimit(
        dataset="cyq_perf",
        domain="capital",
        status="partial",
        measured_start="2018-01-02",
        measured_end="2026-10-29",
        gaps=("官方数据起点 2018-01-02，2014~2017 源侧不可得",),
        notes="15000 积分档特色数据",
    ),
    "dividend": DatasetCoverageLimit(
        dataset="dividend",
        domain="fundamental",
        status="ready",
        measured_start="2014-02-12",
        measured_end="2026-10-28",
        gaps=(),
        notes="ex_date 2014-02-12 起；当日无除权事件=正常空",
    ),
    "earnings_express": DatasetCoverageLimit(
        dataset="earnings_express",
        domain="fundamental",
        status="ready",
        measured_start="2014-01-04",
        measured_end="2026-10-30",
        gaps=(),
        notes="#629 回补 2014-01-04 起 24,412 行全覆盖（回补期 11 个瞬态失败日已全部重试愈合）；快报为已审数口径浓缩披露，与正式三表非同一颗粒度",
    ),
    "earnings_forecast": DatasetCoverageLimit(
        dataset="earnings_forecast",
        domain="fundamental",
        status="partial",
        measured_start="2014-01-01",
        measured_end="2026-10-30",
        gaps=(
            "2024-01-31 单日不可得——forecast_vip 该高峰日经代理确定性 PaginationCorruptionError（直连探针实证，几何重试不收敛）；按 #640 语义季块保持可重试，修复通道可见",
        ),
        notes="#629 回补 2014-01-01 起 120,461 行；公告日驱动事件集，平日 0 行=正常无公告；上下界万元/单边可空/update_flag 独立版本口径见 supporting-sources-verification.md",
    ),
    "etf_basic": DatasetCoverageLimit(
        dataset="etf_basic",
        domain="metadata",
        status="ready",
        measured_start=None,
        measured_end=None,
        gaps=(),
        notes="",
    ),
    "etf_daily": DatasetCoverageLimit(
        dataset="etf_daily",
        domain="market",
        status="ready",
        measured_start="2013-01-04",
        measured_end="2026-10-29",
        gaps=(),
        notes="2013-01-04 起",
    ),
    "etf_nav": DatasetCoverageLimit(
        dataset="etf_nav",
        domain="market",
        status="partial",
        measured_start="2014-01-01",
        measured_end="2026-10-26",
        gaps=("末端 2026-10-26 后缺（10-29 摄取 failed 待 P1）",),
        notes="2014-01-01 起",
    ),
    "etf_reference": DatasetCoverageLimit(
        dataset="etf_reference",
        domain="metadata",
        status="partial",
        measured_start="2013-01-04",
        measured_end="2026-11-03",
        gaps=(
            "config 声明源已登记（#658 批次2，2026-11-03 config 快照 10 行）；夜链 tushare 恒 SOURCE_UNSUPPORTED 属设计，SLA 168h 随时间转 stale——声明变更时手动重摄取 config 源（一次性命令，无自动节奏）",
        ),
        notes="config 源声明式配置，#408 两阶段映射",
    ),
    "fina_indicator": DatasetCoverageLimit(
        dataset="fina_indicator",
        domain="fundamental",
        status="ready",
        measured_start="2012-03-31",
        measured_end="2026-09-30",
        gaps=(),
        notes="2012-03-31 起超目标；存量跨年错位 33,851 组已由 #620 修复（2026-10-27 --apply 分区修复，2026-11-03 复测 263,672 行/0 跨分区同键）；10-29 failed（无新报告期日失败语义待 P1；Q3 报告期数据完整）",
    ),
    "fund_adj": DatasetCoverageLimit(
        dataset="fund_adj",
        domain="market",
        status="ready",
        measured_start="2013-01-04",
        measured_end="2026-10-29",
        gaps=(),
        notes="2013-01-04 起",
    ),
    "fund_portfolio": DatasetCoverageLimit(
        dataset="fund_portfolio",
        domain="fundamental",
        status="partial",
        measured_start="2014-01-20",
        measured_end="2026-10-26",
        gaps=(
            "交易所上市基金子集边界（#627 量化定界非缺损）：单披露日 9,031 只公募中 ~97-100% 为 .OF 场外基金经写入层 FK 过滤不入库；扩域至公募全覆盖= 基金宇宙注册决策另票",
        ),
        notes="#627 量化定界：本地=交易所上市基金子集（ETF/LOF ~1,240 只≈单日 披露 9,031 只公募的 13.7%），非公募全覆盖；市场级 ann_date 响应 97-100% 为 .OF 场外基金，写入层 FK 过滤拒绝并 WARN 留痕。披露范围 分别标记：Q1/Q3 季报=前十大重仓、Q2/Q4 半年报/年报=全部持仓明细， 未披露≠零持仓；修订=同报告期多公告日版本行（kd=ann_date 分版本）。 P0 探针 period=2026 返回 0 的根因=参数形状（需完整季度末 YYYYMMDD）， #627 修正为 period=20141231 实测 ok。对拍与矩阵见 holdings-disclosure-verification.md",
    ),
    "fund_share": DatasetCoverageLimit(
        dataset="fund_share",
        domain="market",
        status="partial",
        measured_start="2013-01-04",
        measured_end="2026-10-30",
        gaps=(
            "ETF 无状态数据集，份额非逐日必有——87.9% 会话在场为观测口径（no_status_dataset 证据边界）",
            "源侧全量 ~1,807 行/日 vs 本地 ~1,714（LOF/非 ETF 名册标的 FK 过滤，#503 线裁决）",
        ),
        notes="2013-01-04 起 160 万行、逐年交易日全覆盖；#625 晚发布近窗重取治愈尾部（10-26..30 各 1,713-1,715 行）；对拍 3/3 一致",
    ),
    "futures_basic": DatasetCoverageLimit(
        dataset="futures_basic",
        domain="market",
        status="ready",
        measured_start="1995-04-17",
        measured_end="2026-10-28",
        gaps=(),
        notes="1995 起 34,057 行",
    ),
    "futures_daily": DatasetCoverageLimit(
        dataset="futures_daily",
        domain="market",
        status="partial",
        measured_start="2026-10-26",
        measured_end="2026-10-29",
        gaps=("仅 2026-10-26 起 4 日，历史未回补",),
        notes="fut_daily 源可达",
    ),
    "fx_daily": DatasetCoverageLimit(
        dataset="fx_daily",
        domain="macro",
        status="ready",
        measured_start="2014-01-01",
        measured_end="2026-10-31",
        gaps=(),
        notes="#629 回补 2014-01-01 起六对全覆盖；根因=GMT 日收盘 vs 北京当日单日请求恒空，7 日回看窗口修复（11-02 夜链首跑 36 行落地实证）；USDCNH 源端 2012-02-18 起（六对中最早起点最晚）；GMT 日 K/bid OHLC 口径见 supporting-sources-verification.md",
    ),
    "global_index_daily": DatasetCoverageLimit(
        dataset="global_index_daily",
        domain="market",
        status="ready",
        measured_start="2014-01-01",
        measured_end="2026-10-29",
        gaps=(),
        notes="2014-01-01 起；#619 拼接修复后 28/29 连续成功，旧故障不重立；品种口径核验属 P5a；instrument 列为 source_ticker（21 个）",
    ),
    "hk_hold": DatasetCoverageLimit(
        dataset="hk_hold",
        domain="capital",
        status="partial",
        measured_start="2016-06-29",
        measured_end="2026-09-30",
        gaps=(
            "历史可得性受限：源墙 2016-06-29（探针 2016-06-28 空），2014-11-17 沪港通上线至源墙间不可得=源端限制；2024-08-19 后非季末无北向披露 是制度性缺席（见 disclosure_segments），不计缺口；日频段另有源端 真空日 ~55 个交易日（逐日 SUCCESS/0 落账，含 2024-06-30 单日空洞 实证）",
        ),
        notes="#621「北向空源」修正：源非空，链路问题；#626 定根因=季度末帧 同股多北向持有者行撞存储主键（dq unique 整日拒绝），适配器确定性 收敛后季度末北向可入库；#626 回补 2016-06-29 起 4,224,382 行/4,227 标的（日频段+季度末段），平日 0 行=南向过滤+制度性缺席，对拍与 矩阵见 event-disclosure-verification.md",
    ),
    "hsgt_top10": DatasetCoverageLimit(
        dataset="hsgt_top10",
        domain="capital",
        status="ready",
        measured_start="2014-11-17",
        measured_end="2026-10-30",
        gaps=(),
        notes="#626 回补 2014-11-17 起 50,730 行/633 标的；源端历年共 130 个 交易日无披露（每年 5-16 天，逐日 SUCCESS/0 落账）非链路缺口；制度 分段见 disclosure_segments，对拍与矩阵见 event-disclosure-verification.md",
    ),
    "income_statement": DatasetCoverageLimit(
        dataset="income_statement",
        domain="fundamental",
        status="ready",
        measured_start="2011-12-31",
        measured_end="2026-09-30",
        gaps=(),
        notes="2011-12-31 起超目标（同 balance_sheet 家族口径）；本地库对 schema.sql 有漂移守卫拦截记录（XDG 陈旧库，非本库）",
    ),
    "index_basic": DatasetCoverageLimit(
        dataset="index_basic",
        domain="metadata",
        status="ready",
        measured_start=None,
        measured_end=None,
        gaps=(),
        notes="20,886 只含大量细分/海外指数定义",
    ),
    "index_daily": DatasetCoverageLimit(
        dataset="index_daily",
        domain="market",
        status="ready",
        measured_start="2014-01-02",
        measured_end="2026-10-29",
        gaps=(),
        notes="2014-01-02 起；178 只集合完整性逐指核验属 P2",
    ),
    "index_valuation": DatasetCoverageLimit(
        dataset="index_valuation",
        domain="capital",
        status="partial",
        measured_start="2026-10-26",
        measured_end="2026-10-29",
        gaps=("仅 2026-10-26 起 60 行×15 指数，历史未回补",),
        notes="",
    ),
    "index_weight": DatasetCoverageLimit(
        dataset="index_weight",
        domain="market",
        status="ready",
        measured_start="2014-01-30",
        measured_end="2026-09-30",
        gaps=(),
        notes="2014-01-30 起 191 万行；月度数据末端 2026-09-30（10 月未结束，正常）",
    ),
    "industry_classification": DatasetCoverageLimit(
        dataset="industry_classification",
        domain="metadata",
        status="partial",
        measured_start=None,
        measured_end=None,
        gaps=("csrc_industrial 2002 权限不足（SW 申万线可用）",),
        notes="申万 L1 28 分类（探针核实）+映射 7,919 行",
    ),
    "industry_mapping": DatasetCoverageLimit(
        dataset="industry_mapping",
        domain="metadata",
        status="ready",
        measured_start="1984-05-09",
        measured_end="2026-09-24",
        gaps=(),
        notes="as-of 语义=#452；周刷 cron 已建（#612）",
    ),
    "limit_list": DatasetCoverageLimit(
        dataset="limit_list",
        domain="market",
        status="partial",
        measured_start="2026-09-30",
        measured_end="2026-10-29",
        gaps=("仅 2026-09-30 起无历史回补",),
        notes="",
    ),
    "macro_indicators": DatasetCoverageLimit(
        dataset="macro_indicators",
        domain="macro",
        status="partial",
        measured_start="2015-01-01",
        measured_end="2026-09-01",
        gaps=(
            "月度数据末端 2026-09-01，10 月未更新；近期日链 failed 待 P1",
            "884 行×7 指标，FRED 系列覆盖完整性属 P5a",
        ),
        notes="tushare 全系+fred 探针可达；alfred:vintages=observations+realtime 参数",
    ),
    "margin_trading": DatasetCoverageLimit(
        dataset="margin_trading",
        domain="capital",
        status="partial",
        measured_start="2013-01-04",
        measured_end="2026-10-30",
        gaps=(
            "2026-10-30 深市部分行（2,017/4,486，沪市先到）——源侧 T+3（周五数据下周一上午更新）节奏，晚发布近窗重取自动收敛",
        ),
        notes="2013-01-04 起 3355/3355 交易日全覆盖、684 万行（#625 回补+通路修复）；列名语义修正 margin_buy_amount（原误标 volume，#390 破坏窗口）；月末披露含 null 余额为真实形态（not_null 收敛到业务键）；对拍 3/3 逐字段一致",
    ),
    "moneyflow": DatasetCoverageLimit(
        dataset="moneyflow",
        domain="capital",
        status="partial",
        measured_start="2013-01-04",
        measured_end="2026-10-30",
        gaps=(
            "BSE 2023-2026 ~20.5 万会话源端不覆盖（moneyflow 端点无北交所数据，#575 裁决 BSE 先不覆盖）",
            "stock_status 数据集空洞致 82,422 会话缺口无法归因（2021/2022 为主，P2 线既知边界）",
        ),
        notes="2013-01-04 起 1,256 万行（#196 回补 +",
    ),
    "namechange": DatasetCoverageLimit(
        dataset="namechange",
        domain="metadata",
        status="ready",
        measured_start="2013-01-10",
        measured_end="2026-10-29",
        gaps=(),
        notes="2013-01-10 起 3,538 行；窗口拼接=#619",
    ),
    "pledge_ratio": DatasetCoverageLimit(
        dataset="pledge_ratio",
        domain="capital",
        status="partial",
        measured_start="2014-03-07",
        measured_end="2026-09-18",
        gaps=("周更数据末端 2026-09-18，停更 6 周；10-27/10-29 摄取 failed 待 P1",),
        notes="2014-03-07 起 163 万行（#503 线回补后）",
    ),
    "st_history": DatasetCoverageLimit(
        dataset="st_history",
        domain="market",
        status="ready",
        measured_start="2013-01-14",
        measured_end="2026-10-20",
        gaps=(),
        notes="1,848 行区间语义",
    ),
    "stock_basic": DatasetCoverageLimit(
        dataset="stock_basic",
        domain="metadata",
        status="ready",
        measured_start=None,
        measured_end=None,
        gaps=(),
        notes="当前上市快照 5,928（含退市史在 instrument 表 28,678）",
    ),
    "stock_daily": DatasetCoverageLimit(
        dataset="stock_daily",
        domain="market",
        status="ready",
        measured_start="2013-01-04",
        measured_end="2026-10-29",
        gaps=(),
        notes="2013-01-04 起（超 2014 目标）；BSE 不覆盖=#575 裁决",
    ),
    "stock_limit": DatasetCoverageLimit(
        dataset="stock_limit",
        domain="market",
        status="ready",
        measured_start="2014-01-02",
        measured_end="2026-10-29",
        gaps=(),
        notes="2014-01-02 起；停牌日发行语义 #571",
    ),
    "stock_status": DatasetCoverageLimit(
        dataset="stock_status",
        domain="market",
        status="partial",
        measured_start="2016-08-09",
        measured_end="2026-10-29",
        gaps=(
            "起点 2016-08-09（bak_basic 官方可得起点），2014~2016-08 缺",
            "BSE 244 标的不覆盖（#575 裁决）",
        ),
        notes="bak_basic 当日终值 21:50 就绪（#583 实测）",
    ),
    "top10_floatholders": DatasetCoverageLimit(
        dataset="top10_floatholders",
        domain="capital",
        status="ready",
        measured_start="2014-01-08",
        measured_end="2026-10-31",
        gaps=(),
        notes="#627 新通路（Tushare doc 62）：字段同 top10_holders，名单口径= 流通股东榜——两榜同名行值可一致（2026-04-30 000002.SZ 实测），语义 不同各存一行不互推；不推导整体持仓。对拍与矩阵见 holdings-disclosure-verification.md",
    ),
    "top10_holders": DatasetCoverageLimit(
        dataset="top10_holders",
        domain="capital",
        status="ready",
        measured_start="2014-01-02",
        measured_end="2026-10-31",
        gaps=(),
        notes="#627 新通路（Tushare doc 61）：公告日驱动市场级 ann_date 单请求 日更+按标的报告期区间回填；主键 (标的, 报告期, 持有人名, 公告日)， kd=公告日，修订=新公告日版本行。跨期名单跌出≠清仓；hold_amount 股、 hold_ratio 占总股本 %、hold_change 0=不变 null=新进；送转使股数跳变 而比例持平，环比前须按公司行为调整。对拍与矩阵见 holdings-disclosure-verification.md",
    ),
    "top_inst": DatasetCoverageLimit(
        dataset="top_inst",
        domain="capital",
        status="ready",
        measured_start="2014-01-02",
        measured_end="2026-10-30",
        gaps=(),
        notes="席位不推导整体仓位——「机构专用」是多家机构共用席位名，席位 金额≠机构持仓（#621/#626 语义）；源墙远早于 2014（#626 探针 2013-01-04 已有 754 行），按 #621 2014 锚回补不承诺更早；同键 「机构专用」多行适配器确定性收敛（#482 先例，#626 下沉共用）； #626 回补 2014-01-02 起 2,343,110 行/5,787 标的，存量 2026-09-22+ 窗口已按新收敛规则 force 重拉收敛（F1b）；源端 buy/net 双侧 null 对称（席位单边披露），对拍零差异",
    ),
    "top_list": DatasetCoverageLimit(
        dataset="top_list",
        domain="capital",
        status="ready",
        measured_start="2014-01-02",
        measured_end="2026-10-30",
        gaps=(),
        notes="席位不推导整体仓位（#621 语义）；源墙远早于 2014（#626 探针 2010-01-04 已有行），按 #621 2014 锚回补不承诺更早；同 (标的, 日, 原因) 冗余多行适配器确定性收敛（#626）；#626 回补 2014-01-02 起 192,527 行/5,927 标的，逐年交易日全覆盖，可转债榜行（11x/12x 码） 身份过滤不入库——对拍与矩阵见 event-disclosure-verification.md",
    ),
    "valuation_metrics": DatasetCoverageLimit(
        dataset="valuation_metrics",
        domain="capital",
        status="ready",
        measured_start="2014-01-02",
        measured_end="2026-10-29",
        gaps=(),
        notes="2014-01-02 起 1,229 万行",
    ),
}


def get_dataset_coverage(dataset: str) -> DatasetCoverageLimit | None:
    """返回单数据集覆盖限制；未注册数据集返回 None（调用方 fail-closed 处理）。"""
    return _DATASET_COVERAGE.get(dataset)


def list_dataset_coverage() -> tuple[DatasetCoverageLimit, ...]:
    """返回全部数据集覆盖限制（按 dataset 字典序）。"""
    return tuple(_DATASET_COVERAGE[dataset] for dataset in sorted(_DATASET_COVERAGE))
