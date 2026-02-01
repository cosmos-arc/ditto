"""
Features Domain - 技术指标与衍生特征域.

提供技术指标数据（趋势、动量、波动率、成交量等）的存储和查询,
支持灵活的特征工程和因子计算.

命名映射:
- sid: Security ID
- indicator_id: 指标唯一标识符 (如 'indicator_rsi_14')
- indicator_type: 指标类型 (trend/momentum/volatility/volume)
- value: 指标值
"""

from ditto_datahub.domains.features.feature_service import (
    FeatureQuery,
    FeatureService,
)
from ditto_datahub.domains.features.technical import (
    IndicatorMetadataStore,
    IndicatorStore,
)

__all__ = [
    "FeatureQuery",
    "FeatureService",
    "IndicatorMetadataStore",
    "IndicatorStore",
]
