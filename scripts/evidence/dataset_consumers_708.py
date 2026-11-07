"""Read-only business-consumer evidence for the frozen November 2026 scope.

Run with explicit DITTO_STATE_ROOT, DITTO_CONFIG_ROOT and DITTO_CACHE_ROOT.
The dates below deliberately match #708's frozen acceptance window. Output
includes business values and the coverage restrictions consumed with them.
Experimental opt-in verifies reachability; it never grants production/PIT use.
"""

import argparse
from contextlib import closing
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import orjson
import polars as pl
from ditto_application.config.queries import get_all_datasets
from ditto_application.processes.execution.classification_snapshot import (
    build_classification_snapshot_fn,
)
from ditto_application.queries.capital import CapitalQueryFacade
from ditto_application.queries.catalog import CatalogQueryFacade
from ditto_application.queries.commodity import CommodityQueryFacade
from ditto_application.queries.dataset_coverage import DatasetCoverageQueryFacade
from ditto_application.queries.fundamental import FundamentalQueryFacade
from ditto_application.queries.futures import FuturesQueryFacade
from ditto_application.queries.fx import FXQueryFacade
from ditto_application.queries.macro import MacroQueryFacade
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_apps.registry.container import make_app_container
from ditto_data.services.metadata_service import MetadataService
from ditto_kernel.identity import InstrumentId

parser = argparse.ArgumentParser(
    description="Read all 47 frozen dataset consumers against explicit DITTO roots."
)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
p = args.output
p.parent.mkdir(parents=True, exist_ok=True)
out = {"started_at": datetime.now(UTC).isoformat(), "datasets": {}}
cutoff = "2026-11-06T03:30:00Z"
now = date(2026, 11, 6)
exp = {"allow_experimental_data": True}


def save():
    p.write_bytes(
        orjson.dumps(
            out, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS, default=str
        )
    )


