"""Tests for CapitalTushareAdapter."""

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
import pytest_mock
from ditto_data.sources.tushare.adapters.capital import CapitalTushareAdapter


class TestCapitalTushareAdapterFetchValuationMetrics:
    """Tests for fetch_valuation_metrics method."""

    def test_fetch_valuation_metrics_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching valuation metrics returns valid DataFrame."""
        # Arrange - Mock Tushare API response (using actual API field names)
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20240101"],
                "pe": [10.5],
                "pb": [1.2],
                "ps": [2.3],
                "dv_ratio": [0.03],  # API returns dv_ratio, not dividend_yield
                "total_mv": [1000000000.0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_valuation_metrics(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "source_ticker" in result.columns
        assert "trade_date" in result.columns
        assert "pe_ratio" in result.columns
        assert "pb_ratio" in result.columns
        assert result["source_ticker"][0] == "000001.SZ"

    def test_fetch_valuation_metrics_empty_response_returns_empty_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """
        Test fetching valuation metrics with empty response returns empty
        DataFrame.
        """
        # Arrange
        mock_response = pl.DataFrame()

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_valuation_metrics(ts_code="000001.SZ")

        # Assert
        assert len(result) == 0
        assert "source_ticker" in result.columns


class TestCapitalTushareAdapterFetchDividend:
    """Tests for fetch_dividend method."""

    def test_fetch_dividend_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching dividend data returns valid DataFrame."""
        # Arrange - Mock Tushare API response (using actual API field names)
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ex_date": ["20240101"],
                "cash_div": [0.5],  # API returns cash_div
                "record_date": ["20240102"],
                "ann_date": ["20240101"],
                "div_proc": ["实施"],  # P015: 实施进度
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_dividend(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "source_ticker" in result.columns
        assert "ex_dividend_date" in result.columns
        assert "dividend_per_share" in result.columns
        assert "div_proc" in result.columns  # P015: 验证实施进度字段


class TestCapitalTushareAdapterFetchMarginTrading:
    """Tests for fetch_margin_trading method."""

    def test_fetch_margin_trading_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching margin trading data returns valid DataFrame."""
        # Arrange - Mock Tushare API response (using actual API field names)
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20240101"],
                "rzye": [100000.0],  # 融资余额
                "rzmre": [1000.0],  # 融资买入量
                "rqye": [50000.0],  # 融券余额
                "rqmcl": [500.0],  # 融券卖出量
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_margin_trading(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "source_ticker" in result.columns
        assert "margin_buy_balance" in result.columns
        assert "short_sell_balance" in result.columns


class TestCapitalTushareAdapterFetchPledgeRatio:
    """Tests for fetch_pledge_ratio method."""

    def test_fetch_pledge_ratio_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching pledge ratio data returns valid DataFrame."""
        # Arrange - Mock Tushare API response (using actual API field names)
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "end_date": ["20240101"],  # Required for date conversion
                "pledge_ratio": [5.5],
                "total_share": [10000000.0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_pledge_ratio(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "source_ticker" in result.columns
        assert "pledge_ratio" in result.columns
        assert "total_shares" in result.columns

    def test_fetch_pledge_ratio_forwards_report_date_as_end_date(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """report_date must reach the API as end_date (#512).

        此前 report_date 被静默丢弃，「按期拉取」退化为全表翻页且被
        单次 1000 行上限静默截断。
        """
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ", "000002.SZ"],
                "end_date": ["20240329", "20240329"],
                "pledge_ratio": [5.5, 1.2],
                "total_share": [10000000.0, 20000000.0],
            }
        )
        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        adapter = CapitalTushareAdapter(_client=mock_client)
        adapter.fetch_pledge_ratio(report_date="20240329")

        call_kwargs = mock_client.query.call_args.kwargs
        assert call_kwargs["api_name"] == "pledge_stat"
        assert call_kwargs["end_date"] == "20240329"

    def test_fetch_pledge_ratio_without_report_date_keeps_full_pull(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """按标的回填模式（无日期过滤）保持全历史语义，不受本修复影响."""
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "end_date": ["20240329"],
                "pledge_ratio": [5.5],
                "total_share": [10000000.0],
            }
        )
        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        adapter = CapitalTushareAdapter(_client=mock_client)
        adapter.fetch_pledge_ratio(ts_code="000001.SZ")

        call_kwargs = mock_client.query.call_args.kwargs
        assert "end_date" not in call_kwargs
        assert call_kwargs["ts_code"] == "000001.SZ"


class TestCapitalTushareAdapterFetchIndexComposition:
    """Tests for fetch_index_composition method."""

    def test_fetch_index_composition_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Latest composition keeps only current members (is_new boundary)."""
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ", "600000.SH"],
                "in_date": ["20200101", "20200101"],
                "out_date": ["", "20240614"],
                "is_new": [1, 0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_index_composition(index_code="000001.SH")

        assert result["source_ticker"].to_list() == ["000001.SZ"]
        assert "index_id" in result.columns
        assert "effective_from" in result.columns

    def test_fetch_index_composition_asof_keeps_removed_members_in_window(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Historical asof keeps old members inside their in/out window."""
        mock_response = pl.DataFrame(
            {
                "ts_code": [
                    "000001.SZ",
                    "600000.SH",
                    "000002.SZ",
                    "600036.SH",
                ],
                "in_date": ["20200101", "20200101", "20240617", "20200101"],
                "out_date": ["", "20240620", "", "20240601"],
                "is_new": [1, 0, 1, 0],
            }
        )
        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_index_composition("000300.SH", asof_date="2024-06-16")

        assert sorted(result["source_ticker"].to_list()) == ["000001.SZ", "600000.SH"]
        mock_client.query.assert_called_once_with(
            api_name="index_member",
            index_code="000300.SH",
            fields="ts_code,in_date,out_date,is_new",
        )

    def test_fetch_index_composition_with_weight_joins_on_source_ticker(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """with_weight uses the same ticker key as fetch_index_weight."""
        mock_client = mocker.Mock()
        mock_client.query.side_effect = [
            pl.DataFrame(
                {
                    "ts_code": ["000001.SZ", "600000.SH"],
                    "in_date": ["20200101", "20200101"],
                    "out_date": ["", ""],
                    "is_new": [1, 1],
                }
            ),
            pl.DataFrame(
                {
                    "index_code": ["000001.SZ", "600000.SH"],
                    "con_code": ["000001.SZ", "600000.SH"],
                    "trade_date": ["20241227", "20241227"],
                    "weight": [60.0, 40.0],
                }
            ),
        ]

        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_index_composition("000300.SH", with_weight=True)

        assert sorted(result["weight"].to_list()) == [40.0, 60.0]

    def test_fetch_index_weight_returns_observation_fact_rows(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Weights stay monthly observation facts; no fabricated effective dates."""
        mock_client = mocker.Mock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "index_code": ["000300.SH", "000300.SH"],
                "con_code": ["600000.SH", "600036.SH"],
                "trade_date": ["20241227", "20241227"],
                "weight": [60.0, 40.0],
            }
        )
        adapter = CapitalTushareAdapter(_client=mock_client)

        result = adapter.fetch_index_weight("000300.SH", "20241227")

        assert result.columns == [
            "index_code",
            "source_ticker",
            "trade_date",
            "weight",
        ]
        assert result["trade_date"].dtype == pl.Date
        assert result["trade_date"].to_list() == [
            date(2024, 12, 27),
            date(2024, 12, 27),
        ]
        assert "effective_from" not in result.columns
        assert "effective_to" not in result.columns

    def test_fetch_index_weight_supports_provider_date_range(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        mock_client = mocker.Mock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "index_code": ["000300.SH"],
                "con_code": ["600000.SH"],
                "trade_date": ["20241227"],
                "weight": [100.0],
            }
        )
        adapter = CapitalTushareAdapter(_client=mock_client)

        adapter.fetch_index_weight(
            "000300.SH",
            start_date="20240101",
            end_date="20241231",
        )

        mock_client.query.assert_called_once_with(
            api_name="index_weight",
            index_code="000300.SH",
            start_date="20240101",
            end_date="20241231",
            fields="index_code,con_code,trade_date,weight",
        )


class TestCapitalTushareAdapterFetchCorporateActions:
    """Tests for fetch_corporate_actions method."""

    def test_fetch_corporate_actions_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Normalize official repurchase and share-float endpoints together."""
        repurchase = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ann_date": ["20240101"],
                "end_date": ["20240115"],
                "proc": ["完成"],
                "exp_date": [None],
                "vol": [1_000_000.0],
                "amount": [10_000_000.0],
            }
        )
        share_float = pl.DataFrame(
            {
                "ts_code": ["000002.SZ"],
                "ann_date": ["20240102"],
                "float_date": ["20240120"],
                "float_share": [2_000_000.0],
                "float_ratio": [1.5],
                "holder_name": ["holder"],
                "share_type": ["首发原股东限售股份"],
            }
        )

        # #517：第三路 rights（配股）也并入公司行为组合；此处给空帧
        mock_client = mocker.Mock()
        mock_client.query.side_effect = [repurchase, share_float, pl.DataFrame()]

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_corporate_actions(
            start_date="20240101",
            end_date="20240331",
        )

        assert result["source_ticker"].to_list() == ["000001.SZ", "000002.SZ"]
        assert result["action_type"].to_list() == [
            "share_repurchase",
            "restricted_share_release",
        ]
        assert result["action_date"].to_list() == [
            date(2024, 1, 15),
            date(2024, 1, 20),
        ]
        assert result["knowledge_date"].to_list() == [
            date(2024, 1, 1),
            date(2024, 1, 2),
        ]
        assert result["effective_from"].to_list() == [
            date(2024, 1, 1),
            date(2024, 1, 2),
        ]
        assert result["effective_to"].to_list() == [None, None]
        assert result.columns == [
            "source_ticker",
            "action_type",
            "action_date",
            "knowledge_date",
            "effective_from",
            "effective_to",
            "description",
        ]
        api_names = [
            call.kwargs["api_name"] for call in mock_client.query.call_args_list
        ]
        assert api_names == [
            "repurchase",
            "share_float",
            "rights",
        ]

    def test_fetch_corporate_actions_fills_missing_provider_dates_without_lookahead(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Required event dates fall back only to dates observable on the row."""
        repurchase = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ann_date": ["20240101"],
                "end_date": [None],
                "proc": ["预案"],
                "exp_date": ["20240630"],
                "vol": [None],
                "amount": [None],
            }
        )
        share_float = pl.DataFrame(
            {
                "ts_code": ["000002.SZ"],
                "ann_date": [None],
                "float_date": ["20240120"],
                "float_share": [2_000_000.0],
                "float_ratio": [1.5],
                "holder_name": ["holder"],
                "share_type": ["股权分置限售股份"],
            }
        )
        mock_client = mocker.Mock()
        mock_client.query.side_effect = [repurchase, share_float, pl.DataFrame()]

        result = CapitalTushareAdapter(_client=mock_client).fetch_corporate_actions(
            start_date="20240101",
            end_date="20240331",
        )

        assert result["action_date"].to_list() == [
            date(2024, 1, 1),
            date(2024, 1, 20),
        ]
        assert result["knowledge_date"].to_list() == [
            date(2024, 1, 1),
            date(2024, 1, 20),
        ]
        assert result["effective_from"].to_list() == [
            date(2024, 1, 1),
            date(2024, 1, 20),
        ]
        assert result["effective_to"].to_list() == [None, None]

    def test_fetch_corporate_actions_exact_announcement_date_uses_documented_filter(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Both constituent APIs are bounded by the same exact knowledge date."""
        mock_client = mocker.Mock()
        mock_client.query.side_effect = [
            pl.DataFrame(),
            pl.DataFrame(),
            pl.DataFrame(),
        ]

        CapitalTushareAdapter(_client=mock_client).fetch_corporate_actions(
            ann_date="20240102"
        )

        assert [item.kwargs for item in mock_client.query.call_args_list] == [
            {
                "api_name": "repurchase",
                "fields": "ts_code,ann_date,end_date,proc,exp_date,vol,amount",
                "ann_date": "20240102",
            },
            {
                "api_name": "share_float",
                "fields": (
                    "ts_code,ann_date,float_date,float_share,float_ratio,"
                    "holder_name,share_type"
                ),
                "ann_date": "20240102",
            },
            {
                "api_name": "rights",
                "fields": (
                    "ts_code,rights_type,ann_date,reg_date,ex_date,"
                    "rights_price,rights_ratio"
                ),
                "ann_date": "20240102",
            },
        ]


class TestCapitalTushareAdapterFetchShareBuyback:
    """Tests for fetch_share_buyback method."""

    def test_fetch_share_buyback_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching share buyback data returns valid DataFrame."""
        # Arrange - Mock Tushare share_float API response
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ann_date": ["20240101"],
                "float_date": ["20240115"],
                "float_share": [50000000.0],
                "float_ratio": [2.5],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_share_buyback(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "source_ticker" in result.columns
        assert "announcement_date" in result.columns
        assert "effective_date" in result.columns
        assert "float_shares" in result.columns
        assert "float_ratio" in result.columns

    def test_fetch_share_buyback_empty_response(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching share buyback with empty response returns empty DataFrame."""
        # Arrange
        mock_response = pl.DataFrame()

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_share_buyback(ts_code="000001.SZ")

        # Assert
        assert len(result) == 0
        assert "source_ticker" in result.columns


class TestCapitalTushareAdapterFetchRightsIssue:
    """Tests for fetch_rights_issue method."""

    def test_fetch_rights_issue_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching rights issue data returns valid DataFrame."""
        # Arrange - Mock Tushare rights API response
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "rights_type": ["A"],
                "ann_date": ["20240101"],
                "reg_date": ["20240110"],
                "ex_date": ["20240111"],
                "rights_price": [5.0],
                "rights_ratio": [0.3],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_rights_issue(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "source_ticker" in result.columns
        assert "rights_type" in result.columns
        assert "announcement_date" in result.columns
        assert "record_date" in result.columns
        assert "ex_rights_date" in result.columns
        assert "rights_price" in result.columns
        assert "rights_ratio" in result.columns

    def test_fetch_rights_issue_empty_response(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching rights issue with empty response returns empty DataFrame."""
        # Arrange
        mock_response = pl.DataFrame()

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_rights_issue(ts_code="000001.SZ")

        # Assert
        assert len(result) == 0
        assert "source_ticker" in result.columns


class TestCorporateActionsRightsComposition:
    """#517：rights（配股）并入公司行为组合的归一锁定."""

    def test_rights_row_normalized_with_ex_date_anchor(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        repurchase = pl.DataFrame()
        share_float = pl.DataFrame()
        rights = pl.DataFrame(
            {
                "ts_code": ["600000.SH"],
                "rights_type": ["A"],
                "ann_date": ["20240101"],
                "reg_date": ["20240110"],
                "ex_date": ["20240115"],
                "rights_price": [5.0],
                "rights_ratio": [0.3],
            }
        )
        mock_client = mocker.Mock()
        mock_client.query.side_effect = [repurchase, share_float, rights]

        result = CapitalTushareAdapter(_client=mock_client).fetch_corporate_actions(
            ann_date="20240101"
        )

        assert result.height == 1
        row = result.row(0, named=True)
        assert row["source_ticker"] == "600000.SH"
        assert row["action_type"] == "rights_issue"
        # 行为日=除权日（真实生效锚），知识日=公告日
        assert row["action_date"] == date(2024, 1, 15)
        assert row["knowledge_date"] == date(2024, 1, 1)
        assert "rights_type=A" in row["description"]
        assert "rights_price=5.0" in row["description"]

    def test_rights_missing_ex_date_falls_back_to_reg_then_ann(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        rights = pl.DataFrame(
            {
                "ts_code": ["600000.SH"],
                "rights_type": ["A"],
                "ann_date": ["20240101"],
                "reg_date": [None],
                "ex_date": [None],
                "rights_price": [None],
                "rights_ratio": [None],
            }
        )
        mock_client = mocker.Mock()
        mock_client.query.side_effect = [pl.DataFrame(), pl.DataFrame(), rights]

        result = CapitalTushareAdapter(_client=mock_client).fetch_corporate_actions(
            ann_date="20240101"
        )

        row = result.row(0, named=True)
        # 除权/登记日缺失 → 回退公告日，不用未来日期冒充生效锚
        assert row["action_date"] == date(2024, 1, 1)
        assert "rights_price=unknown" in row["description"]


class TestCorporateActionsRightsTransportBoundary:
    """#517：代理未开通 rights 端点（50101）时组合降级留痕."""

    def test_rights_50101_degrades_to_two_legs(self, mocker) -> None:
        from ditto_data.errors import SourceFetchError
        from ditto_data.sources.tushare.adapters.capital_corporate import (
            CapitalCorporateTushareAdapter,
        )

        mock_client = mocker.Mock()
        mock_client.query.side_effect = [
            pl.DataFrame(),
            pl.DataFrame(),
            SourceFetchError(
                message="请指定正确的接口名",
                source="tushare",
                details={"code": 50101},
            ),
        ]
        result = CapitalCorporateTushareAdapter(
            _client=mock_client
        ).fetch_corporate_actions(ann_date="20260930")
        assert result.is_empty()
        assert mock_client.query.call_count == 3

    def test_rights_other_errors_still_fail_closed(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        from ditto_data.errors import SourceFetchError
        from ditto_data.sources.tushare.adapters.capital_corporate import (
            CapitalCorporateTushareAdapter,
        )

        mock_client = mocker.Mock()
        mock_client.query.side_effect = [
            pl.DataFrame(),
            pl.DataFrame(),
            SourceFetchError(message="network error", source="tushare"),
        ]
        with pytest.raises(SourceFetchError, match="Failed to fetch"):
            CapitalCorporateTushareAdapter(_client=mock_client).fetch_corporate_actions(
                ann_date="20260930"
            )


class TestRightsBoundaryCodeMatching:
    """rights 降级判别走结构化错误码（details.code==50101）."""

    def _client_with_rights_error(self, message: str, details: dict | None):
        from ditto_data.errors import SourceFetchError

        client = MagicMock()
        client.query.side_effect = [
            pl.DataFrame(),
            pl.DataFrame(),
            SourceFetchError(message=message, source="tushare", details=details),
        ]
        return client

    def test_degrades_on_structured_code(self, mocker) -> None:
        from ditto_data.sources.tushare.adapters.capital_corporate import (
            CapitalCorporateTushareAdapter,
        )

        client = self._client_with_rights_error("请指定正确的接口名", {"code": 50101})
        result = CapitalCorporateTushareAdapter(_client=client).fetch_corporate_actions(
            ann_date="20260930"
        )
        assert result.is_empty()

    def test_message_without_code_still_fails_closed(self, mocker) -> None:
        import pytest
        from ditto_data.errors import SourceFetchError
        from ditto_data.sources.tushare.adapters.capital_corporate import (
            CapitalCorporateTushareAdapter,
        )

        client = self._client_with_rights_error("请指定正确的接口名", None)
        with pytest.raises(SourceFetchError, match="Failed to fetch"):
            CapitalCorporateTushareAdapter(_client=client).fetch_corporate_actions(
                ann_date="20260930"
            )
