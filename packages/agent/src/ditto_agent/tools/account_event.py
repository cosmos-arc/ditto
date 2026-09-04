"""Privacy-minimal read-only Manual Account event evidence tool."""

from __future__ import annotations

from collections.abc import Mapping
from zoneinfo import ZoneInfo

from ditto_application.queries.account_event_evidence_contracts import (
    AccountEventEvidenceQueryPort,
    AccountEventEvidenceRedaction,
)

from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import EgressClass, TemporalToolContext
from ditto_agent.models.port import ModelToolSpec
from ditto_agent.tools._common import (
    Arguments,
    application_context,
    function_spec,
    seal_account_event_evidence,
)

_SHANGHAI = ZoneInfo("Asia/Shanghai")


class AccountEventEvidenceTool:
    """Expose exact Manual ledger facts after host-selected redaction."""

    spec: ModelToolSpec = function_spec(
        name="account_event_evidence",
        description=(
            "Read the exact as-of Manual Account event stream. Private notes, "
            "operator identifiers, attachments, and broker references are omitted."
        ),
        properties={"account_id": {"type": "string", "minLength": 1}},
        required=("account_id",),
    )

    def __init__(self, *, facade: AccountEventEvidenceQueryPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Derive date/privacy from trusted host context, never model arguments."""
        if context.egress_class is EgressClass.PROHIBITED:
            raise PermissionError("Manual Account evidence egress is prohibited")
        parsed = Arguments(arguments, required=("account_id",))
        redaction = (
            AccountEventEvidenceRedaction.CLOUD_REDACTED
            if context.egress_class is EgressClass.CLOUD_ALLOWED
            else AccountEventEvidenceRedaction.LOCAL_DETAIL
        )
        as_of = context.knowledge_cutoff.astimezone(_SHANGHAI).date().isoformat()
        read_model = self._facade.get_evidence(
            account_id=parsed.text("account_id"),
            as_of=as_of,
            redaction=redaction,
            context=application_context(context),
        )
        return seal_account_event_evidence(
            tool_name=self.spec.name,
            read_model=read_model,
            context=context,
        )


__all__ = ["AccountEventEvidenceTool"]
