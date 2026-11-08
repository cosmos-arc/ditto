"""Frozen ETF selection uses real metadata storage without replacing history."""

import json
from pathlib import Path

import pytest
from ditto_apps.registry.contexts.universe import create_universe_write_context
from ditto_apps.scripts.materialize_etf_universe import main
from ditto_platform.foundation import SQLiteClient


@pytest.mark.pit
def test_frozen_etf_initialization_is_repeatable_and_preserves_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DITTO_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("DITTO_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring")
    from ditto_apps.registry.container import make_app_container

    container = make_app_container()
    try:
        client = container.get(SQLiteClient)
        client.executemany(
            "INSERT INTO instrument "
            "(instrument_id,ticker,name,exchange,asset_class,list_date,delist_date) "
            "VALUES (?,?,?,?,?,?,?)",
            [
                (2000001, "510300", "Test ETF", "SSE", "etf", "2020-01-02", None),
                (
                    2000002,
                    "159915",
                    "Closed ETF",
                    "SZSE",
                    "etf",
                    "2020-01-03",
                    "2020-02-01",
                ),
            ],
        )
        client.commit()
    finally:
        container.close()
    plan = {
        "universe_id": "csi_etf_broad",
        "name": "Frozen sample",
        "selected_at": "2026-11-08T04:00:00+00:00",
        "source_observed_at": "2026-11-08T04:00:00+00:00",
        "source": "instrument_registry",
        "selection_rule": "Explicit finite list before returns",
        "excluded_scope": "All other funds",
        "candidate_window": {"start": "2020-01-03", "end": "2020-01-31"},
        "limitations": "Fixed current sample; historical availability not certified",
        "members": [
            {
                "instrument_id": 2000001,
                "ticker": "510300",
                "name": "Test ETF",
                "exchange": "SSE",
                "asset_class": "etf",
                "list_date": "2020-01-02",
                "delist_date": None,
            },
            {
                "instrument_id": 2000002,
                "ticker": "159915",
                "name": "Closed ETF",
                "exchange": "SZSE",
                "asset_class": "etf",
                "list_date": "2020-01-03",
                "delist_date": "2020-02-01",
            },
        ],
    }
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps(plan))
    args = ["--selection", str(selection)]
    with create_universe_write_context() as metadata:
        metadata.universe.create_universe("unrelated", "Preserve")
        metadata.universe.add_constituents(
            "unrelated",
            [
                {
                    "instrument_id": 2000001,
                    "effective_from": "2019-01-01",
                    "effective_to": "2020-01-01",
                }
            ],
        )
    assert main(args) == 0  # dry-run is read-only
    with create_universe_write_context() as metadata:
        assert metadata.universe.get_universe_detail("csi_etf_broad") is None
    assert main([*args, "--apply"]) == 0
    with create_universe_write_context() as metadata:
        before = metadata.universe.get_constituent_history("csi_etf_broad")
        assert metadata.get_universe("csi_etf_broad", "2020-01-01") == []
        assert metadata.get_universe("csi_etf_broad", "2020-01-02") == [2000001]
        assert metadata.get_universe("csi_etf_broad", "2020-01-03") == [
            2000001,
            2000002,
        ]
        assert metadata.get_universe("csi_etf_broad", "2020-02-01") == [2000001]
    assert main([*args, "--apply"]) == 0
    with create_universe_write_context() as metadata:
        assert metadata.universe.get_constituent_history("csi_etf_broad") == before
        assert metadata.get_universe("unrelated", "2019-12-31") == [2000001]
        assert metadata.get_universe("unrelated", "2020-01-01") == []
        metadata.universe.add_constituents(
            "csi_etf_broad",
            [
                {
                    "instrument_id": 2000001,
                    "effective_from": "2019-01-01",
                    "effective_to": "2020-01-01",
                }
            ],
        )
    with pytest.raises(ValueError, match="conflict"):
        main([*args, "--apply"])
    with create_universe_write_context() as metadata:
        assert metadata.get_universe("csi_etf_broad", "2019-12-31") == [2000001]
