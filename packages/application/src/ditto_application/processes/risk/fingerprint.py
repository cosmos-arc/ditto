"""Canonical fingerprint of authoritative portfolio holdings."""

from __future__ import annotations

from hashlib import sha256

import orjson
from ditto_portfolio.accounting import AccountView

__all__ = ["position_fingerprint"]


def position_fingerprint(account_view: AccountView) -> str:
    """Hash holdings identity without treating T+1 availability as drift."""
    positions = [
        {
            "instrument_id": int(instrument_id),
            "quantity": position.quantity,
        }
        for instrument_id, position in sorted(account_view.positions.items())
    ]
    payload = orjson.dumps(positions, option=orjson.OPT_SORT_KEYS)
    return f"sha256:{sha256(payload).hexdigest()}"
