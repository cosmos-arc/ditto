"""
向后兼容别名：domains → stores

⚠️ 已废弃：请使用 from ditto_datahub.stores import ...
   此模块将在 v0.15.0 版本移除。

迁移说明:
- Market 域: from ditto_datahub.stores.market import ...
- Metadata 域: from ditto_datahub.stores.metadata import ...
- Fundamental 域: from ditto_datahub.stores.fundamental import ...
- Capital 域: from ditto_datahub.stores.capital import ...
- Macro 域: from ditto_datahub.stores.macro import ...
- Factors 域: from ditto_datahub.stores.factors import ...
- Features 域: from ditto_datahub.stores.features import ...
"""

import warnings

# 导入所有 Store（使用别名保持向后兼容）
from ditto_datahub.stores import *  # noqa: F403

warnings.warn(
    (
        "ditto_datahub.domains 已废弃, 请使用 ditto_datahub.stores. "
        "此别名将在 v0.15.0 版本移除."
    ),
    DeprecationWarning,
    stacklevel=2,
)
