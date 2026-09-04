# Visual Audit: factor-analysis

- Result: **PASS**
- Pixel diff: **3.50%**
- Route: `/research/factors/$id`
- React URL: http://127.0.0.1:5173/research/factors/$id
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-factor-analysis.html
- Viewport: 1200x800
- Captured: 2026-08-30T06:42:14.612Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1200x800 | 0, 0, 1200x800 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x800 | 0, 0, 56x800 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1144x76 | 56, 0, 1144x68 | 0 | 0 | 0 | -8 |
| meta | 56, 76, 1144x36 | 56, 68, 1144x66.20 | 0 | -8 | 0 | 30.20 |
| main | 56, 157, 1144x607 | 56, 204.86, 1144x550.14 | 0 | 47.86 | 0 | -56.86 |
| sidebar | 844, 169, 340x583 | 848, 216.86, 340x526.14 | 4 | 47.86 | 0 | -56.86 |

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
| meta | `boxShadow` | oklch(0.166 0.01 253 / 0.08) 0px 1px 6px -2px | none |
| meta | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.3705 0.0402 247.6) | oklch(0.94 0.004 253) |
| meta | `borderBottomColor` | oklch(0.3705 0.0402 247.6) | oklch(0.94 0.004 253) |
| meta | `borderStyle` | none none solid | solid |
| meta | `background` | oklch(0.176 0.004 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| meta | `zIndex` | 1 | auto |
| meta | `borderWidth` | 0px 0px 1px | 0px |
| meta | `backgroundColor` | oklch(0.176 0.004 253) | rgba(0, 0, 0, 0) |
| main | `borderStyle` | none | solid |
| sidebar | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.255 0.006 253) |
| sidebar | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| sidebar | `borderStyle` | none none none solid | solid |
| sidebar | `background` | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box | oklch(0.215 0.012 253) none repeat scroll 0% 0% / auto padding-box border-box |
| sidebar | `backgroundColor` | rgba(0, 0, 0, 0) | oklch(0.215 0.012 253) |

## Warnings

No missing target selectors or page issues.
