---
name: ditto-product-discovery
description: Use when defining a new Ditto product direction, page, workflow, or capability and the work needs product positioning, competitor or domain research, a system description, constraints, or an explicit assumption registry before architecture begins.
---

# Ditto Product Discovery

Turn an ambiguous product idea into evidence-backed inputs for `ditto-product-arch`.

## Read first

1. Read `.discovery-manifest.json` and resume an incomplete phase instead of restarting.
2. Read `PRODUCT.md` plus existing `docs/brief/` and `docs/research/` artifacts.
3. Read only the references needed for the requested mode:
   - [questioning-protocol.md](references/questioning-protocol.md) for interviews and assumption extraction.
   - [templates.md](references/templates.md) before writing artifacts.
   - [manifest-schema.md](references/manifest-schema.md) before changing the manifest.
   - [special-modes.md](references/special-modes.md) for validate/resume/focused work.

## Outputs

- `docs/brief/product-brief.md`: users, problem, differentiation, success measures, scope.
- `docs/brief/constitution.md`: concise non-negotiable product, UX, technical, security constraints.
- `docs/brief/system-description.md`: entities, capabilities, actors, events, integrations, constraints.
- `docs/brief/assumptions.md`: assumption, risk, evidence, status, next validation.
- `docs/research/competitive/landscape.md` and `docs/research/domain/knowledge-gaps.md`.
- `.discovery-manifest.json`: phase, artifact digests, status and recovery point.

## Workflow

1. **Vision** — establish user, job, pain, differentiation and measurable success.
2. **Landscape** — research claims that can be verified externally, then ask only decisions the user owns.
3. **System** — describe domain entities, capabilities, roles, events, integrations and priorities.
4. **Constraints** — capture explicit not-doing, UX, security, compliance and platform boundaries.
5. **Synthesis** — validate coverage and cross-artifact consistency, surface unresolved high-risk assumptions, update the manifest.

Ask one material decision at a time. Record evidence separately from inference. Mark unknowns rather than filling them with plausible detail. The user owns product-scope decisions; research can recommend but cannot silently decide them.

## Completion

- Every high-risk claim has evidence, an owner, or an explicit validation path.
- Brief, system description, constitution and research agree on scope and terminology.
- The manifest points to existing artifacts and a reproducible recovery state.
- Handoff names the facts that `ditto-product-arch` may treat as fixed and those still provisional.
