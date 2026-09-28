"""
Shared test-selection expressions (single source for every consumer).

The fast lane selects by resource and journey cost — slow, serial,
snapshot, sandbox_live, capacity, e2e — never by the unit/integration
layer: a genuinely cheap, parallel-safe integration test stays in the
quick lane when its layer changes (#330 B1). ``scripts/test.py --fast``
and the harness owner-coverage probe import the same constant.
"""

FAST_LANE_EXPR = (
    "not slow and not serial and not e2e"
    " and not snapshot and not sandbox_live and not capacity"
)
