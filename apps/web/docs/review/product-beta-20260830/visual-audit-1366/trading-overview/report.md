# Visual Audit: trading-overview

- Result: **PASS**
- Pixel diff: **4.35%**
- Route: `/trading`
- React URL: http://127.0.0.1:5173/trading
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-trading-overview.html
- Viewport: 1366x768
- Captured: 2026-08-30T06:24:38.362Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1366x744 | 0, 0, 1366x768 | 0 | 0 | 0 | 24 |
| rail | 0, 0, 56x744 | 0, 0, 56x768 | 0 | 0 | 0 | 24 |
| header | 56, 0, 1310x68 | 56, 0, 1310x68 | 0 | 0 | 0 | 0 |
| strip | 56, 68, 1310x36 | 56, 68, 1310x36 | 0 | 0 | 0 | 0 |
| main | 56, 251.88, 1010x312.13 | 56, 251.88, 1010x312.13 | 0 | 0 | 0 | 0 |
| activity | 1066, 251.88, 300x492.13 | 1066, 251.88, 300x492.13 | 0 | 0 | 0 | 0 |
| analysis | 56, 564, 1010x180 | 56, 564, 1010x180 | 0 | 0 | 0 | 0 |
| status | 0, 744, 1310x24 | 0, 744, 1310x24 | 0 | 0 | 0 | 0 |

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
| strip | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.3705 0.0402 247.6) | oklch(0.94 0.004 253) |
| strip | `borderBottomColor` | oklch(0.3705 0.0402 247.6) | oklch(0.94 0.004 253) |
| strip | `borderStyle` | none none solid | solid |
| strip | `background` | oklch(0.176 0.004 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| strip | `zIndex` | 1 | auto |
| strip | `borderWidth` | 0px 0px 1px | 0px |
| strip | `backgroundColor` | oklch(0.176 0.004 253) | rgba(0, 0, 0, 0) |
| main | `borderStyle` | none | solid |
| main | `zIndex` | 1 | auto |
| activity | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.94 0.004 253) |
| activity | `borderLeftColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| activity | `borderStyle` | none none none solid | solid |
| activity | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| activity | `zIndex` | 1 | auto |
| activity | `borderWidth` | 0px 0px 0px 1px | 0px |
| activity | `backgroundColor` | oklch(0.184 0.011 253) | rgba(0, 0, 0, 0) |
| analysis | `borderColor` | oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) | oklch(0.94 0.004 253) |
| analysis | `borderStyle` | solid none none | solid |
| analysis | `background` | oklch(0.215 0.012 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| analysis | `zIndex` | 1 | auto |
| analysis | `borderWidth` | 1px 0px 0px | 0px |
| analysis | `backgroundColor` | oklch(0.215 0.012 253) | rgba(0, 0, 0, 0) |
| status | `backdropFilter` | blur(8px) | none |
| status | `borderColor` | oklch(0.255 0.006 253) oklch(0.605 0.007 253) oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderLeftColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderBottomColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderStyle` | solid none none | solid |
| status | `zIndex` | 25 | 50 |
| status | `letterSpacing` | 0.2px | normal |

## Warnings

No missing target selectors or page issues.
