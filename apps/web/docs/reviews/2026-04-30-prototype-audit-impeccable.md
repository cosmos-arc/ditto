# Ditto Prototype Audit — impeccable:audit

> **Tool**: impeccable:audit (best level)
> **Scope**: `docs/designs/specs/prototypes/` 27 active pages + shared CSS/JS + 20 spec documents
> **Date**: 2026-04-30
> **Branch**: feat/prototype-three-zone-architecture

---

## Audit Health Score

| # | Dimension | Score | Key Finding |
|---|-----------|:-----:|-------------|
| 1 | **Accessibility (A11y)** | **1/4** | 30+ `div[role="button"]` without keyboard activation; ARIA tabs incomplete in 4/5 pages; 3/5 pages missing `<h1>` |
| 2 | **Performance** | **2/4** | `getComputedStyle` per `cssVar()` call; unthrottled `mousemove`; `transition: all` widespread |
| 3 | **Theming** | **4/4** | 9-layer token system + OKLCH color space + 3 themes, SSOT architecture complete |
| 4 | **Responsive Design** | **1/4** | Single breakpoint (720px header); shell layouts overflow <1200px; `100vh` mobile bug |
| 5 | **Anti-Patterns** | **4/4** | Zero AI slop tells; zero inline styles; domain-driven color; restrained professional design language |
| **Total** | | **12/20** | **Acceptable** — Accessibility and Responsive are primary weaknesses |

**Rating bands**: 18-20 Excellent | 14-17 Good | 10-13 Acceptable | 6-9 Poor | 0-5 Critical

---

## Anti-Patterns Verdict

**PASS.** Zero AI-generated tells across all 27 prototype pages.

Evidence:
- No gradient text, no glassmorphism cards, no hero metrics, no generic card grids
- Colors strictly segregated by business domain (Market/Risk/Execution/System/DataQuality/Model/Agent), zero cross-domain mixing
- All mock data uses real financial terminology (specific stock codes, actual metrics)
- Animations serve information hierarchy (stagger entrance, hover lift), not decoration
- Design token architecture is complete and consistent — systematic human design, not AI patchwork

---

## Executive Summary

- **Audit Health Score**: **12/20** (Acceptable)
- **Issues found**: **P0: 5 | P1: 9 | P2: 8 | P3: 6** = 28 total
- **Top 5 critical issues**:
  1. **P0** `div[role="button"]` pervasive (30+ instances), keyboard users cannot activate
  2. **P0** `outline: none` removes focus indicator, WCAG 2.4.7 violation
  3. **P0** Only 1 responsive breakpoint across 27 pages, non-desktop environments unusable
  4. **P1** ARIA tab pattern incomplete in 4/5 sampled pages, only signals-inbox fully implements
  5. **P1** 13 interaction design spec gaps (keyboard nav, motion spec, focus ring undefined)
- **Recommended next steps**: Fix P0 accessibility → Fill spec gaps → Responsive strategy

---

## Detailed Findings by Severity

### P0 Blocking (5 issues)

#### [P0-1] `div[role="button"]` without keyboard activation handlers

- **Location**: `shared/prototype-interactions.js:342`, plus agent-console/platform/instrument-hub/markets-intel/signals-inbox totaling 30+ instances
- **Category**: Accessibility
- **Impact**: Keyboard users can Tab to these elements but cannot activate with Enter/Space, completely blocking keyboard operation paths
- **WCAG**: 2.1.1 Keyboard (Level A) + 2.5.2 Pointer Gestures
- **Recommendation**: Either (a) add global `initButtons()` module auto-binding `keydown` for Enter/Space on all `[role="button"]`, or (b) replace with native `<button>` + CSS reset
- **Suggested command**: `/harden`

#### [P0-2] `outline: none` without visible replacement focus indicator

