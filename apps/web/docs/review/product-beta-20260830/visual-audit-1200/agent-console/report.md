# Visual Audit: agent-console

- Result: **FAIL**
- Pixel diff: **4.73%**
- Route: `/platform/agents`
- React URL: http://127.0.0.1:5173/platform/agents
- Prototype URL: http://127.0.0.1:8888/docs/designs/specs/prototypes/page-agent-console-v2.html
- Viewport: 1200x800
## Blocking Failures

- geometry-width-ratio (source): actual 3.2214022140221403, allowed 0.03
- geometry-height-ratio (source): actual 0.6006756756756757, allowed 0.05
- geometry-x (main): actual 272, allowed 4
- geometry-y (main): actual 265.95, allowed 4
- geometry-width-ratio (main): actual 1.2, allowed 0.03
- geometry-height-ratio (main): actual 0.8409159159159159, allowed 0.05
- geometry-x (inspector): actual 793, allowed 4
- geometry-y (inspector): actual 371.91, allowed 4
- geometry-width-ratio (inspector): actual 2.259259259259259, allowed 0.03
- geometry-height-ratio (inspector): actual 0.5584234234234234, allowed 0.05

- Captured: 2026-08-30T06:23:22.303Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| shell | 0, 0, 1200x776 | 0, 0, 1200x800 | 0 | 0 | 0 | 24 |
| rail | 0, 0, 56x776 | 0, 0, 56x800 | 0 | 0 | 0 | 24 |
| header | 56, 0, 1144x68 | 56, 0, 1144x68 | 0 | 0 | 0 | 0 |
| tabs | 56, 68, 1144x42 | 56, 68, 1144x42 | 0 | 0 | 0 | 0 |
| source | 56, 110, 271x666 | 56, 110, 1144x265.95 | 0 | 0 | 873 | -400.05 |
| main | 328, 110, 520x666 | 56, 375.95, 1144x105.95 | -272 | 265.95 | 624 | -560.05 |
| inspector | 849, 110, 351x666 | 56, 481.91, 1144x294.09 | -793 | 371.91 | 793 | -371.91 |
| status | 56, 776, 1144x24 | 56, 776, 1144x24 | 0 | 0 | 0 | 0 |

## Style Diffs

| Target | Property | Prototype | React |
| --- | --- | --- | --- |
| shell | `borderStyle` | none | solid |
| shell | `background` | oklch(0.166 0.01 253) none repeat scroll 0% 0% / auto padding-box border-box | rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box |
| shell | `backgroundColor` | oklch(0.166 0.01 253) | rgba(0, 0, 0, 0) |
| rail | `borderColor` | oklch(0.94 0.004 253) oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94... | oklch(0.255 0.006 253) |
| rail | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderStyle` | none solid none none | solid |
| rail | `background` | oklch(0.215 0.012 253) none repeat scroll 0% 0% / auto padding-box border-box | oklch(0.166 0.01 253) none repeat scroll 0% 0% / auto padding-box border-box |
| rail | `zIndex` | 1 | auto |
| rail | `backgroundColor` | oklch(0.215 0.012 253) | oklch(0.166 0.01 253) |
| header | `borderColor` | oklch(0.3628 0.03232 247.96) oklch(0.3628 0.03232 247.96) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| header | `borderLeftColor` | oklch(0.3628 0.03232 247.96) | oklch(0.255 0.006 253) |
| header | `borderStyle` | none none solid | solid |
| header | `zIndex` | 1 | 5 |
| tabs | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| tabs | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| tabs | `borderStyle` | none none solid | solid |
| tabs | `background` | oklch(0.184 0.011 253 / 0.92) none repeat scroll 0% 0% / auto padding-box bor... | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box |
| tabs | `zIndex` | 1 | auto |
| tabs | `backgroundColor` | oklch(0.184 0.011 253 / 0.92) | oklch(0.184 0.011 253) |
| source | `borderColor` | oklch(0.94 0.004 253) oklch(0.255 0.006 253) oklch(0.94 0.004 253) oklch(0.94... | oklch(0.255 0.006 253) |
| source | `borderLeftColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| source | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| source | `borderStyle` | none solid none none | solid |
| source | `background` | oklch(0.184 0.011 253 / 0.92) none repeat scroll 0% 0% / auto padding-box bor... | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box |
| source | `zIndex` | 1 | auto |
| source | `borderWidth` | 0px 1px 0px 0px | 0px 0px 1px |
| source | `backgroundColor` | oklch(0.184 0.011 253 / 0.92) | oklch(0.184 0.011 253) |
| main | `borderStyle` | none | solid |
| main | `background` | oklch(0.184 0.011 253 / 0.88) none repeat scroll 0% 0% / auto padding-box bor... | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box |
| main | `zIndex` | 1 | auto |
| main | `backgroundColor` | oklch(0.184 0.011 253 / 0.88) | oklch(0.184 0.011 253) |
| inspector | `borderColor` | oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.94 0.004 253) oklch(0.255... | oklch(0.255 0.006 253) |
| inspector | `borderBottomColor` | oklch(0.94 0.004 253) | oklch(0.255 0.006 253) |
| inspector | `borderStyle` | none none none solid | solid |
| inspector | `background` | oklch(0.184 0.011 253 / 0.94) none repeat scroll 0% 0% / auto padding-box bor... | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box |
| inspector | `zIndex` | 1 | auto |
| inspector | `borderWidth` | 0px 0px 0px 1px | 1px 0px 0px |
| inspector | `backgroundColor` | oklch(0.184 0.011 253 / 0.94) | oklch(0.184 0.011 253) |
| status | `borderColor` | oklch(0.255 0.006 253) oklch(0.605 0.007 253) oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderLeftColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderBottomColor` | oklch(0.605 0.007 253) | oklch(0.255 0.006 253) |
| status | `borderStyle` | solid none none | solid |
| status | `background` | oklch(0.184 0.011 253) none repeat scroll 0% 0% / auto padding-box border-box | oklch(0.166 0.01 253) none repeat scroll 0% 0% / auto padding-box border-box |
| status | `zIndex` | 3 | auto |
| status | `fontSize` | 10px | 11px |
| status | `backgroundColor` | oklch(0.184 0.011 253) | oklch(0.166 0.01 253) |

## Warnings

No missing target selectors or page issues.
