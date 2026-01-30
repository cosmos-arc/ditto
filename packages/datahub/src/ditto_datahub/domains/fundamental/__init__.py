"""
Fundamental Domain - 企业基本面数据域。

提供财务报表、分红、公司行为、业绩预告等数据的存储和查询，
支持完整的 PIT（Point-in-Time）能力。

命名映射：
- instrument_id: 标的 ID（统一标识符）
- PIT 时间: effective_from, effective_to
"""

from ditto_datahub.domains.fundamental.fundamental_store import FundamentalStore

__all__ = ["FundamentalStore"]
