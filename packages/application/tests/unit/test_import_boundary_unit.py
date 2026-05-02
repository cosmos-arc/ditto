import sys


def test_application_imports_successfully() -> None:
    import ditto_application

    assert ditto_application.__version__ == "0.1.0"


def test_application_does_not_import_entry_packages() -> None:
    import ditto_application  # noqa: F401

    loaded = {m for m in sys.modules if m.startswith("ditto_") and m != "ditto_application"}
    forbidden_prefixes = ("ditto_apps",)
    forbidden = {m for m in loaded if any(m == p or m.startswith(p + ".") for p in forbidden_prefixes)}
    assert not forbidden, f"Application imported forbidden packages: {sorted(forbidden)}"
