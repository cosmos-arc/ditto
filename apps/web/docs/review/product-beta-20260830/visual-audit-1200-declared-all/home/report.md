# Visual Audit: home

- Result: **PASS**
- Pixel diff: **5.00%**
- Route: `/`
- React URL: http://127.0.0.1:5173/
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-home.html
- Viewport: 1200x800
- Captured: 2026-08-30T06:42:24.031Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1200x800 | 0, 0, 1200x800 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x800 | 0, 0, 56x800 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1144x68 | 56, 0, 1144x68 | 0 | 0 | 0 | 0 |
| pulse | 56, 68, 1144x24 | 56, 68, 1144x24 | 0 | 0 | 0 | 0 |
| main | 56, 92, 824x708 | 56, 92, 824x708 | 0 | 0 | 0 | 0 |
| sidebar | 880, 92, 320x708 | 880, 92, 320x708 | 0 | 0 | 0 | 0 |
| decision-banner | 72, 135, 792x96 | 73, 136, 790x94 | 1 | 1 | -2 | -2 |
| priority-queue | 72, 243, 792x329.50 | 72, 243, 792x329.50 | 0 | 0 | 0 | 0 |
| secondary | 72, 584.50, 792x508.16 | 72, 584.50, 792x508 | 0 | 0 | 0 | -0.16 |

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
| pulse | `boxShadow` | none | oklch(0.64 0.12 235 / 0.06) 0px 1px 4px -1px |
| pulse | `borderColor` | oklch(0.2954 0.00992 238.68) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.605 0.007 253) oklch(0.605 0.007 253) oklch(0.2858 0.01512 251.56) |
| pulse | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.605 0.007 253) |
| pulse | `borderBottomColor` | oklch(0.255 0.006 253) | oklch(0.2858 0.01512 251.56) |
| pulse | `borderStyle` | solid none | solid |
| pulse | `background` | oklch(0.22272 0.00808 238.68) none repeat scroll 0% 0% / auto padding-box bor... | oklch(0.176 0.004 253) none repeat scroll 0% 0% / auto padding-box border-box |
| pulse | `zIndex` | 1 | auto |
| pulse | `fontSize` | 13px | 10px |
| pulse | `borderWidth` | 1px 0px | 0px 0px 1px |
| pulse | `backgroundColor` | oklch(0.22272 0.00808 238.68) | oklch(0.176 0.004 253) |
| pulse | `color` | oklch(0.94 0.004 253) | oklch(0.605 0.007 253) |
| main | `borderStyle` | none | solid |
| main | `zIndex` | 1 | auto |
| sidebar | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.255 0.006 253) |
| sidebar | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| sidebar | `borderStyle` | none none none solid | solid |
| sidebar | `zIndex` | 1 | auto |
| decision-banner | `borderColor` | oklch(0.3459 0.01482 220.78) oklch(0.3964 0.01972 202.88) oklch(0.3964 0.0197... | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.64 ... |
| decision-banner | `borderLeftColor` | oklch(0.3964 0.01972 202.88) | oklch(0.64 0.12 235 / 0.35) |
| decision-banner | `borderBottomColor` | oklch(0.3964 0.01972 202.88) | oklch(0.94 0.004 253) |
| decision-banner | `background` | oklch(0.20128 0.01232 247.63) none repeat scroll 0% 0% / auto padding-box bor... | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| decision-banner | `zIndex` | 1 | auto |
| decision-banner | `borderRadius` | 8px | 0px |
| decision-banner | `borderWidth` | 1px | 0px 0px 0px 2px |
| decision-banner | `backgroundColor` | oklch(0.20128 0.01232 247.63) | rgba(0, 0, 0, 0) |
| secondary | `zIndex` | 1 | auto |

## Warnings

No missing target selectors or page issues.
