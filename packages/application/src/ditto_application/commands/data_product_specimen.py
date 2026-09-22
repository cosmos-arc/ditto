"""Application boundary for append-only adjudicated data specimens."""

from __future__ import annotations

from typing import Any

from ditto_data.catalog.specimen import DataSpecimen, SpecimenWriter

from ditto_application.exceptions import AppCommandError

__all__ = ["DataProductSpecimenCommands"]


class DataProductSpecimenCommands:
    """Validate one human adjudication and append it immutably."""

    def __init__(self, writer: SpecimenWriter) -> None:
        self._writer = writer

    def record(self, payload: dict[str, Any]) -> DataSpecimen:
        """Record one adjudicated specimen; invalid claims fail closed."""
        try:
            specimen = DataSpecimen.from_payload(payload)
            self._writer.append_specimen(specimen)
        except (KeyError, TypeError, ValueError) as error:
            raise AppCommandError(
                f"invalid specimen adjudication: {error}",
                command="record_data_specimen",
            ) from error
        return specimen
