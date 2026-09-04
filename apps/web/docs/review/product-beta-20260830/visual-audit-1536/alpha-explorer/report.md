# Visual Audit: alpha-explorer

- Result: **PASS**
- Pixel diff: **4.47%**
- Route: `/research/alpha`
- React URL: http://127.0.0.1:5173/research/alpha
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-alpha-explorer.html
- Viewport: 1536x900
- Captured: 2026-08-30T06:14:53.772Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1536x876 | 0, 0, 1536x900 | 0 | 0 | 0 | 24 |
| rail | 0, 0, 56x876 | 0, 0, 56x900 | 0 | 0 | 0 | 24 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| source | 56, 68, 276x636 | 56, 68, 276x636 | 0 | 0 | 0 | 0 |
| main | 333, 68, 842x636 | 332, 68, 844x636 | -1 | 0 | 2 | 0 |
| inspector | 1176, 68, 360x808 | 1176, 68, 360x808 | 0 | 0 | 0 | 0 |
| adoption | 56, 704, 276x172 | 56, 704, 276x172 | 0 | 0 | 0 | 0 |
| graph | 333, 704, 842x172 | 332, 704, 844x172 | -1 | 0 | 2 | 0 |
| status | 56, 876, 1480x24 | 56, 876, 1480x24 | 0 | 0 | 0 | 0 |

## Style Diffs

| Target | Property | Prototype | React |
| --- | --- | --- | --- |
| shell | `borderStyle` | none | solid |
| shell | `background` | linear-gradient(oklch(0.64 0.12 235 / 0.05), rgba(0, 0, 0, 0) 240px) repeat s... | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| shell | `backgroundImage` | linear-gradient(oklch(0.64 0.12 235 / 0.05), rgba(0, 0, 0, 0) 240px), none | none |
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
| source | `borderColor` | oklch(0.94 0.004 253) oklch(0.255 0.006 253) oklch(0.255 0.006 253) oklch(0.9... | oklch(0.255 0.006 253) |
| source | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| source | `borderStyle` | none solid solid none | solid |
| source | `background` | oklch(0.184 0.011 253 / 0.92) none repeat scroll 0% 0% / auto padding-box bor... | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box |
| source | `zIndex` | 1 | auto |
| source | `backgroundColor` | oklch(0.184 0.011 253 / 0.92) | oklch(0.184 0.011 253) |
| main | `borderColor` | oklch(0.38856 0.03092 266.16) oklch(0.255 0.006 253) oklch(0.255 0.006 253) o... | oklch(0.255 0.006 253) |
| main | `borderLeftColor` | oklch(0.38856 0.03092 266.16) | oklch(0.255 0.006 253) |
| main | `borderStyle` | none solid solid none | solid |
| main | `background` | oklch(0.184 0.011 253 / 0.92) none repeat scroll 0% 0% / auto padding-box bor... | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box |
| main | `zIndex` | 1 | auto |
| main | `borderWidth` | 0px 1px 1px 0px | 0px 0px 1px |
| main | `backgroundColor` | oklch(0.184 0.011 253 / 0.92) | oklch(0.184 0.011 253) |
| inspector | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.255 0.006 253) |
| inspector | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| inspector | `borderStyle` | none none none solid | solid |
| inspector | `background` | oklch(0.184 0.011 253 / 0.94) none repeat scroll 0% 0% / auto padding-box bor... | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box |
| inspector | `backgroundColor` | oklch(0.184 0.011 253 / 0.94) | oklch(0.184 0.011 253) |
| adoption | `borderColor` | oklch(0.94 0.004 253) oklch(0.255 0.006 253) oklch(0.255 0.006 253) oklch(0.9... | oklch(0.255 0.006 253) |
| adoption | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| adoption | `borderStyle` | none solid solid none | solid |
| adoption | `background` | oklch(0.184 0.011 253 / 0.92) none repeat scroll 0% 0% / auto padding-box bor... | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box |
| adoption | `zIndex` | 1 | auto |
| adoption | `borderWidth` | 0px 1px 1px 0px | 0px 1px 0px 0px |
| adoption | `backgroundColor` | oklch(0.184 0.011 253 / 0.92) | oklch(0.184 0.011 253) |
| graph | `borderColor` | oklch(0.94 0.004 253) oklch(0.255 0.006 253) oklch(0.255 0.006 253) oklch(0.9... | oklch(0.255 0.006 253) |
| graph | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| graph | `borderStyle` | none solid solid none | solid |
| graph | `background` | oklch(0.184 0.011 253 / 0.92) none repeat scroll 0% 0% / auto padding-box bor... | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box |
| graph | `zIndex` | 1 | auto |
| graph | `borderWidth` | 0px 1px 1px 0px | 0px |
| graph | `backgroundColor` | oklch(0.184 0.011 253 / 0.92) | oklch(0.184 0.011 253) |
| status | `borderColor` | oklch(0.255 0.006 253) oklch(0.605 0.007 253) oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderLeftColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderBottomColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderStyle` | solid none none | solid |
| status | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | oklch(0.166 0.01 253) none repeat scroll 0% 0% / auto padding-box border-box |
| status | `zIndex` | 3 | 50 |
| status | `backgroundColor` | oklch(0.184 0.011 253) | oklch(0.166 0.01 253) |

## Warnings

No missing target selectors or page issues.
