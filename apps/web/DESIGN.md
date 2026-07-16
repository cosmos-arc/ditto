---
version: "1.0"
name: Ditto Graphite Studio
description: >
  Personal quantitative research and live-trading professional workstation.
  Terminal-style workspace with high information density.

colors:
  # ── L1 Neutral Primitives (15 levels) — hue 253, reduced chroma ──
  neutral:
    0:   "oklch(0.166 0.010 253)"
    25:  "oklch(0.184 0.011 253)"
    50:  "oklch(0.198 0.012 253)"
    75:  "oklch(0.215 0.012 253)"
    100: "oklch(0.240 0.013 253)"
    150: "oklch(0.261 0.014 253)"
    200: "oklch(0.303 0.015 253)"
    300: "oklch(0.342 0.013 253)"
    400: "oklch(0.420 0.012 253)"
    500: "oklch(0.495 0.011 253)"
    600: "oklch(0.594 0.009 253)"
    700: "oklch(0.707 0.008 253)"
    800: "oklch(0.814 0.006 253)"
    900: "oklch(0.920 0.004 253)"
    950: "oklch(0.978 0.002 253)"

  # ── L1 Brand Primitives — Lapis Blue hue 235 ──
  brand:
    300: "oklch(0.830 0.065 235)"
    400: "oklch(0.760 0.090 235)"
    500: "oklch(0.640 0.120 235)"   # Primary — Lapis hue 235°
    600: "oklch(0.540 0.100 235)"
    700: "oklch(0.450 0.080 235)"

  # ── L1 Functional Primitives ──
  functional:
    green:  { 400: "oklch(0.4479 0.0741 157.11)", 500: "oklch(0.6442 0.1203 156.74)", 600: "oklch(0.7055 0.1278 153.45)" }
    red:    { 400: "oklch(0.4779 0.1020 14.27)",  500: "oklch(0.6317 0.1567 22.64)",  600: "oklch(0.6656 0.1479 21.89)" }
    amber:  { 400: "oklch(0.4699 0.0626 80.62)",  500: "oklch(0.7341 0.1177 79.66)",  600: "oklch(0.7613 0.1110 77.09)" }
    orange: { 400: "oklch(0.4646 0.0742 48.27)",  500: "oklch(0.7187 0.1270 50.23)",  600: "oklch(0.7218 0.1216 49.42)" }
    cyan:   { 400: "oklch(0.6394 0.1037 220.78)", 500: "oklch(0.7312 0.1106 220.00)", 600: "oklch(0.7935 0.0910 218.53)" }
    purple: { 400: "oklch(0.4494 0.0772 298.93)", 500: "oklch(0.7324 0.1170 300.20)", 600: "oklch(0.7948 0.0862 299.72)" }

  # ── L2 Semantic: Surface Elevation ──
  surface:
    app:             "{colors.neutral.0}"              # Level 0: App background — deepest
    panel-base:      "{colors.neutral.25}"             # Level 1: Primary content containers
    panel-elevated:  "{colors.neutral.75}"             # Level 2: Nested cards, secondary panels
    strip:           "oklch(0.176 0.004 253)"          # Level 3: Horizontal bars
    overlay:         "oklch(0.255 0.006 253)"          # Level 4: Floating elements
    modal:           "oklch(0.290 0.007 253)"          # Level 5: Highest elevation
    muted:           "oklch(0.170 0.010 253)"          # Recessed — inputs, skeletons
    elevated:        "{colors.neutral.75}"             # Raised interactive — buttons, gallery headers
    frosted:         "oklch(from var(--surface-app) l c h / 0.85)"    # Frosted glass
    frosted-subtle:  "oklch(from var(--surface-app) l c h / 0.80)"

  # ── L2 Semantic: Text Hierarchy ──
  text:
    primary:    "oklch(0.940 0.004 253)"
    secondary:  "oklch(0.660 0.007 253)"
    tertiary:   "oklch(0.605 0.007 253)"
    quaternary: "oklch(0.580 0.006 253)"
    disabled:   "oklch(0.415 0.005 253)"
    inverse:    "{colors.neutral.0}"
    data-stale: "oklch(0.660 0.020 55)"
    link:       "{colors.brand.500}"
    link-hover: "{colors.brand.400}"
    error:      "{colors.functional.red.500}"
    warning:    "{colors.functional.amber.500}"
    success:    "{colors.functional.green.500}"

  # ── L2 Semantic: Border Hierarchy ──
  border:
    subtle:  "oklch(0.255 0.006 253)"
    default: "oklch(0.325 0.008 253)"
    strong:  "oklch(0.425 0.010 253)"
    focus:   "oklch(from var(--brand-500) l c h / 0.50)"    # derived from brand
    error:   "{colors.functional.red.500}"
    warning: "{colors.functional.amber.500}"

  # ── L2 Semantic: Brand Accent ──
  brand-accent:
    accent:       "{colors.brand.500}"
    accent-hover: "{colors.brand.400}"
    accent-subtle: "oklch(from var(--brand-500) l c h / 0.10)"
    accent-fg:    "oklch(0.99 0.002 253)"

  # ── L2 Semantic: Signature Brass (default / home / trading) ──
  brand-signature:
    fg:      "oklch(0.760 0.055 74)"       # Brass hue 74
    muted:   "oklch(0.660 0.040 74)"
    line:    "oklch(0.620 0.040 74)"
    subtle:  "oklch(0.760 0.055 74 / 0.08)"

  # ── L7 Domain Signatures ──
  domain:
    trading:
      fg:      "oklch(0.760 0.055 74)"     # Brass hue 74
      muted:   "oklch(0.660 0.040 74)"
      line:    "oklch(0.620 0.040 74)"
      subtle:  "oklch(0.760 0.055 74 / 0.08)"
    markets:
      fg:      "oklch(0.731 0.095 220)"    # Cyan hue 220
      muted:   "oklch(0.631 0.070 220)"
      line:    "oklch(0.580 0.065 220)"
      subtle:  "oklch(0.731 0.095 220 / 0.08)"
    research:
      fg:      "oklch(0.732 0.095 300)"    # Purple hue 300
      muted:   "oklch(0.632 0.070 300)"
      line:    "oklch(0.582 0.065 300)"
      subtle:  "oklch(0.732 0.095 300 / 0.08)"
    platform:
      fg:      "oklch(0.640 0.100 235)"    # Lapis hue 235
      muted:   "oklch(0.540 0.080 235)"
      line:    "oklch(0.470 0.070 235)"
      subtle:  "oklch(0.640 0.100 235 / 0.08)"
    home:
      fg:      "oklch(0.760 0.055 74)"     # Brass hue 74
      muted:   "oklch(0.660 0.040 74)"
      line:    "oklch(0.620 0.040 74)"
      subtle:  "oklch(0.760 0.055 74 / 0.08)"

  # ── L7 Domain Business Colors: Market (CN default: red=up, green=down) ──
  market:
    up-fg:      "oklch(0.670 0.170 20)"
    up-bg:      "oklch(0.670 0.170 20 / 0.10)"
    up-subtle:  "oklch(0.670 0.170 20 / 0.08)"
    down-fg:    "oklch(0.680 0.120 155)"
    down-bg:    "oklch(0.680 0.120 155 / 0.10)"
    down-subtle: "oklch(0.680 0.120 155 / 0.08)"
    flat-fg:    "{colors.neutral.500}"
    strong-fg:  "{colors.functional.red.600}"
    weak-fg:    "{colors.functional.green.600}"

  # ── L7 Domain Business Colors: Risk ──
  risk:
    low-fg:       "{colors.functional.green.500}"
    low-bg:       "oklch(0.2280 0.0238 162 / 0.20)"
    medium-fg:    "{colors.functional.amber.500}"
    medium-bg:    "oklch(0.2229 0.0212 76.17 / 0.20)"
    high-fg:      "{colors.functional.orange.500}"
    high-bg:      "oklch(0.2165 0.0265 47.45 / 0.20)"
    critical-fg:  "{colors.functional.red.600}"
    critical-bg:  "oklch(0.2242 0.0365 8.74 / 0.25)"

  # ── L7 Domain Business Colors: Execution ──
  execution:
    pending-fg:   "{colors.functional.amber.500}"
    partial-fg:   "{colors.functional.cyan.500}"
    filled-fg:    "{colors.functional.green.500}"
    cancelled-fg: "{colors.neutral.500}"
    rejected-fg:  "{colors.functional.red.600}"

  # ── L7 Domain Business Colors: System ──
  system:
    healthy-fg:   "{colors.functional.green.500}"
    degraded-fg:  "{colors.functional.amber.500}"
    stale-fg:     "{colors.functional.orange.500}"
    down-fg:      "{colors.functional.red.600}"
    recovering-fg: "{colors.functional.cyan.500}"

  # ── L7 Domain Business Colors: Data Quality ──
  data-quality:
    fresh-fg:     "{colors.functional.green.500}"
    delayed-fg:   "{colors.functional.amber.500}"
    missing-fg:   "{colors.functional.red.500}"
    partial-fg:   "{colors.functional.orange.500}"
    revised-fg:   "{colors.functional.purple.500}"

  # ── L7 Domain Business Colors: Model ──
  model:
    stable-fg:    "{colors.functional.green.500}"
    degrading-fg: "{colors.functional.amber.500}"
    drifting-fg:  "{colors.functional.orange.500}"
    invalid-fg:   "{colors.functional.red.600}"
    candidate-fg: "{colors.functional.cyan.500}"

  # ── L7 Domain Business Colors: Agent ──
  agent:
    idle-fg:             "{colors.neutral.500}"
    running-fg:          "{colors.brand.500}"
    waiting-approval-fg: "{colors.functional.amber.500}"
    blocked-fg:          "{colors.functional.red.500}"
    failed-fg:           "{colors.functional.red.600}"

  # ── L4 Data Visualization: Asset Class Colors (Paul Tol bright, colorblind-safe) ──
  asset-class:
    equity:       "oklch(0.623 0.127 252)"     # blue
    fixed-income: "oklch(0.753 0.157 75)"      # amber
    crypto:       "oklch(0.634 0.197 327)"     # magenta
    commodity:    "oklch(0.591 0.142 153)"     # green
    fx:           "oklch(0.702 0.137 199)"     # cyan
    volatility:   "oklch(0.746 0.165 50)"      # orange
    alternative:  "oklch(0.604 0.109 305)"     # purple

  # ── L4 Data Visualization: Data Freshness (opacity-based time-fade) ──
  data-freshness:
    live:     1.0
    recent:   0.85     # < 30s
    aging:    0.65     # 30s – 5min
    stale:    0.40     # 5min – 30min
    expired:  0.25     # > 30min

  # ── L6 Interaction ──
  interaction:
    focus-ring:         "oklch(from var(--brand-500) l c h / 0.50)"
    focus-border:       "oklch(from var(--brand-500) l c h / 0.70)"
    hover-subtle-bg:    "oklch(1 0 0 / 0.04)"
    hover-strong-bg:    "oklch(1 0 0 / 0.08)"
    selected-bg:        "oklch(from var(--brand-500) l c h / 0.12)"
    selected-border:    "oklch(from var(--brand-500) l c h / 0.25)"
    active-bg:          "oklch(0 0 0 / 0.12)"

