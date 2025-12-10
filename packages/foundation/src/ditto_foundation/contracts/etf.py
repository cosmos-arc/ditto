"""Pydantic models for ETF-related data contracts."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ETFInfoModel(BaseModel):
    """Pydantic model for ETF information validation."""

    symbol: str = Field(..., description="ETF symbol code")
    name: str = Field(..., description="ETF name")
    fund_manager: str | None = Field(None, description="Fund manager name")
    tracking_index: str | None = Field(None, description="Tracking index")
    establishment_date: date | None = Field(None, description="Establishment date")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """Validate ETF symbol format."""
        if not v or len(v) < 6:
            raise ValueError("ETF symbol must be at least 6 characters")
        return v.upper()

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate ETF name."""
        if not v or len(v.strip()) < 2:
            raise ValueError("ETF name must be at least 2 characters")
        return v.strip()

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",  # Forbid extra fields
    )
