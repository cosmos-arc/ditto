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

## Required data-* Attributes

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
- Selection-to-command actions must dispatch the schema below with the selected time range, series id, value payload, and originating chart id.
- Toolbar period buttons, if present, must update the same linked time range contract instead of acting as disconnected filters.
- Real implementation should use the existing `lightweight-charts` dependency already declared in `package.json`; do not add another charting dependency for these surfaces.

## Selection Command Schema

`data-chart-selection-command` is the command id for the chart surface. Task 3.2 should route every chart selection through the prototype command/action bus, or an equivalent DOM event bridge when the page is still static HTML:

```ts
type ChartSelectionCommandPayload = {
	chartId: string;
	rangeId: string;
	commandId: string;
	selection: {
		kind: "point" | "range" | "bar" | "series";
	};
	timeRange: {
		from: string;
		to: string;
	};
	timestamp: string | null;
	seriesId: string;
	value: number | string | Record<string, unknown> | null;
};
```

Dispatch contract:

- `chartId` comes from `data-chart-interaction-contract`.
- `rangeId` comes from `data-chart-linked-time-range`.
- `commandId` comes from `data-chart-selection-command`.
- `selection.kind` identifies the user selection shape: `point`, `range`, `bar`, or `series`.
- `timeRange.from` and `timeRange.to` are ISO date/time strings or market session date strings for the visible selected range.
- `timestamp` is the selected datum timestamp for `point` and `bar`; use `null` for pure range or series selections.
- `seriesId` is the selected logical series; use the primary series id when the chart has a single series.
- `value` carries the selected numeric value, OHLC object, risk metric object, or `null` when the selection is range-only.
- The static prototype bridge should emit `prototype:chart-selection-command` with this payload in `CustomEvent.detail`; React implementation may map the same payload into the command palette/action bus.

## Accessibility And Reduced Motion

- Every chart surface must keep an `aria-label`; Task 3.2 should add keyboard navigation for moving the crosshair by datum, zooming the range, and opening the selection command.
- Tooltips must be reachable by keyboard focus and must not rely on color alone for direction, threshold breach, or risk severity.
- `prefers-reduced-motion: reduce` must disable animated crosshair easing, tooltip transitions, and inertial pan while preserving instant state updates.
- Visual focus must use existing interaction focus tokens; no inline styles or new design tokens are allowed for this contract.

## Testing Expectations

Task 3.2 must cover at least these boundaries:

- DOM contract: each required `data-chart-interaction-contract` id appears exactly once per representative page, and no undeclared chart marker is present.
- Interaction: pointer hover/drag updates crosshair, tooltip, zoom, pan, and selected range state.
- Keyboard/a11y: focus can move the active datum, zoom the range, open the selection command, and expose tooltip content without pointer input.
- Reduced motion: `prefers-reduced-motion: reduce` disables animated crosshair, tooltip, and pan easing while preserving instant state changes.
- Linked range sync: charts sharing `data-chart-linked-time-range` stay synchronized after period button changes, zoom, pan, and refresh.
- Selection command payload: point, range, bar, and series selections dispatch `prototype:chart-selection-command` or the React equivalent with the schema fields above.
