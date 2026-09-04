# Visual Audit: regime-monitor

- Result: **PASS**
- Pixel diff: **3.61%**
- Route: `/research/regime`
- React URL: http://127.0.0.1:5173/research/regime
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-regime-monitor.html
- Viewport: 1366x768
- Captured: 2026-08-30T06:24:13.347Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1366x768 | 0, 0, 1366x768 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x768 | 0, 0, 56x768 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1310x68 | 56, 0, 1310x68 | 0 | 0 | 0 | 0 |
| strip | 56, 68, 1310x36 | 56, 68, 1310x42 | 0 | 0 | 0 | 6 |
| main | 72, 157, 962x571 | 56, 110, 1010x490 | -16 | -47 | 48 | -81 |
| activity | 1050, 157, 300x571 | 1066, 110, 300x490 | 16 | -47 | 0 | -81 |

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
| strip | `boxShadow` | oklch(0.166 0.01 253 / 0.08) 0px 1px 6px -2px | none |
| strip | `borderColor` | oklch(0.38856 0.03092 266.16) oklch(0.38856 0.03092 266.16) oklch(0.3705 0.04... | oklch(0.94 0.004 253) |
| strip | `borderLeftColor` | oklch(0.38856 0.03092 266.16) | oklch(0.94 0.004 253) |
| strip | `borderBottomColor` | oklch(0.3705 0.0402 247.6) | oklch(0.94 0.004 253) |
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

## Warnings

No missing target selectors or page issues.