- **Location**: `shared/layout-base.css:2277-2300` (`.filter-select:focus`, `.filter-search:focus`)
- **Category**: Accessibility
- **Impact**: `border-color` change alone has insufficient contrast (<3:1) on dark backgrounds; keyboard users cannot see focus position
- **WCAG**: 2.4.7 Focus Visible (Level AA)
- **Recommendation**: Add `box-shadow: 0 0 0 2px var(--interaction-focus-ring)` as focus ring, consistent with other focus-visible elements in the codebase
- **Suggested command**: `/harden`

#### [P0-3] Responsive design nearly absent

- **Location**: `shared/layout-base.css` — only 1 `@media (max-width: 720px)` at line 704
- **Category**: Responsive
- **Impact**: All shell grid layouts (screener 6-col, signal 8-col, risk metrics 6-col) overflow or become unreadable below ~1200px viewport. `100vh` produces blank space on mobile Safari with dynamic address bar
- **Recommendation**:
  1. Immediate: `100vh` → `100dvh` (6 locations: lines 134, 149, 187, 2187, 2557, 3489)
  2. Medium-term: Define 3-breakpoint strategy (1200px / 1024px / 768px) with per-shell degradation plans
  3. Long-term: Spec 10 (Shell Family) should add responsive specifications per shell
- **Suggested command**: `/adapt`

#### [P0-4] Missing `<h1>` breaks page heading hierarchy

- **Location**:
  - `page-agent-console.html:1638` — `<span class="header-title">`
  - `page-platform.html:2039` — `<span class="header-title">`
  - `page-signals-inbox.html:1822` — `<span class="header-title">`
- **Category**: Accessibility
- **Impact**: Screen readers cannot identify page main title; navigation tree incomplete
- **WCAG**: 1.3.1 Info and Relationships (Level A)
- **Recommendation**: Change all `<span class="header-title">` to `<h1 class="header-title">` and reset browser default `h1` styles in CSS
- **Suggested command**: `/harden`

#### [P0-5] `reducedMotion` read once at load, never updated

- **Location**: `shared/prototype-interactions.js:13`
- **Category**: Accessibility
- **Impact**: Affects 6 animation modules (DonutGauge, NumberTicker, ScrollReveal, MouseGlow, ConfidenceBar, AnimatedCounter). If user toggles motion preference at runtime, all modules continue using stale value
- **Recommendation**: Use `matchMedia().addEventListener('change', ...)` to listen for live changes
- **Suggested command**: `/harden`

---

### P1 Major (9 issues)

#### [P1-1] ARIA Tab Pattern implementation inconsistent

- **Location**: Only `page-signals-inbox.html` fully implements `role="tab"` + `aria-selected` + `role="tabpanel"` + `aria-controls` across 5 sampled pages
- **Category**: Accessibility
- **Impact**: Screen reader users cannot understand tab navigation structure on 4/5 pages

| Page | `aria-selected` | `role="tabpanel"` | `aria-controls` |
|------|:---:|:---:|:---:|
| agent-console | ✗ | ✗ | ✗ |
| platform | ✓ | ✗ | ✗ |
| instrument-hub | ✗ | ✗ | ✗ |
| markets-intel | ✗ | ✗ | ✗ |
| **signals-inbox** | **✓** | **✓** | **✓** |

- **Recommendation**: Use signals-inbox as standard template; unify all pages to full ARIA tab pattern
- **Suggested command**: `/normalize`

#### [P1-2] `::after` on `<select>` does not render

- **Location**: `shared/layout-base.css:2257-2271`
- **Category**: Accessibility + Functional Bug
- **Impact**: Custom dropdown arrow invisible in Chrome/Firefox/Safari; users cannot identify dropdown capability
- **Recommendation**: Replace with `background-image: url("data:image/svg+xml,...")` or use wrapper div pattern
- **Suggested command**: `/harden`

#### [P1-3] `getComputedStyle(document.documentElement)` per `cssVar()` call

- **Location**: `shared/prototype-interactions.js:22-25`
- **Category**: Performance
- **Impact**: 20+ sparkline/heatmap instances per page = 20 forced style recalculations
- **Recommendation**: Cache `getComputedStyle` result; invalidate on `themechange` event:
  ```js
  var _csCache = null;
  function cssVar(name, fallback) {
    if (!_csCache) _csCache = getComputedStyle(document.documentElement);
    var v = _csCache.getPropertyValue(name);
    return v ? v.trim() : fallback;
  }
  document.addEventListener('themechange', function() { _csCache = null; });
  ```
