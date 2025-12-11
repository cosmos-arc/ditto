"""
Data quality reporting module for Ditto.

This module provides the DataQualityReporter class which generates
comprehensive quality reports for financial market data.
"""

from datetime import datetime
from typing import Any

import polars as pl

from ..validators.base import BaseValidator, ValidationResult
from ..validators.price import PriceValidator
from ..validators.volume import VolumeValidator

# Quality score thresholds
EXCELLENT_THRESHOLD = 0.9
GOOD_THRESHOLD = 0.7
FAIR_THRESHOLD = 0.5


class DataQualityReporter:
    """
    Data quality report generator.

    Uses configured validators to perform comprehensive quality checks on data,
    and generates detailed quality reports including scores and specific metrics.

    Attributes:
        validators: List of validators for checking different dimensions of data quality

    """

    def __init__(self, validators: list[BaseValidator] | None = None) -> None:
        """
        Initialize DataQualityReporter.

        Args:
            validators: Optional list of validators. If None, uses default validators.

        """
        # Use provided validators or default to PriceValidator and VolumeValidator
        self.validators: list[BaseValidator] = validators or [
            PriceValidator(),
            VolumeValidator(),
        ]

    def generate_report(self, data: pl.DataFrame, symbol: str) -> dict[str, Any]:
        """
        Generate data quality report for a single symbol.

        Performs checks on the input data using all configured validators,
        and summarizes the results into a quality report.

        Args:
            data: DataFrame containing market data, should include OHLCV fields
            symbol: Symbol code (e.g. "510300.SH")

        Returns:
            Dictionary containing:
            - symbol: Symbol code
            - timestamp: Report generation time (ISO format)
            - total_records: Total number of records
            - date_range: Data date range {"start": start_date, "end": end_date}
            - validators: Detailed results from each validator
            - summary: Validation summary with passed/failed/warnings counts
            - quality_score: Overall quality score (float between 0-1)

        """
        # Initialize report structure
        report: dict[str, Any] = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "total_records": len(data),
            "date_range": {},
            "validators": [],
            "summary": {"passed": 0, "failed": 0, "warnings": 0},
            "quality_score": 0.0,
        }

        # Handle empty data
        if len(data) == 0:
            report["summary"]["failed"] = len(self.validators)
            report["quality_score"] = 0.0
            report["validators"] = [
                {
                    "name": validator.name,
                    "status": "failed",
                    "message": "数据为空",
                    "details": {"error": "No data to validate"},
                }
                for validator in self.validators
            ]
            return report

        # Extract date range if date column exists
        if "date" in data.columns:
            report["date_range"] = {
                "start": data["date"].min(),
                "end": data["date"].max(),
            }

        # Run all validators
        for validator in self.validators:
            try:
                result: ValidationResult = validator.validate(data)

                # Convert ValidationResult to report format
                validator_report: dict[str, Any] = {
                    "name": validator.name,
                    "status": "passed" if result.is_valid else "failed",
                    "message": result.message,
                    "details": result.details,
                }

                report["validators"].append(validator_report)

                # Update summary
                if result.is_valid:
                    report["summary"]["passed"] += 1
                else:
                    report["summary"]["failed"] += 1

            except Exception as e:
                # Handle validator errors gracefully
                validator_report = {
                    "name": validator.name,
                    "status": "failed",
                    "message": f"验证器执行错误: {e!s}",
                    "details": {"error": str(e)},
                }
                report["validators"].append(validator_report)
                report["summary"]["failed"] += 1

        # Calculate overall quality score
        total_validators = len(self.validators)
        if total_validators > 0:
            report["quality_score"] = report["summary"]["passed"] / total_validators

        return report

    def generate_batch_report(
        self, data_dict: dict[str, pl.DataFrame]
    ) -> dict[str, Any]:
        """
        Generate batch data quality reports for multiple symbols.

        Performs quality checks on each DataFrame in the dictionary,
        and generates a summary report.

        Args:
            data_dict: Mapping from symbol code to DataFrame,
                      e.g. {"510300.SH": df1, "516010.SH": df2}

        Returns:
            Dictionary containing:
            - timestamp: Report generation time (ISO format)
            - total_symbols: Total number of symbols checked
            - reports: List of detailed reports for each symbol
            - summary: Batch processing summary including:
              * total_records: Total records across all symbols
              * avg_quality_score: Average quality score
              * failed_symbols: List of symbols with issues
              * score_distribution: Quality score distribution statistics

        """
        # Initialize batch report structure
        batch_report: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "total_symbols": len(data_dict),
            "reports": [],
            "summary": {
                "total_records": 0,
                "avg_quality_score": 0.0,
                "failed_symbols": [],
                "score_distribution": {
                    "excellent": 0,  # 0.9-1.0
                    "good": 0,  # 0.7-0.9
                    "fair": 0,  # 0.5-0.7
                    "poor": 0,  # <0.5
                },
            },
        }

        # Track statistics for summary
        total_quality_score = 0.0
        score_list: list[float] = []

        # Generate report for each symbol
        for symbol, data in data_dict.items():
            # Generate individual report
            report = self.generate_report(data, symbol)
            batch_report["reports"].append(report)

            # Update summary statistics
            batch_report["summary"]["total_records"] += report["total_records"]
            total_quality_score += report["quality_score"]
            score_list.append(report["quality_score"])

            # Track failed symbols
            if report["summary"]["failed"] > 0:
                batch_report["summary"]["failed_symbols"].append(symbol)

        # Calculate averages and distributions
        if len(data_dict) > 0:
            # Average quality score
            batch_report["summary"]["avg_quality_score"] = total_quality_score / len(
                data_dict
            )

            # Score distribution
            for score in score_list:
                if score >= EXCELLENT_THRESHOLD:
                    batch_report["summary"]["score_distribution"]["excellent"] += 1
                elif score >= GOOD_THRESHOLD:
                    batch_report["summary"]["score_distribution"]["good"] += 1
                elif score >= FAIR_THRESHOLD:
                    batch_report["summary"]["score_distribution"]["fair"] += 1
                else:
                    batch_report["summary"]["score_distribution"]["poor"] += 1

        return batch_report

    def add_validator(self, validator: BaseValidator) -> None:
        """
        Add a new validator to the reporter.

        Args:
            validator: Validator instance to add

        """
        self.validators.append(validator)

    def remove_validator(self, validator_name: str) -> bool:
        """
        Remove validator by name.

        Args:
            validator_name: Name of the validator to remove

        Returns:
            Whether the validator was successfully removed

        """
        for i, validator in enumerate(self.validators):
            if validator.name == validator_name:
                self.validators.pop(i)
                return True
        return False

    def list_validators(self) -> list[str]:
        """
        Get list of all validator names.

        Returns:
            List of validator names

        """
        return [validator.name for validator in self.validators]
