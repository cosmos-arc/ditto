"""Factor spec validation gate for CI."""

from __future__ import annotations

from ditto_kernel.strategy import DerivedRole, DerivedSpec, MaterializationProfile
from loguru import logger

from ditto_features.expression.compiler import (
    ExpressionCompiler,
    detect_dependency_cycles,
)
from ditto_features.expression.lexer import tokenize
from ditto_features.expression.parser import ExpressionParser
from ditto_features.factors.factor_specs import ALL_FACTOR_SPECS
from ditto_features.factors.spec import FactorSpec

__all__ = ["validate_factor_specs"]

_KNOWN_DATA_PREFIXES = ("market.", "fundamentals.", "capital.")
# 维护点: 新增数据域前缀时需同步更新此元组。
# 长期方案: 从已注册 FactorSpec 的 dependencies 中自动提取前缀。

_COMPILER = ExpressionCompiler()


def _is_known_data_column(dep: str) -> bool:
    """Check whether a dependency refers to a known data column prefix."""
    return any(dep.startswith(prefix) for prefix in _KNOWN_DATA_PREFIXES)


def _validate_expression_compilation(
    factor_id: str,
    expression: str,
) -> list[str]:
    """Validate that a single expression can be parsed and compiled."""
    errors: list[str] = []
    try:
        tokens = tokenize(expression)
        ExpressionParser(tokens, expression).parse()
    except Exception as exc:
        msg = f"[{factor_id}] expression parse failed: {exc}"
        logger.warning(msg)
        errors.append(msg)
        return errors

    try:
        spec = DerivedSpec(
            id=factor_id,
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression=expression,
        )
        _COMPILER.compile(spec)
    except Exception as exc:
        msg = f"[{factor_id}] expression compilation failed: {exc}"
        logger.warning(msg)
        errors.append(msg)
    return errors


def _validate_dependencies(
    specs: dict[str, FactorSpec],
) -> list[str]:
    """Validate that all dependencies reference known factors or data columns."""
    errors: list[str] = []
    known_ids = set(specs)
    for factor_id, spec in specs.items():
        for dep in spec.dependencies:
            if dep in known_ids or _is_known_data_column(dep):
                continue
            msg = (
                f"[{factor_id}] unknown dependency '{dep}': "
                f"must be a registered factor id or a known data column "
                f"(prefixes: {', '.join(_KNOWN_DATA_PREFIXES)})"
            )
            logger.warning(msg)
            errors.append(msg)
    return errors


def _validate_python_factors(
    specs: dict[str, FactorSpec],
) -> list[str]:
    """Validate constraints for python-type factors."""
    errors: list[str] = []
    for factor_id, spec in specs.items():
        if spec.computation_type != "python":
            continue
        if not spec.description:
            msg = f"[{factor_id}] python-type factor must have a non-empty description"
            logger.warning(msg)
            errors.append(msg)
        if len(spec.dependencies) == 0:
            msg = f"[{factor_id}] python-type factor must have at least one dependency"
            logger.warning(msg)
            errors.append(msg)
    return errors


def validate_factor_specs(
    specs: dict[str, FactorSpec] | None = None,
) -> list[str]:
    """
    Validate all factor specs and return a list of error messages.

    Returns empty list if all validations pass.

    Checks:
    1. All expression-type factors compile successfully.
    2. No dependency cycles.
    3. All dependencies reference a known factor or a legal data column prefix.
    4. Python-type factors have non-empty description and at least one dependency.
    """
    if specs is None:
        specs = ALL_FACTOR_SPECS

    errors: list[str] = []

    # --- 1. Expression compilation ---
    for factor_id, spec in specs.items():
        if spec.computation_type == "expression":
            errors.extend(_validate_expression_compilation(factor_id, spec.expression))

    # --- 2. Cycle detection ---
    dep_graph: dict[str, tuple[str, ...]] = {
        fid: spec.dependencies for fid, spec in specs.items()
    }
    try:
        detect_dependency_cycles(dep_graph)
    except ValueError as exc:
        msg = f"dependency cycle: {exc}"
        logger.error(msg)
        errors.append(msg)

    # --- 3. Dependency references ---
    errors.extend(_validate_dependencies(specs))

    # --- 4. Python-type factor constraints ---
    errors.extend(_validate_python_factors(specs))

    if errors:
        logger.error("factor spec validation failed with {} error(s)", len(errors))
    else:
        logger.info("factor spec validation passed ({} specs checked)", len(specs))

    return errors