typography:
  ui:
    fontFamily: Inter
    fallback: "Noto Sans SC Variable, Source Han Sans SC, PingFang SC, system-ui"
    sizes: [10, 11, 12, 13, 14, 16, 18, 20, 24]  # px
    weights: [400, 500, 600]
    lineHeight: { body: 1.5, compact: 1.35, dense: 1.25 }
    letterSpacing: { label: "-0.01em", heading: "-0.02em" }
  heading:
    fontFamily: "Geist Sans"
    fallback: Inter
  numeric:
    fontFamily: "JetBrains Mono"
    features: "tabular-nums slashed-zero"
  code:
    fontFamily: "Geist Mono"
    fallback: "JetBrains Mono"

spacing:
  scale: 4pt
  steps: [2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 32]  # px

rounded:
  steps: [2, 3, 4, 6, 8, 12]  # px

shadows:
  dragging: "0 8px 24px oklch(0 0 0 / 0.4)"

motion:
  durations: { fast: 100ms, normal: 200ms, slow: 350ms }
  easings:
    standard: "cubic-bezier(0.4, 0, 0.2, 1)"
    emphasis: "cubic-bezier(0.2, 0, 0, 1)"

overlay:
  steps: { 2: 0.02, 3: 0.03, 4: 0.04, 6: 0.06, 8: 0.08, 10: 0.10, 12: 0.12 }

