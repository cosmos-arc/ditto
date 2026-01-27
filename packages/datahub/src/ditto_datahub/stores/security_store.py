"""
SecurityStore for securities master data with PIT support.

⚠️ DEPRECATED: 此模块已迁移到 domains/metadata/security/security_store.py

请使用新的导入路径：
    from ditto_datahub.domains.metadata.security import SecurityStore

此文件保留用于向后兼容，将在未来版本中移除。
"""

import warnings

warnings.warn(
    "SecurityStore 已迁移到 ditto_datahub.domains.metadata.security",
    DeprecationWarning,
    stacklevel=2,
)

# 从新位置导入
from ditto_datahub.domains.metadata.security.security_store import (  # noqa: E402
    SecurityRegistration,
    SecurityStore,
)

__all__ = ["SecurityRegistration", "SecurityStore"]
