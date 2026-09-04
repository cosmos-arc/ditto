# Review detail implementation feedback

- React route: `/research/reviews/$id`
- Contract verification: 2026-08-30
- The workbench consumes the existing review packet, strategy version, canonical diff, and append-only event resources; it introduces no review aggregator or persistence layer.
- Decision, evidence, lineage, and audit views preserve the same experiment, strategy version, packet bundle, spec, and snapshot identity in the fixed meta and bottom strips.
- Missing packet data fails closed. A hard-gate block disables approval and publication but intentionally keeps rejection available.
- Statistical payload hashes remain evidence only and never become a synthetic PASS. Missing R1 or exposure evidence remains explicitly unpublished.
- The established strategy object-hub prototype is reused as the shell anchor. Its rollback sheet is used only as the visual confirmation-sheet reference; review actions retain their generated governance API semantics.
