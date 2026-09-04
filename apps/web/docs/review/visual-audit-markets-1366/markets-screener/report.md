# Visual Audit: markets-screener

- Result: **PASS**
- Pixel diff: **3.68%**
- Route: `/markets/screener`
- React URL: http://127.0.0.1:5173/markets/screener
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-markets-screener.html
- Viewport: 1366x768
- Captured: 2026-08-30T03:26:36.066Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1366x768 | 0, 0, 1366x768 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x768 | 0, 0, 56x768 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1310x68 | 56, 0, 1310x68 | 0 | 0 | 0 | 0 |
| toolbar | 56, 68, 1310x32 | 56, 68, 1310x57.47 | 0 | 0 | 0 | 25.47 |
| main | 56, 311, 989x457 | 56, 125.47, 990x642.53 | 0 | -185.53 | 1 | 185.53 |
| detail | 1046, 100, 320x668 | 1046, 125.47, 320x642.53 | 0 | 25.47 | 0 | -25.47 |

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
| toolbar | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| toolbar | `borderBottomColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| toolbar | `borderStyle` | none none solid | solid |
| toolbar | `background` | oklch(0.17 0.01 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| toolbar | `borderWidth` | 0px 0px 1px | 0px |
| toolbar | `backgroundColor` | oklch(0.17 0.01 253) | rgba(0, 0, 0, 0) |
| main | `borderStyle` | none | solid |
| detail | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.94 0.004 253) |
| detail | `borderLeftColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| detail | `borderStyle` | none none none solid | solid |
| detail | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| detail | `borderWidth` | 0px 0px 0px 1px | 0px |
| detail | `backgroundColor` | oklch(0.184 0.011 253) | rgba(0, 0, 0, 0) |

## Warnings

No missing target selectors or page issues.
