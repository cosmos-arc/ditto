"""Fork-safe Ditto API server entrypoint."""

from granian.cli import entrypoint as granian_entrypoint

from ditto_apps.registry.infra.config import preload_runtime_secrets


def main() -> None:
    """Load Keychain credentials in the parent, then delegate to Granian."""
    preload_runtime_secrets()
    granian_entrypoint()


if __name__ == "__main__":  # pragma: no cover - exercised by process smoke tests
    main()
