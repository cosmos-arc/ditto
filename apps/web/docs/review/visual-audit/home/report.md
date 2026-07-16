# Visual Audit: home

- Route: `/`
- React URL: http://localhost:5173/
- Prototype URL: http://localhost:8888/docs/designs/specs/prototypes/page-home.html
- Viewport: 1536x900
- Captured: 2026-04-13T09:37:31.138Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| rail | 0, 0, 56x900 | 0, 0, 56x900 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| status | missing | missing | n/a | n/a | n/a | n/a |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| strip | 56, 68, 1480x32 | 56, 68, 1480x32 | 0 | 0 | 0 | 0 |
| main | 56, 100, 1160x800 | 56, 100, 1160x800 | 0 | 0 | 0 | 0 |
| sidebar | 1216, 100, 320x800 | 1216, 100, 320x800 | 0 | 0 | 0 | 0 |
| decision | 73, 117, 1126x147.39 | 73, 117, 1126x147 | 0 | 0 | 0 | -0.39 |
| queue | 72, 277.39, 1128x191.48 | 72, 277, 1128x192 | 0 | -0.39 | 0 | 0.52 |
| secondary | 72, 646.88, 1128x237.13 | 72, 646.14, 1128x237.86 | 0 | -0.74 | 0 | 0.73 |

## Style Diffs

| Target | Property | Prototype | React |
| --- | --- | --- | --- |
| rail | `borderColor` | oklch(0.925 0.004 253) oklch(0.255 0.006 253) oklch(0.925 0.004 253) oklch(0.... | oklch(0.255 0.006 253) |
| rail | `borderLeftColor` | oklch(0.925 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderBottomColor` | oklch(0.925 0.004 253) | oklch(0.255 0.006 253) |
| rail | `borderStyle` | none solid none none | solid |
| rail | `zIndex` | 1 | auto |
| header | `borderColor` | oklch(0.925 0.004 253) oklch(0.925 0.004 253) oklch(0.255 0.006 253) | oklch(0.255 0.006 253) |
| header | `borderLeftColor` | oklch(0.925 0.004 253) | oklch(0.255 0.006 253) |
| header | `borderStyle` | none none solid | solid |
| header | `zIndex` | 1 | 5 |
| shell | `borderStyle` | none | solid |
| strip | `borderColor` | oklch(0.925 0.004 253) oklch(0.925 0.004 253) oklch(0.2858 0.01512 251.56) | oklch(0.555 0.007 253) oklch(0.555 0.007 253) oklch(0.2858 0.01512 251.56) |
| strip | `borderLeftColor` | oklch(0.925 0.004 253) | oklch(0.555 0.007 253) |
| strip | `borderStyle` | none none solid | solid |
| strip | `zIndex` | 1 | auto |
| strip | `fontSize` | 13px | 10px |
| strip | `color` | oklch(0.925 0.004 253) | oklch(0.555 0.007 253) |
| main | `borderStyle` | none | solid |
| main | `zIndex` | 1 | auto |
| sidebar | `borderColor` | oklch(0.925 0.004 253) oklch(0.925 0.004 253) oklch(0.925 0.004 253) oklch(0.... | oklch(0.255 0.006 253) |
| sidebar | `borderBottomColor` | oklch(0.925 0.004 253) | oklch(0.255 0.006 253) |
| sidebar | `borderStyle` | none none none solid | solid |
| sidebar | `zIndex` | 1 | auto |
| decision | `borderStyle` | none none none solid | solid |
| secondary | `borderStyle` | none | solid |

## Warnings

- prototype: Missing selector "status": .status-bar
- prototype: console error: Failed to load resource: the server responded with a status of 404 (File not found)
- react: Missing selector "status": [data-slot='status-bar']
