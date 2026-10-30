"""#622 覆盖合同结构守卫：注册表一致性 + 状态词表 + 未知项不得冒充就绪。

合同机读真源为 docs/data/coverage-contract.yaml；本测试只校验结构不变量，
不校验实测数值（数值由测量方法与票内证据背书）。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from ditto_application.config.queries import get_all_datasets
from ditto_data.models.common import Dataset

CONTRACT_PATH = (
    Path(__file__).resolve().parents[5] / "docs" / "data" / "coverage-contract.yaml"
)
ALLOWED_STATUSES = {"ready", "partial", "empty"}


def _load_contract() -> dict:
    with CONTRACT_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_contract_exists_and_parses() -> None:
    assert CONTRACT_PATH.exists(), f"missing coverage contract: {CONTRACT_PATH}"
    contract = _load_contract()
    assert set(contract) == {"meta", "datasets"}


def test_contract_covers_registry_exactly() -> None:
    contract = _load_contract()
    contract_ids = set(contract["datasets"])
    registry_ids = {ds.value for ds in Dataset}
    assert contract_ids == registry_ids, (
        f"contract/registry drift: only-in-contract={contract_ids - registry_ids}, "
        f"only-in-registry={registry_ids - contract_ids}"
    )
    spec_ids = {ds.value for ds in get_all_datasets()}
    assert contract_ids == spec_ids, (
        "coverage contract out of sync with INGESTION_SPECS"
    )


def test_status_vocabulary_is_closed() -> None:
    contract = _load_contract()
    statuses = {name: entry["status"] for name, entry in contract["datasets"].items()}
    bad = {n: s for n, s in statuses.items() if s not in ALLOWED_STATUSES}
    assert not bad, f"unknown/unmeasured statuses are forbidden: {bad}"


def test_ready_entries_are_backed_by_measurement() -> None:
    contract = _load_contract()
    problems: list[str] = []
    for name, entry in contract["datasets"].items():
        if entry["status"] == "ready":
            if entry["gaps"]:
                problems.append(f"{name}: ready but has gaps")
            if entry["measured"]["rows"] <= 0:
                problems.append(f"{name}: ready but zero measured rows")
            if (
                entry["declared"]["frequency"] != "static"
                and not entry["measured"]["start"]
            ):
                problems.append(f"{name}: ready but no measured start")
            if (
                entry["declared"]["frequency"] == "trading_daily"
                and entry["catalog_latest"]["date"]
                and entry["measured"]["end"]
                and entry["measured"]["end"] < entry["catalog_latest"]["date"]
            ):
                problems.append(
                    f"{name}: ready but measured end {entry['measured']['end']} "
                    f"behind catalog latest {entry['catalog_latest']['date']}"
                )
    assert not problems, problems


def test_provider_apis_have_probe_evidence() -> None:
    contract = _load_contract()
    probes = set(contract["meta"]["permission_matrix"]["probes"])
    problems: list[str] = []
    for name, entry in contract["datasets"].items():
        for api in entry["provider_apis"]:
            if f"tushare:{api}" not in probes and f"fred:{api}" not in probes:
                problems.append(f"{name}: api {api} has no probe evidence entry")
    assert not problems, problems


def test_entry_shape() -> None:
    contract = _load_contract()
    required = {
        "domain",
        "tier",
        "sources",
        "provider_apis",
        "declared",
        "measured",
        "catalog_latest",
        "status",
        "gaps",
        "consumers",
        "notes",
    }
    problems: list[str] = []
    for name, entry in contract["datasets"].items():
        missing = required - set(entry)
        if missing:
            problems.append(f"{name}: missing {missing}")
            continue
        measured = entry["measured"]
        if not isinstance(measured["rows"], int) or measured["rows"] < 0:
            problems.append(f"{name}: measured.rows must be a non-negative int")
        if measured["rows"] > 0 and measured["instruments"] == 0:
            problems.append(
                f"{name}: rows>0 but instruments==0 is ambiguous"
                " (use null when the dataset has no instrument dimension)"
            )
        if entry["status"] == "empty" and measured["rows"] != 0:
            problems.append(f"{name}: empty status must match zero measured rows")
        if entry["status"] != "empty" and measured["rows"] == 0:
            problems.append(f"{name}: zero rows but status is {entry['status']}")
        if "config" not in entry["sources"] and not entry["provider_apis"]:
            problems.append(f"{name}: non-config dataset without provider_apis")
        if not entry["consumers"]:
            problems.append(f"{name}: consumer surface must be stated (traceability)")
    assert not problems, problems
