# Visual Audit: platform-settings

- Result: **PASS**
- Pixel diff: **3.22%**
- Route: `/platform/settings`
- React URL: http://127.0.0.1:5173/platform/settings
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-platform-settings.html
- Viewport: 1536x900
- Captured: 2026-08-30T06:15:32.441Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| rail | 0, 0, 56x900 | 0, 0, 56x900 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| health | 56, 68, 1480x36 | 56, 68, 1480x36 | 0 | 0 | 0 | 0 |
| main | 56, 104, 1140x796 | 56, 104, 1140x796 | 0 | 0 | 0 | 0 |
| detail | 1196, 104, 340x796 | 1196, 104, 340x796 | 0 | 0 | 0 | 0 |

## Style Diffs

| Target | Property | Prototype | React |
| --- | --- | --- | --- |
| shell | `borderStyle` | none | solid |
| shell | `background` | linear-gradient(oklch(0.64 0.12 235 / 0.04), rgba(0, 0, 0, 0) 160px) repeat s... | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| shell | `backgroundImage` | linear-gradient(oklch(0.64 0.12 235 / 0.04), rgba(0, 0, 0, 0) 160px), none | none |
| shell | `backgroundColor` | oklch(0.166 0.01 253) | rgba(0, 0, 0, 0) |
| rail | `borderColor` | oklch(0.94 0.004 253) oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94... | oklch(0.255 0.006 253) |
| rail | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderStyle` | none solid none none | solid |
| rail | `background` | oklch(0.215 0.012 253) none repeat scroll 0% 0% / auto padding-box border-box | oklch(0.166 0.01 253) none repeat scroll 0% 0% / auto padding-box border-box |
| rail | `zIndex` | 1 | auto |
| rail | `backgroundColor` | oklch(0.215 0.012 253) | oklch(0.166 0.01 253) |
| header | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| header | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| header | `borderStyle` | none none solid | solid |
| header | `zIndex` | 1 | 5 |
| health | `borderColor` | oklch(0.3628 0.03232 247.96) oklch(0.3628 0.03232 247.96) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| health | `borderLeftColor` | oklch(0.3628 0.03232 247.96) | oklch(0.255 0.006 253) |
| health | `borderStyle` | none none solid | solid |
| health | `zIndex` | 1 | auto |
| main | `borderStyle` | none | solid |
| main | `zIndex` | 1 | auto |
| detail | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.255 0.006 253) |
| detail | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| detail | `borderStyle` | none none none solid | solid |
| detail | `zIndex` | 1 | auto |

## Warnings

No missing target selectors or page issues.
