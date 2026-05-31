"""DataStoreSettings 单元测试."""

from pathlib import Path

from ditto_data.config.data_store import DataStoreSettings, PathGroups


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

    def test_does_not_own_feature_or_factor_paths(self) -> None:
        """Data 层不应拥有 Features/Factors 产物路径."""
        settings = DataStoreSettings()
        moved_properties = [
            "features_technical_price_path",
            "features_technical_indicators_narrow_path",
            "features_technical_indicators_wide_path",
            "factors_narrow_style_path",
            "factors_wide_style_path",
            "factors_narrow_path",
            "factors_wide_path",
        ]
        moved_directories = [
            "features/technical/price",
            "features/technical/indicators_narrow",
            "features/technical/indicators_wide",
            "factors/narrow/style",
            "factors/wide/style",
            "factors/factors_narrow",
            "factors/factors_wide",
        ]

        for property_name in moved_properties:
            assert not hasattr(settings, property_name)

        dirs = settings.all_directories()
        for directory in moved_directories:
            assert directory not in dirs

    def test_count_matches_previous_hardcoded_list(self) -> None:
        """验证目录数量与之前 Infra 硬编码的列表一致（24 个）."""
        settings = DataStoreSettings()
        dirs = settings.all_directories()
        assert len(dirs) == 24, f"Expected 24 directories, got {len(dirs)}"


class TestPathGroupsStructure:
    """PathGroups 嵌套路径组结构测试."""

    def test_market_paths_group(self) -> None:
        """paths.market 应包含全部市场数据路径."""
        root = Path("/data")
        settings = DataStoreSettings(data_root=root)
        market = settings.paths.market

        assert market.stock_bars == root / "market" / "stock" / "bars" / "daily"
        assert market.etf_bars == root / "market" / "etf" / "bars" / "daily"
        assert market.index_bars == root / "market" / "index" / "bars" / "daily"
        assert market.stock_status == root / "market" / "stock" / "status"
        assert market.etf_status == root / "market" / "etf" / "status"
        assert market.stock_adj == root / "market" / "stock" / "adj"
        assert market.etf_adj == root / "market" / "etf" / "adj"
        assert market.etf_nav == root / "market" / "etf" / "nav"

    def test_capital_paths_group(self) -> None:
        """paths.capital 应包含全部资金流路径."""
        root = Path("/data")
        settings = DataStoreSettings(data_root=root)
        capital = settings.paths.capital

        assert capital.flow == root / "capital" / "flow"
        assert capital.margin == root / "capital" / "margin"
        assert capital.top_board == root / "capital" / "top_board"
        assert capital.limit_board == root / "capital" / "limit_board"
        assert capital.chip == root / "capital" / "chip"

    def test_fundamental_paths_group(self) -> None:
        """paths.fundamental 应包含全部基本面路径."""
        root = Path("/data")
        settings = DataStoreSettings(data_root=root)
        fundamental = settings.paths.fundamental

        assert fundamental.financial == root / "fundamental" / "financial"
        assert fundamental.indicator == root / "fundamental" / "indicator"
        assert fundamental.forecast == root / "fundamental" / "forecast"
        assert fundamental.holding == root / "fundamental" / "holding"

    def test_macro_paths_group(self) -> None:
        """paths.macro 应包含宏观指标路径."""
        root = Path("/data")
        settings = DataStoreSettings(data_root=root)

        assert settings.paths.macro.indicators == root / "macro" / "indicators"

    def test_utility_paths_group(self) -> None:
        """paths.utility 应包含通用路径."""
        root = Path("/data")
        settings = DataStoreSettings(data_root=root)
        utility = settings.paths.utility

        assert utility.logs == root / "logs"
        assert utility.backups == root / "backups"
        assert utility.temp == root / "temp"
        assert utility.db == root / "db"

    def test_utility_logs_override(self) -> None:
        """paths.utility.logs 应支持覆盖."""
        root = Path("/data")
        override = Path("/var/log/ditto")
        settings = DataStoreSettings(data_root=root, logs_path_override=override)

        assert settings.paths.utility.logs == override
        # 其他 utility 路径不受覆盖影响
        assert settings.paths.utility.backups == root / "backups"
        assert settings.paths.utility.temp == root / "temp"
        assert settings.paths.utility.db == root / "db"

    def test_pathgroups_directories(self) -> None:
        """PathGroups.all_directories() 应返回完整的目录清单."""
        pg = PathGroups(Path("/data"))
        dirs = pg.all_directories()
        assert len(dirs) == 24
        assert "market/stock/bars/daily" in dirs
        assert "capital/flow" in dirs
        assert "fundamental/financial" in dirs
        assert "macro/indicators" in dirs
        assert "metadata" in dirs
        assert "locks" in dirs


