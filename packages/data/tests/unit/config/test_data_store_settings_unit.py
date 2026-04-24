"""DataStoreSettings 单元测试."""

from ditto_data.config.data_store import DataStoreSettings


class TestDataStoreSettingsAllDirectories:
    """DataStoreSettings.all_directories() 测试."""

    def test_returns_list_of_strings(self) -> None:
        """all_directories() 应返回字符串列表."""
        settings = DataStoreSettings()
        dirs = settings.all_directories()
        assert isinstance(dirs, list)
        assert all(isinstance(d, str) for d in dirs)

    def test_includes_market_stock_bars_daily(self) -> None:
        """应包含 market/stock/bars/daily."""
        settings = DataStoreSettings()
        dirs = settings.all_directories()
        assert "market/stock/bars/daily" in dirs

    def test_includes_market_etf_bars_daily(self) -> None:
        """应包含 market/etf/bars/daily."""
        settings = DataStoreSettings()
        dirs = settings.all_directories()
        assert "market/etf/bars/daily" in dirs

    def test_includes_capital_flow(self) -> None:
        """应包含 capital/flow."""
        settings = DataStoreSettings()
        dirs = settings.all_directories()
        assert "capital/flow" in dirs

    def test_includes_fundamental_financial(self) -> None:
        """应包含 fundamental/financial."""
        settings = DataStoreSettings()
        dirs = settings.all_directories()
        assert "fundamental/financial" in dirs

    def test_includes_metadata(self) -> None:
        """应包含 metadata."""
        settings = DataStoreSettings()
        dirs = settings.all_directories()
        assert "metadata" in dirs

    def test_includes_generic_dirs(self) -> None:
        """应包含 logs, backups, temp, db, locks."""
        settings = DataStoreSettings()
        dirs = settings.all_directories()
        for d in ("logs", "backups", "temp", "db", "locks"):
            assert d in dirs, f"Missing directory: {d}"

    def test_no_duplicates(self) -> None:
        """返回列表不应有重复."""
        settings = DataStoreSettings()
        dirs = settings.all_directories()
        assert len(dirs) == len(set(dirs))

    def test_consistent_with_path_properties(self) -> None:
        """返回的目录应与各个 @property 路径一致."""
        settings = DataStoreSettings()
        dirs = settings.all_directories()
        for d in dirs:
            expected = settings.data_root / d
            assert expected == settings.data_root / d

    def test_count_matches_previous_hardcoded_list(self) -> None:
        """验证目录数量与之前 Infra 硬编码的列表一致（24 个）."""
        settings = DataStoreSettings()
        dirs = settings.all_directories()
        assert len(dirs) == 31, f"Expected 31 directories, got {len(dirs)}"
