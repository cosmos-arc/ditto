"""E2E 测试共享 fixtures。

提供端到端验证测试所需的核心 fixtures，包括：
- 黄金数据集配置
- 真实数据源（Tushare、TDX）
- 预期快照加载
- 报告生成器

参考文档：docs/plans/2026-02-17-e2e-validation-design.md
"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保 tests 目录在 sys.path 中（支持 xdist 并行测试）
# 必须在所有其他导入之前执行
_tests_root = Path(__file__).parent.parent
if str(_tests_root) not in sys.path:
    sys.path.insert(0, str(_tests_root))

import os  # noqa: E402
from datetime import date  # noqa: E402

import polars as pl  # noqa: E402
import pytest  # noqa: E402
from ditto_data.quality import GoldenDatasetSpec  # noqa: E402
from ditto_datahub.config import DataSourceSettings  # noqa: E402
from ditto_datahub.sources import TushareSource  # noqa: E402
from ditto_datahub.sources.tdx import TdxSource  # noqa: E402
from ditto_datahub.stores.market.stock.bars import (  # noqa: E402
    StockBarsReader,
    StockBarsWriter,
)

from tests.e2e.reporter import E2EReporter  # noqa: E402

# ==============================================================================
# 数据完整性验证
# ==============================================================================


@pytest.fixture(scope="session")
def e2e_data_validation() -> dict[str, bool]:
    """验证 E2E 测试数据完整性.

    Session 级别 fixture，检查 TDX 样本和 PIT 快照数据是否存在。
    如果关键数据缺失，测试将被跳过。

    Returns:
        dict[str, bool]: 数据完整性状态字典。

    Raises:
        pytest.skip: 如果关键数据缺失。

    """
    validation_result: dict[str, bool] = {
        "tdx_samples": False,
        "pit_snapshots": False,
    }

    # 检查 TDX 样本数据
    tdx_sh = Path("tests/tdx_samples/vipdoc/sh/lday")
    tdx_sz = Path("tests/tdx_samples/vipdoc/sz/lday")

    sh_files = list(tdx_sh.glob("*.day")) if tdx_sh.exists() else []
    sz_files = list(tdx_sz.glob("*.day")) if tdx_sz.exists() else []

    validation_result["tdx_samples"] = len(sh_files) + len(sz_files) >= 10

    # 检查 PIT 快照数据
    snapshot_dir = Path("tests/fixtures/golden_expected/daily_snapshots")
    snapshot_files = (
        list(snapshot_dir.glob("*.parquet")) if snapshot_dir.exists() else []
    )

    validation_result["pit_snapshots"] = len(snapshot_files) >= 10

    # 如果关键数据缺失，跳过需要这些数据的测试
    if not validation_result["tdx_samples"]:
        pytest.skip(
            f"TDX 样本数据不完整: SH {len(sh_files)} 文件, SZ {len(sz_files)} 文件。"
            "请运行: pixi run -e dev python tests/scripts/prepare_e2e_data.py"
        )

    if not validation_result["pit_snapshots"]:
        pytest.skip(
            f"PIT 快照数据不完整: {len(snapshot_files)} 文件。"
            "请运行: pixi run -e dev python tests/scripts/prepare_e2e_data.py --snapshots"
        )

    return validation_result


# ==============================================================================
# 黄金数据集
# ==============================================================================


@pytest.fixture(scope="session")
def golden_spec(e2e_data_validation: dict[str, bool]) -> GoldenDatasetSpec:
    """加载黄金数据集配置。

    Session 级别 fixture，整个测试会话只加载一次。
    黄金数据集包含 25 个精选标的，覆盖流动性分层、市场板块、资产类型等维度。

    Args:
        e2e_data_validation: 数据完整性验证结果（确保数据存在）。

    Returns:
        GoldenDatasetSpec: 黄金数据集配置对象。

    """
    _ = e2e_data_validation  # 依赖此 fixture 进行数据验证
    import yaml

    yaml_path = Path("config/default/golden_dataset.yml")
    with yaml_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return GoldenDatasetSpec(**data)


# ==============================================================================
# 真实数据源
# ==============================================================================


@pytest.fixture(scope="session")
def tushare_source() -> TushareSource:
    """连接真实 Tushare API。

    Session 级别 fixture，整个测试会话只初始化一次。
    Token 优先从 keyring 读取，其次从环境变量 TUSHARE_TOKEN 读取。

    Returns:
        TushareSource: Tushare 数据源实例。

    Raises:
        pytest.skip: 如果 Token 未配置。

    """
    import keyring
    from keyring.errors import KeyringError

    # 优先从 keyring 读取
    token = None
    try:
        token = keyring.get_password("ditto", "tushare")
    except KeyringError:
        pass  # keyring 不可用，回退到环境变量

    # 回退到环境变量
    if not token:
        token = os.environ.get("TUSHARE_TOKEN")

    if not token:
        pytest.skip("Tushare Token 未配置 (keyring 或 TUSHARE_TOKEN 环境变量)")

    return TushareSource(settings=DataSourceSettings(), token=token)


@pytest.fixture(scope="session")
def tdx_source() -> TdxSource:
    """加载内置 TDX 样本文件。

    Session 级别 fixture，整个测试会话只初始化一次。
    使用 tests/tdx_samples 目录下的 TDX 样本文件进行质量对账。

    Returns:
        TdxSource: TDX 数据源实例。

    """
    settings = DataSourceSettings(tdx_path="tests/tdx_samples")
    return TdxSource(data_source_settings=settings)


# ==============================================================================
# 预期结果
# ==============================================================================


@pytest.fixture
def expected_snapshots(golden_spec: GoldenDatasetSpec) -> dict[str, pl.DataFrame]:
    """加载黄金数据集的预期快照。

    从 tests/fixtures/golden_expected/daily_snapshots/ 目录加载 parquet 格式的预期快照。

    Args:
        golden_spec: 黄金数据集配置（预留用于过滤）。

    Returns:
        dict[str, pl.DataFrame]: 以 ticker 为键的预期数据帧字典。

    """
    _ = golden_spec  # 预留参数，未来可用于过滤快照
    return load_expected_snapshots("tests/fixtures/golden_expected/daily_snapshots/")


def load_expected_snapshots(path: str) -> dict[str, pl.DataFrame]:
    """加载预期快照文件。

    Args:
        path: 快照目录路径。

    Returns:
        dict[str, pl.DataFrame]: 以 ticker 为键的预期数据帧字典。

    """
    snapshots: dict[str, pl.DataFrame] = {}
    snapshot_dir = Path(path)
    if not snapshot_dir.exists():
        return snapshots
    for file in snapshot_dir.glob("*.parquet"):
        ticker = file.stem
        snapshots[ticker] = pl.read_parquet(file)
    return snapshots


# ==============================================================================
# Store 层 Fixtures（数据存储验证）
# ==============================================================================


@pytest.fixture
def stock_bars_reader(tmp_path: Path) -> StockBarsReader:
    """创建 Stock 日线数据 Reader.

    使用 tmp_path 进行隔离测试，每次测试使用独立的临时目录。

    Args:
        tmp_path: pytest 提供的临时目录 fixture.

    Returns:
        StockBarsReader: Stock 日线数据 Reader 实例.

    """
    return StockBarsReader(data_root=tmp_path)


@pytest.fixture
def stock_bars_writer(tmp_path: Path) -> StockBarsWriter:
    """创建 Stock 日线数据 Writer.

    使用 tmp_path 进行隔离测试，每次测试使用独立的临时目录。

    Args:
        tmp_path: pytest 提供的临时目录 fixture.

    Returns:
        StockBarsWriter: Stock 日线数据 Writer 实例.

    """
    return StockBarsWriter(data_root=tmp_path)


@pytest.fixture
def sample_bars_df() -> pl.DataFrame:
    """创建样本日线数据 DataFrame.

    用于测试 Writer/Reader 的基本功能。

    Returns:
        pl.DataFrame: 样本日线数据，包含 3 条记录.

    """
    return pl.DataFrame(
        {
            "instrument_id": [1000001, 1000001, 1000001],
            "trade_date": pl.date_range(
                start=date(2024, 1, 2),
                end=date(2024, 1, 4),
                interval="1d",
                eager=True,
            ),
            "open": [10.0, 10.5, 11.0],
            "high": [10.5, 11.0, 11.5],
            "low": [9.8, 10.2, 10.8],
            "close": [10.3, 10.8, 11.2],
            "volume": [1000000, 1200000, 1100000],
            "amount": [10250000.0, 12960000.0, 12320000.0],
        }
    )


@pytest.fixture
def multi_ticker_bars_df() -> pl.DataFrame:
    """创建多标的日线数据 DataFrame.

    用于测试多标的并发写入功能。

    Returns:
        pl.DataFrame: 多标的日线数据，包含 5 个标的各 10 条记录.

    """
    tickers = [1000001, 1000002, 1000003, 1000004, 1000005]
    records_per_ticker = 10

    data = {
        "instrument_id": [],
        "trade_date": [],
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
        "amount": [],
    }

    for ticker in tickers:
        for i in range(records_per_ticker):
            data["instrument_id"].append(ticker)
            trade_date = date(2024, 1, 2) + __import__("datetime").timedelta(days=i)
            data["trade_date"].append(trade_date)
            base_price = 10.0 + ticker % 10
            data["open"].append(base_price)
            data["high"].append(base_price + 0.5)
            data["low"].append(base_price - 0.2)
            data["close"].append(base_price + 0.3)
            data["volume"].append(1000000)
            data["amount"].append(base_price * 1000000)

    return pl.DataFrame(data)


# ==============================================================================
# 报告生成
# ==============================================================================


@pytest.fixture(scope="session")
def reporter(golden_spec: GoldenDatasetSpec) -> E2EReporter:
    """创建 E2E 验收报告生成器。

    Session 级别 fixture，在测试会话期间记录各阶段结果，
    最终生成 Markdown 格式的验收报告。

    Args:
        golden_spec: 黄金数据集配置。

    Returns:
        E2EReporter: 报告生成器实例。

    """
    return E2EReporter(golden_spec)


@pytest.fixture(scope="session", autouse=True)
def generate_report(request: pytest.FixtureRequest, reporter: E2EReporter) -> None:
    """自动生成 E2E 验收报告。

    Session 级别自动 fixture，在所有测试结束后自动生成报告。
    报告保存至 tests/reports/e2e_validation_YYYYMMDD.md。

    Args:
        request: pytest fixture 请求对象。
        reporter: 报告生成器实例。

    """
    _ = request  # 预留参数，可用于获取测试会话信息
    yield
    # 所有测试结束后生成报告
    output_path = Path(f"tests/reports/e2e_validation_{date.today():%Y%m%d}.md")
    reporter.generate_markdown(output_path)
