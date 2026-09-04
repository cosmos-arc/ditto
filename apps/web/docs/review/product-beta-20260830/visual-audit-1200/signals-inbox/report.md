# Visual Audit: signals-inbox

- Result: **PASS**
- Pixel diff: **4.96%**
- Route: `/trading/signals`
- React URL: http://127.0.0.1:5173/trading/signals
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-signals-inbox.html
- Viewport: 1200x800
- Captured: 2026-08-30T06:24:26.987Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1200x776 | 0, 0, 1200x800 | 0 | 0 | 0 | 24 |
| rail | 0, 0, 56x776 | 0, 0, 56x800 | 0 | 0 | 0 | 24 |
| header | 56, 0, 1144x68 | 56, 0, 1144x68 | 0 | 0 | 0 | 0 |
| health | 56, 68, 1144x36 | 56, 68, 1144x36 | 0 | 0 | 0 | 0 |
| main | 56, 104, 763x672 | 56, 104, 764x672 | 0 | 0 | 1 | 0 |
| detail | 820, 104, 380x672 | 820, 104, 380x672 | 0 | 0 | 0 | 0 |
| status | 0, 776, 1200x24 | 0, 776, 1200x24 | 0 | 0 | 0 | 0 |

## Style Diffs

| Target | Property | Prototype | React |
| --- | --- | --- | --- |
| shell | `borderStyle` | none | solid |
| rail | `borderColor` | oklch(0.94 0.004 253) oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94... | oklch(0.255 0.006 253) |
| rail | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderStyle` | none solid none none | solid |
| rail | `zIndex` | 10 | auto |
| header | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| header | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| header | `borderStyle` | none none solid | solid |
| health | `boxShadow` | oklch(0.166 0.01 253 / 0.08) 0px 1px 6px -2px | none |
| health | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.3705 0.0402 247.6) | oklch(0.94 0.004 253) |
| health | `borderBottomColor` | oklch(0.3705 0.0402 247.6) | oklch(0.94 0.004 253) |
| health | `borderStyle` | none none solid | solid |
| health | `background` | oklch(0.176 0.004 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| health | `zIndex` | 1 | auto |
| health | `borderWidth` | 0px 0px 1px | 0px |
| health | `backgroundColor` | oklch(0.176 0.004 253) | rgba(0, 0, 0, 0) |
| main | `borderStyle` | none | solid |
| main | `zIndex` | 1 | auto |
| detail | `borderColor` | oklch(0.3964 0.01972 202.88) oklch(0.3964 0.01972 202.88) oklch(0.3964 0.0197... | oklch(0.94 0.004 253) |
| detail | `borderLeftColor` | oklch(0.325 0.008 253) | oklch(0.94 0.004 253) |
| detail | `borderBottomColor` | oklch(0.3964 0.01972 202.88) | oklch(0.94 0.004 253) |
| detail | `borderStyle` | none none none solid | solid |
| detail | `background` | oklch(0.215 0.012 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| detail | `zIndex` | 1 | auto |
| detail | `borderWidth` | 0px 0px 0px 1px | 0px |
| detail | `backgroundColor` | oklch(0.215 0.012 253) | rgba(0, 0, 0, 0) |
| status | `backdropFilter` | blur(8px) | none |
| status | `borderColor` | oklch(0.31275 0.0231 250.3) oklch(0.605 0.007 253) oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderLeftColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderBottomColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderStyle` | solid none none | solid |
| status | `zIndex` | 25 | 50 |
| status | `letterSpacing` | 0.2px | normal |

## Warnings

No missing target selectors or page issues.
