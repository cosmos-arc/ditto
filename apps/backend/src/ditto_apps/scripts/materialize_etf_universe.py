"""
Initialize csi_etf_broad from a reviewed, frozen registry selection.

Default is read-only. --apply uses existing domain writes, preserves all old
intervals, and resumes an interrupted identical initialization. Conflicts reject.
The selection timestamp is evidence about today's choice, never a knowledge date.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import orjson
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from ditto_apps.registry.contexts.universe import create_universe_write_context


class ETFMember(BaseModel):
    """Registry facts frozen before any return calculation."""

    model_config = ConfigDict(extra="forbid")
    instrument_id: int = Field(gt=0)
    ticker: str = Field(pattern=r"^\d{6}$")
    name: str = Field(min_length=1)
    exchange: Literal["SSE", "SZSE"]
    asset_class: Literal["etf"]
    list_date: date
    delist_date: date | None

    @model_validator(mode="after")
    def valid_interval(self) -> ETFMember:
        """Reject placeholder or reversed business dates."""
        if self.list_date < date(1990, 12, 19) or (
            self.delist_date is not None and self.delist_date <= self.list_date
        ):
            raise ValueError("unverifiable listing/exit interval")
        return self


class ETFSelection(BaseModel):
    """Finite research scope; not an official index or historical certification."""

    model_config = ConfigDict(extra="forbid")
    universe_id: Literal["csi_etf_broad"]
    name: str = Field(min_length=1)
    selected_at: AwareDatetime
    source_observed_at: AwareDatetime
    source: str = Field(min_length=1)
    selection_rule: str = Field(min_length=1)
    excluded_scope: str = Field(min_length=1)
    candidate_window: dict[str, str]
    limitations: str = Field(min_length=1)
    members: list[ETFMember] = Field(min_length=1)

    @model_validator(mode="after")
    def frozen_identity(self) -> ETFSelection:
        """Reject duplicate members and invented future observations."""
        if len({m.instrument_id for m in self.members}) != len(self.members) or len(
            {(m.ticker, m.exchange) for m in self.members}
        ) != len(self.members):
            raise ValueError("duplicate ETF member")
        if max(self.selected_at, self.source_observed_at) > datetime.now(UTC):
            raise ValueError("selection/observation cannot be in the future")
        return self


def main(argv: list[str] | None = None) -> int:
    """Validate the full frozen target before making any domain writes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    selection = ETFSelection.model_validate_json(args.selection.read_bytes())
    frozen = selection.model_dump(mode="json")
    frozen_json = orjson.dumps(frozen, option=orjson.OPT_SORT_KEYS)
    source_ref = "instrument_registry:sha256:" + hashlib.sha256(frozen_json).hexdigest()
    members = "; ".join(
        f"{m.ticker} {m.name} [{m.list_date}, {m.delist_date or '开放'})"
        for m in selection.members
    )
    description = (
        f"选择时点 {selection.selected_at.isoformat()}; 来源观察 "
        f"{selection.source_observed_at.isoformat()}, {selection.source}。"
        f"{selection.selection_rule} 纳入: {members}。"
        f"排除: {selection.excluded_scope}。"
        f"候选窗口 {selection.candidate_window} (仍需逐次输入及执行校验)。"
        f"{selection.limitations}"
    )
    definition = {
        "name": selection.name,
        "description": description,
        "universe_type": "derived",
        "source_ref": source_ref,
    }
    records = [
        {
            "instrument_id": member.instrument_id,
            "effective_from": member.list_date.isoformat(),
            "effective_to": member.delist_date.isoformat()
            if member.delist_date
            else None,
            "weight": 1.0,
            "source": source_ref,
            "source_ticker": member.ticker
            + (".SH" if member.exchange == "SSE" else ".SZ"),
        }
        for member in selection.members
    ]
    with create_universe_write_context() as metadata:
        registry = metadata.find_securities(asset_class="etf", is_active=None)
        for member in selection.members:
            expected = member.model_dump(mode="json")
            matches = [
                row
                for row in registry.to_dicts()
                if row["instrument_id"] == member.instrument_id
            ]
            if not matches or any(
                {
                    key: (str(row[key]) if row[key] is not None else None)
                    for key in expected
                }
                != {
                    key: (str(value) if value is not None else None)
                    for key, value in expected.items()
                }
                for row in matches
            ):
                raise ValueError(
                    f"registry conflict for {member.ticker}; frozen list unchanged"
                )
        existing = metadata.universe.get_universe_detail(selection.universe_id)
        if existing is not None and any(
            existing[key] != value for key, value in definition.items()
        ):
            raise ValueError("universe definition conflict; refusing replacement")
        history = metadata.universe.get_constituent_history(selection.universe_id)
        recorded = [{key: row[key] for key in records[0]} for row in history]
        if any(row not in records for row in recorded):
            raise ValueError("universe member history conflict; refusing replacement")
        missing = [row for row in records if row not in recorded]
        if args.apply:
            if existing is None:
                metadata.universe.create_universe(selection.universe_id, **definition)
            if missing:
                metadata.universe.add_constituents(selection.universe_id, missing)
    sys.stdout.write(
        orjson.dumps(
            {
                "universe_id": selection.universe_id,
                "source_ref": source_ref,
                "members": len(records),
                "missing": len(missing),
                "applied": args.apply,
            }
        ).decode()
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
