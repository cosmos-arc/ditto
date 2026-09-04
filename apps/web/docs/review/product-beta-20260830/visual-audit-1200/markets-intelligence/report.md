# Visual Audit: markets-intelligence

- Result: **PASS**
- Pixel diff: **3.80%**
- Route: `/markets/intelligence`
- React URL: http://127.0.0.1:5173/markets/intelligence
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-markets-intelligence.html
- Viewport: 1200x800
- Captured: 2026-08-30T06:23:57.751Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1200x800 | 0, 0, 1200x800 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x800 | 0, 0, 56x800 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1144x68 | 56, 0, 1144x68 | 0 | 0 | 0 | 0 |
| strip | 56, 68, 1144x35 | 56, 68, 1144x61.47 | 0 | 0 | 0 | 26.47 |
| main | 56, 103, 824x572 | 56, 129.47, 844x598.53 | 0 | 26.47 | 20 | 26.53 |
| activity | 880, 103, 320x668 | 900, 129.47, 300x646.53 | 20 | 26.47 | -20 | -21.47 |
| analysis | 56, 675, 824x96 | 56, 728, 844x48 | 0 | 53 | 20 | -48 |

## Style Diffs

| Target | Property | Prototype | React |
| --- | --- | --- | --- |
| shell | `borderStyle` | none | solid |
| rail | `borderColor` | oklch(0.94 0.004 253) oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94... | oklch(0.255 0.006 253) |
| rail | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderStyle` | none solid none none | solid |
| rail | `zIndex` | 30 | auto |
| header | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| header | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| header | `borderStyle` | none none solid | solid |
| header | `zIndex` | 120 | 5 |
| strip | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| strip | `borderBottomColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| strip | `borderStyle` | none none solid | solid |
| strip | `background` | oklch(0.166 0.01 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| strip | `zIndex` | 15 | auto |
| strip | `borderWidth` | 0px 0px 1px | 0px |
| strip | `backgroundColor` | oklch(0.166 0.01 253) | rgba(0, 0, 0, 0) |
| main | `borderStyle` | none | solid |
| activity | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.94 0.004 253) |
| activity | `borderLeftColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| activity | `borderStyle` | none none none solid | solid |
| activity | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| activity | `borderWidth` | 0px 0px 0px 1px | 0px |
| activity | `backgroundColor` | oklch(0.184 0.011 253) | rgba(0, 0, 0, 0) |
| analysis | `borderColor` | oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) | oklch(0.94 0.004 253) |
| analysis | `borderStyle` | solid none none | solid |
| analysis | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| analysis | `borderWidth` | 1px 0px 0px | 0px |
| analysis | `backgroundColor` | oklch(0.184 0.011 253) | rgba(0, 0, 0, 0) |

## Warnings

No missing target selectors or page issues.
