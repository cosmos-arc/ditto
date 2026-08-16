from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import orjson
import pytest
from ditto_agent.evals.cases import EvalCaseError, load_eval_cases

FIXTURES = Path(__file__).parents[2] / "fixtures" / "evals"


def test_versioned_eval_cases_have_stable_input_observation_and_case_hashes() -> None:
    cases = load_eval_cases(FIXTURES)

    assert len(cases) == 4
    assert tuple(case.case_id for case in cases) == tuple(
        sorted(case.case_id for case in cases)
    )
    assert all(case.schema_version == 1 for case in cases)
    assert all(case.verify_hashes() for case in cases)
    assert len({case.case_hash for case in cases}) == len(cases)


def test_eval_case_loader_rejects_unknown_fields_versions_and_hash_tamper(
    tmp_path: Path,
) -> None:
    source = orjson.loads((FIXTURES / "passing.json").read_bytes())
    source["unexpected"] = True
    (tmp_path / "unknown.json").write_bytes(orjson.dumps(source))

    with pytest.raises(EvalCaseError) as unknown_info:
        load_eval_cases(tmp_path)

    assert unknown_info.value.reason_code == "eval_case_fields_invalid"

    case = load_eval_cases(FIXTURES)[0]
    with pytest.raises(ValueError, match="schema_version"):
        replace(case, schema_version=2)
    object.__setattr__(case, "case_hash", "0" * 64)
    assert not case.verify_hashes()
