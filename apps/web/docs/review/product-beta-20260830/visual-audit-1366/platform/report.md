# Visual Audit: platform

- Result: **PASS**
- Pixel diff: **6.74%**
- Route: `/platform`
- React URL: http://127.0.0.1:5173/platform
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-platform.html
- Viewport: 1366x768
- Captured: 2026-08-30T06:24:08.049Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1366x744 | 0, 0, 1366x768 | 0 | 0 | 0 | 24 |
| rail | 0, 0, 56x744 | 0, 0, 56x768 | 0 | 0 | 0 | 24 |
| header | 56, 0, 1310x68 | 56, 0, 1310x68 | 0 | 0 | 0 | 0 |
| health | 56, 68, 1310x36 | 56, 68, 1310x37 | 0 | 0 | 0 | 1 |
| main | 56, 104, 970x640 | 56, 105, 970x639 | 0 | 1 | 0 | -1 |
| detail | 1026, 104, 340x640 | 1026, 105, 340x639 | 0 | 1 | 0 | -1 |
| status | 0, 744, 1366x24 | 0, 744, 1366x24 | 0 | 0 | 0 | 0 |

## Style Diffs

| Target | Property | Prototype | React |
| --- | --- | --- | --- |
| shell | `borderStyle` | none | solid |
| rail | `borderColor` | oklch(0.94 0.004 253) oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94... | oklch(0.255 0.006 253) |
| rail | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderStyle` | none solid none none | solid |
| rail | `zIndex` | 1 | auto |
| header | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| header | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| header | `borderStyle` | none none solid | solid |
| header | `zIndex` | 1 | 5 |
| health | `borderColor` | oklch(0.3628 0.03232 247.96) oklch(0.3628 0.03232 247.96) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| health | `borderLeftColor` | oklch(0.3628 0.03232 247.96) | oklch(0.255 0.006 253) |
| health | `borderStyle` | none none solid | solid |
| health | `zIndex` | 1 | auto |
| main | `borderStyle` | none | solid |
| detail | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.255 0.006 253) |
| detail | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| detail | `borderStyle` | none none none solid | solid |
| detail | `zIndex` | 1 | auto |
| status | `backdropFilter` | blur(8px) | none |
| status | `borderColor` | oklch(0.255 0.006 253) oklch(0.605 0.007 253) oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderLeftColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderBottomColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderStyle` | solid none none | solid |
| status | `zIndex` | 25 | 50 |
| status | `letterSpacing` | 0.2px | normal |

## Warnings

No missing target selectors or page issues.
