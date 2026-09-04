# Visual Audit: orders-ledger

- Result: **PASS**
- Pixel diff: **3.64%**
- Route: `/trading/orders`
- React URL: http://127.0.0.1:5173/trading/orders
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-orders-ledger.html
- Viewport: 1536x900
- Captured: 2026-08-30T06:22:56.839Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1536x876 | 0, 0, 1536x900 | 0 | 0 | 0 | 24 |
| rail | 0, 0, 56x876 | 0, 0, 56x900 | 0 | 0 | 0 | 24 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| health | 56, 68, 1480x36 | 56, 68, 1480x36 | 0 | 0 | 0 | 0 |
| main | 56, 152, 1139x724 | 56, 152, 1140x728 | 0 | 0 | 1 | 4 |
| detail | 1196, 104, 340x772 | 1196, 104, 340x772 | 0 | 0 | 0 | 0 |
| status | 0, 876, 1536x24 | 0, 876, 1536x24 | 0 | 0 | 0 | 0 |

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
| health | `boxShadow` | oklch(0.166 0.01 253 / 0.08) 0px 1px 6px -2px | none |
| health | `borderColor` | oklch(0.3964 0.01972 202.88) oklch(0.3964 0.01972 202.88) oklch(0.3705 0.0402... | oklch(0.94 0.004 253) |
| health | `borderLeftColor` | oklch(0.3964 0.01972 202.88) | oklch(0.94 0.004 253) |
| health | `borderBottomColor` | oklch(0.3705 0.0402 247.6) | oklch(0.94 0.004 253) |
| health | `borderStyle` | none none solid | solid |
| health | `background` | oklch(0.176 0.004 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| health | `zIndex` | 1 | auto |
| health | `borderWidth` | 0px 0px 1px | 0px |
| health | `backgroundColor` | oklch(0.176 0.004 253) | rgba(0, 0, 0, 0) |
| main | `borderStyle` | none | solid |
| detail | `borderColor` | oklch(0.3474 0.03336 248.68) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklc... | oklch(0.94 0.004 253) |
| detail | `borderLeftColor` | oklch(0.255 0.006 253) | oklch(0.94 0.004 253) |
| detail | `borderStyle` | solid none none solid | solid |
| detail | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| detail | `borderWidth` | 1px 0px 0px 1px | 0px |
| detail | `backgroundColor` | oklch(0.184 0.011 253) | rgba(0, 0, 0, 0) |
| status | `backdropFilter` | blur(8px) | none |
| status | `borderColor` | oklch(0.35125 0.0345 248.5) oklch(0.605 0.007 253) oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderLeftColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderBottomColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderStyle` | solid none none | solid |
| status | `zIndex` | 25 | 50 |
| status | `letterSpacing` | 0.2px | normal |

## Warnings

No missing target selectors or page issues.
