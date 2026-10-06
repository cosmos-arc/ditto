"""#529：dq 规则引擎接线守卫——type_check 期望 dtype 与源帧契约一致.

写时门禁（run_write_quality_gate）检查的是 adapter 输出帧（instrument_id
富集之前）。本文件按各数据集摄取管线的权威 dtype 契约（ColumnMapping
经 TushareDataTransformer 空帧派生 / SourceSchema / adapter 内联 schema）
核对 dq_rules yml 的 type_check 期望，并守住 #529 的键语义裁决：
technical 键规则使用门禁帧真实键（source_ticker），fx_daily/commodity_daily
（帧原生 instrument_id）与 macro_indicators（indicator_code）除外。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
import yaml
from ditto_data.quality.checkers.technical import (
    TechnicalChecker,
    _dtype_base,
    _expected_dtype_base,
)
from ditto_data.quality.engine import QualityEngine
from ditto_data.quality.spec import DatasetRules, DQSpec
from ditto_data.sources.schemas import (
    FX_SOURCE_SCHEMA,
    MACRO_INDICATOR_SOURCE_SCHEMA,
)
from ditto_data.sources.schemas.commodity_schemas import COMMODITY_SOURCE_SCHEMA
from ditto_data.sources.tushare.adapters.capital_corporate import (
    _empty_corporate_actions,
)
from ditto_data.sources.tushare.processors.mappings import (
    ADJ_FACTOR_MAPPING,
    BALANCE_SHEET_MAPPING,
    CASH_FLOW_MAPPING,
    CYQ_PERF_MAPPING,
    DAILY_OHLCV_MAPPING,
    DIVIDEND_MAPPING,
    ETF_NAV_MAPPING,
    FINA_INDICATOR_MAPPING,
    FUND_ADJ_MAPPING,
    FUND_PORTFOLIO_MAPPING,
    FUND_SHARE_MAPPING,
    HK_HOLD_MAPPING,
    HSGT_TOP10_MAPPING,
    INCOME_STATEMENT_MAPPING,
    LIMIT_LIST_MAPPING,
    MARGIN_TRADING_MAPPING,
    MONEYFLOW_MAPPING,
    PLEDGE_RATIO_MAPPING,
    STOCK_LIMIT_MAPPING,
    TOP_INST_MAPPING,
    TOP_LIST_MAPPING,
    VALUATION_METRICS_MAPPING,
)
from ditto_data.sources.tushare.processors.transformer import TushareDataTransformer

# 帧原生携带 instrument_id 的数据集（adapter 内联 Int64 键）
_NATIVE_INSTRUMENT_DATASETS = frozenset({"fx_daily", "commodity_daily"})
# 已知不配置 type_check 的数据集（index_weight：weight dtype 随 API 推断漂移，
# #515 后仅 not_null/unique；若未来加 type_check 须先固化其帧契约）
_DATASETS_WITHOUT_TYPE_CHECK = frozenset({"index_weight"})


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config" / "default" / "dq_rules").is_dir():
            return parent
    raise AssertionError("repo root with config/default/dq_rules not found")


def _load_yml_specs() -> dict[str, DatasetRules]:
    specs: dict[str, DatasetRules] = {}
    for path in sorted(
        (_repo_root() / "config" / "default" / "dq_rules").glob("*.yml")
    ):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        specs[data["dataset"]] = DatasetRules(**data)
    return specs


def _mapping_schema(mapping, *, add_pit: bool = False) -> dict[str, pl.DataType]:
    """按 transformer 空帧路径派生映射权威 schema；PIT 内联列为适配器统一后置步.

    transformer 空帧对计算列的类型推断回退 String（多根表达式）或不可见
    （引用非输出声明列，如 etf_nav 的 nav_date）——按真实变换顺序（声明
    cast 列 + 计算列求值，均在 output 选择之前）在定型空帧上求值计算列
    表达式取真实 dtype（0 行求值仅定 dtype，不触数据）。
    """
    typed = TushareDataTransformer.transform(pl.DataFrame(), "wiring", mapping)
    schema = dict(typed.schema)
    if mapping.computed_columns:
        intermediate = dict(schema)
        for col in mapping.date_columns:
            intermediate.setdefault(col, pl.Date)
        for col in mapping.float_columns:
            intermediate.setdefault(col, pl.Float64)
        for col in mapping.int_columns:
            intermediate.setdefault(col, pl.Int64)
        for col in mapping.boolean_columns:
            intermediate.setdefault(col, pl.Boolean)
        evaluated = pl.DataFrame(schema=intermediate).select(
            [expr.alias(name) for name, expr in mapping.computed_columns.items()]
        )
        schema.update(dict(evaluated.schema))
    if add_pit:
        schema["effective_from"] = pl.Date
        schema["effective_to"] = pl.Date
    return schema


def _frame_dtype_table() -> dict[str, dict[str, pl.DataType]]:
    table: dict[str, dict[str, pl.DataType]] = {
        "adj_factor": _mapping_schema(ADJ_FACTOR_MAPPING),
        "fund_adj": _mapping_schema(FUND_ADJ_MAPPING),
        "etf_nav": _mapping_schema(ETF_NAV_MAPPING),
        "fund_share": _mapping_schema(FUND_SHARE_MAPPING),
        "stock_daily": _mapping_schema(DAILY_OHLCV_MAPPING),
        "etf_daily": _mapping_schema(DAILY_OHLCV_MAPPING),
        "index_daily": _mapping_schema(DAILY_OHLCV_MAPPING),
        "stock_limit": _mapping_schema(STOCK_LIMIT_MAPPING),
        "limit_list": _mapping_schema(LIMIT_LIST_MAPPING),
        "balance_sheet": _mapping_schema(BALANCE_SHEET_MAPPING, add_pit=True),
        "income_statement": _mapping_schema(INCOME_STATEMENT_MAPPING, add_pit=True),
        "cash_flow": _mapping_schema(CASH_FLOW_MAPPING, add_pit=True),
        "dividend": _mapping_schema(DIVIDEND_MAPPING, add_pit=True),
        "valuation_metrics": _mapping_schema(VALUATION_METRICS_MAPPING, add_pit=True),
        "margin_trading": _mapping_schema(MARGIN_TRADING_MAPPING, add_pit=True),
        "pledge_ratio": _mapping_schema(PLEDGE_RATIO_MAPPING, add_pit=True),
        "moneyflow": _mapping_schema(MONEYFLOW_MAPPING),
        "cyq_perf": _mapping_schema(CYQ_PERF_MAPPING),
        "hk_hold": _mapping_schema(HK_HOLD_MAPPING),
        "hsgt_top10": _mapping_schema(HSGT_TOP10_MAPPING),
        "top_list": _mapping_schema(TOP_LIST_MAPPING),
        "top_inst": _mapping_schema(TOP_INST_MAPPING),
        "fund_portfolio": _mapping_schema(FUND_PORTFOLIO_MAPPING),
        "corporate_actions": dict(_empty_corporate_actions().schema),
        "fx_daily": dict(FX_SOURCE_SCHEMA.schema),
        "commodity_daily": dict(COMMODITY_SOURCE_SCHEMA.schema),
        "macro_indicators": dict(MACRO_INDICATOR_SOURCE_SCHEMA.schema),
    }
    fina = _mapping_schema(FINA_INDICATOR_MAPPING)
    # 适配器契约：身份列（source_ticker/report_date/knowledge_date）外
    # 全部 cast Float64（fundamental._normalize_fina_numeric_columns）
    fina.update({"eps": pl.Float64, "roe": pl.Float64})
    table["fina_indicator"] = fina
    return table


def _type_check_columns(rules: DatasetRules) -> dict[str, str]:
    matched = [r for r in rules.technical if r.get("rule") == "type_check"]
    assert len(matched) <= 1, f"multiple type_check rules in {rules.dataset}"
    return dict(matched[0]["columns"]) if matched else {}


@pytest.mark.unit
class TestTypeCheckWiring:
    def test_expected_dtypes_match_source_frame_contract(self) -> None:
        """yml type_check 期望必须与摄取帧权威 dtype 契约逐列一致."""
        table = _frame_dtype_table()
        specs = _load_yml_specs()
        checked = 0
        for dataset, rules in specs.items():
            columns = _type_check_columns(rules)
            if not columns:
                assert dataset in _DATASETS_WITHOUT_TYPE_CHECK, (
                    f"{dataset} 无 type_check 须先登记或补规则"
                )
                continue
            assert dataset in table, f"{dataset} 缺帧契约接线 wiring 表"
            frame = table[dataset]
            for column, expected in columns.items():
                if column == "instrument_id" and dataset not in (
                    _NATIVE_INSTRUMENT_DATASETS
                ):
                    # 富集后注入列（Int64），门禁帧上 inert——期望记号必须是 int
                    assert _expected_dtype_base(expected) == "int", (
                        f"{dataset}.instrument_id 期望应为 int"
                    )
                    continue
                assert column in frame, f"{dataset}.{column} 不在摄取帧中"
                assert _dtype_base(str(frame[column])) == _expected_dtype_base(
                    expected
                ), f"{dataset}.{column}: 帧 {frame[column]} vs 期望 {expected}"
                checked += 1
        assert checked > 100  # 防接线表整体失效的哨兵

    def test_technical_key_rules_use_gate_frame_key(self) -> None:
        """#529 裁决守卫：键规则写门禁帧真实键，FK 死规则不得回流.

        - not_null/unique 引用 instrument_id 仅允许帧原生携带它的
          fx_daily/commodity_daily；其余数据集键为 source_ticker
          （或 macro_indicators 的 indicator_code）。
        - foreign_key instrument_id 为死配置（#513 裁决不接线
          reference_values；身份 FK 由写入器富集解析 + 存储 PK 承担），
          已全部删除，不得再写入 yml。
        """
        for dataset, rules in _load_yml_specs().items():
            for rule in rules.technical:
                assert rule.get("rule") != "foreign_key", (
                    f"{dataset} 含已裁决删除的 FK 死规则"
                )
                if rule.get("rule") not in {"not_null", "unique"}:
                    continue  # type_check 的 instrument_id 期望是留档的富集后契约
                columns = rule.get("columns") or []
                if dataset in _NATIVE_INSTRUMENT_DATASETS:
                    continue
                assert "instrument_id" not in columns, (
                    f"{dataset} 键规则引用富集前不存在的 instrument_id"
                )

    def test_stock_daily_type_check_fires_on_dtype_drift(self) -> None:
        """活规则证明（A 修复）：volume 以 Int64 而非 Float64 到帧 → ERROR 阻断."""
        rules = _load_yml_specs()["stock_daily"]
        engine = QualityEngine(config=DQSpec(datasets={"stock_daily": rules}))
        frame = pl.DataFrame(
            {
                "source_ticker": ["600519.SH"],
                "trade_date": [date(2026, 9, 30)],
                "open": [1700.0],
                "high": [1710.0],
                "low": [1695.0],
                "close": [1705.0],
                "volume": pl.Series([240000], dtype=pl.Int64),
                "amount": [4.1e8],
                "knowledge_date": [date(2026, 10, 1)],
                "pre_close": [1700.0],
                "pct_change": [0.29],
            }
        )
        result = engine.check(df=frame, dataset="stock_daily")
        assert not result.passed
        assert any(i.rule_name == "type_check" for i in result.issues)

    def test_stock_daily_unique_fires_on_duplicate_source_ticker(self) -> None:
        """活规则证明（B 落地）：重复 (source_ticker, trade_date) → ERROR 阻断."""
        rules = _load_yml_specs()["stock_daily"]
        engine = QualityEngine(config=DQSpec(datasets={"stock_daily": rules}))
        row = {
            "source_ticker": ["600519.SH", "600519.SH"],
            "trade_date": [date(2026, 9, 30)] * 2,
            "open": [1700.0, 1700.0],
            "high": [1710.0, 1710.0],
            "low": [1695.0, 1695.0],
            "close": [1705.0, 1705.0],
            "volume": [240000.0, 240000.0],
            "amount": [4.1e8, 4.1e8],
            "knowledge_date": [date(2026, 10, 1)] * 2,
            "pre_close": [1700.0, 1700.0],
            "pct_change": [0.29, 0.29],
        }
        result = engine.check(df=pl.DataFrame(row), dataset="stock_daily")
        assert not result.passed
        assert any(i.rule_name == "unique" for i in result.issues)

    def test_mapping_conformant_frame_passes(self) -> None:
        """契约一致帧过全量 technical 门禁（type_check 复活后的正确放行侧）."""
        rules = _load_yml_specs()["stock_daily"]
        engine = QualityEngine(config=DQSpec(datasets={"stock_daily": rules}))
        schema = _frame_dtype_table()["stock_daily"]
        frame = pl.DataFrame(
            {
                "source_ticker": ["600519.SH"],
                "trade_date": [date(2026, 9, 30)],
                "open": [1700.0],
                "high": [1710.0],
                "low": [1695.0],
                "close": [1705.0],
                "volume": [240000.0],
                "amount": [4.1e8],
                "knowledge_date": [date(2026, 10, 1)],
                "pre_close": [1700.0],
                "pct_change": [0.29],
            },
            schema=schema,
        )
        assert engine.check(df=frame, dataset="stock_daily").passed


@pytest.mark.unit
class TestTypeCheckMatchingSemantics:
    """_check_type 匹配语义（#529：键名 columns + 大小写无关基名匹配）."""

    def setup_method(self) -> None:
        self.checker = TechnicalChecker()

    def test_lowercase_tokens_match_polars_dtypes(self) -> None:
        df = pl.DataFrame(
            {
                "id": pl.Series([1], dtype=pl.Int64),
                "d": pl.Series([date(2026, 1, 1)], dtype=pl.Date),
                "v": pl.Series([1.5], dtype=pl.Float64),
                "s": pl.Series(["x"], dtype=pl.String),
            }
        )
        rule = {
            "rule": "type_check",
            "columns": {"id": "int", "d": "date", "v": "float", "s": "str"},
            "message": "mismatch",
        }
        assert self.checker.check(df, [rule]) == []

    def test_date_does_not_match_datetime(self) -> None:
        df = pl.DataFrame({"d": pl.Series([], dtype=pl.Datetime("us"))})
        rule = {"rule": "type_check", "columns": {"d": "date"}, "message": "mismatch"}
        issues = self.checker.check(df, [rule])
        assert len(issues) == 1
        assert issues[0].rule_name == "type_check"
        assert issues[0].severity.value == "error"

    def test_float_expectation_rejects_int_column(self) -> None:
        df = pl.DataFrame({"v": pl.Series([1], dtype=pl.Int64)})
        rule = {"rule": "type_check", "columns": {"v": "float"}, "message": "mismatch"}
        assert len(self.checker.check(df, [rule])) == 1

    def test_missing_column_still_skips(self) -> None:
        df = pl.DataFrame({"v": [1.5]})
        rule = {
            "rule": "type_check",
            "columns": {"instrument_id": "int", "v": "float"},
            "message": "mismatch",
        }
        assert self.checker.check(df, [rule]) == []