shell:
  rail-width: 56px
  rail-collapsed: 0px
  header-height: 68px
  sidebar-width: 320px
  sidebar-collapsed-width: 56px
  detail-width: 340px
  drawer-width: 440px
  context-bar-height: 2rem
  scope-strip-height: 2rem
  status-bar-height: 1.5rem

density:
  presets:
    dense:
      row-height: 2.125rem     # 34px
      panel-padding: 8px
      section-gap: 8px
      cell-padding-y: 4px
      strip-height: 2rem
      input-height: 1.75rem
      action-height: 1.75rem
      header-height: 1.75rem
    compact:                    # default
      row-height: 2.25rem
      panel-padding: 12px
      section-gap: 12px
      cell-padding-y: 6px
      strip-height: 2.25rem
      input-height: 2rem
      action-height: 2rem
      header-height: 2rem
    comfortable:
      row-height: 2.625rem     # 42px
      panel-padding: 16px
      section-gap: 16px
      cell-padding-y: 8px
      strip-height: 2.5rem
      input-height: 2.25rem
      action-height: 2.25rem
      header-height: 2.25rem

components:
  panel:
    backgroundColor: "{colors.surface.panel-base}"
    borderColor: "{colors.border.subtle}"
    borderWidth: 1px
    rounded: "{rounded.8}"
    headerPadding: "8px 12px"
  button-primary:
    backgroundColor: "{colors.brand-accent.accent}"
    textColor: "{colors.surface.app}"
    rounded: "{rounded.4}"
    paddingY: 4px
    paddingX: 8px
    fontSize: 12px
    height: "{density.presets.compact.action-height}"
  button-secondary:
    backgroundColor: "{colors.surface.elevated}"
    textColor: "{colors.text.primary}"
    borderColor: "{colors.border.default}"
    rounded: "{rounded.4}"
    paddingY: 4px
    paddingX: 8px
    fontSize: 12px
  button-sm:
    paddingY: 2px
    paddingX: 6px
    fontSize: 10px
    rounded: "{rounded.4}"
  badge:
    sm-padding-y: 1px
    sm-padding-x: 4px
    sm-radius: "{rounded.2}"
    md-padding-y: 2px
    md-padding-x: 6px
    md-radius: "{rounded.4}"
    pill-radius: "{rounded.12}"
    fontSize: 10px
    fontWeight: 500
  input:
    padding-y: 6px
    padding-x: 12px
    rounded: "{rounded.6}"
    fontSize: 12px
  input-sm:
    padding-y: 2px
    padding-x: 8px
    rounded: "{rounded.4}"
  tab:
    pill-padding-y: 4px
    pill-padding-x: 8px
    pill-radius: "{rounded.4}"
    underline-padding-x: 12px
    indicator-width: 2px
    fontSize: 12px
  card:
    rounded: "{rounded.6}"
    padding: "10px 12px"
    border: "1px solid {colors.border.subtle}"

