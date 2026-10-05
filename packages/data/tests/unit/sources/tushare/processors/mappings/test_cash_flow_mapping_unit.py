"""Tests for the cash-flow official field-name contract（#434 前置小修）.

官方 cashflow 端点字段为 n_cashflow_inv_act/n_cashflow_fnc_act（doc_id=44）；
旧拼写 n_cash_flows_* 会取不到值并把投资/净现金流置 null。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import polars as pl
from ditto_data.sources.tushare.adapters.fundamental import _CASH_FLOW_FIELDS
from ditto_data.sources.tushare.processors.mappings.capital import CASH_FLOW_MAPPING
from ditto_data.sources.tushare.processors.transformer import TushareDataTransformer


def test_request_fields_use_official_cashflow_names() -> None:
    assert "n_cashflow_inv_act" in _CASH_FLOW_FIELDS
    assert "n_cashflow_fnc_act" in _CASH_FLOW_FIELDS
    assert "n_cash_flows_inv_act" not in _CASH_FLOW_FIELDS
    assert "n_cash_flows_fnc_act" not in _CASH_FLOW_FIELDS


def test_official_field_names_survive_transform() -> None:
    """官方命名的投资现金流 -20 必须保留，不再被置 null（复审离线反例）。"""
    frame = pl.DataFrame(
        {
            "ts_code": ["600000.SH"],
            "end_date": ["20251231"],
            "f_ann_date": ["20260331"],
            "n_cashflow_act": [100.0],
            "n_cashflow_inv_act": [-20.0],
            "n_cashflow_fnc_act": [-10.0],
        }
    )
    metrics = SimpleNamespace(data_records=SimpleNamespace(add=lambda *a, **k: None))
    with patch("ditto_data.sources.tushare.processors.transformer.Metrics", metrics):
        result = TushareDataTransformer.transform(frame, "cash_flow", CASH_FLOW_MAPPING)

    row = result.to_dicts()[0]
    assert row["operating_cash_flow"] == 100.0
    assert row["investing_cash_flow"] == -20.0
    assert row["financing_cash_flow"] == -10.0
    assert row["net_cash_flow"] == 70.0


def test_decorative_dead_fields_dropped_from_output() -> None:
    """官方端点已无同名字段且无消费者的三个装饰字段不再出现在输出。"""
    for column in ("depreciation", "interest_paid", "tax_paid"):
        assert column not in CASH_FLOW_MAPPING.output_columns
        assert column not in CASH_FLOW_MAPPING.float_columns
