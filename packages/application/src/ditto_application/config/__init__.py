"""
Dataset configuration registry for data ingestion.

从 ditto_apps.models.config 提取至此，供 app 层直接引用，
无需依赖 port/interfaces。

This module defines the central registry of all datasets with their configuration,
including task tier, dependencies, and task mappings.

The registry enables:
1. Dynamic task generation based on tier
2. Dependency-aware execution orchestration
3. Type-safe dataset references
4. Consistent configuration across ingestion system
"""

from __future__ import annotations

from ditto_application.config.helpers import now_iso
from ditto_application.config.ingestion_scope import (
    IngestionScope,
    resolve_ingestion_scope,
)
from ditto_application.config.queries import (
    INGESTION_SPECS,
    get_all_datasets,
    get_dataset_config,
    get_dataset_config_by_value,
    get_datasets_by_tier,
    get_parallel_datasets,
)
from ditto_application.config.specs import (
    DEFAULT_INITIAL_CASH,
    DatasetRef,
    DatasetSpec,
    T1ConfigSpec,
    TaskTier,
    create_t0_config,
    create_t1_config,
)

__all__ = [
    "DEFAULT_INITIAL_CASH",
    "INGESTION_SPECS",
    "DatasetRef",
    "DatasetSpec",
    "IngestionScope",
    "T1ConfigSpec",
    "TaskTier",
    "create_t0_config",
    "create_t1_config",
    "get_all_datasets",
    "get_dataset_config",
    "get_dataset_config_by_value",
    "get_datasets_by_tier",
    "get_parallel_datasets",
    "now_iso",
    "resolve_ingestion_scope",
]
