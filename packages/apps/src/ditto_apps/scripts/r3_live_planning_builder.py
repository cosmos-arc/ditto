"""CLI compatibility wrapper for registry-composed live planning."""

from ditto_apps.registry.live.r3_live_planning_builder import (
    LivePlanningArtifact,
    LivePlanningServices,
    build_live_planning_artifact,
    ensure_research_candidate,
    main,
    planning_request_document,
    write_live_planning_artifact,
)

__all__ = [
    "LivePlanningArtifact",
    "LivePlanningServices",
    "build_live_planning_artifact",
    "ensure_research_candidate",
    "planning_request_document",
    "write_live_planning_artifact",
]

if __name__ == "__main__":
    raise SystemExit(main())
