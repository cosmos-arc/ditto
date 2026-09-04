# Visual Audit: review-list

- Result: **PASS**
- Pixel diff: **3.75%**
- Route: `/research/reviews`
- React URL: http://127.0.0.1:5173/research/reviews
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-experiment-list.html
- Viewport: 1536x900
- Captured: 2026-08-30T06:15:48.213Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x900 | 0, 0, 56x900 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| toolbar | 56, 68, 1480x32 | 56, 108, 1480x48 | 0 | 40 | 0 | 16 |
| main | 56, 137, 1159x763 | 56, 156, 1160x744 | 0 | 19 | 1 | -19 |
| detail | 1216, 100, 320x800 | 1216, 156, 320x744 | 0 | 56 | 0 | -56 |

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
| toolbar | `background` | oklch(0.176 0.004 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| toolbar | `borderWidth` | 0px 0px 1px | 0px |
| toolbar | `backgroundColor` | oklch(0.176 0.004 253) | rgba(0, 0, 0, 0) |
| main | `borderStyle` | none | solid |
| detail | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.94 0.004 253) |
| detail | `borderLeftColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| detail | `borderStyle` | none none none solid | solid |
| detail | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| detail | `borderWidth` | 0px 0px 0px 1px | 0px |
| detail | `backgroundColor` | oklch(0.184 0.011 253) | rgba(0, 0, 0, 0) |

## Warnings

No missing target selectors or page issues.
