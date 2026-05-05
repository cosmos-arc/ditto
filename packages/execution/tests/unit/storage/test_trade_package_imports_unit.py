import subprocess
import sys
from pathlib import Path


def _run_python(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed test snippets, no user input
        [sys.executable, "-c", code],
        capture_output=True,
        check=False,
        text=True,
    )


def test_trade_package_has_no_lazy_service_cycle():
    from ditto_execution.storage.sqlite import trade

    source = Path(trade.__file__).read_text()

    assert "TYPE_CHECKING" not in source
    assert "__getattr__" not in source
    assert "import_module" not in source


def test_trade_dependency_groups_import_before_trade_service() -> None:
    result = _run_python(
        "from ditto_execution.storage.deps import "
        "ExecutionReaders, ExecutionWriters\n"
        "import ditto_execution.storage.sqlite.trade as trade\n"
        "from ditto_execution.storage.sqlite.trade.service import TradeService\n"
        "from ditto_execution.di.storage import ExecutionStorageProvider\n"
        "print(ExecutionReaders.__name__, ExecutionWriters.__name__, "
        "TradeService.__name__, trade.FillReader.__name__, "
        "ExecutionStorageProvider.__name__)\n"
    )

    assert result.returncode == 0, result.stderr


def test_trade_service_type_hints_resolve_runtime_dependencies() -> None:
    result = _run_python(
        "from typing import get_type_hints\n"
        "from ditto_execution.storage.sqlite.trade.service import TradeService\n"
        "hints = get_type_hints(TradeService.__init__)\n"
        "print(hints['readers'].__name__, hints['writers'].__name__)\n"
    )

    assert result.returncode == 0, result.stderr
