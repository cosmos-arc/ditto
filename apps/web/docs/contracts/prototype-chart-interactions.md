# Prototype Chart Interaction Contract

> Scope: Phase 3 prototype chart placeholders. This contract marks analysis surfaces that must become interactive charts in Task 3.2 without changing dependencies.

## Required Affordances

Every marked chart surface must support these affordance tokens:

| Affordance | Token | Requirement |
| --- | --- | --- |
| Crosshair | `crosshair` | Pointer and keyboard focus expose a vertical or XY reference line tied to the active datum. |
| Tooltip | `tooltip` | Hover, focus, and selection expose readable value, time, series name, and threshold context. |
| Zoom / pan | `zoom-pan` | Wheel, pinch, drag, keyboard, and explicit controls can inspect a narrower or wider time range. |
| Linked time range | `linked-time-range` | Charts sharing a range id synchronize visible logical range and selected timestamp. |
| Selection to command | `selection-to-command` | Selecting a point, range, bar, or series exposes a stable command action for downstream workflow. |

## Required `data-*` Attributes

Marked prototype placeholders use these attributes as the machine-readable handoff to React and `lightweight-charts`.

| Attribute | Required | Value |
| --- | --- | --- |
| `data-chart-interaction-contract` | Yes | Stable chart id unique within the prototype page. |
| `data-chart-affordances` | Yes | Space-separated tokens: `crosshair tooltip zoom-pan linked-time-range selection-to-command`. |
| `data-chart-linked-time-range` | Yes | Stable range group id. Charts with the same value synchronize their visible time range. |
| `data-chart-selection-command` | Yes | Stable command id invoked from chart selection. |
| `aria-label` | Yes | Human-readable chart purpose and current data scope. |

Optional implementation metadata may add `data-chart-series`, `data-chart-resolution`, or `data-chart-thresholds` when Task 3.2 wires real data.

## Representative Pages

| Page | Prototype | Required chart ids |
| --- | --- | --- |
| Instrument Hub | `page-instrument-hub.html` | `instrument-price-primary` |
| Risk Center | `page-risk-center.html` | `risk-var-trend`, `risk-drawdown-trend`, `risk-exposure-breakdown` |
| Backtest Result | `page-backtest-result.html` | `backtest-nav-drawdown` |
| Trading Overview | `page-trading-overview.html` | `trading-equity-pnl` |

## Interaction Rules

- Crosshair and tooltip state must be derived from chart model state, not decorative SVG-only elements.
- Linked time range updates must preserve the user's explicit zoom / pan range across refreshes within the same view.
- Selection-to-command actions must pass the selected time range, series id, value payload, and originating chart id.
- Toolbar period buttons, if present, must update the same linked time range contract instead of acting as disconnected filters.
- Real implementation should use the existing `lightweight-charts` dependency already declared in `package.json`; do not add another charting dependency for these surfaces.

## Accessibility And Reduced Motion

- Every chart surface must keep an `aria-label`; Task 3.2 should add keyboard navigation for moving the crosshair by datum, zooming the range, and opening the selection command.
- Tooltips must be reachable by keyboard focus and must not rely on color alone for direction, threshold breach, or risk severity.
- `prefers-reduced-motion: reduce` must disable animated crosshair easing, tooltip transitions, and inertial pan while preserving instant state updates.
- Visual focus must use existing interaction focus tokens; no inline styles or new design tokens are allowed for this contract.
