"""Shared conftest for execution unit tests — puts this dir on sys.path so test
helper modules can be imported under --import-mode=importlib."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
