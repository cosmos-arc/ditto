# Visual Audit: strategy-studio

- Result: **PASS**
- Pixel diff: **4.00%**
- Route: `/research/strategies/$id/studio`
- React URL: http://127.0.0.1:5173/research/strategies/$id/studio
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-strategy-studio.html
- Viewport: 1366x768
- Captured: 2026-08-29T15:14:52.230Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1366x744 | 0, 0, 1366x768 | 0 | 0 | 0 | 24 |
| rail | 0, 0, 56x744 | 0, 0, 56x768 | 0 | 0 | 0 | 24 |
| header | 56, 0, 1310x68 | 56, 0, 1310x68 | 0 | 0 | 0 | 0 |
| modes | 56, 68, 1310x36 | 56, 68, 1310x36 | 0 | 0 | 0 | 0 |
| source | 56, 104, 240x508 | 56, 104, 240x508 | 0 | 0 | 0 | 0 |
| main | 297, 104, 768x508 | 296, 104, 770x508 | -1 | 0 | 2 | 0 |
| inspector | 1066, 104, 300x508 | 1066, 104, 300x508 | 0 | 0 | 0 | 0 |
| logs | 56, 612, 1310x132 | 56, 612, 1310x132 | 0 | 0 | 0 | 0 |
| status | 56, 744, 1310x24 | 56, 744, 1310x24 | 0 | 0 | 0 | 0 |

## Style Diffs

| Target | Property | Prototype | React |
| --- | --- | --- | --- |
| shell | `borderStyle` | none | solid |
| rail | `borderColor` | oklch(0.94 0.004 253) oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94... | oklch(0.255 0.006 253) |
| rail | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderStyle` | none solid none none | solid |
| rail | `zIndex` | 1 | auto |
| header | `borderColor` | oklch(0.38856 0.03092 266.16) oklch(0.38856 0.03092 266.16) oklch(0.255 0.006... | oklch(0.255 0.006 253) |
| header | `borderLeftColor` | oklch(0.38856 0.03092 266.16) | oklch(0.255 0.006 253) |
| header | `borderStyle` | none none solid | solid |
| modes | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.3531 0.0237 267.1) | oklch(0.94 0.004 253) |
| modes | `borderBottomColor` | oklch(0.3531 0.0237 267.1) | oklch(0.94 0.004 253) |
| modes | `borderStyle` | none none solid | solid |
| modes | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| modes | `zIndex` | 1 | auto |
| modes | `borderWidth` | 0px 0px 1px | 0px |
| modes | `backgroundColor` | oklch(0.184 0.011 253) | rgba(0, 0, 0, 0) |
| source | `borderColor` | oklch(0.94 0.004 253) oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94... | oklch(0.94 0.004 253) |
| source | `borderStyle` | none solid none none | solid |
| source | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| source | `zIndex` | 1 | auto |
| source | `borderWidth` | 0px 1px 0px 0px | 0px |
| source | `backgroundColor` | oklch(0.184 0.011 253) | rgba(0, 0, 0, 0) |
| main | `borderStyle` | none | solid |
| main | `background` | oklch(0.166 0.01 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| main | `zIndex` | 1 | auto |
| main | `backgroundColor` | oklch(0.166 0.01 253) | rgba(0, 0, 0, 0) |
| inspector | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.94 0.004 253) |
| inspector | `borderLeftColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| inspector | `borderStyle` | none none none solid | solid |
| inspector | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| inspector | `zIndex` | 1 | auto |
| inspector | `borderWidth` | 0px 0px 0px 1px | 0px |
| inspector | `backgroundColor` | oklch(0.184 0.011 253) | rgba(0, 0, 0, 0) |
| logs | `borderColor` | oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) | oklch(0.94 0.004 253) |
| logs | `borderStyle` | solid none none | solid |
| logs | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| logs | `zIndex` | 1 | auto |
| logs | `borderWidth` | 1px 0px 0px | 0px |
| logs | `backgroundColor` | oklch(0.184 0.011 253) | rgba(0, 0, 0, 0) |
| status | `backdropFilter` | blur(8px) | none |
| status | `borderColor` | oklch(0.255 0.006 253) oklch(0.605 0.007 253) oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderLeftColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderBottomColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderStyle` | solid none none | solid |
| status | `zIndex` | 25 | 50 |
| status | `letterSpacing` | 0.2px | normal |

## Warnings

No missing target selectors or page issues.
