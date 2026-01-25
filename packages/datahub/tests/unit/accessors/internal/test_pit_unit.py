"""PIT 纯函数模块单元测试。"""

from datetime import date

import polars as pl
from ditto_datahub.accessors.internal.pit import (
    filter_by_knowledge_date,
    parse_asof_date,
)


def test_parse_asof_date_from_string():
    """测试从字符串解析日期。"""
    result = parse_asof_date("2024-01-15")
    assert result == date(2024, 1, 15)


def test_parse_asof_date_from_date():
    """测试从 date 对象返回。"""
    input_date = date(2024, 1, 15)
    result = parse_asof_date(input_date)
    assert result == input_date


def test_filter_by_knowledge_date():
    """测试根据 knowledge_date 过滤。"""
    df = pl.DataFrame(
        {
            "sid": [1, 1, 1],
            "knowledge_date": [
                date(2024, 1, 1),
                date(2024, 1, 15),
                date(2024, 2, 1),
            ],
            "value": [10, 20, 30],
        }
    )

    result = filter_by_knowledge_date(df, date(2024, 1, 20))

    assert len(result) == 2
    assert result["value"].to_list() == [10, 20]


def test_filter_by_knowledge_date_fallback_to_trade_date():
    """测试缺少 knowledge_date 时回退到 trade_date。"""
    df = pl.DataFrame(
        {
            "sid": [1, 1],
            "trade_date": [date(2024, 1, 1), date(2024, 1, 15)],
            "value": [10, 20],
        }
    )

    result = filter_by_knowledge_date(df, date(2024, 1, 10))

    # 验证回退到 trade_date 的过滤功能正常
    assert len(result) == 1
    assert result["value"].to_list() == [10]
    # 注意：由于 xdist 兼容性问题，这里不测试日志输出
