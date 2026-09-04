# Universe catalog implementation feedback

- React route: `/research/universes`
- Contract verification: 2026-08-30
- Static definitions were replaced by the generated universe list, membership, create, update, and delete APIs. Mock and live modes now enter the same mapper, query hooks, and Catalog view.
- Membership is fail-closed until a complete `as-of` date is explicitly bound. The date is part of the query cache key and request; selection changes never inherit an unscoped member result.
- The current public membership DTO exposes effective-date lookup but not a knowledge cutoff or source-snapshot identity. The page states this limitation and does not present the member list as trading-decision evidence.
- Preset definitions have no edit or delete affordance. Custom definitions use the prototype-aligned edit sheet and destructive confirmation; optional member revisions require an explicit effective date.
- No generic universe service, schema renderer, implicit “latest” query, or security/ownership layer was introduced.