- **Suggested command**: `/optimize`

#### [P1-4] MouseGlow `mousemove` unthrottled

- **Location**: `shared/prototype-interactions.js:715-729`
- **Category**: Performance
- **Impact**: Every mouse movement triggers `radial-gradient` recomputation; 60 background repaints/second at 60fps
- **Recommendation**: Use `requestAnimationFrame` throttling + CSS custom properties:
  ```js
  el.addEventListener('mousemove', function(e) {
    requestAnimationFrame(function() {
      el.style.setProperty('--glow-x', e.offsetX + 'px');
      el.style.setProperty('--glow-y', e.offsetY + 'px');
    });
  });
  ```
- **Suggested command**: `/optimize`

#### [P1-5] `transition: all` widespread

- **Location**: `shared/layout-base.css` lines 2229, 2531, 2651, 2788, etc.
- **Category**: Performance + Anti-pattern
- **Impact**: Transitions fire on every computable property change, not just the intended ones; can cause layout jitter on hover
- **Recommendation**: Replace `transition: all` with specific properties, e.g. `transition: background-color var(--motion-duration-fast) var(--motion-easing-standard), border-color var(--motion-duration-fast) var(--motion-easing-standard)`
- **Suggested command**: `/polish`

#### [P1-6] SVG visualization components lack ARIA annotations

- **Location**: `shared/prototype-interactions.js:409` (Sparkline), `:494` (DonutGauge), `:562` (HeatGrid)
- **Category**: Accessibility
- **Impact**: SVG charts completely invisible to screen readers; trend information conveyed by charts is lost
- **Recommendation**: Add `role="img"` + `aria-label="Trend: up 12.5%"` format description to each SVG
- **Suggested command**: `/harden`

#### [P1-7] Keyboard navigation specification missing at spec level

- **Location**: Spec 04 (Interaction & State Spec) Section 3 only mentions "focus must be uniformly visible"
- **Category**: Accessibility (Spec Gap)
- **Impact**: No Tab order rules, no Escape-to-close patterns, no Cmd+K search shortcut spec, no modal focus trap spec
- **Recommendation**: Add Section 17 "Keyboard Navigation Specification" to Spec 04, covering Tab order, Enter/Space activation, Escape dismiss, focus traps, shortcut definitions
- **Suggested command**: `/harden`

#### [P1-8] Motion specification fragmented, no unified Motion Spec

- **Location**: Scattered across Spec 04 §14.3 (0.15s), Audit §3.2 (150ms), Audit §4.4 (200ms), Spec 10 §10.3
- **Category**: Consistency (Spec Gap)
- **Impact**: Different documents recommend slightly different motion durations; implementers cannot determine canonical values
- **Recommendation**: Create new Spec 21 `ditto_motion_spec.md` defining all motion durations, easing curves, `prefers-reduced-motion` degradation strategies
- **Suggested command**: `/normalize`

#### [P1-9] Focus-Visible specification not quantified

- **Location**: Spec 04 §3 only says "not overly subtle"
- **Category**: Accessibility (Spec Gap)
- **Impact**: Different pages may implement different focus ring widths/colors/offsets. Currently markets-intel uses `--interaction-selected-bg` while others use `--interaction-selected-border`
- **Recommendation**: Define in Spec 04 or Token Spec: `--focus-ring-width: 2px`, `--focus-ring-color`, `--focus-ring-offset: 2px` and mandate uniform usage
- **Suggested command**: `/normalize`

---

### P2 Minor (8 issues)

#### [P2-1] `!important` proliferation (15+ in single rule block)

- **Location**: `shared/layout-base.css:526-567` (header buttons) + multiple other locations
- **Impact**: Specificity model broken; downstream overrides impossible
- **Recommendation**: Restructure selectors to increase specificity naturally rather than compensating with `!important`
- **Suggested command**: `/normalize`

