# Visual Audit: instrument-hub

- Result: **PASS**
- Pixel diff: **2.47%**
- Route: `/instruments/$id`
- React URL: http://127.0.0.1:5173/instruments/1000001
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-instrument-hub.html
- Viewport: 1536x900
- Captured: 2026-08-30T03:25:10.319Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x900 | 0, 0, 56x900 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1480x76 | 56, 0, 1480x68 | 0 | 0 | 0 | -8 |
| meta | 240.03, 9, 837.97x57 | 56, 68, 1480x62.20 | -184.03 | 59 | 642.03 | 5.20 |
| tabs | 56, 112, 1480x45 | 56, 130.20, 1480x44 | 0 | 18.20 | 0 | -1 |
| main | 56, 157, 1140x525 | 56, 174.20, 1480x665.30 | 0 | 17.20 | 340 | 140.30 |
| bottom | 56, 682, 1140x194 | 56, 839.50, 1480x36.50 | 0 | 157.50 | 340 | -157.50 |
| status | 56, 876, 1480x24 | 56, 876, 1480x24 | 0 | 0 | 0 | 0 |

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
| header | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| header | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| header | `borderStyle` | none none solid | solid |
| header | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | oklch(0.166 0.01 253 / 0.85) none repeat scroll 0% 0% / auto padding-box bord... |
| header | `zIndex` | 120 | 5 |
| header | `backgroundColor` | oklch(0.184 0.011 253) | oklch(0.166 0.01 253 / 0.85) |
| meta | `borderColor` | oklch(0.38828 0.03092 243.76) | oklch(0.94 0.004 253) |
| meta | `borderLeftColor` | oklch(0.38828 0.03092 243.76) | oklch(0.94 0.004 253) |
| meta | `borderBottomColor` | oklch(0.38828 0.03092 243.76) | oklch(0.94 0.004 253) |
| meta | `borderStyle` | none | solid |
| meta | `background` | oklch(0.20041 0.01352 252.01) none repeat scroll 0% 0% / auto padding-box bor... | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| meta | `backgroundColor` | oklch(0.20041 0.01352 252.01) | rgba(0, 0, 0, 0) |
| tabs | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| tabs | `borderBottomColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| tabs | `borderStyle` | none none solid | solid |
| tabs | `background` | oklch(0.166 0.01 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| tabs | `borderWidth` | 0px 0px 1px | 0px |
| tabs | `backgroundColor` | oklch(0.166 0.01 253) | rgba(0, 0, 0, 0) |
| main | `borderStyle` | none | solid |
| main | `zIndex` | 1 | auto |
| bottom | `borderColor` | oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) | oklch(0.94 0.004 253) |
| bottom | `borderStyle` | solid none none | solid |
| bottom | `zIndex` | 1 | auto |
| bottom | `borderWidth` | 1px 0px 0px | 0px |
| status | `backdropFilter` | blur(8px) | none |
| status | `borderColor` | oklch(0.255 0.006 253) oklch(0.66 0.007 253) oklch(0.66 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderLeftColor` | oklch(0.66 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderBottomColor` | oklch(0.66 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderStyle` | solid none none | solid |
| status | `zIndex` | 3 | 50 |
| status | `fontSize` | 12px | 10px |
| status | `letterSpacing` | 0.24px | normal |
| status | `color` | oklch(0.66 0.007 253) | oklch(0.605 0.007 253) |

## Warnings

No missing target selectors or page issues.
