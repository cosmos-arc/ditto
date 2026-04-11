# Visual Audit: trading

- Route: `/trading`
- React URL: http://localhost:5173/trading
- Prototype URL: http://localhost:8889/page-trading-overview.html
- Viewport: 1536x900
- Captured: 2026-04-11T15:20:15.334Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| rail | 0, 0, 56x876 | 0, 0, 56x900 | 0 | 0 | 0 | 24 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| status | 0, 876, 1536x24 | missing | n/a | n/a | n/a | n/a |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| strip | 56, 68, 1480x36 | 56, 68, 1480x34.14 | 0 | 0 | 0 | -1.86 |
| main | missing | 56, 265.95, 1180x634.05 | n/a | n/a | n/a | n/a |
| session | 72, 76.50, 57x18 | missing | n/a | n/a | n/a | n/a |
| positions | 72, 471.58, 1148x254.80 | 72, 391.22, 1148x223.66 | 0 | -80.36 | 0 | -31.14 |
| orders | 72, 742.38, 1148x181.63 | 84, 425.22, 1124x163.33 | 12 | -317.16 | -24 | -18.30 |
| content | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| layout | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| banner | missing | 56, 102.14, 1480x163.81 | n/a | n/a | n/a | n/a |
| activity | missing | 1236, 265.95, 300x634.05 | n/a | n/a | n/a | n/a |
| analysis | missing | missing | n/a | n/a | n/a | n/a |

## Warnings

- targets: prototype target "session" has no matching react target
- targets: react target "content" has no matching prototype target
- targets: react target "layout" has no matching prototype target
- targets: react target "banner" has no matching prototype target
- targets: react target "activity" has no matching prototype target
- targets: react target "analysis" has no matching prototype target
- prototype: Missing selector "main": .main-grid, .trading-main
- prototype: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- prototype: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: Missing selector "status": [data-slot='status-bar']
- react: Missing selector "analysis": [data-slot='analysis']
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