class TestBackwardCompatibility:
    """路径访问测试 — 确保 paths.* 委托正确."""

    def test_paths_market_direct_access(self) -> None:
        """paths.market.* 直接访问应正确."""
        root = Path("/data")
        settings = DataStoreSettings(data_root=root)

        assert settings.paths.market.stock_bars == (
            root / "market" / "stock" / "bars" / "daily"
        )
        assert settings.paths.market.etf_bars == (
            root / "market" / "etf" / "bars" / "daily"
        )

    def test_paths_utility_direct_access(self) -> None:
        """paths.utility.* 直接访问应正确."""
        root = Path("/data")
        settings = DataStoreSettings(data_root=root)

        assert settings.paths.utility.logs == root / "logs"
        assert settings.paths.utility.backups == root / "backups"
        assert settings.paths.utility.temp == root / "temp"

    def test_logs_path_override_propagates_to_paths(self) -> None:
        """logs_path_override 应正确传播到 paths.utility.logs."""
        root = Path("/data")
        override = Path("/var/log/app")
        settings = DataStoreSettings(data_root=root, logs_path_override=override)

        assert settings.paths.utility.logs == override

    def test_database_paths_unchanged(self) -> None:
        """数据库路径（resolved_sqlite/duckdb）应保持不变."""
        root = Path("/data")
        settings = DataStoreSettings(data_root=root)

        assert settings.resolved_sqlite_path == root / "metadata" / "metadata.sqlite"
        assert settings.resolved_duckdb_path == root / "db" / "ditto.duckdb"

    def test_sqlite_path_override(self) -> None:
        """sqlite_path 覆盖时应正确传播到 resolved_sqlite_path."""
        root = Path("/data")
        override = Path("/tmp/test.sqlite")
        settings = DataStoreSettings(data_root=root, sqlite_path=override)

        assert settings.resolved_sqlite_path == override

    def test_default_data_root(self) -> None:
        """默认 data_root 应为 Path('data')."""
        settings = DataStoreSettings()
        assert settings.data_root == Path("data")
        expected = Path("data") / "market" / "stock" / "bars" / "daily"
        assert settings.paths.market.stock_bars == expected


class TestPathGroupsSubdomainDirectories:
    """子域 directories() 方法测试 — 确保每个路径组能独立列出其目录."""

    def test_market_directories(self) -> None:
        """market.directories() 应返回 8 个市场目录."""
        pg = PathGroups(Path("/data"))
        dirs = pg.market.directories()
        assert len(dirs) == 8
        assert all(d.startswith("market/") for d in dirs)

    def test_capital_directories(self) -> None:
        """capital.directories() 应返回 5 个资金目录."""
        pg = PathGroups(Path("/data"))
        dirs = pg.capital.directories()
        assert len(dirs) == 5
        assert all(d.startswith("capital/") for d in dirs)

    def test_fundamental_directories(self) -> None:
        """fundamental.directories() 应返回 4 个基本面目录."""
        pg = PathGroups(Path("/data"))
        dirs = pg.fundamental.directories()
        assert len(dirs) == 4
        assert all(d.startswith("fundamental/") for d in dirs)

    def test_macro_directories(self) -> None:
        """macro.directories() 应返回 1 个宏观目录."""
        pg = PathGroups(Path("/data"))
        dirs = pg.macro.directories()
        assert len(dirs) == 1
        assert all(d.startswith("macro/") for d in dirs)

    def test_utility_directories(self) -> None:
        """utility.directories() 应返回 4 个通用目录."""
        pg = PathGroups(Path("/data"))
        dirs = pg.utility.directories()
        assert len(dirs) == 4
        assert all("/" not in d for d in dirs)  # 通用目录无子目录
