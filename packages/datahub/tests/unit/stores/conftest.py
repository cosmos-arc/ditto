"""Pytest configuration for stores tests."""

# Configure coverage to avoid issues with polars fixtures
import sys

# Add the test directory to the path
sys.path.insert(0, str(__file__).replace("/conftest.py", ""))