# ── Chromatic Atmosphere (runtime dynamic) ──
atmosphere:
  hue-shift: 0           # ±7 degrees, set by JS hook
  chroma-boost: 0        # ±0.002
  lightness-shift: 0     # ±0.003
  breathe-duration: 45s
---

## Overview

**Design Philosophy**: Ditto is a professional quantitative workstation — not a consumer SaaS, not a content product, not a single research tool. Its visual system serves one goal: enabling faster judgment, smoother operation, and stable long-term use.

**Core Principle**: > Visuals serve judgment first, operation second, aesthetics last. Beauty emerges from efficiency, not from decoration overlaid on efficiency.

**Product Positioning**: Personal quantitative research and live-trading professional workstation. Terminal-style workspace with high information density. Covers Home, Markets, Research, Trading, and Platform as five product domains; AI is embedded intelligence surfaced through Home, Platform Agents, and the global Copilot sidecar.

**Reference Aesthetics**: Linear / Vercel / Raycast — modern SaaS clean style with balanced density. Graphite Studio direction.

**Color Space**: All colors use OKLCH for precise perceptual control. Do not convert to hex or HSL.

## Colors

### Palette Architecture (3 tiers)

1. **L1 Base Primitives** (`tokens-base.css`): Neutral (15-step gray), Brand (Lapis 5-step), Functional (6 colors x 3 steps). No business semantics.
2. **L2 Semantic** (`tokens-semantic.css`): Surface elevation (6 levels), Text hierarchy (7+ levels), Border (3 levels), Brand accent, Signature Brass.
3. **L7 Domain Business** (`tokens-domain.css`): Market, Risk, Execution, System, Data Quality, Model, Agent — each with state-specific foreground/background tokens.

