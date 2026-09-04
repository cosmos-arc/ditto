# Visual Audit: strategies-detail

- Result: **FAIL**
- Pixel diff: **3.61%**
- Route: `/research/strategies/$id`
- React URL: http://127.0.0.1:5173/research/strategies/$id
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-strategies-detail.html
- Viewport: 1200x800
## Blocking Failures

- geometry-height-ratio (rail): actual 2.3203287125425414, allowed 0.05
- geometry-x (header): actual 20, allowed 4
- geometry-y (header): actual 14.59, allowed 4
- geometry-width-ratio (header): actual 0.7177177177177178, allowed 0.03
- geometry-height-ratio (header): actual 0.34734619445244264, allowed 0.05
- geometry-y (meta): actual 8, allowed 4
- geometry-height-ratio (meta): actual 1.1111111111111112, allowed 0.08
- geometry-y (tabs): actual 32, allowed 4
- geometry-height-ratio (tabs): actual 0.2, allowed 0.08
- geometry-y (main): actual 23, allowed 4
- geometry-height-ratio (main): actual 9.514810179390906, allowed 0.08
- geometry-y (bottom): actual 563.06, allowed 4
- geometry-height-ratio (bottom): actual 0.1111111111111111, allowed 0.08

- Captured: 2026-08-29T14:42:20.867Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1200x800 | 0, 0, 1200x800 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x240.94 | 0, 0, 56x800 | 0 | 0 | 0 | 559.06 |
| header | 76, -14.59, 666x104.19 | 56, 0, 1144x68 | -20 | 14.59 | 478 | -36.19 |
| meta | 56, 76, 1144x36 | 56, 68, 1144x76 | 0 | -8 | 0 | 40 |
| tabs | 56, 112, 1144x45 | 56, 144, 1144x36 | 0 | 32 | 0 | -9 |
| main | 56, 157, 1144x47.94 | 56, 180, 1144x504.08 | 0 | 23 | 0 | 456.14 |
| bottom | 56, 204.94, 1144x36 | 56, 768, 1144x32 | 0 | 563.06 | 0 | -4 |

## Style Diffs

| Target | Property | Prototype | React |
| --- | --- | --- | --- |
| shell | `borderStyle` | none | solid |
| rail | `borderColor` | oklch(0.94 0.004 253) oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94... | oklch(0.255 0.006 253) |
| rail | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderStyle` | none solid none none | solid |
| rail | `zIndex` | 10 | auto |
| header | `backdropFilter` | none | blur(12px) |
| header | `borderColor` | oklch(0.38856 0.03092 266.16) | oklch(0.255 0.006 253) |
| header | `borderLeftColor` | oklch(0.38856 0.03092 266.16) | oklch(0.255 0.006 253) |
| header | `borderBottomColor` | oklch(0.38856 0.03092 266.16) | oklch(0.255 0.006 253) |
| header | `borderStyle` | none | solid |
| header | `background` | oklch(0.20044 0.01352 254.41) none repeat scroll 0% 0% / auto padding-box bor... | oklch(0.166 0.01 253 / 0.85) none repeat scroll 0% 0% / auto padding-box bord... |
| header | `zIndex` | auto | 5 |
| header | `borderWidth` | 0px | 0px 0px 1px |
| header | `backgroundColor` | oklch(0.20044 0.01352 254.41) | oklch(0.166 0.01 253 / 0.85) |
| meta | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| meta | `borderBottomColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| meta | `borderStyle` | none none solid | solid |
| meta | `background` | oklch(0.176 0.004 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| meta | `zIndex` | 1 | auto |
| meta | `borderWidth` | 0px 0px 1px | 0px |
| meta | `backgroundColor` | oklch(0.176 0.004 253) | rgba(0, 0, 0, 0) |
| tabs | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| tabs | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| tabs | `borderStyle` | none none solid | solid |
| tabs | `background` | oklch(0.166 0.01 253) none repeat scroll 0% 0% / auto padding-box border-box | oklch(0.176 0.004 253) none repeat scroll 0% 0% / auto padding-box border-box |
| tabs | `borderWidth` | 0px 0px 1px | 1px 0px |
| tabs | `backgroundColor` | oklch(0.166 0.01 253) | oklch(0.176 0.004 253) |
| main | `borderStyle` | none | solid |
| main | `fontSize` | 13px | 12px |
| bottom | `borderColor` | oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| bottom | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| bottom | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| bottom | `borderStyle` | solid none none | solid |
| bottom | `zIndex` | 1 | auto |
| bottom | `fontSize` | 13px | 11px |
| bottom | `color` | oklch(0.94 0.004 253) | oklch(0.605 0.007 253) |

## Warnings

No missing target selectors or page issues.
