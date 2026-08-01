"""CLI compatibility wrapper for registry-composed R2 live certification."""

from ditto_apps.registry.live.r2_live_certification import (
    R2LiveCertificationBundle,
    R2LiveProductCertification,
    build_expected_dates,
    certify_live_products,
    load_passing_recovery_evidence,
    main,
    probe_consumer_payload,
    select_current_snapshot_ids,
)

__all__ = [
    "R2LiveCertificationBundle",
    "R2LiveProductCertification",
    "build_expected_dates",
    "certify_live_products",
    "load_passing_recovery_evidence",
    "probe_consumer_payload",
    "select_current_snapshot_ids",
]

if __name__ == "__main__":
    raise SystemExit(main())