### Brand: Lapis Blue (hue 235)

Selected for its balance between professionalism and visual energy. Not too cold (like pure blue), not too warm — sits at the intersection of trust and clarity.

### Signature: Brass (hue 74)

Used for accent warmth in home and trading domains. Conveys premium quality without garishness. Applied to signature indicators, header underlines, rail light bars.

### Domain Signatures

| Domain | Hue | Color | Personality |
|--------|-----|-------|-------------|
| trading | 74 | Brass | Warm, operational |
| markets | 220 | Cyan | Calm observation |
| research | 300 | Purple | Thinking, exploration |
| platform | 235 | Lapis | Order, control |
| home | 74 | Brass | Warm welcome |

AI is not a product domain signature. Copilot and Agent experiences inherit the current page domain and use model / agent capability tokens for confidence, evidence, and approval states.

### Rules

- **Colors are business language, not UI decoration.** Each color belongs to a specific business semantic domain before reaching components.
- **No cross-domain color mixing.** Market-down green ≠ system-healthy green ≠ risk-low green.
- **Dual-dimension expression required for critical info.** Combine color with text labels, icons, position, weight, or shape.
- **OKLCH only.** Do not convert to hex, RGB, or HSL.

## Typography

### 4-Role Font System

| Role | Font | Fallback | Use Case |
|------|------|----------|----------|
| UI | Inter | Noto Sans SC, Source Han Sans, PingFang SC | Body text, labels, buttons |
| Heading | Geist Sans | Inter | Page titles, section headers |
| Numeric | JetBrains Mono | ui-monospace | Prices, percentages, metrics |
| Code | Geist Mono | JetBrains Mono | Code blocks, technical content |

### Size Scale (9 levels)

| Token | px | Tailwind | Use |
|-------|-----|----------|-----|
| `--font-size-10` | 10 | `text-xs` | Badges, tiny labels |
| `--font-size-11` | 11 | — | Tight contexts |
| `--font-size-12` | 12 | `text-sm` | Default body, table cells |
| `--font-size-13` | 13 | `text-base` | Standard reading |
| `--font-size-14` | 14 | `text-md` | Emphasized body |
| `--font-size-16` | 16 | `text-lg` | Section headers |
| `--font-size-18` | 18 | — | Sub-headings |
| `--font-size-20` | 20 | — | Card titles |
| `--font-size-24` | 24 | `text-2xl` | Page titles |

### Weight Rules

| Weight | Use |
|--------|-----|
| 400 (regular) | Body text, descriptions, data |
| 500 (medium) | Labels, badges, table headers, emphasis |
| 600 (semibold) | Headings, page titles, strong indicators |

### Numeric Rules

- Always use `tabular-nums` and `slashed-zero` for financial figures.
- Monetary values: consistent decimal alignment.
- Percentages: sign alignment.

## Layout

### Shell Architecture (3-zone)

```
┌──────────────────────────────────────────────┐
│ Rail (56px) │ Header (68px)                   │
├─────────────┼────────────────────────────────┤
│             │ Main Content                    │
│ Navigation  │                                 │
│ (domain     │   Primary workspace (55-70%)    │
│  context    │   Secondary workspace (20-30%)  │
│  + nav)     │   Context background            │
│             │                                 │
├─────────────┼────────────────────────────────┤
│             │ Status Bar (24px)               │
└──────────────────────────────────────────────┘
```

### Shell Chrome

- Rail is domain navigation only: Home, Markets, Research, Trading, Platform.
- Header utilities are fixed and global: command, Copilot, notifications, help, account.
- Theme and density live inside Account / View Preferences, not as permanent header segments.
- Local filter/search/export/columns actions belong to workspace or data toolbars.

### Page Types

| Type | Pattern | Examples |
|------|---------|----------|
| Dashboard | Banner + grid panels | Home, Trading Overview, Risk Center |
| List | Table + filters + detail | Strategy List, Factor List, Experiment List |
| Detail | Object center + context rail | Instrument Hub, Strategy Detail, Backtest Result |
| Builder | Editor + preview + config | Strategy Studio, Copilot Sidecar |
| Console | Terminal + activity + logs | Agent Console, Platform Settings |