with closing(make_app_container()) as c:
    market = c.get(MarketQueryFacade)
    meta = c.get(MetadataQueryFacade)
    capital = c.get(CapitalQueryFacade)
    fund = c.get(FundamentalQueryFacade)
    macro = c.get(MacroQueryFacade)
    futures = c.get(FuturesQueryFacade)
    commodity = c.get(CommodityQueryFacade)
    fx = c.get(FXQueryFacade)
    catalog = c.get(CatalogQueryFacade)
    assets = catalog.list_assets()

    def record(ds, purpose, fn, semantics="latest_available"):
        r = {
            "measured_at": datetime.now(UTC).isoformat(),
            "purpose": purpose,
            "read_semantics": semantics,
            "coverage": asdict(DatasetCoverageQueryFacade().get(ds)),
        }
        try:
            value = fn()
            if isinstance(value, pl.DataFrame):
                if (
                    ds == "industry_mapping"
                    and not value["sector_id"].drop_nulls().len()
                ):
                    raise RuntimeError("industry grouping requires a known sector_id")
                r.update(
                    rows=value.height,
                    fields=value.columns,
                    business_values=value.tail(3).to_dicts(),
                    empty=value.is_empty(),
                )
            elif isinstance(value, list):
                r.update(
                    rows=len(value),
                    business_values=[
                        asdict(x) if is_dataclass(x) else x for x in value[:3]
                    ],
                    empty=not value,
                )
            elif isinstance(value, dict):
                r.update(
                    rows=len(value),
                    business_values=dict(list(value.items())[:3]),
                    empty=not value,
                )
            else:
                r.update(business_values=value, empty=value is None)
            r["status"] = "read" if not r["empty"] else "empty"
        except Exception as e:
            r.update(status="failed", error=type(e).__name__, message=str(e))
        out["datasets"][ds] = r
        save()
        print(ds, r["status"], r.get("rows"), r.get("message", ""), flush=True)

    allstocks = meta.find_securities(asset_class="stock", is_active=None)
    stockids = allstocks["instrument_id"].unique().to_list()

    def iid(code, asset):
        return int(
            meta.find_securities(
                source_tickers=[code], asset_class=asset, is_active=None
            )["instrument_id"][0]
        )

    stock = iid("000001.SZ", "stock")
    etf = iid("510300.SH", "etf")
    index = iid("000300.SH", "index")
    record(
        "calendar",
        "下一会话与自然日/交易日区分",
        lambda: meta.list_calendar_range(
            start="2026-11-01", end="2026-11-10", only_open=False
        ),
    )
    for ds, asset in [
        ("stock_basic", "stock"),
        ("etf_basic", "etf"),
        ("index_basic", "index"),
    ]:
        record(
            ds,
            "标的代码/交易所/生命周期识别",
            lambda asset=asset: meta.find_securities(asset_class=asset, is_active=None),
        )
    for ds, asset, idv in [
        ("stock_daily", "stock", stock),
        ("etf_daily", "etf", etf),
        ("index_daily", "index", index),
    ]:
        record(
            ds,
            "当前价格序列及成交量展示",
            lambda asset=asset, idv=idv: market.find_bars(
                instrument_ids=[idv],
                asset_class=asset,
                start="2026-10-01",
                end="2026-11-05",
                **exp,
            ),
        )
    record(
        "global_index_daily",
        "21全球指数展示参考,禁止策略输入",
        lambda: market.get_global_index_bars("2026-10-01", "2026-11-05", **exp),
    )
    record(
        "stock_status",
        "辨别停牌、ST与正常交易会话",
        lambda: market.get_stock_status(start="2026-11-04", end="2026-11-05", **exp),
    )
    record(
        "adj_factor",
        "复权价格因子,保留观察版本",
        lambda: market.get_adj_factors(start="2026-11-04", end="2026-11-05", **exp),
    )
    record(
        "fund_adj",
        "ETF后复权图表的因子消费",
        lambda: market.find_bars(
            instrument_ids=[etf],
            asset_class="etf",
            adj="hfq",
            start="2026-10-01",
            end="2026-11-05",
            **exp,
        ),
    )
    record(
        "etf_nav",
        "ETF单位及累计净值展示,不伪造收益基准",
        lambda: market.get_etf_nav(
            instrument_id=etf, start="2026-10-01", end="2026-11-05"
        ),
    )
    record(
        "stock_limit",
        "个股法定上下限价格,非封板时间",
        lambda: market.get_stock_limits(start="2026-11-04", end="2026-11-05", **exp),
    )
    record(
        "limit_list",
        "披露涨跌停事件与炸板等原生字段,ST缺席未知",
        lambda: market.get_limit_list("2026-11-04", "2026-11-05", **exp),
    )
    record(
        "fund_share",
        "ETF份额变化研究,万份,缺席不补零",
        lambda: market.get_fund_share("2026-10-30", "2026-11-05", **exp),
    )
    for ds, method in [
        ("moneyflow", "get_moneyflow"),
        ("top_list", "get_top_list"),
        ("top_inst", "get_top_inst"),
        ("hk_hold", "get_hk_hold"),
        ("top10_holders", "get_top10_holders"),
        ("top10_floatholders", "get_top10_floatholders"),
    ]:
        record(
            ds,
            "个股资金/披露事实展示,不推导整体持仓",
            lambda method=method: getattr(capital, method)(
                iid("000002.SZ", "stock")
                if method in ("get_top_list", "get_top_inst")
                else stock,
                "2014-01-01",
                "2026-11-05",
                **exp,
            ),
        )
    record(
        "cyq_perf",
        "成本分布/胜率源指标,非真实投资者完整持仓",
        lambda: capital.get_cyq_perfs(start="2026-11-04", end="2026-11-05", **exp),
    )
    record(
        "hsgt_top10",
        "互联互通活跃榜披露",
        lambda: capital.get_hsgt_top10s("2026-11-01", "2026-11-05", **exp),
    )
    record(
        "margin_trading",
        "融资融券余额与买入额展示",
        lambda: capital.get_margin_trading_range(
            stock, "2026-10-01", "2026-11-05", as_of_date=now, **exp
        ),
    )
    record(
        "valuation_metrics",
        "个股估值画像",
        lambda: capital.get_valuation_metrics(stock, now, **exp),
    )
    record(
        "pledge_ratio",
        "质押比例风险提示",
        lambda: capital.get_pledge_ratio(stock, now, **exp),
    )
    record(
        "index_valuation",
        "指数PE/PB及元计市值展示",
        lambda: capital.get_index_valuation(index, "2026-10-01", "2026-11-05", **exp),
    )
    for ds, method in [
        ("balance_sheet", "get_balance_sheet"),
        ("income_statement", "get_income_statement"),
        ("cash_flow", "get_cash_flow"),
        ("dividend", "get_dividend"),
    ]:
        record(
            ds,
            "截至公告日可见的个股财务披露",
            lambda method=method: getattr(fund, method)(stock, now, **exp),
            "announcement_cutoff_latest_storage",
        )
    record(
        "corporate_actions",
        "回购和解禁事件核对,计划日不等于已实施",
        lambda: fund.list_corporate_actions(
            stock, date(2014, 1, 1), now, as_of_date=now, **exp
        ),
    )
    record(
        "fina_indicator",
        "报告期财务指标研究",
        lambda: fund.get_fina_indicator(
            stock, "2026-01-01", "2026-11-05", "2026-11-06", **exp
        ),
    )
    for ds, method in [
        ("earnings_forecast", "get_earnings_forecast"),
        ("earnings_express", "get_earnings_express"),
    ]:
        record(
            ds,
            "预告/快报与正式财报分开展示",
            lambda method=method: getattr(fund, method)(
                "000001.SZ", "2014-01-01", "2026-11-05", **exp
            ),
        )
    record(
        "fund_portfolio",
        "公募已披露股票持仓与原文类型,非全资产",
        lambda: fund.get_fund_portfolio(
            "000001.OF", "2025-01-01", "2026-11-05", "2026-11-06", **exp
        ),
        "disclosure_observations",
    )
    record(
        "macro_indicators",
        "按频率/单位展示最新宏观背景值,非历史可知性",
        lambda: macro.find_indicators(start="2026-01-01", end="2026-11-05", **exp),
    )
    record(
        "fx_daily",
        "六汇率对GMT日线买价参考",
        lambda: fx.list_bars(
            instrument_ids=fx.get_all_instrument_ids(),
            start="2026-10-01",
            end="2026-11-05",
        ),
    )
    record(
        "commodity_daily",
        "八条商品参考腿;FRED单值与金属/连续期货分开",
        lambda: commodity.list_bars(
            instrument_ids=commodity.get_all_instrument_ids(),
            start="2026-10-01",
            end="2026-11-05",
        ),
    )
    record(
        "index_weight",
        "最新观察指数成分权重,非历史生效证明",
        lambda: market.get_index_weights(
            index_id="000300.SH", as_of_date="2026-11-06", **exp
        ),
    )
    record(
        "industry_classification",
        "申万一级行业分类标签",
        meta.list_industries,
    )
    record(
        "industry_mapping",
        "行业截面研究分组",
        lambda: build_classification_snapshot_fn(c.get(MetadataService).instrument)(
            [InstrumentId(stock)], now
        ),
    )
    record(
        "namechange",
        "历史名称与当前名分开识别",
        lambda: meta.get_stock_names(stockids, asof="2026-11-05", cutoff=cutoff),
        "observed_history_at_cutoff",
    )
    record(
        "st_history",
        "ST证据优先,未覆盖标的未知",
        lambda: meta.get_st_status(stockids, asof="2026-11-05", cutoff=cutoff),
        "observed_history_at_cutoff",
    )
    record(
        "futures_basic",
        "真实到期合约乘数、挂牌/到期日",
        lambda: futures.get_futures_contracts("SHFE", "RB", **exp),
    )
    record(
        "futures_daily",
        "真实RB合约价格、结算价及持仓量",
        lambda: futures.get_futures_daily(
            "2026-11-01", "2026-11-05", ["RB2701.SHF"], **exp
        ),
    )
    record(
        "etf_reference",
        "ETF候选对比与跟踪限制",
        lambda: meta.list_etf_candidates(
            asof="2026-11-05",
            cutoff=cutoff,
            source_snapshot_id=meta.list_etf_reference_snapshots(cutoff=cutoff)[-1],
        ),
    )
    out["catalog_assets"] = [asdict(a) for a in assets]
    out["finished_at"] = datetime.now(UTC).isoformat()
    save()

assert set(out["datasets"]) == {dataset.value for dataset in get_all_datasets()}
if any(row["status"] != "read" for row in out["datasets"].values()):
    raise SystemExit("one or more business consumers failed or returned no data")
