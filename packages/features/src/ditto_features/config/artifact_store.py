"""Features and factors artifact storage configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class FeatureArtifactStoreSettings(BaseModel):
    """Features 层产物存储路径配置."""

    model_config = ConfigDict(extra="ignore")

    data_root: Path = Field(default=Path("data"), description="数据根目录")

    @property
    def features_technical_price_path(self) -> Path:
        """技术特征（价格）路径。"""
        return self.data_root / "features" / "technical" / "price"

    @property
    def features_technical_indicators_narrow_path(self) -> Path:
        """技术指标窄表路径。"""
        return self.data_root / "features" / "technical" / "indicators_narrow"

    @property
    def features_technical_indicators_wide_path(self) -> Path:
        """技术指标宽表路径。"""
        return self.data_root / "features" / "technical" / "indicators_wide"

    @property
    def factors_narrow_style_path(self) -> Path:
        """窄风格因子路径。"""
        return self.data_root / "factors" / "narrow" / "style"

    @property
    def factors_wide_style_path(self) -> Path:
        """宽风格因子路径。"""
        return self.data_root / "factors" / "wide" / "style"

    @property
    def factors_narrow_path(self) -> Path:
        """因子窄表路径。"""
        return self.data_root / "factors" / "factors_narrow"

    @property
    def factors_wide_path(self) -> Path:
        """因子宽表路径。"""
        return self.data_root / "factors" / "factors_wide"

    def all_directories(self) -> list[str]:
        """返回 Features 层拥有的产物目录（相对于 data_root）。"""
        return [
            "features/technical/price",
            "features/technical/indicators_narrow",
            "features/technical/indicators_wide",
            "factors/narrow/style",
            "factors/wide/style",
            "factors/factors_narrow",
            "factors/factors_wide",
        ]


__all__ = ["FeatureArtifactStoreSettings"]