### Workspace Rules

- **One primary workspace per page** (55-70% attention).
- **One optional secondary workspace** (20-30%).
- **Navigation recedes, context advances.** Users should know their current work before knowing where to go.
- **Information hierarchy**: 3 levels (L1 primary, L2 secondary, L3 collapsible background).

## Elevation & Depth

### Surface Layers (6 levels)

| Level | Token | Purpose |
|-------|-------|---------|
| 0 | `--surface-app` | Application background (deepest) |
| 1 | `--surface-panel-base` | Primary content containers |
| 2 | `--surface-panel-elevated` | Nested cards, secondary panels |
| 3 | `--surface-strip` | Horizontal bars, toolbars |
| 4 | `--surface-overlay` | Floating elements, popovers |
| 5 | `--surface-modal` | Modal dialogs (highest) |

### Frosted Glass

- `--surface-frosted` (85% opacity): Header bars, persistent UI.
- `--surface-frosted-subtle` (80% opacity): Secondary floating elements.

### Overlay System

7-step opacity scale: 2%, 3%, 4%, 6%, 8%, 10%, 12% — used for subtle separators, hover states, and layered surfaces.

## Shapes

### Border Radius (6 levels)

| Token | px | Use |
|-------|-----|-----|
| `--radius-2` | 2 | Badge-sm, checkbox |
| `--radius-3` | 3 | Tight contexts |
| `--radius-4` | 4 | Buttons, badges, inputs-sm, tab pills |
| `--radius-6` | 6 | Cards, inputs, panels (small) |
| `--radius-8` | 8 | Panels (standard) |
| `--radius-12` | 12 | Badge pill, large containers |

### Border Hierarchy (3 levels)

| Token | Use |
|-------|-----|
| `--border-subtle` | Default panel borders, dividers |
| `--border-default` | Inputs, interactive elements |
| `--border-strong` | Selected states, emphasized sections |

## Components

### Core Component Tokens

All component structural tokens are defined in `tokens-component.css` and reference L1/L2 semantic tokens. Key component families:

- **Panel**: `panel` / `panel-header` / `panel-grow` — primary content container
- **Button**: `button-primary` / `button-secondary` / `button-sm`
- **Badge/Tag**: `badge-sm` / `badge-md` / `badge-pill`
- **Input/Select**: `input` / `input-sm`
- **Tab**: `tab-pill` / `tab-underline`
- **Card**: `card` — elevated content block

### Component Token Pattern

```css
/* All component tokens reference semantic tokens */
--btn-radius: var(--radius-4);           /* L1 → component */
--card-border: 1px solid var(--border-subtle);  /* L2 → component */
--badge-font-size: var(--font-size-10);  /* L1 → component */
```

## Domain Identity

### Signature Color Flow

Domain signature colors flow through the page via:

1. **Header underline** — thin colored line under page title
2. **Rail light bar** — subtle accent on active navigation item
3. **Panel breathing border** — faint colored border on hover/focus

### Domain Switching

Signature colors are applied via `data-domain` attribute on the root element:

```html
<div data-domain="trading">  <!-- Brass signature -->
<div data-domain="markets">   <!-- Cyan signature -->
<div data-domain="research">  <!-- Purple signature -->
```

## Chromatic Atmosphere

### Mechanism

Sub-perceptual background color temperature shifts that provide contextual identity without conscious awareness. Runtime-adjusted via JS hook (`useAtmosphere`).

### Parameters

| Variable | Range | Effect |
|----------|-------|--------|
| `--atmosphere-hue-shift` | ±7° | Background hue drift |
| `--atmosphere-chroma-boost` | ±0.002 | Background saturation |
| `--atmosphere-lightness-shift` | ±0.003 | Background lightness |
| `--atmosphere-breathe-duration` | 45s | Full cycle time |

### Implementation

Atmosphere tokens are **runtime dynamic** — set by JS, not static CSS. They modify `--surface-app-atmosphere` which feeds into `--surface-app`.

## Density System

Three presets for different usage contexts:

