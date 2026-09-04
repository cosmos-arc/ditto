# Agent Console implementation feedback

- React route: `/platform/agents`
- Contract verification: 2026-08-30
- The page consumes the generated Agent capability, session, run, approval, campaign, and event-stream contracts. Mock and live modes use the same API paths and workspace.
- Exact context inputs, immutable evidence references, budget usage, guardrail outcomes, approval state, artifact identity, and stream recovery state remain visible without inventing omitted values.
- Run creation, cancellation, exact-action approval, campaign drafting, adoption approval, and campaign cancellation are backed by the declared write paths and triggerable overlays.
- The 1536px and 1366px contract viewports pass selector, geometry, runtime-error, and pixel-difference gates with no console warnings.
- The contract pairs the prototype's full-page `.agent-shell` with the semantic application-shell root; the page-local `[data-slot='shell']` remains the Agent workspace below the global header.
- [proto-deviation] At widths below the declared 1366px compact viewport, the React workspace deliberately reflows its source, main, and inspector regions instead of preserving the prototype's compressed three-column geometry. This is an accessibility and usability fallback, not a direct geometry-equivalence target.
- No new Agent orchestration API, browser-held provider credential, or client-side research inference was introduced.
