"""Research strategy template catalog for the template-first authoring flow."""

from __future__ import annotations

from ditto_application.queries.strategy_templates import StrategyTemplateCatalogQuery


def test_catalog_lists_exactly_the_three_research_templates() -> None:
    entries = StrategyTemplateCatalogQuery().list_entries()

    assert [entry.template_id for entry in entries] == [
        "stock_selection",
        "etf_rotation",
        "etf_trend_swing",
    ]
    by_id = {entry.template_id: entry for entry in entries}
    assert by_id["stock_selection"].asset_class == "stock"
    assert by_id["etf_rotation"].asset_class == "etf"
    assert by_id["etf_trend_swing"].asset_class == "etf"
    # 人类可读名称（中文业务标签），不暴露内部模板字符串给 UI 自行翻译。
    assert by_id["stock_selection"].display_name == "股票多因子选股"
    assert by_id["etf_rotation"].display_name == "ETF 轮动"
    assert by_id["etf_trend_swing"].display_name == "ETF 趋势"


def test_catalog_entries_carry_runnable_defaults_and_param_constraints() -> None:
    entries = StrategyTemplateCatalogQuery().list_entries()

    for entry in entries:
        assert entry.universe
        assert entry.benchmark
        assert entry.default_frequency
        assert entry.required_datasets
        assert entry.param_constraints
        # 约束元数据完整：参数可由业务表单按 min/max/step/枚举校验。
        for constraint in entry.param_constraints:
            assert constraint["name"]
            assert constraint["dtype"] in {"bool", "int", "float", "str"}


def test_catalog_template_ids_match_strategy_spec_valid_templates() -> None:
    from ditto_strategy.alpha.specs import StrategySpec

    valid = StrategySpec._VALID_TEMPLATES
    entries = StrategyTemplateCatalogQuery().list_entries()

    assert {entry.template_id for entry in entries} <= valid