#### [P2-2] Skip link uses dated `left: -9999px` technique

- **Location**: `shared/layout-base.css:43-57`
- **Impact**: May create horizontal scroll in screen magnifier combinations
- **Recommendation**: Switch to `clip-path: inset(50%)` or `transform: translateX(-100%)`
- **Suggested command**: `/harden`

#### [P2-3] `comfortable` density mode is a no-op

- **Location**: `tokens-style.css:85-87`
- **Impact**: Users switch to comfortable density and see no change; misleading
- **Recommendation**: Either fill in comfortable density values (row-height: 42px, padding: 16px) or remove the option from UI
- **Suggested command**: `/normalize`

#### [P2-4] `html[data-resizing-panel="true"] *` universal selector during resize

- **Location**: `shared/layout-base.css:3665-3668`
- **Impact**: Forces style recalculation on every DOM element when resize begins; can cause jank on complex pages
- **Recommendation**: Scope selector to `.shell *` or use CSS containment
- **Suggested command**: `/optimize`

#### [P2-5] Tooltip `setTimeout` magic number not synced with CSS transition

- **Location**: `shared/prototype-interactions.js:1034`
- **Impact**: 150ms JS timer may desync from CSS transition duration, causing tooltip flicker
- **Recommendation**: Replace `150` with `cssVar('--motion-duration-fast', '150ms')` or define as constant
- **Suggested command**: `/polish`

#### [P2-6] Most hover transitions lack `prefers-reduced-motion` protection

- **Location**: `shared/layout-base.css` — most `.xxx:hover` rules
- **Impact**: Users who requested reduced motion still see hover transition animations
- **Recommendation**: Extend `prefers-reduced-motion` media query from collapsible sections only to all transition declarations
- **Suggested command**: `/harden`

#### [P2-7] innerHTML construction via string concatenation

- **Location**: `shared/prototype-interactions.js:338-342`, `:351-354`
- **Impact**: If data contains `<` or `&` characters, DOM parsing breaks
- **Recommendation**: Use `document.createElement` + `textContent` pattern instead
- **Suggested command**: `/harden`

#### [P2-8] `.style-label` `aria-hidden` inconsistent across pages

- **Location**: Only `page-signals-inbox.html:1803` adds `aria-hidden="true"`; other 4 sampled pages do not
- **Impact**: Prototype style label "Style B · Graphite Studio" read aloud by screen reader on most pages
- **Recommendation**: Unify by adding `aria-hidden="true"` to all `.style-label` elements
- **Suggested command**: `/normalize`

---

### P3 Polish (6 issues)

| # | Issue | Location | Suggested command |
|---|-------|----------|-------------------|
| P3-1 | layout-base.css monolithic file (4000 lines) | `shared/layout-base.css` | `/extract` |
| P3-2 | ScreenerWorkflow module 270-line monolith | `shared/prototype-interactions.js:131-402` | `/extract` |
| P3-3 | `--card-radius` / `--card-padding` reference undefined tokens | `shared/layout-base.css:3969` | `/normalize` |
| P3-4 | tokens-style.css inconsistent units (px vs rem) | `tokens-style.css:22-31` | `/normalize` |
| P3-5 | `oklch(from ...)` relative color syntax limited browser support | `tokens-style.css:19` | `/harden` |
| P3-6 | Tooltip capture-phase global event listener overhead | `shared/prototype-interactions.js:937-940` | `/optimize` |

---

## Patterns & Systemic Issues

### 1. `<div role="button">` systematically replaces `<button>` (global)

30+ instances use `<div>` / `<span>` + `role="button"` instead of native `<button>`. Root cause: prototypes use CSS-only checkbox/radio hack for interactions (e.g., overlay toggle), requiring `<label>` instead of `<button>`. This is an inherent limitation of prototype technique but must be eliminated in React implementation.

### 2. ARIA compliance inconsistent (global)

