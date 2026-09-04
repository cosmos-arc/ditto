# Visual Audit: strategy-list

- Result: **PASS**
- Pixel diff: **5.23%**
- Route: `/research/strategies`
- React URL: http://127.0.0.1:5173/research/strategies
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-strategy-list.html
- Viewport: 1200x800
- Captured: 2026-08-30T06:43:02.583Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1200x800 | 0, 0, 1200x800 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x800 | 0, 0, 56x800 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1144x68 | 56, 0, 1144x68 | 0 | 0 | 0 | 0 |
| toolbar | 56, 68, 1144x32 | 56, 68, 1144x32 | 0 | 0 | 0 | 0 |
| main | 56, 137, 843x663 | 56, 137, 844x663 | 0 | 0 | 1 | 0 |
| detail | 900, 100, 300x700 | 900, 100, 300x700 | 0 | 0 | 0 | 0 |
| governance-summary | 56, 100, 843x37 | 56, 100, 844x37 | 0 | 0 | 1 | 0 |

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
| header | `zIndex` | 120 | 5 |
| toolbar | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| toolbar | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| toolbar | `borderStyle` | none none solid | solid |
| main | `borderStyle` | none | solid |
| main | `background` | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box |
| main | `backgroundColor` | rgba(0, 0, 0, 0) | oklch(0.184 0.011 253) |
| detail | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.255 0.006 253) |
| detail | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| detail | `borderStyle` | none none none solid | solid |
| governance-summary | `borderColor` | oklch(0.38856 0.03092 266.16) oklch(0.38856 0.03092 266.16) oklch(0.255 0.006... | oklch(0.255 0.006 253) |
| governance-summary | `borderLeftColor` | oklch(0.38856 0.03092 266.16) | oklch(0.255 0.006 253) |
| governance-summary | `borderStyle` | none none solid | solid |

## Warnings

No missing target selectors or page issues.
