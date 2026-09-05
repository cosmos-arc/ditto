# Prototype Quality Score Contract

## Purpose

This document prevents false regressions caused by comparing different score families.

## Score Families

### Gate Score

Gate score answers: does the prototype satisfy implementation readiness gates?

Inputs:

- token usage
- viewport gates at 1536, 1366, and 1200 px
- route coverage
- overlay coverage
- state coverage
- visual consistency tests
- runtime errors

Gate score can improve when a page has more states, overlays, contract slots, and verification coverage.

### Release UX Score

Release UX score answers: would a professional quant trader trust this interface for real work?

Inputs:

- five-second state comprehension
- high-risk action safety
- cognitive load
- primary decision clarity
- recovery and auditability
- keyboard and assistive technology confidence
- long-session visual fatigue

Release UX score can drop when a page adds more visible options, more proof text, more panels, more motion, or more competing status indicators.

## Current Baseline

As of 2026-05-11:

- Active route prototype gates: pass for all active routes.
- Static browser sweep: pass for all prototype HTML pages.
- Fast impeccable detector: 0 findings for every HTML page.
- Release UX critique: 23/40, acceptable but not release-grade.
- Main release blockers: high-risk confirmations, primary answer dilution, visible action overload, visual noise, component semantics.

## Rule

Do not raise manifest numeric scores after cosmetic changes. Raise release confidence only after:

1. high-risk confirmation contract passes,
2. primary answer contract passes,
3. action tier contract passes,
4. `bun run prototype:gates` passes,
5. targeted final-review tests pass,
6. `bun run check` passes.
