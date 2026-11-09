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
COVERAGE_MEASURED_AT = date(2026, 11, 7)

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
    "etf_dividend": "provider_anchor",
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
    """返回已保存的知识轴分类；纯元数据和无知识轴参考序列返回 None。"""
    return _KNOWLEDGE_AXES.get(dataset)


@dataclass(frozen=True)
class DatasetCoverageLimit:
    """单数据集覆盖限制（测量时点 2026-11-07，非实时）。"""

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
        measured_end="2026-11-06",
        gaps=(),
        notes="股票新补两条价格的复权因子已补齐;当前逐会话审计有价缺因子为 0。黄金集/版本边界沿用 #620,不将最新因子称当年所见。",
    ),
    "balance_sheet": DatasetCoverageLimit(
        dataset="balance_sheet",
        domain="fundamental",
        status="ready",
        measured_start="2011-12-31",
        measured_end="2026-09-30",
        gaps=(),
        notes="截至公告日可见的财务披露,保留 2011 起比较期;金额元,null 非零。公告切片不等于任意本地历史快照重放。",
    ),
    "calendar": DatasetCoverageLimit(
        dataset="calendar",
        domain="metadata",
        status="partial",
        measured_start="2013-01-01",
        measured_end="2027-12-31",
        gaps=(
            "北向/结算日历未独立取证,严格跨市场公开时间用途未获证明。",
            "本次业务验收窗截至11-05;另有11-06日级失败保留,不能据本票声明后续日更健康或当前全市场新鲜。",
        ),
        notes="SSE 交易日历覆盖目标窗及前后边界;不代表北向/结算日历。",
    ),
    "cash_flow": DatasetCoverageLimit(
        dataset="cash_flow",
        domain="fundamental",
        status="partial",
        measured_start="2011-12-31",
        measured_end="2026-09-30",
        gaps=(
            "旧失败窗口已逐次重取;当前重试结果/未闭合窗口见验收清单,不以总行数结案。",
            "本次业务验收窗截至11-05;另有11-06日级失败保留,不能据本票声明后续日更健康或当前全市场新鲜。",
        ),
        notes="现金流量表独立核验,金额元;旧失败分区不能借另外两表推定闭合,保留具体窗口复测。",
    ),
    "commodity_daily": DatasetCoverageLimit(
        dataset="commodity_daily",
        domain="macro",
        status="partial",
        measured_start="2013-12-31",
        measured_end="2026-11-05",
        gaps=(
            "Sina GC/SI 的 2014-01-01…2016-11-01 原生端点窗口为 0;端点为滚动深度参考序列。",
            "本次业务验收窗截至11-05;另有11-06日级失败保留,不能据本票声明后续日更健康或当前全市场新鲜。",
        ),
        notes=(
            "8/8 配置腿:FXCM 金银、Sina CL/GC/SI、FRED WTI/Brent/VIX"
            "。FRED 单值不伪造 OHLC,点号缺测过滤、负油价保留;Sina GC/SI 2016-11"
            "-02 起,此前 2014 窗实测空。仅展示参考,无连续合约回测。"
        ),
    ),
    "corporate_actions": DatasetCoverageLimit(
        dataset="corporate_actions",
        domain="capital",
        status="ready",
        measured_start="2007-05-23",
        measured_end="2034-01-20",
        gaps=(),
        notes="冻结用途为回购/解禁,rights 排除;计划日可到 2034 年,不代表已实施,PIT 由可知时间守。",
    ),
    "cyq_perf": DatasetCoverageLimit(
        dataset="cyq_perf",
        domain="capital",
        status="partial",
        measured_start="2018-01-02",
        measured_end="2026-11-06",
        gaps=(
            "当前官方文档称 2018-02-01 起；配置源保留快照实际覆盖 2018-01-02 起，2014–2017 未取得源数据。",
        ),
        notes="2018-01-02 为配置源实测起点（2026-10-10 快照），当前官方页面起点为 2018-02-01；成本分布指标，不是真实投资者完整仓位。",
    ),
    "dividend": DatasetCoverageLimit(
        dataset="dividend",
        domain="fundamental",
        status="ready",
        measured_start="2014-01-03",
        measured_end="2026-10-29",
        gaps=(),
        notes="公告/登记/除权/到账日期分开;未披露值不补零,修订与实施状态分开;保留此前可知比较值。",
    ),
    "etf_dividend": DatasetCoverageLimit(
        dataset="etf_dividend",
        domain="fundamental",
        status="empty",
        measured_start=None,
        measured_end=None,
        gaps=(
            "生产库尚未回补；2026-11-10 探针 tushare:fund_div 510300.SH 全历史 14 行可取，2014/2025 双窗口事实与发行人公告一致（docs/evidence/etf-cash-dividends-761.md）",
        ),
        notes="个人基金分配收入暂免所得税（财税〔2002〕128 号）；份额折算与收益转份额不属于本数据集；空响应与缺失公告区间区分，公告/实施公告取较晚为 knowledge_date。",
    ),
    "earnings_express": DatasetCoverageLimit(
        dataset="earnings_express",
        domain="fundamental",
        status="ready",
        measured_start="2014-01-04",
        measured_end="2026-11-06",
        gaps=(),
        notes="快报原始 audit_status 保留,不能一概称已审计;公告日与本机回填观察日分开。",
    ),
    "earnings_forecast": DatasetCoverageLimit(
        dataset="earnings_forecast",
        domain="fundamental",
        status="partial",
        measured_start="2014-01-01",
        measured_end="2026-10-30",
        gaps=(
            "2024-01-31 forecast_vip 重新取尽并摄取 2,209 行;knowledge_date 为本次观察日,不冒充当年可知。",
        ),
        notes="2014 起公告,利润上下界万元;2024-01-31 原分页失败经实测重取 2,209 行闭合;回填 knowledge_date 不伪装当年可知。",
    ),
    "etf_basic": DatasetCoverageLimit(
        dataset="etf_basic",
        domain="metadata",
        status="partial",
        measured_start=None,
        measured_end=None,
        gaps=(
            "21 个历史错误分类已纠正且保留审计分解;历史分类公开版本未证,仅当前分类观察。",
        ),
        notes=(
            "历史扩展表 1,868=1,847 ETF+21 联接/LOF。21 个 instrument."
            "asset_class 已按 fund_basic 与 etf_basic 排除证据纠正为 fu"
            "nd;初始 ETF 1,847,随后完整源目录增加 158076.SZ/158081.SZ 两只"
            ",当前 1,849、活跃 1,847;11-05 适用上市候选 1,848,158076 于 1"
            "1-06 上市,新增身份单独登记/补数且不改全公募名册。159908J.SZ/510680J.S"
            "H 按源 list_status=D 纠正活跃标志,两个历史身份仍计入分母且不推造退市日。旧 I"
            "D、映射、扩展和历史行情保留;当前分类纠错不声称历史分类版本。"
        ),
    ),
    "etf_daily": DatasetCoverageLimit(
        dataset="etf_daily",
        domain="market",
        status="partial",
        measured_start="2013-01-04",
        measured_end="2026-11-06",
        gaps=(
            "162,244 个会话在精确 fund_daily 请求中未返回;无 ETF 状态全集,源缺席不等于停牌。",
        ),
        notes=(
            "初始 1,847 加新2只共 1,849 ETF,11-05 上市范围 1,848;增量价格/因"
            "子逐值审计另列。4 个转型日误作首次上市日已按交易所原文纠正,上市前价异常清零。当前 162,2"
            "44 个缺价会话均与 fund_daily 原生请求精确匹配,源返回未补入为 0;无状态全集,源"
            "空不推断停牌。"
        ),
    ),
    "etf_nav": DatasetCoverageLimit(
        dataset="etf_nav",
        domain="market",
        status="partial",
        measured_start="2014-01-01",
        measured_end="2026-11-06",
        gaps=(
            "原 388 个累计/7 个单位请求窗已逐项重核,当前累计空值 277,850 条;精确区间见 refresh-nav-closeout-2026-11.md 及逐窗证据。",
            "本批未闭合窗口的 2026-08-11 前累计历史暂不支持;保留 277,850 条空值及后续目标,不据此生成累计收益、前填或以单位值替代。",
            "2026-08-11…10-28 的本批目标返回值已对拍,累计空值 0 条;后续缺值仍明确缺失,源响应缺席不冒称合法未披露或永不可得。",
            "公告版本与当前源修订分开;分页/同键变值失败保留 fail closed,不用当前读取授予严格历史用途。",
            "覆盖与新鲜度分别验收;历史失败尝试保留,本批不声明当日全市场新鲜或连续五日运行通过。",
        ),
        notes="正式 ETF 净值查询;本批完整保留原 395 个请求窗分母。七个单位窗口按基金成立日和 11 个市场完成窗口核销,源本次缺席仍明确缺失;不按交易所上市日删除有效基金净值。累计值为源 accum_nav 原值映射到 acc_nav,旧错误字段回执不冒充累计覆盖。维护者选择近期闭合、早期累计缺口对应历史暂不支持;剩余精确范围保留。application 保留累计 null;HTTP 仅展示单位净值并传播 partial 限制,不伪造收益基准。同标的同估值日保留不同 knowledge_date 观察,查询采用最新披露,不声称保存全部 vintage。",
    ),
    "etf_reference": DatasetCoverageLimit(
        dataset="etf_reference",
        domain="metadata",
        status="ready",
        measured_start="2013-01-04",
        measured_end="2026-11-06",
        gaps=(),
        notes="读取真实 source_snapshot_id 的候选参考观察;config 为声明变更时刷新,168 小时 SLA,不伪造历史 config。",
    ),
    "fina_indicator": DatasetCoverageLimit(
        dataset="fina_indicator",
        domain="fundamental",
        status="ready",
        measured_start="2012-03-31",
        measured_end="2026-09-30",
        gaps=(),
        notes="报告期、公告锚及财务指标原列透传;保留 2012 起比较期。旧跨年分区问题已修,不重复实施。",
    ),
    "fund_adj": DatasetCoverageLimit(
        dataset="fund_adj",
        domain="market",
        status="partial",
        measured_start="2013-01-04",
        measured_end="2026-11-06",
        gaps=(
            (
                "当前 ETF 有价缺因子残余 30 会话/3 码,fund_adj 同窗返回 0;原 21 个非"
                " ETF 身份的 19 旧会话另列,不要求 ETF 源补 LOF。"
            ),
        ),
        notes=(
            "ETF 后复权图表已实际消费;价格补齐后复测并逐项重取;当前 ETF 残余 30 会话属 512"
            "390.SH/560000.SH/560650.SH 原生零响应。21 个已纠正普通基金的旧因子"
            "缺口另列,缺因子仍 fail closed。"
        ),
    ),
    "fund_portfolio": DatasetCoverageLimit(
        dataset="fund_portfolio",
        domain="fundamental",
        status="partial",
        measured_start="2013-09-30",
        measured_end="2026-09-30",
        gaps=(
            "全持有人批量补数执行结果见 #708;未验证报告类型保持 unknown。",
            "原文对拍已证半年报/年报公告组缺前十股票;不支持要求完整持仓/全资产的消费。",
            "按需 T2 支持逐基金及合法公告日市场请求;后续须人工刷新,尚无自动全公募日更承诺。",
            "本次业务验收窗截至11-05;另有11-06日级失败保留,不能据本票声明后续日更健康或当前全市场新鲜。",
            (
                "历史失败台账保留;合法公告日市场请求已恢复,完成度绑定精确COMPLETE及载荷。11-06旧零"
                "观察未重取,不计本票截止窗覆盖;旧全窗待修订不由窗口并集伪造关闭。"
            ),
        ),
        notes=(
            "初始fund_basic 32,842;fresh32,893新增61/缺旧10,保守并集32,"
            "903独立持有人;有界逐基金或按公告日全市场摄取。持仓金额元、数量股、源比率百分比;null 非"
            "零。报告类型仅取原文哈希与精确持仓内容绑定,其他 unknown/disclosed_subse"
            "t;正文/摘要/显式修订分开。000001.OF 季报 10/10、半年报 67/77、年报 1"
            "22/132 对拍,均不称全资产。CLI 返回源观察快照,不声称可重放的冻结结果。 本次 329"
            "03/32903 持有人覆盖由初始32,842个核验的截至09-30逐基金前段和10-01至11"
            "-05全部36/36个公告日市场COMPLETE并集,加新增61个完整窗COMPLETE组成。前"
            "段有12423个逐基金零观察;市场缺席不称逐基金零响应。另有9764个精确逐基金末段窗独立对拍。"
            "新增61另有完整窗零响应COMPLETE,成立日未知或晚于截止日不推断其当时已成立。10-27用"
            "全部名册并集分片经逐值预审后正常重放。旧全窗因截止日截断保持待修订,不合成全窗快照;原请求范围不"
            "等于已核验覆盖。"
        ),
    ),
    "fund_share": DatasetCoverageLimit(
        dataset="fund_share",
        domain="market",
        status="partial",
        measured_start="2013-01-04",
        measured_end="2026-11-05",
        gaps=(
            "本次业务验收窗截至11-05;另有11-06日级失败保留,不能据本票声明后续日更健康或当前全市场新鲜。",
        ),
        notes=(
            "正式 ETF 份额研究;1849/1849 个标的已由核验后的历史回执及本次成功请求覆盖 201"
            "4-01-01…2026-11-05。同码窗绑定快照及载荷或源空观察,市场窗另按完整原生响应及入"
            "库值核验,允许成功窗口并集覆盖,原失败请求不改写。源披露不承诺逐交易日必有;净值公告锚与份额 T"
            "+1 派生分别保留。"
        ),
    ),
    "futures_basic": DatasetCoverageLimit(
        dataset="futures_basic",
        domain="market",
        status="ready",
        measured_start="1995-04-17",
        measured_end="2026-11-02",
        gaps=(),
        notes="11,363 唯一源身份中实际合约 11,100;目标窗适用 8,979。保留到期历史、挂牌/到期、乘数,连续/占位代码不混作真实合约分母。",
    ),
    "futures_daily": DatasetCoverageLimit(
        dataset="futures_daily",
        domain="market",
        status="partial",
        measured_start="2014-01-02",
        measured_end="2026-11-06",
        gaps=(
            "8 个 INE SCTAS 2020 合约完整挂牌窗 fut_daily 返回 0;精确代码/区间见 #708。",
        ),
        notes=(
            "六所实际合约,2014 或上市日起;8,979 应有合约中 8,971 有行情,8 个 INE "
            "SCTAS 在原生完整挂牌窗 fut_daily 实测空。结算/持仓单位按合约乘数,观察回填不授"
            "权历史策略;无主连拼接。"
        ),
    ),
    "fx_daily": DatasetCoverageLimit(
        dataset="fx_daily",
        domain="macro",
        status="ready",
        measured_start="2014-01-01",
        measured_end="2026-11-05",
        gaps=(),
        notes="6/6 汇率对;GMT 日线 bid 参考,缺值不补零;无历史发布时间与完整修订证据,不用于严格 PIT。",
    ),
    "global_index_daily": DatasetCoverageLimit(
        dataset="global_index_daily",
        domain="market",
        status="partial",
        measured_start="2014-01-01",
        measured_end="2026-11-06",
        gaps=(
            "RTS 的 2014–2019、IBOVESPA 的 2014–2026-07-02:index_global 原生请求返回 0。",
        ),
        notes=(
            "21/21 参考指数;RTS 2020-01-03 起,IBOVESPA 2026-07-03 "
            "起;对应此前窗口 index_global 实测空。HKTECH 2020-07-27 起。kn"
            "owledge_date 为回填观察,不授权严格历史策略。"
        ),
    ),
    "hk_hold": DatasetCoverageLimit(
        dataset="hk_hold",
        domain="capital",
        status="partial",
        measured_start="2016-06-29",
        measured_end="2026-09-30",
        gaps=("制度分段的公开日历与存量版本尚按 #706 整改,不能以现有旧行放行历史。",),
        notes="通道真实开通/源起点及 2024-08-19 制度分段;观察锚不能冒充季末当时可知。存量版本问题归 #706。",
    ),
    "hsgt_top10": DatasetCoverageLimit(
        dataset="hsgt_top10",
        domain="capital",
        status="partial",
        measured_start="2014-11-17",
        measured_end="2026-11-06",
        gaps=("旧 knowledge_date 与重复有效事实归 #706,修正前限制严格历史消费者。",),
        notes="互联互通活跃榜;制度后未披露买卖/净额保留 null;并存旧错误版本与重复有效事实的纠正归 #706。",
    ),
    "income_statement": DatasetCoverageLimit(
        dataset="income_statement",
        domain="fundamental",
        status="ready",
        measured_start="2011-12-31",
        measured_end="2026-09-30",
        gaps=(),
        notes="累计/单季及报表类型原样保留,金额元;同报告期不同公告日不自动等于修订。",
    ),
    "index_basic": DatasetCoverageLimit(
        dataset="index_basic",
        domain="metadata",
        status="ready",
        measured_start=None,
        measured_end=None,
        gaps=(),
        notes="目录 20,897 定义不作为分母;冻结 178 码均存在。当前源目录多出的 10 个申万码单列,不自动更改冻结集合。",
    ),
    "index_daily": DatasetCoverageLimit(
        dataset="index_daily",
        domain="market",
        status="partial",
        measured_start="2014-01-02",
        measured_end="2026-11-06",
        gaps=(
            "2014-06-01 为非交易日,当前入口正确跳过;旧 DQ 失败记录保留,不写成假成功。",
            "申万存量481557行已于2026-11-07授权纠正为手/千元并登记13个修正快照；169个旧载荷保留原单位，仅供溯源，不可视为已归一快照。",
        ),
        notes="冻结 178/178 代码有行情;价格/成交量展示,早于指数发布或源实际起点不回造。",
    ),
    "index_valuation": DatasetCoverageLimit(
        dataset="index_valuation",
        domain="capital",
        status="ready",
        measured_start="2014-01-02",
        measured_end="2026-11-06",
        gaps=(),
        notes="冻结 15 指数,市值元、估值倍数,2014 或真实起点;本机观察锚,非当年已知快照。",
    ),
    "index_weight": DatasetCoverageLimit(
        dataset="index_weight",
        domain="market",
        status="partial",
        measured_start="2014-01-30",
        measured_end="2026-10-30",
        gaps=(
            "23/23 指数十月权重已逐代码补齐;观察日不等于公告/生效时刻,严格历史用途不放行。",
        ),
        notes=(
            "冻结 23 指数;按单 index_code 取数。月度观察日不是公告或生效日;未知发布时刻不伪"
            "造。23/23 代码十月窗口已补齐并核对;不因今日名册回造成立前成员。"
        ),
    ),
    "industry_classification": DatasetCoverageLimit(
        dataset="industry_classification",
        domain="metadata",
        status="partial",
        measured_start=None,
        measured_end=None,
        gaps=("当前申万分类标签可读;定义表无历史发布时间轴,历史分类版本未获证明。",),
        notes="申万 31 个一级分类,CSRC 排除是冻结范围,不是此次新增缩域;定义版本与历史公开证据分开。",
    ),
    "industry_mapping": DatasetCoverageLimit(
        dataset="industry_mapping",
        domain="metadata",
        status="partial",
        measured_start="1984-05-09",
        measured_end="2026-10-28",
        gaps=("有效日期不等于公开日,无完整历史发布证据时仅受限研究。",),
        notes="申万有效区间用于研究分组,当前有效起止不证明历史公开;已有 11-02 覆盖修复保留,不重复实施。",
    ),
    "limit_list": DatasetCoverageLimit(
        dataset="limit_list",
        domain="market",
        status="partial",
        measured_start="2020-01-02",
        measured_end="2026-11-06",
        gaps=(
            "官方 2020 起且不含 ST 统计;ST 封板时间/炸板次数等细节不支持,股票整体分母保留 ST。",
        ),
        notes=(
            "limit_list_d 官方 2020 起且不统计 ST;未出现 ST 行不等于无事件。ST "
            "仍在正式股票池,需要的价格限幅事实取 stock_daily/stock_limit/st_hi"
            "story;封板细节缺失。"
        ),
    ),
    "macro_indicators": DatasetCoverageLimit(
        dataset="macro_indicators",
        domain="macro",
        status="partial",
        measured_start="2014-01-01",
        measured_end="2026-11-05",
        gaps=(
            (
                "部分高频系列大跨度 realtime_end-only 请求超过 2000 vintage 上限"
                ";支持已验证的当前/点时范围,未承诺全 vintage。"
            ),
            "例行刷新由 #707 验收;本票一次补齐不证明持续运行。",
        ),
        notes=(
            "51 FRED + 8 中国指标 + SHIBOR 共 60 序列;各自频率/单位保留。FRED"
            " 51 最新+51 点时 vintage 请求均成功;部分高频全 realtime 窗超过 20"
            "00 vintage 限制,非缺 realtime_start。中国 PMI 小写字段修复并补 "
            "2014 起;最新背景用途不要求全 vintage 仓库。"
        ),
    ),
    "margin_trading": DatasetCoverageLimit(
        dataset="margin_trading",
        domain="capital",
        status="partial",
        measured_start="2013-01-04",
        measured_end="2026-11-05",
        gaps=("迟发、错误旧版本与画像选版未由本票豁免;分别见 #706/#707。",),
        notes=(
            "沪深两融余额/融资买入额,元;T+1 上午发布,11-05 截面不因 EOD 零行视为完整。旧 "
            "knowledge_date 及画像选版归 #706,09:15 运行归 #707。"
        ),
    ),
    "moneyflow": DatasetCoverageLimit(
        dataset="moneyflow",
        domain="capital",
        status="partial",
        measured_start="2013-01-04",
        measured_end="2026-11-06",
        gaps=("完整历史版本与可知性未证,当前读通不授予严格历史用途。",),
        notes="沪深资金流展示,金额单位遵循字段合同;BSE 不扩域。未核验完整历史版本与可知性,不因查询成功放行严格历史。",
    ),
    "namechange": DatasetCoverageLimit(
        dataset="namechange",
        domain="metadata",
        status="ready",
        measured_start="2013-01-10",
        measured_end="2026-11-10",
        gaps=(),
        notes="更名公告、生效与观察截点分开,包含退市/旧码;未来生效日不提前使用,缺历史名不回退当前名称。",
    ),
    "pledge_ratio": DatasetCoverageLimit(
        dataset="pledge_ratio",
        domain="capital",
        status="partial",
        measured_start="2014-03-07",
        measured_end="2026-09-18",
        gaps=(
            "末端 2026-09-18;09-25 至 11-05 七次请求对应周快照均源空,不等同于事实无质押或永久停供。",
        ),
        notes="质押比例周频风险提示;库存末端 2026-09-18;之后七个请求日 pledge_stat 原生端点均返回零行,不能称当前新鲜。",
    ),
    "st_history": DatasetCoverageLimit(
        dataset="st_history",
        domain="market",
        status="ready",
        measured_start="2013-01-14",
        measured_end="2026-11-05",
        gaps=(),
        notes="ST 证据区间与 cutoff 传播;没有覆盖证据的标的返回未知,不用当前名称重建过去 ST。",
    ),
    "stock_basic": DatasetCoverageLimit(
        dataset="stock_basic",
        domain="metadata",
        status="partial",
        measured_start=None,
        measured_end=None,
        gaps=("3 个沪深历史代码缺上市日,未据行情推造。",),
        notes=(
            "正式沪深名册 5,571(含退市与旧码);BSE 359 保留但个股链范围外。600849.SH"
            " 旧码及 300060.SZ/002525.SZ 撤销发行保留身份并退出当前活跃池,不造日期;4"
            " 个错误 1970 上市日及 601313 首次上市日已按原文纠正;另 4 个变更代码的旧身份退"
            "出当前活跃池,仍保留完整历史分母。"
        ),
    ),
    "stock_daily": DatasetCoverageLimit(
        dataset="stock_daily",
        domain="market",
        status="partial",
        measured_start="2013-01-04",
        measured_end="2026-11-06",
        gaps=(
            "206,620 个非停牌缺价会话在精确 daily 请求中未返回;缺价不等于停牌或现实无成交,旧码区间单列。",
        ),
        notes=(
            "沪深全生命周期,2014 目标;当前 206,620 个非停牌缺价会话均与逐码 daily 原生"
            "请求精确匹配,未探测及源返回未补入均为 0。源缺价不证明现实无成交;停牌、退市、旧码和源缺席分别"
            "取证,BSE 存量单列保留。"
        ),
    ),
    "stock_limit": DatasetCoverageLimit(
        dataset="stock_limit",
        domain="market",
        status="ready",
        measured_start="2014-01-02",
        measured_end="2026-11-06",
        gaps=(),
        notes="元/股上下限事实;支持与日线/ST 证据合读,不由日线制造封板时间、炸板次数。特殊上市限幅以源事实为准。",
    ),
    "stock_status": DatasetCoverageLimit(
        dataset="stock_status",
        domain="market",
        status="partial",
        measured_start="2016-08-09",
        measured_end="2026-11-06",
        gaps=(
            "官方 2016 年前不覆盖;精确库存起点 2016-08-09。",
            (
                "剩余缺状态 8931 会话中,已探测 8931、源未返回 8931、源返回待补 0、未测 0;未"
                "测项保持未知。6 个时段空但正成交量会话在 suspend_d/daily 原生响应中同样并存,"
                "不放行严格交易消费者。"
            ),
            (
                "保留 24 个官方 2016 年源起点之前的拒绝与 25 个日期全市场源空失败;精确尝试和逐代码"
                "补证见 ledger-failure-dispositions.json。"
            ),
        ),
        notes=(
            "bak_basic 官方声明 2016 年起;本库存实测 2016-08-09 起,两者不可混写"
            "。停牌有价物理 1,845 项中 1,448 有盘中时段、391 为零成交量、6 项时段空但正成"
            "交量(两原生接口同样返回)。沪深正式异常 1,831 项,BSE 14 项另列;不从日线存在推断"
            "允许交易。 其中 6,100 个缺状态会话落在 4 个官方已换码身份的旧码停用区间;这是代码有效"
            "区间例外,不等于公司退市或停牌。"
        ),
    ),
    "top10_floatholders": DatasetCoverageLimit(
        dataset="top10_floatholders",
        domain="capital",
        status="ready",
        measured_start="2014-01-08",
        measured_end="2026-11-06",
        gaps=(),
        notes="独立的流通股股东榜;退出、送转和股份类别不得与总股东榜混用。",
    ),
    "top10_holders": DatasetCoverageLimit(
        dataset="top10_holders",
        domain="capital",
        status="ready",
        measured_start="2014-01-02",
        measured_end="2026-11-06",
        gaps=(),
        notes="公告锚十大股东披露;持股股数/比例与股类透传,名单退出不推造清仓,保留版本限制。",
    ),
    "top_inst": DatasetCoverageLimit(
        dataset="top_inst",
        domain="capital",
        status="ready",
        measured_start="2014-01-02",
        measured_end="2026-11-05",
        gaps=(),
        notes="机构席位披露,买卖单边 null/重复保留;席位金额不是整体资金仓位。",
    ),
    "top_list": DatasetCoverageLimit(
        dataset="top_list",
        domain="capital",
        status="ready",
        measured_start="2014-01-02",
        measured_end="2026-11-06",
        gaps=(),
        notes="沪深龙虎榜事件展示;无事件与抓取失败分开;当前夜链失败治理归 #707。",
    ),
    "valuation_metrics": DatasetCoverageLimit(
        dataset="valuation_metrics",
        domain="capital",
        status="ready",
        measured_start="2014-01-02",
        measured_end="2026-11-05",
        gaps=(),
        notes="估值画像,倍数/百分比/市值按字段合同;负值/null、分母与版本保真。",
    ),
}


def get_dataset_coverage(dataset: str) -> DatasetCoverageLimit | None:
    """返回单数据集覆盖限制；未注册数据集返回 None（调用方 fail-closed 处理）。"""
    return _DATASET_COVERAGE.get(dataset)


def list_dataset_coverage() -> tuple[DatasetCoverageLimit, ...]:
    """返回全部数据集覆盖限制（按 dataset 字典序）。"""
    return tuple(_DATASET_COVERAGE[dataset] for dataset in sorted(_DATASET_COVERAGE))
