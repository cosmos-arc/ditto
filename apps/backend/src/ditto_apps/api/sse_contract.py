"""OpenAPI descriptions for versioned JSON payloads inside SSE frames."""

from typing import Any

from ditto_apps.models.common import ErrorResponse


def sse_openapi_response(
    *,
    data_schema: str,
    terminal_field: str,
    terminal_values: tuple[str, ...],
) -> dict[int | str, dict[str, Any]]:
    """Bind an SSE frame's JSON data and terminal semantics into OpenAPI."""
    schema_reference = f"#/components/schemas/{data_schema}"
    return {
        200: {
            "description": "Ordered replay of persisted versioned events",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "x-ditto-sse-data-schema": {"$ref": schema_reference},
                    "x-ditto-sse-terminal": {
                        "field": terminal_field,
                        "values": list(terminal_values),
                    },
                }
            },
        },
        410: {
            "description": "Last-Event-ID is not retained by the target stream",
            "model": ErrorResponse,
        },
    }
