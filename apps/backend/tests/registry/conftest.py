"""Registry tests use deterministic secrets without accessing the host keychain."""

from collections.abc import Iterator

import keyring
import pytest
from keyring.backends.null import Keyring


@pytest.fixture(autouse=True)
def isolated_keyring() -> Iterator[None]:
    """Keep real config-provider wiring while replacing only system secret I/O."""
    original = keyring.get_keyring()
    keyring.set_keyring(Keyring())
    try:
        yield
    finally:
        keyring.set_keyring(original)
