# Visual Audit: a-shares

- Result: **PASS**
- Pixel diff: **17.16%**
- Route: `/markets/a-shares`
- React URL: http://127.0.0.1:5173/markets/a-shares
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-a-shares.html
- Viewport: 1536x900
- Captured: 2026-08-30T06:14:48.442Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x900 | 0, 0, 56x900 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1474x68 | 56, 0, 1480x68 | 0 | 0 | 6 | 0 |
| strip | 56, 100, 1474x32 | 56, 68, 1480x47.47 | 0 | -32 | 6 | 15.47 |
| main | 56, 132, 1174x551.50 | 56, 115.47, 1180x784.53 | 0 | -16.53 | 6 | 233.03 |
| activity | 1230, 132, 300x551.50 | 1236, 115.47, 300x784.53 | 6 | -16.53 | 0 | 233.03 |

## Style Diffs

| Target | Property | Prototype | React |
| --- | --- | --- | --- |
| shell | `borderStyle` | none | solid |
| shell | `background` | oklch(0.166 0.01 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| shell | `backgroundColor` | oklch(0.166 0.01 253) | rgba(0, 0, 0, 0) |
| rail | `borderColor` | oklch(0.94 0.004 253) oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94... | oklch(0.255 0.006 253) |
| rail | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderStyle` | none solid none none | solid |
| rail | `zIndex` | 30 | auto |
| header | `backdropFilter` | none | blur(12px) |
| header | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| header | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| header | `borderStyle` | none none solid | solid |
| header | `background` | oklch(0.166 0.01 253) none repeat scroll 0% 0% / auto padding-box border-box | oklch(0.166 0.01 253 / 0.85) none repeat scroll 0% 0% / auto padding-box bord... |
| header | `zIndex` | 120 | 5 |
| header | `backgroundColor` | oklch(0.166 0.01 253) | oklch(0.166 0.01 253 / 0.85) |
| strip | `borderColor` | oklch(0.38828 0.03092 243.76) oklch(0.38828 0.03092 243.76) oklch(0.255 0.006... | oklch(0.94 0.004 253) |
| strip | `borderLeftColor` | oklch(0.38828 0.03092 243.76) | oklch(0.94 0.004 253) |
| strip | `borderBottomColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| strip | `borderStyle` | none none solid | solid |
| strip | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| strip | `zIndex` | 14 | auto |
| strip | `borderWidth` | 0px 0px 1px | 0px |
| strip | `backgroundColor` | oklch(0.184 0.011 253) | rgba(0, 0, 0, 0) |
| main | `borderStyle` | none | solid |
| activity | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.94 0.004 253) |
| activity | `borderLeftColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| activity | `borderStyle` | none none none solid | solid |
| activity | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| activity | `borderWidth` | 0px 0px 0px 1px | 0px |
| activity | `backgroundColor` | oklch(0.184 0.011 253) | rgba(0, 0, 0, 0) |

## Warnings

No missing target selectors or page issues.
