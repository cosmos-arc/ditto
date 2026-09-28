"""Repository-root pytest wiring shared by every collection entry.

The layering plugin is registered here rather than through ``addopts`` so
single-file, owner, full-tree and CI shard entries stay identical even when
a subsystem rebuilds addopts from scratch with ``-o addopts=`` (#330 B1).
"""

pytest_plugins = ["tooling.quality.pytest_layering"]
