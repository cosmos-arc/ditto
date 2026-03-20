"""
Metadata 子服务包.

提供 MetadataService 的内部分解子服务，外部应通过 MetadataService 门面访问。
"""

from ditto_datahub.services.metadata.calendar import (
    CalendarService,
    compute_calendar_enrichment,
)
from ditto_datahub.services.metadata.instrument import InstrumentService, SecurityQuery
from ditto_datahub.services.metadata.universe import UniverseService

__all__ = [
    "CalendarService",
    "InstrumentService",
    "SecurityQuery",
    "UniverseService",
    "compute_calendar_enrichment",
]
