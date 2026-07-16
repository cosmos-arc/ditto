"""Resolve a manual intent's opening baseline from its Signal Package identity."""

from __future__ import annotations

from typing import Protocol, cast

from ditto_execution.models import SignalRecord
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord

from ditto_application.exceptions import AppCommandError
from ditto_application.opening_baseline import OpeningBaseline
from ditto_application.queries.account import AccountBaselineQuery

__all__ = ["OpeningBaselineResolver", "SignalPackageIdentityReader"]


class SignalPackageIdentityReader(Protocol):
    """Narrow reader required to recover one intent's execution identity."""

    def list_by_strategy(self, strategy_id: str) -> list[StrategyArtifactRecord]:
        """List persisted artifacts for one strategy."""
        ...


class OpeningBaselineResolver:
    """Bind an intent to one complete account baseline through its Signal Package."""

    def __init__(
        self,
        *,
        account_query: AccountBaselineQuery,
        package_reader: SignalPackageIdentityReader,
    ) -> None:
        self._account_query = account_query
        self._package_reader = package_reader

    def resolve(self, intent: SignalRecord) -> OpeningBaseline:
        """Return the latest complete opening aggregate at or before signal date."""
        identities = self._package_identities(intent)
        if not identities:
            raise AppCommandError(
                f"Opening baseline identity missing for intent: {intent.intent_id}"
            )
        if len(identities) > 1:
            raise AppCommandError(
                f"Opening baseline has multiple sleeves for intent: {intent.intent_id}"
            )
        account_id, sleeve_id = next(iter(identities))
        expected_sleeve = f"manual-{account_id}-{intent.strategy_id}"
        if sleeve_id != expected_sleeve:
            raise AppCommandError(
                f"Opening baseline sleeve identity mismatch: {sleeve_id}"
            )
        baseline = self._account_query.get_latest(
            account_id=account_id,
            strategy_id=intent.strategy_id,
            signal_date=intent.signal_date,
        )
        if baseline is None:
            raise AppCommandError(
                f"Complete opening baseline missing for intent: {intent.intent_id}"
            )
        account = baseline.account
        if account.run_id != sleeve_id or account.account_id != account_id:
            raise AppCommandError(
                f"Opening baseline aggregate identity mismatch: {account.snapshot_id}"
            )
        return OpeningBaseline(account=account, positions=baseline.positions)

    def _package_identities(self, intent: SignalRecord) -> set[tuple[str, str]]:
        identities: set[tuple[str, str]] = set()
        for artifact in self._package_reader.list_by_strategy(intent.strategy_id):
            if not _contains_intent(artifact, intent):
                continue
            account_id = _nonblank(artifact.metadata.get("account_id"))
            sleeve_id = _nonblank(artifact.metadata.get("sleeve_id"))
            if account_id is None or sleeve_id is None:
                raise AppCommandError(
                    f"Signal Package identity invalid for intent: {intent.intent_id}"
                )
            identities.add((account_id, sleeve_id))
        return identities


def _contains_intent(
    artifact: StrategyArtifactRecord,
    intent: SignalRecord,
) -> bool:
    if (
        artifact.artifact_type != ArtifactKind.SIGNAL_PACKAGE
        or artifact.status != "active"
        or artifact.metadata.get("strategy_id") != intent.strategy_id
        or artifact.metadata.get("signal_date") != intent.signal_date
    ):
        return False
    raw_intents = artifact.metadata.get("intents")
    if not isinstance(raw_intents, list | tuple):
        return False
    intent_entries = cast(list[object] | tuple[object, ...], raw_intents)
    return any(_matches_intent_entry(raw, intent.intent_id) for raw in intent_entries)


def _matches_intent_entry(value: object, intent_id: str) -> bool:
    if not isinstance(value, dict):
        return False
    entry = cast(dict[str, object], value)
    return entry.get("intent_id") == intent_id


def _nonblank(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
