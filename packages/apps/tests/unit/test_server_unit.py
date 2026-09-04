"""Fork-safe API server entrypoint tests."""

from ditto_apps import server


def test_server_preloads_secrets_before_granian(monkeypatch) -> None:
    events: list[str] = []
    monkeypatch.setattr(
        server,
        "preload_runtime_secrets",
        lambda: events.append("preload"),
    )
    monkeypatch.setattr(
        server,
        "granian_entrypoint",
        lambda: events.append("serve"),
    )

    server.main()

    assert events == ["preload", "serve"]
