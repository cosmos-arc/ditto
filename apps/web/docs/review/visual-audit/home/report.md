# Visual Audit: home

- Route: `/`
- React URL: http://127.0.0.1:5176/
- Prototype URL: http://127.0.0.1:8766/page-home.html
- Viewport: 1536x900
- Captured: 2026-04-11T02:40:18.806Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| rail | 0, 0, 56x900 | 0, 0, 56x368 | 0 | 0 | 0 | -532 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| status | missing | 56, 876, 1480x24 | n/a | n/a | n/a | n/a |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| strip | 56, 68, 1480x32 | 56, 68, 1480x28 | 0 | 0 | 0 | -4 |
| main | 56, 100, 1160x800 | missing | n/a | n/a | n/a | n/a |
| sidebar | 1216, 100, 320x800 | 1216, 96, 320x441.13 | 0 | -4 | 0 | -358.87 |
| decision | 73, 117, 1126x147.39 | 72, 112, 1128x215.55 | -1 | -5 | 2 | 68.16 |
| queue | 72, 277.39, 1128x191.48 | 72, 339.55, 1128x266.13 | 0 | 62.16 | 0 | 74.65 |
| secondary | 72, 646.88, 1128x237.13 | missing | n/a | n/a | n/a | n/a |
| layout | missing | 56, 68, 1480x808 | n/a | n/a | n/a | n/a |
| content | missing | 56, 68, 1480x808 | n/a | n/a | n/a | n/a |

## Warnings

- targets: prototype target "main" has no matching react target
- targets: prototype target "secondary" has no matching react target
- targets: react target "layout" has no matching prototype target
- targets: react target "content" has no matching prototype target
- prototype: Missing selector "status": .status-bar
- prototype: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- prototype: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
