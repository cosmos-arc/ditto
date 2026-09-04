# Visual Audit: portfolio

- Result: **PASS**
- Pixel diff: **1.93%**
- Route: `/trading/portfolio`
- React URL: http://127.0.0.1:5173/trading/portfolio
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-portfolio.html
- Viewport: 1200x800
- Captured: 2026-08-30T06:42:33.458Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1200x800 | 0, 0, 1200x800 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x800 | 0, 0, 56x800 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1144x68 | 56, 0, 1144x68 | 0 | 0 | 0 | 0 |
| strip | 56, 68, 1144x36 | 56, 68, 1144x36 | 0 | 0 | 0 | 0 |
| main | 56, 104, 884x476 | 56, 104, 884x476 | 0 | 0 | 0 | 0 |
| activity | 940, 104, 260x696 | 940, 104, 260x696 | 0 | 0 | 0 | 0 |
| analysis | 56, 580, 884x220 | 56, 580, 884x220 | 0 | 0 | 0 | 0 |

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
| strip | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| strip | `borderBottomColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| strip | `borderStyle` | none none solid | solid |
| strip | `background` | oklch(0.176 0.004 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| strip | `borderWidth` | 0px 0px 1px | 0px |
| strip | `backgroundColor` | oklch(0.176 0.004 253) | rgba(0, 0, 0, 0) |
| main | `borderStyle` | none | solid |
| activity | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.94 0.004 253) |
| activity | `borderLeftColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| activity | `borderStyle` | none none none solid | solid |
| activity | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| activity | `borderWidth` | 0px 0px 0px 1px | 0px |
| activity | `backgroundColor` | oklch(0.184 0.011 253) | rgba(0, 0, 0, 0) |
| analysis | `borderColor` | oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) | oklch(0.94 0.004 253) |
| analysis | `borderStyle` | solid none none | solid |
| analysis | `background` | oklch(0.215 0.012 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| analysis | `borderWidth` | 1px 0px 0px | 0px |
| analysis | `backgroundColor` | oklch(0.215 0.012 253) | rgba(0, 0, 0, 0) |

## Warnings

No missing target selectors or page issues.
