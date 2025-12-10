"""Pydantic models for ETF-related data contracts."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Constants for ETF validation
MIN_SYMBOL_LENGTH = 6
MIN_NAME_LENGTH = 2


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
        if not v or len(v) < MIN_SYMBOL_LENGTH:
            raise ValueError(
                f"ETF symbol must be at least {MIN_SYMBOL_LENGTH} characters"
            )
        return v.upper()

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate ETF name."""
        if not v or len(v.strip()) < MIN_NAME_LENGTH:
            raise ValueError(f"ETF name must be at least {MIN_NAME_LENGTH} characters")
        return v.strip()

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",  # Forbid extra fields
    )