| Preset | Row Height | Panel Padding | Use Case |
|--------|-----------|---------------|----------|
| dense | 34px | 8px | High-frequency monitoring, data-heavy views |
| compact | 36px | 12px | **Default** — balanced for most workflows |
| comfortable | 42px | 16px | Research, reading-heavy content |

Applied via `data-density` attribute: `<div data-density="compact">`.

## Interaction States

### Focus

- Ring: brand-500 at 50% opacity
- Border: brand-500 at 70% opacity

### Hover

- Subtle: white overlay at 4% (dark) / black overlay at 4% (light)
- Strong: white overlay at 8% (dark) / black overlay at 7% (light)

### Selected

- Background: brand-500 at 12%
- Border: brand-500 at 25%

### Active/Press

- Background: black overlay at 12% (dark) / 8% (light)

## Motion

| Token | Value | Use |
|-------|-------|-----|
| `--motion-duration-fast` | 100ms | Micro-interactions, state changes |
| `--motion-duration-normal` | 200ms | Transitions, reveals |
| `--motion-duration-slow` | 350ms | Page transitions, complex animations |
| `--motion-easing-standard` | ease-out | Default |
| `--motion-easing-emphasis` | ease-in-out | Emphasized movement |

## Data Visualization

### Chart Tokens

- Grid: `oklch(1 0 0 / 0.06)` — subtle grid lines
- Grid major: `oklch(1 0 0 / 0.10)` — major grid lines
- Crosshair: `oklch(1 0 0 / 0.25)`
- Series colors derived from market tokens (up/down/neutral)

### Data Freshness (opacity-based time-fade)

| State | Opacity | Age |
|-------|---------|-----|
| live | 1.0 | Real-time |
| recent | 0.85 | < 30s |
| aging | 0.65 | 30s – 5min |
| stale | 0.40 | 5min – 30min |
| expired | 0.25 | > 30min |

### Asset Class Colors

7 qualitative colors following Paul Tol bright scheme (colorblind-safe): equity (blue), fixed-income (amber), crypto (magenta), commodity (green), fx (cyan), volatility (orange), alternative (purple).

## Do's and Don'ts

### Don'ts

1. **No hex or RGB color values** — use OKLCH tokens only.
2. **No cross-domain color reuse** — market-down green ≠ system-healthy green.
3. **No feature-level inline styles** — use Tailwind CSS utility classes; dynamic chart / progress dimensions belong in allowlisted primitives.
4. **No `@apply` outside `globals.css` or shadcn components**.
5. **No hardcoded pixel values** — use design token references.
6. **No `any` type or `@ts-ignore`** — use `unknown` + type guard.
7. **No gradient/glow/decoration overuse** — restraint over ornamentation.
8. **No multiple primary workspaces per page** — one main, one optional secondary.
9. **No navigation-forwarding** — context must appear before navigation options.
10. **No AI/Agent visual separation** — AI modules follow the same workspace grammar.

### Do's

- Reference semantic tokens (`--text-primary`, `--surface-panel-base`), not base tokens.
- Use `var(--brand-signature-fg)` for domain-colored elements.
- Apply dual-dimension expression for critical information (color + label/shape/position).
- Use `tabular-nums` and `slashed-zero` for all numeric displays.
- Follow L1 → L2 → L7 token hierarchy (base → semantic → domain).
- Test with accessibility: color-blind users must understand structure without color alone.

## Glossary

| Term | Definition |
|------|-----------|
| **Shell** | Page layout framework: Rail + Header + Main. |
| **Rail** | Left navigation sidebar (56px). |
| **Header** | Top bar (68px) with domain title and controls. |
| **Context Rail** | Right sidebar providing object context. |
| **Panel** | Primary content container with header and body. |
| **Panel Grow** | Flexible panel that fills available space. |
| **Strip** | Horizontal bar (toolbar, scope strip). |
| **Pulse** | Status/activity feed in sidebar or dedicated section. |
| **Density** | Spacing/size preset (dense/compact/comfortable). |
| **Domain** | Business area (home/markets/research/trading/platform). |
| **Signature** | Domain-specific accent color (Brass, Cyan, Purple, Lapis). |
| **Chromatic Atmosphere** | Sub-perceptual background color temperature shift. |
| **Token** | CSS custom property for design values. |
| **SSOT** | Single Source of Truth — `src/styles/design-tokens/`. |