5 sampled pages present 3 different tab implementation patterns:
- **Pattern A** (agent-console): radio + label, no aria-selected, no tabpanel
- **Pattern B** (platform): radio + label + aria-selected, no tabpanel
- **Pattern C** (signals-inbox): complete ARIA tab pattern

Pattern C should be the only standard.

### 3. `transition: all` systematic usage (global)

`transition: all` appears 10+ times in layout-base.css. Global performance and predictability issue.

### 4. 13 Spec-level gaps (documentation)

Audit found 13 gaps in the spec system (see Spec Gap Analysis below). Most critical: keyboard navigation spec missing and motion spec fragmented.

---

## Positive Findings

1. **Zero inline styles**: All 27 pages fully comply with no-inline-style rule
2. **9-layer token system**: Industry-leading token architecture with OKLCH color space + domain signatures + surface elevation
3. **`prefers-reduced-motion`**: All 5 sampled pages implement it (though coverage is incomplete)
4. **Skip links**: Present on all pages
5. **Focus-visible ring**: Unified `box-shadow` focus ring system using brand accent
6. **Color dual-encoding**: markets-intelligence explicitly provides colorblind-friendly ▲/▼ symbol fallbacks
7. **Data-attribute driven**: `data-tooltip`, `data-density`, `data-slot` declarative interaction patterns separate code from configuration
8. **State coverage documentation**: Each prototype HTML embeds state coverage comments, traceable
9. **Resize separator ARIA**: `page-agent-console.html:2321` `role="separator"` with complete ARIA attributes is a benchmark implementation
10. **Domain color isolation**: Strict Market/Risk/Execution/System/DataQuality/Model/Agent color segregation, zero cross-domain mixing

---

## Interaction Design Improvement Recommendations

### 1. Keyboard Navigation System (largest current gap)

**Current state**: Spec 04 only mentions "focus must be uniformly visible". No complete keyboard interaction model defined.

**Recommended keyboard specification**:

| Pattern | Keys | Behavior | Applicable scope |
|---------|------|----------|------------------|
| Tab navigation | Tab / Shift+Tab | Move focus between interactive elements | Global |
| Activation | Enter / Space | Activate button/link/card | All `[role="button"]` |
| List selection | ↑/↓ | Move focus and select between list items | Signal table, Screener results, Order list |
| Tab switching | ←/→ | Move focus between tabs | Tab bar, Filter chips |
| Panel resize | Ctrl+←/→ | Adjust resizable panel width ±40px | Analytical/Studio/Ops shell |
| Panel fine-tune | Ctrl+Shift+←/→ | Adjust ±8px | Same |
| Panel reset | Double-click separator | Restore default ratio | Same |
| Dismiss | Escape | Close overlay/modal/dropdown/bottom tray | Global |
| Search | Cmd/Ctrl+K | Open global search | Shell Chrome |
| Focus trap | Tab cycle | Cycle focus within modal/overlay | All overlay panels |

### 2. Focus Ring Specification (eliminate ambiguity)

**Current state**: markets-intel uses `--interaction-selected-bg`, other pages use `--interaction-selected-border`.

**Recommendation**: Add to `tokens-interaction.css`:

```css
--focus-ring-width: 2px;
--focus-ring-color: oklch(from var(--brand-500) l c h / 0.7);
--focus-ring-offset: 2px;
--focus-ring: 0 0 0 var(--focus-ring-width) var(--focus-ring-color);
```

All interactive elements uniformly use `box-shadow: var(--focus-ring)`.

### 3. Motion Specification Unification (resolve fragmentation)

**Current state**: Motion durations scattered across 4 documents with 150ms / 200ms / 0.15s / 1s values.

**Recommended Motion Scale**:

| Token | Duration | Usage |
|-------|----------|-------|
| `--motion-instant` | 50ms | Color switch, opacity change |
| `--motion-fast` | 100ms | Hover feedback, chip toggle |
| `--motion-normal` | 200ms | Panel fold/expand, bottom tray |
| `--motion-deliberate` | 350ms | Page transition, overlay slide-in |
| `--motion-entrance` | 500ms | List item stagger entrance |

