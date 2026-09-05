"""Contract tests for offline, reproducible Web schema generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tooling.contracts import generate_web_schema


def test_generated_header_records_provenance() -> None:
    header = generate_web_schema.generated_header(
        schema_sha256="a" * 64,
        generator_version="7.13.0",
    )

    assert header.startswith("/**\n * DO NOT EDIT")
    assert "Schema SHA-256: " + "a" * 64 in header
    assert "Generator: openapi-typescript 7.13.0" in header


@pytest.mark.parametrize(
    "reference",
    [
        "https://example.invalid/schema.json",
        "http://example.invalid/schema.json",
        "ftp://example.invalid/schema.json",
        "file:///tmp/schema.json",
        "//example.invalid/schema.json",
        "./schema.json#/components/schemas/X",
    ],
)
def test_remote_schema_references_are_rejected(reference: str) -> None:
    schema = {"openapi": "3.1.0", "components": {"schemas": {"X": {"$ref": reference}}}}

    with pytest.raises(generate_web_schema.RemoteReferenceError, match="local-only"):
        generate_web_schema.assert_local_only_references(schema)


def test_internal_schema_reference_is_accepted() -> None:
    schema = {
        "openapi": "3.1.0",
        "components": {"schemas": {"X": {"$ref": "#/components/schemas/Internal"}}},
    }

    generate_web_schema.assert_local_only_references(schema)


def test_candidate_generation_uses_local_snapshot_and_temp_output(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "v1.json"
    snapshot.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "T", "version": "1"},
                "paths": {},
            }
        ),
        encoding="utf-8",
    )
    calls: list[tuple[Path, Path]] = []
    source_payloads: list[bytes] = []

    def fake_generator(source: Path, output: Path) -> None:
        calls.append((source, output))
        source_payloads.append(source.read_bytes())
        output.write_text("export interface paths {}\n", encoding="utf-8")

    candidate = generate_web_schema.generate_candidate_bytes(
        snapshot_path=snapshot,
        generator_version="7.13.0",
        run_generator=fake_generator,
    )

    assert calls[0][0] != snapshot.resolve()
    assert source_payloads == [snapshot.read_bytes()]
    assert calls[0][1].parent != snapshot.parent
    assert not calls[0][1].exists()
    assert candidate.endswith(b"export interface paths {}\n")


def test_type_and_runtime_candidates_share_one_immutable_snapshot(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "v1.json"
    original = json.dumps(
        {
            "openapi": "3.1.0",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/api/v1/original": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "ok",
                                "content": {"application/json": {}},
                            }
                        }
                    }
                }
            },
        },
        sort_keys=True,
    ).encode()
    snapshot.write_bytes(original)

    def mutating_generator(source: Path, output: Path) -> None:
        snapshot.write_text(
            json.dumps(
                {
                    "openapi": "3.1.0",
                    "info": {"title": "T", "version": "2"},
                    "paths": {},
                }
            ),
            encoding="utf-8",
        )
        assert source.read_bytes() == original
        output.write_text("export interface paths {}\n", encoding="utf-8")

    types, runtime = generate_web_schema.generate_candidates_bytes(
        snapshot_path=snapshot,
        generator_version="7.13.0",
        run_generator=mutating_generator,
    )

    digest = hashlib.sha256(original).hexdigest().encode()
    assert digest in types
    assert digest in runtime
    assert b'"get /api/v1/original"' in runtime


def test_generated_schema_mismatch_does_not_rewrite_output(tmp_path: Path) -> None:
    output = tmp_path / "schema.d.ts"
    stale = b"export interface stale {}\n"
    output.write_bytes(stale)

    with pytest.raises(generate_web_schema.GeneratedSchemaMismatchError):
        generate_web_schema.check_generated_schema(
            output,
            b"export interface current {}\n",
        )

    assert output.read_bytes() == stale


def test_runtime_response_contracts_bind_method_path_status_and_media_type(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "v1.json"
    snapshot.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "T", "version": "1"},
                "components": {
                    "schemas": {
                        "Event": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["schema_version", "event_type", "status"],
                            "properties": {
                                "schema_version": {"type": "integer", "const": 1},
                                "event_type": {
                                    "type": "string",
                                    "enum": ["event_started", "event_completed"],
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["running", "completed"],
                                },
                            },
                        }
                    }
                },
                "paths": {
                    "/api/v1/status": {
                        "get": {
                            "responses": {
                                "200": {
                                    "description": "ok",
                                    "content": {"application/json": {}},
                                },
                                "default": {
                                    "description": "error",
                                    "content": {"application/problem+json": {}},
                                },
                            }
                        }
                    },
                    "/api/v1/events": {
                        "post": {
                            "responses": {
                                "202": {
                                    "description": "accepted",
                                    "content": {
                                        "text/event-stream": {
                                            "schema": {"type": "string"},
                                            "x-ditto-sse-data-schema": {
                                                "$ref": "#/components/schemas/Event"
                                            },
                                            "x-ditto-sse-terminal": {
                                                "field": "status",
                                                "values": ["completed"],
                                            },
                                        }
                                    },
                                }
                            }
                        }
                    },
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    candidate = generate_web_schema.generate_operation_contracts_bytes(
        snapshot_path=snapshot,
    )

    text = candidate.decode()
    assert "DO NOT EDIT: generated from contracts/openapi/v1.json" in text
    assert '"get /api/v1/status"' in text
    assert '"200": ["application/json"]' in text
    assert '"default": ["application/problem+json"]' in text
    assert '"post /api/v1/events"' in text
    assert '"202": ["text/event-stream"]' in text
    assert "export const operationEventContracts" in text
    assert '"dataSchema": "#/components/schemas/Event"' in text
    assert '"schemaVersion": 1' in text
    assert '"fields": ["event_type", "schema_version", "status"]' in text
    assert '"eventTypes": ["event_started", "event_completed"]' in text
    assert '"statusValues": ["running", "completed"]' in text
    assert '"field": "status"' in text
    assert '"values": ["completed"]' in text


def test_runtime_event_contract_rejects_terminal_values_outside_data_schema(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "v1.json"
    snapshot.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "T", "version": "1"},
                "components": {
                    "schemas": {
                        "Event": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["schema_version", "event_type"],
                            "properties": {
                                "schema_version": {"const": 1},
                                "event_type": {
                                    "type": "string",
                                    "enum": ["started"],
                                },
                            },
                        }
                    }
                },
                "paths": {
                    "/events": {
                        "get": {
                            "responses": {
                                "200": {
                                    "description": "events",
                                    "content": {
                                        "text/event-stream": {
                                            "schema": {"type": "string"},
                                            "x-ditto-sse-data-schema": {
                                                "$ref": "#/components/schemas/Event"
                                            },
                                            "x-ditto-sse-terminal": {
                                                "field": "event_type",
                                                "values": ["completed"],
                                            },
                                        }
                                    },
                                }
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(generate_web_schema.CodegenError, match="terminal values"):
        generate_web_schema.generate_operation_contracts_bytes(snapshot_path=snapshot)


@pytest.mark.parametrize("wire_schema", [None, {"type": "object"}])
def test_runtime_event_contract_requires_a_string_sse_wire_schema(
    tmp_path: Path,
    wire_schema: dict[str, str] | None,
) -> None:
    snapshot = tmp_path / "v1.json"
    media: dict[str, object] = {
        "x-ditto-sse-data-schema": {"$ref": "#/components/schemas/Event"},
        "x-ditto-sse-terminal": {
            "field": "event_type",
            "values": ["completed"],
        },
    }
    if wire_schema is not None:
        media["schema"] = wire_schema
    snapshot.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "T", "version": "1"},
                "components": {
                    "schemas": {
                        "Event": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["schema_version", "event_type"],
                            "properties": {
                                "schema_version": {"const": 1},
                                "event_type": {
                                    "type": "string",
                                    "enum": ["completed"],
                                },
                            },
                        }
                    }
                },
                "paths": {
                    "/events": {
                        "get": {
                            "responses": {
                                "200": {
                                    "description": "events",
                                    "content": {"text/event-stream": media},
                                }
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(generate_web_schema.CodegenError, match=r"wire schema.*string"):
        generate_web_schema.generate_operation_contracts_bytes(snapshot_path=snapshot)


def test_runtime_response_contracts_reject_ambiguous_status_keys(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "v1.json"
    snapshot.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "T", "version": "1"},
                "paths": {
                    "/api/v1/status": {
                        "get": {
                            "responses": {
                                "20x": {
                                    "description": "ambiguous",
                                    "content": {"application/json": {}},
                                }
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(generate_web_schema.CodegenError, match="response status"):
        generate_web_schema.generate_operation_contracts_bytes(
            snapshot_path=snapshot,
        )


def test_runtime_response_contracts_support_openapi_31_response_features(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "v1.json"
    snapshot.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "T", "version": "1"},
                "components": {
                    "responses": {
                        "TextResponse": {
                            "description": "text",
                            "content": {"text/plain; charset=UTF-8": {}},
                        }
                    }
                },
                "paths": {
                    "/api/v1/ranged": {
                        "get": {
                            "responses": {
                                "2XX": {"$ref": "#/components/responses/TextResponse"},
                                "x-runtime-note": {"owner": "contract"},
                            }
                        }
                    }
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    candidate = generate_web_schema.generate_operation_contracts_bytes(
        snapshot_path=snapshot,
    ).decode()

    assert '"2XX": ["text/plain;charset=utf-8"]' in candidate
    assert "x-runtime-note" not in candidate


def test_runtime_response_contracts_reject_cyclic_response_refs(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "v1.json"
    snapshot.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "T", "version": "1"},
                "components": {
                    "responses": {
                        "First": {"$ref": "#/components/responses/Second"},
                        "Second": {"$ref": "#/components/responses/First"},
                    }
                },
                "paths": {
                    "/api/v1/cycle": {
                        "get": {
                            "responses": {
                                "200": {"$ref": "#/components/responses/First"}
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(generate_web_schema.CodegenError, match="cyclic response ref"):
        generate_web_schema.generate_operation_contracts_bytes(
            snapshot_path=snapshot,
        )


def test_runtime_contracts_support_paths_extensions_and_local_path_item_refs(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "v1.json"
    snapshot.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "T", "version": "1"},
                "components": {
                    "pathItems": {
                        "Status": {
                            "get": {
                                "responses": {
                                    "200": {
                                        "description": "ok",
                                        "content": {"application/json": {}},
                                    }
                                }
                            }
                        }
                    }
                },
                "paths": {
                    "x-owner": {"team": "contract"},
                    "/api/v1/status": {"$ref": "#/components/pathItems/Status"},
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    candidate = generate_web_schema.generate_operation_contracts_bytes(
        snapshot_path=snapshot,
    ).decode()

    assert '"get /api/v1/status"' in candidate
    assert "x-owner" not in candidate


def test_runtime_request_contracts_bind_declared_parameter_locations(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "v1.json"
    snapshot.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "T", "version": "1"},
                "components": {
                    "parameters": {
                        "Limit": {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer"},
                        }
                    }
                },
                "paths": {
                    "/api/v1/items/{item_id}": {
                        "parameters": [
                            {
                                "name": "X-Tenant",
                                "in": "header",
                                "required": True,
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "item_id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            },
                        ],
                        "get": {
                            "parameters": [{"$ref": "#/components/parameters/Limit"}],
                            "responses": {
                                "200": {
                                    "description": "ok",
                                    "content": {"application/json": {}},
                                }
                            },
                        },
                    }
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    candidate = generate_web_schema.generate_operation_contracts_bytes(
        snapshot_path=snapshot,
    ).decode()

    assert "export const operationRequestContracts" in candidate
    assert '"header": ["X-Tenant"]' in candidate
    assert '"path": ["item_id"]' in candidate
    assert '"query": ["limit"]' in candidate


def test_runtime_contracts_reject_cyclic_path_item_refs(tmp_path: Path) -> None:
    snapshot = tmp_path / "v1.json"
    snapshot.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "T", "version": "1"},
                "components": {
                    "pathItems": {
                        "First": {"$ref": "#/components/pathItems/Second"},
                        "Second": {"$ref": "#/components/pathItems/First"},
                    }
                },
                "paths": {"/api/v1/cycle": {"$ref": "#/components/pathItems/First"}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(generate_web_schema.CodegenError, match="cyclic path item ref"):
        generate_web_schema.generate_operation_contracts_bytes(
            snapshot_path=snapshot,
        )
