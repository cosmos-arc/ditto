# Visual Audit: backtest-result

- Result: **PASS**
- Pixel diff: **3.33%**
- Route: `/research/backtest/$id`
- React URL: http://127.0.0.1:5173/research/backtest/bt-001
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-backtest-result.html
- Viewport: 1200x800
- Captured: 2026-08-30T06:41:51.857Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1200x800 | 0, 0, 1200x800 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x800 | 0, 0, 56x800 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1144x76 | 56, 0, 1144x68 | 0 | 0 | 0 | -8 |
| meta | 56, 76, 1144x36 | 56, 68, 1144x36 | 0 | -8 | 0 | 0 |
| tabs | 56, 112, 1144x45 | 56, 160, 1144x45 | 0 | 48 | 0 | 0 |
| main | 56, 157, 1144x607 | 56, 205, 1144x559 | 0 | 48 | 0 | -48 |
| bottom | 56, 764, 1144x36 | 56, 764, 1144x36 | 0 | 0 | 0 | 0 |

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
| meta | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.3705 0.0402 247.6) | oklch(0.255 0.006 253) |
| meta | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| meta | `borderBottomColor` | oklch(0.3705 0.0402 247.6) | oklch(0.255 0.006 253) |
| meta | `borderStyle` | none none solid | solid |
| meta | `zIndex` | 1 | auto |
| tabs | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| tabs | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| tabs | `borderStyle` | none none solid | solid |
| tabs | `background` | oklch(0.166 0.01 253) none repeat scroll 0% 0% / auto padding-box border-box | oklch(0.176 0.004 253) none repeat scroll 0% 0% / auto padding-box border-box |
| tabs | `backgroundColor` | oklch(0.166 0.01 253) | oklch(0.176 0.004 253) |
| main | `borderStyle` | none | solid |
| bottom | `borderColor` | oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| bottom | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| bottom | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| bottom | `borderStyle` | solid none none | solid |
| bottom | `zIndex` | 1 | auto |
| bottom | `fontSize` | 13px | 10px |
| bottom | `color` | oklch(0.94 0.004 253) | oklch(0.605 0.007 253) |

## Warnings

No missing target selectors or page issues.
