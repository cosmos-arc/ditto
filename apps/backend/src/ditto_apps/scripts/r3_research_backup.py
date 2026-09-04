"""CLI compatibility wrapper for registry-composed R3 backup and restore."""

from ditto_apps.registry.live.r3_research_backup import (
    PinnedArtifactBackupReport,
    R3ResearchBackupError,
    R3ResearchBackupReport,
    R3ResearchRestoreReport,
    R3RestoredVerificationReport,
    create_r3_research_backup,
    inspect_r3_research_sources,
    main,
    restore_r3_research_backup,
    verify_r3_research_backup,
    verify_restored_r3_research_backup,
)

__all__ = [
    "PinnedArtifactBackupReport",
    "R3ResearchBackupError",
    "R3ResearchBackupReport",
    "R3ResearchRestoreReport",
    "R3RestoredVerificationReport",
    "create_r3_research_backup",
    "inspect_r3_research_sources",
    "restore_r3_research_backup",
    "verify_r3_research_backup",
    "verify_restored_r3_research_backup",
]

if __name__ == "__main__":
    raise SystemExit(main())
