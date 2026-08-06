"""Code-only research factor registry tests."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, cast

import polars as pl
import pytest
from ditto_application.exceptions import AppBuilderError
from ditto_features.expression.contracts import (
    Analysis,
    CompiledDerivedExpression,
    CompileIdentity,
)
from ditto_features.factors.factor_specs import ALL_FACTOR_SPECS
from ditto_features.factors.spec import FactorContext, FactorSpec


def test_default_registry_copies_all_specs_into_immutable_v1_registrations() -> None:
    """Default research registrations are detached, immutable code snapshots."""
    from ditto_application.builders.research_factor_registry import (
        ResearchFactorRegistry,
    )

    registry = ResearchFactorRegistry()

    assert isinstance(registry.registrations, MappingProxyType)
    assert tuple(registry.registrations) == tuple(sorted(ALL_FACTOR_SPECS))
    for factor_id, source_spec in ALL_FACTOR_SPECS.items():
        registration = registry.registrations[factor_id]
        assert registration.factor_id == factor_id
        assert registration.version == 1
        assert registration.spec == source_spec
        assert registration.spec is not source_spec
        assert len(registration.spec_hash) == 64

    with pytest.raises(TypeError):
        cast(Any, registry.registrations)["new-factor"] = registry.registrations[
            "momentum_1m"
        ]


def _custom_registration(
    *,
    version: int = 1,
    expression: str = "close",
    dependencies: tuple[str, ...] = ("market.close",),
    computation_type: str = "expression",
    calendar_context: FactorContext | None = None,
) -> object:
    from ditto_application.builders.research_factor_registry import (
        ResearchFactorRegistration,
    )

    return ResearchFactorRegistration(
        factor_id="research.custom_factor",
        version=version,
        spec=FactorSpec(
            id="research.custom_factor",
            expression=expression,
            dependencies=dependencies,
            computation_type=cast(Any, computation_type),
            calendar_context=calendar_context,
        ),
    )


@pytest.mark.parametrize(
    "changed_registration",
    [
        pytest.param(_custom_registration(expression="open"), id="expression"),
        pytest.param(
            _custom_registration(dependencies=("market.open",)),
            id="dependencies",
        ),
        pytest.param(
            _custom_registration(expression="", computation_type="python"),
            id="computation",
        ),
        pytest.param(
            _custom_registration(calendar_context=FactorContext(exchange="SSE")),
            id="calendar",
        ),
        pytest.param(_custom_registration(version=2), id="version"),
    ],
)
def test_registry_manifest_covers_every_execution_bearing_factor_field(
    changed_registration: object,
) -> None:
    """Spec semantics and explicit versions are part of the full manifest."""
    from ditto_application.builders.research_factor_registry import (
        ResearchFactorRegistration,
        ResearchFactorRegistry,
    )

    original = cast(ResearchFactorRegistration, _custom_registration())
    changed = cast(ResearchFactorRegistration, changed_registration)

    original_registry = ResearchFactorRegistry(extensions=(original,))
    changed_registry = ResearchFactorRegistry(extensions=(changed,))

    assert original_registry.manifest.manifest_hash == original_registry.manifest_hash
    assert original_registry.registrations[original.factor_id] == original
    assert original in original_registry.manifest.registrations
    assert changed_registry.manifest_hash != original_registry.manifest_hash


def test_exact_lookup_rejects_python_factor_without_code_executor_identity() -> None:
    """No expression CompileIdentity is fabricated for Python implementations."""
    from ditto_application.builders.research_factor_registry import (
        ResearchFactorRegistry,
    )

    with pytest.raises(AppBuilderError) as exc_info:
        ResearchFactorRegistry().resolve_used(("obv_ma20",))

    assert exc_info.value.details["code"] == "EXECUTOR_UNAVAILABLE"
    assert exc_info.value.details["reason"] == "research_factor_executor_unavailable"


def test_binding_hash_covers_actual_serialized_expression_not_compiler_claim() -> None:
    """A compiler cannot reuse a valid identity while swapping executable Expr."""
    from ditto_application.builders.research_factor_registry import (
        ResearchFactorRegistry,
    )

    factor_id = "momentum_1m"
    registration = ResearchFactorRegistry().registrations[factor_id]
    identity = CompileIdentity(
        compile_input_hash="1" * 64,
        operator_fingerprint="2" * 64,
        compiler_fingerprint="3" * 64,
        cache_key="4" * 64,
        engine_codegen_version="polars-codegen-v1",
        analysis_version="factor-analysis-v1",
        polars_version=pl.__version__,
        expr_serialization_format="polars-expr-v1",
    )

    def compiled(expr: pl.Expr) -> CompiledDerivedExpression:
        return CompiledDerivedExpression(
            derived_id=factor_id,
            version=registration.version,
            expr=expr,
            analysis=Analysis(
                dependencies=("close",),
                operator_names=(),
                lookback=0,
                requires_full_day=False,
                scope="row",
            ),
            compile_identity=identity,
        )

    legitimate = ResearchFactorRegistry().bind_compiled(
        (factor_id,),
        (compiled(pl.col("close")),),
    )[0]
    poisoned = ResearchFactorRegistry().bind_compiled(
        (factor_id,),
        (compiled(pl.col("open")),),
    )[0]

    assert legitimate.compile_identity == poisoned.compile_identity
    assert legitimate.compiled_expression_hash != poisoned.compiled_expression_hash
    assert legitimate.binding_hash != poisoned.binding_hash


def test_binding_hash_covers_actual_analysis_that_drives_history_window() -> None:
    """A compiler cannot retain one binding while poisoning analysis lookback."""
    from ditto_application.builders.research_factor_registry import (
        ResearchFactorRegistry,
    )

    factor_id = "momentum_1m"
    registration = ResearchFactorRegistry().registrations[factor_id]
    identity = CompileIdentity(
        compile_input_hash="1" * 64,
        operator_fingerprint="2" * 64,
        compiler_fingerprint="3" * 64,
        cache_key="4" * 64,
        engine_codegen_version="polars-codegen-v1",
        analysis_version="factor-analysis-v1",
        polars_version=pl.__version__,
        expr_serialization_format="polars-expr-v1",
    )

    def compiled(*, lookback: int) -> CompiledDerivedExpression:
        return CompiledDerivedExpression(
            derived_id=factor_id,
            version=registration.version,
            expr=pl.col("close"),
            analysis=Analysis(
                dependencies=("close",),
                operator_names=("ts_mean",),
                lookback=lookback,
                requires_full_day=False,
                scope="row",
            ),
            compile_identity=identity,
        )

    legitimate = ResearchFactorRegistry().bind_compiled(
        (factor_id,),
        (compiled(lookback=20),),
    )[0]
    poisoned = ResearchFactorRegistry().bind_compiled(
        (factor_id,),
        (compiled(lookback=0),),
    )[0]

    assert legitimate.compiled_expression_hash == poisoned.compiled_expression_hash
    assert legitimate.analysis_execution_hash != poisoned.analysis_execution_hash
    assert legitimate.binding_hash != poisoned.binding_hash
