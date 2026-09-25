"""Evidence-bound comparison of one saved ETF target with one account ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, cast

from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.portfolio_comparison import (
    NormalizedPortfolio,
    PortfolioComparisonError,
    PortfolioDriftView,
    compare_portfolio_pair,
    normalize_portfolio,
)
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.portfolio_comparison import PortfolioComparisonRequest
from ditto_application.queries.portfolio_comparison_source import (
    account_valuation,
    context,
    model_valuation,
    valuation_prices,
    valuation_snapshot_id,
)
from ditto_application.queries.technical_analysis import TechnicalAnalysisSourcePort


@dataclass(frozen=True, kw_only=True)
class ETFAllocationReviewRequest:
    """The exact target, ledger, date, and market evidence to compare."""

    allocation_id: str
    version_id: str
    account_kind: Literal["paper", "manual"]
    account_id: str
    as_of: str
    knowledge_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class ETFAllocationReviewView:
    """Server-calculated target and actual values at one PIT cutoff."""

    allocation_id: str
    version_id: str
    account_kind: str
    account_id: str
    as_of: str
    knowledge_cutoff: str
    valuation_snapshot_id: str
    source_snapshot_ids: tuple[str, ...]
    ledger_hash: str
    target: NormalizedPortfolio
    actual: NormalizedPortfolio
    drift: PortfolioDriftView
    target_exposure: dict[str, str]
    actual_exposure: dict[str, str]
    unknown_exposure_instrument_ids: tuple[int, ...]


def _saved_version(
    artifacts: StrategyArtifactService, request: ETFAllocationReviewRequest
) -> StrategyArtifactRecord:
    version = artifacts.get_artifact(request.version_id)
    if (
        version is None
        or version.strategy_id != f"etf-allocation:{request.allocation_id}"
        or version.artifact_type is not ArtifactKind.TARGET_PORTFOLIO
        or version.metadata.get("kind") != "etf_allocation"
    ):
        raise AppQueryError(
            "ETF version was not found", code="ETF_REVIEW_VERSION_NOT_FOUND"
        )
    return version


def _saved_cutoff(saved_target: dict[str, object]) -> datetime:
    """Parse the saved evidence cutoff or fail closed; it bounds visibility."""
    try:
        cutoff = datetime.fromisoformat(
            str(saved_target.get("knowledge_cutoff")).replace("Z", "+00:00")
        )
    except (TypeError, ValueError) as exc:
        raise AppQueryError(
            "saved ETF knowledge cutoff is invalid", code="ETF_REVIEW_TARGET_INVALID"
        ) from exc
    if cutoff.tzinfo is None:
        raise AppQueryError(
            "saved ETF knowledge cutoff needs a timezone",
            code="ETF_REVIEW_TARGET_INVALID",
        )
    return cutoff


def _actual_indexes(
    metadata: MetadataQueryFacade,
    saved_target: dict[str, object],
    as_of: str,
) -> dict[int, str]:
    if as_of != saved_target["asof"]:
        return {}
    candidates = metadata.list_etf_candidates(
        asof=as_of,
        cutoff=str(saved_target["knowledge_cutoff"]),
        source_snapshot_id=str(saved_target["source_snapshot_id"]),
    )
    return {
        item.instrument_id: tracking.value
        for item in candidates
        if (tracking := item.fields.get("tracking_index")) is not None
        and isinstance(tracking.value, str)
    }


class GetETFAllocationReviewQuery:
    """Reuse portfolio comparison valuation and normalization for an ETF version."""

    def __init__(
        self,
        *,
        artifacts: StrategyArtifactService,
        accounts: AccountLedgerQuery,
        metadata: MetadataQueryFacade,
        snapshots: ProviderSnapshotReader,
        valuation: TechnicalAnalysisSourcePort,
    ) -> None:
        self._artifacts = artifacts
        self._accounts = accounts
        self._metadata = metadata
        self._snapshots = snapshots
        self._valuation = valuation

    def get(self, request: ETFAllocationReviewRequest) -> ETFAllocationReviewView:
        """Return a comparison only when all required evidence is visible."""
        if not request.source_snapshot_ids or len(
            set(request.source_snapshot_ids)
        ) != len(request.source_snapshot_ids):
            raise AppQueryError(
                "one or more distinct price snapshots are required",
                code="ETF_REVIEW_SNAPSHOTS_INVALID",
            )
        if request.knowledge_cutoff.tzinfo is None:
            raise AppQueryError(
                "knowledge cutoff needs a timezone", code="ETF_REVIEW_CUTOFF_INVALID"
            )
        version = _saved_version(self._artifacts, request)
        saved_target = version.metadata
        target_asof = str(saved_target["asof"])
        # The saved weights were selected under the saved knowledge cutoff, so
        # a review cutoff must cover both the version creation and that cutoff;
        # otherwise the review would admit evidence the cutoff has not seen.
        if (
            request.as_of < target_asof
            or request.knowledge_cutoff
            < datetime.fromisoformat(version.created_at.replace("Z", "+00:00"))
            or request.knowledge_cutoff < _saved_cutoff(saved_target)
        ):
            raise AppQueryError(
                "ETF target was not yet known", code="ETF_REVIEW_FUTURE_TARGET"
            )
        comparison = PortfolioComparisonRequest(
            strategy_id=f"etf-allocation:{request.allocation_id}",
            model_portfolio_id=version.artifact_id,
            paper_account_id=request.account_id
            if request.account_kind == "paper"
            else "not-selected",
            manual_account_id=request.account_id
            if request.account_kind == "manual"
            else "not-selected",
            paper_session_id="not-selected",
            as_of=request.as_of,
            knowledge_cutoff=request.knowledge_cutoff,
            publication_cutoff=request.knowledge_cutoff,
            source_snapshot_ids=request.source_snapshot_ids,
        )
        account_query = (
            self._accounts.get_paper
            if request.account_kind == "paper"
            else self._accounts.get_manual
        )
        unvalued = account_query(
            account_id=request.account_id,
            as_of=request.as_of,
            recorded_through=request.knowledge_cutoff,
        )
        saved_weights = saved_target["weights"]
        if not isinstance(saved_weights, dict):
            raise AppQueryError(
                "saved ETF weights are invalid", code="ETF_REVIEW_TARGET_INVALID"
            )
        weight_values = cast("dict[str, object]", saved_weights)
        weights = {
            int(instrument_id): Decimal(str(weight))
            for instrument_id, weight in weight_values.items()
        }
        # Only positive target weights need prices of their own: a zero-weight
        # ETF that the account does not hold contributes nothing to either
        # valuation and must not fail the whole review on a missing price.
        instrument_ids = tuple(
            sorted(
                {id_ for id_, weight in weights.items() if weight > 0}
                | {
                    int(position.instrument_id)
                    for position in unvalued.snapshot.positions
                }
            )
        )
        pit_context = context(comparison, self._snapshots)
        sources = {
            snapshot.source
            for snapshot_id in request.source_snapshot_ids
            if (snapshot := self._snapshots.get_snapshot(snapshot_id)) is not None
        }
        if len(sources) != 1:
            raise AppQueryError(
                "price snapshots must share one provider source",
                code="ETF_REVIEW_SOURCE_MIXED",
            )
        source = next(iter(sources))
        instrument_codes = {
            instrument_id: self._metadata.get_source_ticker(
                instrument_id,
                source=source,
                asof=request.as_of,
                # The provider identity itself is PIT evidence: a mapping
                # recorded after the cutoff must stay invisible so a
                # corrected identity cannot select a different price row.
                cutoff=request.knowledge_cutoff.isoformat(),
            )
            or str(instrument_id)
            for instrument_id in instrument_ids
        }
        price_rows = valuation_prices(
            self._valuation, pit_context, instrument_ids, instrument_codes
        )
        prices = {InstrumentId(row.instrument_id): row.price for row in price_rows}
        computed_snapshot_id = valuation_snapshot_id(comparison, price_rows)
        valued = account_query(
            account_id=request.account_id,
            as_of=request.as_of,
            valuation_prices=prices,
            recorded_through=request.knowledge_cutoff,
        )
        if not valued.snapshot.valuation_complete or valued.snapshot.total_value <= 0:
            raise AppQueryError(
                "account valuation is incomplete",
                code="ETF_REVIEW_VALUATION_INCOMPLETE",
            )
        try:
            actual = normalize_portfolio(
                account_valuation(
                    valued.snapshot,
                    kind=request.account_kind,
                    valuation_snapshot_id=computed_snapshot_id,
                    source_snapshot_ids=request.source_snapshot_ids,
                )
            )
            target = normalize_portfolio(
                model_valuation(
                    request=comparison,
                    # Zero-weight entries enter the target only when their
                    # price was fetched anyway (i.e. the account holds them).
                    weights={
                        id_: weight
                        for id_, weight in weights.items()
                        if weight > 0 or id_ in {int(key) for key in prices}
                    },
                    prices={int(key): value for key, value in prices.items()},
                    reference_total=valued.snapshot.total_value,
                    valuation_snapshot_id=computed_snapshot_id,
                )
            )
            drift = compare_portfolio_pair(target, actual)
        except PortfolioComparisonError as exc:
            raise AppQueryError(
                str(exc), code="ETF_REVIEW_NORMALIZATION_INVALID"
            ) from exc
        # The saved reference proves index identity on its research date only.
        # Later account dates need another dated reference; keep exposure unknown.
        index_by_id = _actual_indexes(self._metadata, saved_target, request.as_of)
        exposure: dict[str, Decimal] = {}
        unknown: list[int] = []
        for position in actual.positions:
            index = index_by_id.get(position.instrument_id)
            if not isinstance(index, str) or not index:
                unknown.append(position.instrument_id)
                continue
            exposure[index] = exposure.get(index, Decimal("0")) + position.weight
        return ETFAllocationReviewView(
            allocation_id=request.allocation_id,
            version_id=version.artifact_id,
            account_kind=request.account_kind,
            account_id=request.account_id,
            as_of=request.as_of,
            knowledge_cutoff=request.knowledge_cutoff.isoformat(),
            valuation_snapshot_id=computed_snapshot_id,
            source_snapshot_ids=request.source_snapshot_ids,
            ledger_hash=valued.snapshot.ledger_hash,
            target=target,
            actual=actual,
            drift=drift,
            target_exposure={
                str(key): str(value)
                for key, value in cast(
                    "dict[str, object]", saved_target["tracking_exposure"]
                ).items()
            },
            actual_exposure={
                key: str(value.quantize(Decimal("0.00000001")))
                for key, value in sorted(exposure.items())
            },
            unknown_exposure_instrument_ids=tuple(sorted(unknown)),
        )
