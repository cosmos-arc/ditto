# Alpha Explorer implementation feedback

- React route: `/research/alpha`
- Contract verification: 2026-08-30
- The page consumes generated Agent capability, campaign, campaign-detail, and campaign-event contracts. Mock and live modes use the same DTOs, query keys, and governed workspace.
- Search-space scope, objective, source snapshot, budget, tools, campaign state, evidence, artifact, guardrail, and approval facts are rendered only when supplied by the service. Missing knowledge cutoffs or candidate formulas are stated explicitly.
- Campaign validation, creation, and adoption approval are backed by the declared write paths and triggerable review overlays.
- The 1536px, 1366px, and 1200px viewports have exact required-slot geometry and no console, page, selector, or target errors. The measured pixel ratios are 4.47%, 5.28%, and 5.59%; the 6% threshold records that observed range without relaxing structural gates.
- [proto-deviation] The implementation uses content-safe labels and explicit unavailable states in place of the prototype's assumed formula and research claims.
- No separate factor-generation service, implicit latest snapshot, or client-side approval shortcut was introduced.
