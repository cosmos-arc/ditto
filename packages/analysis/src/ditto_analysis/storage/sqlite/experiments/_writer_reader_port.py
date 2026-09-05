"""Narrow reader port shared by the SQLite experiment writer mixins."""

from __future__ import annotations

from typing import Protocol

from ditto_analysis.experiments.models import ExperimentId
from ditto_analysis.experiments.specs import ExperimentLaunchSpec
from ditto_analysis.research._indexed_artifacts import ArtifactIndexReader


class SQLiteExperimentWriterReaderPort(ArtifactIndexReader, Protocol):
    """Expose only the reads required while composing experiment writes."""

    def get_launch_spec(
        self, experiment_id: ExperimentId
    ) -> ExperimentLaunchSpec | None: ...


class SQLiteExperimentWriterReaderState:
    """Declare the reader dependency shared by SQLite writer mixins."""

    _reader: SQLiteExperimentWriterReaderPort
