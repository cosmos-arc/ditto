from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[5]
    / "scripts"
    / "architecture"
    / "check_architecture_smells.py"
)


def _load_module() -> object:
    spec = spec_from_file_location("check_architecture_smells", _SCRIPT)
    if spec is None or spec.loader is None:
        msg = f"Cannot load {_SCRIPT}"
        raise ImportError(msg)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()


def test_execution_simulation_terms_are_guarded() -> None:
    terms: tuple[str, ...] = _MODULE.EXECUTION_SIMULATION_OWNERSHIP_TERMS  # type: ignore[attr-defined]

    assert "BacktestBrokerage" in terms
    assert "BrokerageModel" in terms
    assert "AShareFillModel" in terms
    assert "FixedBpsSlippage" in terms


def test_execution_simulation_guard_reports_backtest_owned_terms() -> None:
    check = _MODULE.check_execution_no_simulation_ownership  # type: ignore[attr-defined]

    errors = check(
        "class BacktestBrokerage: ...",
        "packages/execution/src/ditto_execution/brokerage.py",
    )

    assert errors == [
        "packages/execution/src/ditto_execution/brokerage.py: "
        "execution owns backtest simulation term 'BacktestBrokerage'",
    ]
