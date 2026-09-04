# Visual Audit: risk-center

- Result: **FAIL**
- Pixel diff: **2.00%**
- Route: `/trading/risk`
- React URL: http://127.0.0.1:5173/trading/risk
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-risk-center.html
- Viewport: 1200x800
## Blocking Failures

- pixel-diff: actual 0.020015625, allowed 0.02

- Captured: 2026-08-30T06:24:24.189Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1200x800 | 0, 0, 1200x800 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x800 | 0, 0, 56x800 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1144x68 | 56, 0, 1144x68 | 0 | 0 | 0 | 0 |
| strip | 56, 68, 1144x36 | 56, 68, 1144x36 | 0 | 0 | 0 | 0 |
| main | 72, 254, 796x347 | 72, 254, 796x347 | 0 | 0 | 0 | 0 |
| activity | 884, 254, 300x347 | 884, 254, 300x347 | 0 | 0 | 0 | 0 |
| analysis | 56, 617, 1144x257.39 | 56, 617, 1144x257 | 0 | 0 | 0 | -0.39 |
| status | 56, 776, 1144x24 | 56, 776, 1144x24 | 0 | 0 | 0 | 0 |

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
| strip | `boxShadow` | oklch(0.166 0.01 253 / 0.08) 0px 1px 6px -2px | none |
| strip | `borderColor` | oklch(0.3964 0.01972 202.88) oklch(0.3964 0.01972 202.88) oklch(0.3705 0.0402... | oklch(0.255 0.006 253) |
| strip | `borderLeftColor` | oklch(0.3964 0.01972 202.88) | oklch(0.255 0.006 253) |
| strip | `borderBottomColor` | oklch(0.3705 0.0402 247.6) | oklch(0.255 0.006 253) |
| strip | `borderStyle` | none none solid | solid |
| strip | `zIndex` | 1 | auto |
| main | `borderStyle` | none | solid |
| activity | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.255 0.006 253) |
| activity | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| activity | `borderStyle` | none none none solid | solid |
| analysis | `borderColor` | oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| analysis | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| analysis | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| analysis | `borderStyle` | solid none none | solid |
| status | `backdropFilter` | blur(8px) | none |
| status | `borderColor` | oklch(0.255 0.006 253) oklch(0.605 0.007 253) oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderLeftColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderBottomColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderStyle` | solid none none | solid |
| status | `zIndex` | 1 | 50 |
| status | `letterSpacing` | 0.2px | normal |

## Warnings

No missing target selectors or page issues.
