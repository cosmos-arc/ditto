"""CLI compatibility wrapper for model-fold input materialization."""

from ditto_apps.registry.model.model_fold_input_materializer import (
    MaterializedModelFoldInputs,
    build_model_fold_calendar_frame,
    build_model_fold_label_price_frame,
    freeze_model_feature_frame,
    main,
    materialize_model_fold_inputs,
)

__all__ = [
    "MaterializedModelFoldInputs",
    "build_model_fold_calendar_frame",
    "build_model_fold_label_price_frame",
    "freeze_model_feature_frame",
    "main",
    "materialize_model_fold_inputs",
]

if __name__ == "__main__":
    raise SystemExit(main())