| Easing | Value | Usage |
|--------|-------|-------|
| `--ease-standard` | cubic-bezier(0.4, 0, 0.2, 1) | Most interactions |
| `--ease-decelerate` | cubic-bezier(0, 0, 0.2, 1) | Entrance animations |
| `--ease-accelerate` | cubic-bezier(0.4, 0, 1, 1) | Exit animations |

### 4. List Row Selection Interaction Enhancement

**Current state**: Spec 04 defines selected state driving right-side context panel, but interaction details insufficient in prototypes.

**Recommendations**:
1. **Single vs double click separation**: Single click = select (refresh right context), double click = navigate to detail page
2. **Keyboard selection feedback**: ↑/↓ row switch should update right context panel within 200ms (not instant, allowing animation transition)
3. **Selection persistence**: Maintain selection across filter changes (clear + notify if filtered out: "Selected XXX not in current filter results")
4. **Multi-select entry**: Shift+click for range / Cmd/Ctrl+click for append; bulk action bar appears at bottom after selection

### 5. Bottom Tray Three-State Interaction Optimization

**Current state**: Spec 04 §16 defines collapsed/peek/expanded, but prototype implementation incomplete.

**Recommendations**:
1. **Drag edge**: Add drag-to-resize edge (consistent with resizable panel VS Code Sash pattern)
2. **Keyboard shortcut**: `Ctrl+`` toggles tray state (collapsed → peek → expanded cycle)
3. **Smart peek**: Auto-upgrade from collapsed to peek when background task errors, showing latest error line
4. **Peek hover expand**: Peek state auto-expands to expanded on hover; reverts to peek on mouse leave

### 6. Overlay Panel Focus Management

**Current state**: Prototypes use checkbox hack for overlays; no focus trap.

**Recommendations**:
1. **Focus trap**: On open, focus moves to first interactive element inside overlay; Tab cycles within overlay
2. **Close restore**: On close, focus returns to triggering element
3. **Escape close**: Escape closes topmost overlay
4. **Background lock**: Background content not Tab-reachable while overlay open (`aria-hidden="true"` on background content)

### 7. Signal State Machine Visualization

**Current state**: Spec 04 §15 defines 8 signal states and regression paths, but no state flow visualization component in prototypes.

**Recommendation**: Add lightweight state flow visualization for Signals Inbox detail panel:

```
pending → reviewing → approved → signal-generated → order-submitted → completed
                        ↑  ↓          ↓
                     expired  ←  expired  ← expired
