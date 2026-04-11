# Visual Audit: research

- Route: `/research`
- React URL: http://localhost:5173/research
- Prototype URL: http://localhost:8889/page-research.html
- Viewport: 1536x900
- Captured: 2026-04-11T15:21:28.089Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| rail | 0, 0, 56x845 | 0, 0, 56x900 | 0 | 0 | 0 | 55 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| status | missing | 84, 173.13, 4x16 | n/a | n/a | n/a | n/a |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| strip | 56, 68, 1480x36 | 56, 68, 1480x34.14 | 0 | 0 | 0 | -1.86 |
| main | missing | 56, 102.14, 1180x577.86 | n/a | n/a | n/a | n/a |
| analysis | 56, 665, 1180x180 | 56, 680, 1180x220 | 0 | 15 | 0 | 40 |
| content | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| layout | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| banner | missing | missing | n/a | n/a | n/a | n/a |
| activity | missing | 1236, 102.14, 300x797.86 | n/a | n/a | n/a | n/a |

## Warnings

- targets: react target "content" has no matching prototype target
- targets: react target "layout" has no matching prototype target
- targets: react target "banner" has no matching prototype target
- targets: react target "activity" has no matching prototype target
- prototype: Missing selector "status": .status-bar
- prototype: Missing selector "main": .main-grid, .research-main
- prototype: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- prototype: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: Missing selector "banner": [data-slot='banner']
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
