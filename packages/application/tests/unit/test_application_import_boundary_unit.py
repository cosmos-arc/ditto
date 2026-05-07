import sys


def test_application_imports_successfully() -> None:
    import ditto_application

    assert ditto_application.__name__ == "ditto_application"


def test_application_does_not_import_entry_packages() -> None:
    before = set(sys.modules)
    import ditto_application  # noqa: F401

    new_modules = set(sys.modules) - before
    forbidden_prefixes = ("ditto_apps",)
    forbidden = {
        m
        for m in new_modules
        if any(m == p or m.startswith(p + ".") for p in forbidden_prefixes)
    }
    assert not forbidden, (
        f"Application imported forbidden packages: {sorted(forbidden)}"
    )