```

- Current state highlighted + pulse animation
- Passed states solid
- Unreached states hollow
- Regression paths shown as dashed lines

### 8. Table Row Interaction Consistency

**Current state**: Different pages use different row interaction methods — some hover highlight, some `cursor: pointer` implying clickability, but no unified row interaction spec.

**Recommended unified Row Interaction Contract**:

| Action | Behavior | Feedback |
|--------|----------|----------|
| Hover row | Background subtle brighten | `--interaction-hover-subtle` |
| Click row | Select row, refresh right panel | Left border accent + background selected color |
| Double-click row | Navigate to detail | None (direct navigation) |
| Right-click row | Open context menu | Native or custom menu |
| Tab to row | Focus ring around entire row | `--focus-ring` |

---

## Spec Gap Analysis (13 gaps)

| # | Gap | Spec Location | Severity | Recommendation |
|---|-----|---------------|:--------:|----------------|
| 1 | Keyboard navigation spec missing | Spec 04 | **P1** | Add Section 17 |
| 2 | Motion spec fragmented | Spec 04/10/Audit | **P1** | Create Spec 21 Motion Spec |
| 3 | Focus-Visible not quantified | Spec 04 §3 | **P1** | Define token-level focus ring spec |
| 4 | Empty state messages incomplete | Spec 04 §4/§13 | P2 | Complete all page types |
| 5 | Stale state visual treatment inconsistent | Spec 04 §13.2 | P2 | Unify stale visual approach |
| 6 | Bottom Tray default state not mapped per shell | Spec 04 §16 | P2 | Define per-shell default |
| 7 | Context-Aware Panel Linkage only for Object Hub | Spec 04 §14.6 | P2 | Extend to Analytical/Studio/Ops |
| 8 | A11y audit findings not reflected back into spec | Spec 10 §5.1 | P2 | Add ARIA mandatory requirements |
| 9 | Compare Mode lacks state persistence rules | Spec 04 §9 | P3 | Define max count + cross-nav behavior |
| 10 | Agent blocked vs waiting-approval lacks transition rules | Spec 04 §11 | P3 | Define state transition matrix |
| 11 | Success state absent from page type mappings | Spec 04 §1/§13 | P3 | Add success visual spec |
| 12 | Visual Constitution lacks quantitative enforcement | Spec 00 | P3 | Add max colors/gradient constraints |
| 13 | Spec 10 section numbering error | Spec 10 | P3 | Fix Section 11/12 duplication |

**Highest priority**: Gaps 1-3 should be completed before React implementation begins; otherwise developers have no spec to follow.

---

## Recommended Actions (Priority Order)

1. **[P0]** `/harden` — Fix 30+ `div[role="button"]` keyboard activation + `outline:none` focus + missing `<h1>` + `reducedMotion` listener
2. **[P0]** `/adapt` — Fix `100vh` → `100dvh`, define responsive breakpoint strategy
3. **[P1]** `/normalize` — Unify ARIA tab pattern (signals-inbox as template) + unify focus ring token + eliminate `!important`
4. **[P1]** `/optimize` — Cache `getComputedStyle` + MouseGlow RAF throttle + eliminate `transition: all`
5. **[P2]** `/polish` — Unify motion duration tokens + tooltip sync + `prefers-reduced-motion` coverage extension
6. **[P2]** `/extract` — Split layout-base.css into concern-separated files + split ScreenerWorkflow module

---

## Sampled Pages Detail

### Pages Audited

| Page | File | Lines | `<h1>` | ARIA Tabs | Key Issues |
|------|------|-------|:------:|:---------:|------------|
| Agent Console | page-agent-console.html | 3,335 | ✗ | ✗ | Missing h1, incomplete tabs, plan-card breathing animation gap in reduced-motion |
| Platform | page-platform.html | 3,339 | ✗ | Partial | Missing h1, `div[role="button"]`, "Incident History" English label in Chinese page |
| Instrument Hub | page-instrument-hub.html | 4,246 | ✓ | ✗ | Redundant `role="banner"` inside `<header>`, heading hierarchy skips h2 |
| Markets Intelligence | page-markets-intelligence.html | 3,733 | ✓ | ✗ | Missing aria-selected on tabs, different focus ring token, bilingual header |
| Signals Inbox | page-signals-inbox.html | 3,432 | ✗ | ✓ | Only page with complete ARIA tabs; redundant `role="main"` on `<main>` |
| Home | page-home.html | 2,632 | — | — | Reviewed in prior audits |
| Trading Overview | page-trading-overview.html | 3,818 | — | — | Reviewed in prior audits |
| Research | page-research.html | 3,964 | — | — | Broken skip link |
| Cross Market | page-cross-market.html | 3,105 | — | — | Duplicate `aria-modal` attributes |
| Strategy Studio | page-strategy-studio.html | 3,691 | — | — | Reviewed in prior audits |

### Shared Infrastructure Audited

| File | Lines | Key Findings |
|------|-------|--------------|
| prototype-interactions.js | ~1,050 | 8 modules; `cssVar()` perf issue; unthrottled MouseGlow; tooltip global capture listeners |
| layout-base.css | ~3,999 | Single responsive breakpoint; `!important` proliferation; `100vh` mobile bug; `transition: all` |
| tokens-style.css | ~105 | Clean; `comfortable` density is no-op; inconsistent px/rem units |
| fonts.css | ~200 | Font loading; no issues |
| mock-data.js | ~200 | Deterministic data; no issues |
| theme-switcher.js | ~250 | Theme toggling; no issues |
