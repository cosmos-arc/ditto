# Visual Audit: cross-market

- Result: **PASS**
- Pixel diff: **4.10%**
- Route: `/markets`
- React URL: http://127.0.0.1:5173/markets
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-cross-market.html
- Viewport: 1536x900
- Captured: 2026-08-30T06:15:01.650Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x900 | 0, 0, 56x900 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1474x68 | 56, 0, 1480x68 | 0 | 0 | 6 | 0 |
| context-bar | 56, 68, 1474x32 | 56, 68, 1480x32 | 0 | 0 | 6 | 0 |
| scope-strip | 56, 100, 1474x37.19 | 56, 100, 1480x48.47 | 0 | 0 | 6 | 11.28 |
| main | 56, 137.19, 1174x707.81 | 56, 148.47, 1180x331.20 | 0 | 11.28 | 6 | -376.61 |
| right-rail | 1230, 137.19, 300x707.81 | 1236, 148.47, 300x134.42 | 6 | 11.28 | 0 | -573.39 |
| status | 56, 876, 1474x24 | 56, 876, 1480x24 | 0 | 0 | 6 | 0 |

## Style Diffs

| Target | Property | Prototype | React |
| --- | --- | --- | --- |
| shell | `borderStyle` | none | solid |
| shell | `background` | radial-gradient(80% 50% at 50% 0%, oklch(0.198 0.012 253 / 0.4), rgba(0, 0, 0... | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| shell | `backgroundImage` | radial-gradient(80% 50% at 50% 0%, oklch(0.198 0.012 253 / 0.4), rgba(0, 0, 0... | none |
| shell | `backgroundColor` | oklch(0.166 0.01 253) | rgba(0, 0, 0, 0) |
| rail | `borderColor` | oklch(0.94 0.004 253) oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94... | oklch(0.255 0.006 253) |
| rail | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderStyle` | none solid none none | solid |
| rail | `zIndex` | 30 | auto |
| header | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| header | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| header | `borderStyle` | none none solid | solid |
| header | `zIndex` | 120 | 5 |
| context-bar | `boxShadow` | oklch(0.166 0.01 253 / 0.08) 0px 1px 6px 0px | oklch(0.64 0.12 235 / 0.06) 0px 1px 4px -1px |
| context-bar | `backdropFilter` | blur(12px) | none |
| context-bar | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.2858 0.01512 251.56) |
| context-bar | `borderBottomColor` | oklch(0.255 0.006 253) | oklch(0.2858 0.01512 251.56) |
| context-bar | `borderStyle` | none none solid | solid |
| context-bar | `background` | oklch(0.166 0.01 253 / 0.8) none repeat scroll 0% 0% / auto padding-box borde... | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| context-bar | `fontSize` | 12px | 13px |
| context-bar | `backgroundColor` | oklch(0.166 0.01 253 / 0.8) | rgba(0, 0, 0, 0) |
| scope-strip | `backdropFilter` | blur(12px) | none |
| scope-strip | `borderColor` | oklch(0.38828 0.03092 243.76) oklch(0.38828 0.03092 243.76) oklch(0.255 0.006... | oklch(0.94 0.004 253) |
| scope-strip | `borderLeftColor` | oklch(0.38828 0.03092 243.76) | oklch(0.94 0.004 253) |
| scope-strip | `borderBottomColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| scope-strip | `borderStyle` | none none solid | solid |
| scope-strip | `background` | oklch(0.166 0.01 253 / 0.8) none repeat scroll 0% 0% / auto padding-box borde... | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| scope-strip | `fontSize` | 12px | 13px |
| scope-strip | `borderWidth` | 0px 0px 1px | 0px |
| scope-strip | `backgroundColor` | oklch(0.166 0.01 253 / 0.8) | rgba(0, 0, 0, 0) |
| main | `borderStyle` | none | solid |
| right-rail | `borderStyle` | none none none solid | solid |
| status | `backdropFilter` | blur(8px) | none |
| status | `borderColor` | oklch(1 0 0 / 0.04) oklch(0.66 0.007 253) oklch(0.66 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderLeftColor` | oklch(0.66 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderBottomColor` | oklch(0.66 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderStyle` | solid none none | solid |
| status | `background` | oklch(0.166 0.01 253 / 0.9) none repeat scroll 0% 0% / auto padding-box borde... | oklch(0.166 0.01 253) none repeat scroll 0% 0% / auto padding-box border-box |
| status | `zIndex` | 25 | 50 |
| status | `letterSpacing` | 0.2px | normal |
| status | `backgroundColor` | oklch(0.166 0.01 253 / 0.9) | oklch(0.166 0.01 253) |
| status | `color` | oklch(0.66 0.007 253) | oklch(0.605 0.007 253) |

## Warnings

No missing target selectors or page issues.
